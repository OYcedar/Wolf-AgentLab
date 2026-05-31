from __future__ import annotations

import json
from pathlib import Path

from pytest import MonkeyPatch

import app.wolf.dec as wolf_dec
import app.wolf.write_back as wolf_write_back
from app.config.schemas import TextRulesSetting
from app.rmmz.schema import TranslationItem
from app.rmmz.text_rules import TextRules
from app.wolf.dump_loader import build_location_path
from app.wolf.extraction import extract_wolf_translation_data_map, wolf_default_placeholder_rules
from app.wolf.layout import is_wolf_engine_version_unsupported, iter_wolf_archives, parse_wolf_engine_version
from app.wolf.runtime_audit import audit_wolf_runtime_translations, collect_runtime_sensitive_string_paths
from app.wolf.tools import WolfToolPaths
from app.wolf.wolftl import WolfTLRunResult
from app.wolf.write_back import write_wolf_translations


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _text_rules() -> TextRules:
    return TextRules.from_setting(
        TextRulesSetting(),
        custom_placeholder_rules=wolf_default_placeholder_rules(),
        structured_placeholder_rules=(),
    )


def test_wolf_best_practice_helpers_detect_version_and_archives(tmp_path: Path) -> None:
    game_dir = tmp_path / "game"
    nested = game_dir / "Data"
    nested.mkdir(parents=True)
    (game_dir / "Data.wolf").write_text("packed", encoding="utf-8")
    (nested / "MapData.wolf").write_text("packed", encoding="utf-8")

    assert parse_wolf_engine_version("3.595.0.0") == (3, 595, 0, 0)
    assert is_wolf_engine_version_unsupported("3.595.0.0") is True
    assert is_wolf_engine_version_unsupported("3.594") is False
    assert sorted(path.name for path in iter_wolf_archives(game_dir)) == ["Data.wolf", "MapData.wolf"]


def _sample_dump(dump_dir: Path) -> None:
    _write_json(dump_dir / "Game.json", {"title": "demo"})
    _write_json(
        dump_dir / "common" / "001.json",
        {
            "id": 1,
            "name": "共通イベント",
            "commands": [
                {"code": 101, "codeStr": "Message", "stringArgs": ["こんにちは\\s[9]君"], "intArgs": [1], "index": 0},
                {"code": 102, "codeStr": "Choices", "stringArgs": ["戦う", "逃げる"], "intArgs": [2], "index": 1},
                {"code": 201, "codeStr": "SetLabel", "stringArgs": ["終了"], "intArgs": [3], "index": 2},
                {"code": 202, "codeStr": "JumpLabel", "stringArgs": ["終了"], "intArgs": [4], "index": 3},
                {"code": 203, "codeStr": "CommonEventByName", "stringArgs": ["神社打工小游戏"], "intArgs": [5], "index": 4},
                {"code": 204, "codeStr": "Picture", "stringArgs": ["Picture/hero.png", "ピクチャ番号"], "intArgs": [6], "index": 5},
            ],
        },
    )
    _write_json(
        dump_dir / "mps" / "Map001.json",
        {
            "events": [
                {
                    "id": 1,
                    "name": "ゲームセンターの女",
                    "pages": [
                        {
                            "list": [
                                {"code": 301, "codeStr": "Message", "stringArgs": ["勝負する？"], "intArgs": [7], "index": 0},
                                {"code": 302, "codeStr": "Sound", "stringArgs": ["SE/start.ogg"], "intArgs": [8], "index": 1},
                            ]
                        }
                    ],
                }
            ]
        },
    )
    _write_json(
        dump_dir / "db" / "DataBase.json",
        {
            "types": [
                {
                    "name": "アイテム",
                    "description": "道具一覧",
                    "fields": [{"name": "説明"}, {"name": "内部ID"}],
                    "data": [
                        {
                            "name": "カフェイン値",
                            "data": [
                                {"name": "説明", "value": "眠気を下げる"},
                                {"name": "画像", "value": "Picture/item.png"},
                            ],
                        }
                    ],
                }
            ]
        },
    )


def test_wolftl_dump_extraction_keeps_runtime_strings_out_of_translation_scope(tmp_path: Path) -> None:
    dump_dir = tmp_path / "dump"
    _sample_dump(dump_dir)

    data_map = extract_wolf_translation_data_map(dump_dir=dump_dir, text_rules=_text_rules())
    items = [item for data in data_map.values() for item in data.translation_items]
    originals = ["\n".join(item.original_lines) for item in items]

    assert "こんにちは\\s[9]君" in originals
    assert "戦う" in originals
    assert "勝負する？" in originals
    assert "アイテム" in originals
    assert "カフェイン値" in originals
    assert "眠気を下げる" in originals
    assert "終了" not in originals
    assert "神社打工小游戏" not in originals
    assert "Picture/hero.png" not in originals
    assert all("intArgs" not in item.location_path for item in items)


def test_wolf_runtime_audit_flags_labels_resources_events_and_parameter_keywords(tmp_path: Path) -> None:
    dump_dir = tmp_path / "dump"
    _sample_dump(dump_dir)

    risky_paths = collect_runtime_sensitive_string_paths(dump_dir)
    assert any(reason == "label" for reason in risky_paths.values())
    assert any(reason.startswith("runtime-command:Picture") for reason in risky_paths.values())
    assert any(reason == "event-name-or-resource" for reason in risky_paths.values())

    label_path = build_location_path("common", "common/001.json", "/commands/2/stringArgs/0")
    issues = audit_wolf_runtime_translations(
        dump_dir=dump_dir,
        translated_items=[
            TranslationItem(
                location_path=label_path,
                item_type="short_text",
                original_lines=["終了"],
                source_line_paths=[label_path],
                translation_lines=["结束"],
            )
        ],
    )

    assert len(issues) == 1
    assert issues[0].reason == "label"


def test_write_back_changes_only_safe_translation_strings(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    dump_dir = tmp_path / "dump"
    _sample_dump(dump_dir)
    data_dir = tmp_path / "Data"
    data_dir.mkdir()
    workspace_dir = tmp_path / "workspace"
    message_path = build_location_path("common", "common/001.json", "/commands/0/stringArgs/0")
    label_path = build_location_path("common", "common/001.json", "/commands/2/stringArgs/0")
    db_field_path = build_location_path("db", "db/DataBase.json", "/types/0/fields/0/name")
    db_value_path = build_location_path("db", "db/DataBase.json", "/types/0/data/0/name")

    def fake_patch(*, wolftl_path: Path, data_dir: Path, output_dir: Path) -> WolfTLRunResult:
        patched_data = output_dir / "patched" / "data"
        patched_data.mkdir(parents=True, exist_ok=True)
        return WolfTLRunResult(ok=True, command=[str(wolftl_path)], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(wolf_write_back, "run_wolftl_patch", fake_patch)
    result = write_wolf_translations(
        source_dump_dir=dump_dir,
        data_dir=data_dir,
        workspace_dir=workspace_dir,
        wolftl_path=tmp_path / "WolfTL.exe",
        translated_items=[
            TranslationItem(
                location_path=message_path,
                item_type="short_text",
                original_lines=["こんにちは\\s[9]君"],
                source_line_paths=[message_path],
                translation_lines=["你好\\s[9]君"],
            ),
            TranslationItem(
                location_path=label_path,
                item_type="short_text",
                original_lines=["終了"],
                source_line_paths=[label_path],
                translation_lines=["结束"],
            ),
            TranslationItem(
                location_path=db_field_path,
                item_type="short_text",
                original_lines=["説明"],
                source_line_paths=[db_field_path],
                translation_lines=["说明"],
            ),
            TranslationItem(
                location_path=db_value_path,
                item_type="short_text",
                original_lines=["カフェイン値"],
                source_line_paths=[db_value_path],
                translation_lines=["咖啡因值"],
            ),
        ],
    )

    written = json.loads((workspace_dir / "translated_wolftl" / "dump" / "common" / "001.json").read_text(encoding="utf-8"))
    written_db = json.loads((workspace_dir / "translated_wolftl" / "dump" / "db" / "DataBase.json").read_text(encoding="utf-8"))
    assert written["commands"][0]["stringArgs"][0] == "你好\\s[9]君"
    assert written["commands"][0]["intArgs"] == [1]
    assert written["commands"][2]["stringArgs"][0] == "終了"
    assert written["commands"][2]["intArgs"] == [3]
    assert written_db["types"][0]["fields"][0]["name"] == "説明"
    assert written_db["types"][0]["data"][0]["name"] == "咖啡因值"
    assert result.written_item_count == 2
    assert result.restored_runtime_string_count == 0


def test_prepare_game_falls_back_from_uberwolf_to_wolfdec_when_wolftl_parse_fails(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    (game_dir / "Game.exe").write_text("", encoding="utf-8")
    (game_dir / "Data.wolf").write_text("packed", encoding="utf-8")
    workspace_dir = tmp_path / "workspace"
    tools = WolfToolPaths(
        wolftl=tmp_path / "WolfTL.exe",
        uberwolf=tmp_path / "UberWolf.exe",
        wolfdec=tmp_path / "WolfDec.exe",
    )

    monkeypatch.setattr(wolf_dec, "resolve_game_workspace", lambda _game_title: workspace_dir)

    def fake_uberwolf(*, uberwolf_path: Path, game_path: Path, output_dir: Path) -> wolf_dec.ProcessResult:
        data_dir = output_dir / "Data"
        (data_dir / "BasicData").mkdir(parents=True)
        return wolf_dec.ProcessResult(command=[str(uberwolf_path)], returncode=0, stdout="", stderr="")

    def fake_wolfdec(*, wolfdec_path: Path, wolf_archives: list[Path], output_dir: Path) -> wolf_dec.ProcessResult:
        data_dir = output_dir / "Data"
        (data_dir / "BasicData").mkdir(parents=True)
        return wolf_dec.ProcessResult(command=[str(wolfdec_path)], returncode=0, stdout="", stderr="")

    def fake_wolftl_create(*, wolftl_path: Path, data_dir: Path, output_dir: Path) -> WolfTLRunResult:
        if "uberwolf" in str(data_dir):
            return WolfTLRunResult(ok=False, command=[str(wolftl_path)], returncode=1, stdout="", stderr="parse failed")
        _sample_dump(output_dir / "dump")
        return WolfTLRunResult(ok=True, command=[str(wolftl_path)], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(wolf_dec, "_run_uberwolf", fake_uberwolf)
    monkeypatch.setattr(wolf_dec, "_run_wolfdec", fake_wolfdec)
    monkeypatch.setattr(wolf_dec, "run_wolftl_create", fake_wolftl_create)

    result = wolf_dec.prepare_wolf_game(game_title="demo", game_path=game_dir, tools=tools)

    assert result.ok is True
    assert [attempt.method for attempt in result.attempts] == ["uberwolf", "wolfdec"]
    assert result.attempts[0].ok is False
    assert result.attempts[1].ok is True
    assert result.dump_dir is not None
    assert (result.dump_dir / "Game.json").is_file()
