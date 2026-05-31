"""High-level Wolf command services."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.agent_toolkit import AgentReport
from app.agent_toolkit.reports import AgentIssue, issue
from app.config.schemas import Setting
from app.persistence import GameRegistry
from app.rmmz.control_codes import CustomPlaceholderRule, REAL_LINE_BREAK_MARKER, REAL_LINE_BREAK_PLACEHOLDER
from app.rmmz.json_types import JsonObject
from app.rmmz.schema import TranslationItem
from app.rmmz.text_rules import TextRules
from app.translation.verify import _mask_known_translation_controls
from app.utils.config_loader_utils import load_setting
from app.wolf.dec import (
    PrepareGameResult,
    prepare_wolf_game,
    require_prepared_wolf_game,
)
from app.wolf.dump_loader import iter_wolftl_dump_files
from app.wolf.extraction import (
    WOLF_DEFAULT_PLACEHOLDER_RULES,
    extract_wolf_translation_data_map,
    wolf_default_placeholder_rules,
)
from app.wolf.layout import is_wolf_engine_version_unsupported, iter_wolf_archives
from app.wolf.paths import resolve_wolf_patches_root
from app.wolf.runtime_audit import (
    audit_translated_dump_runtime_strings,
    audit_wolf_runtime_translations,
    restore_runtime_strings,
    write_runtime_audit_report,
)
from app.wolf.tools import resolve_wolf_tool_paths
from app.wolf.wolftl import run_wolftl_create
from app.wolf.write_back import TRANSLATED_OUTPUT_DIR_NAME


class WolfService:
    """Service boundary for Wolf-specific CLI commands."""

    def __init__(self, *, game_registry: GameRegistry | None = None, setting_path: str | Path | None = None) -> None:
        self.game_registry = game_registry if game_registry is not None else GameRegistry()
        self.setting_path = setting_path

    async def prepare_game(self, *, game_title: str) -> AgentReport:
        """Prepare and WolfTL-validate one registered Wolf game."""
        async with await self.game_registry.open_game(game_title) as session:
            self._require_wolf(session.engine_kind)
            setting = load_setting(self.setting_path, source_language=session.source_language)
            result = prepare_wolf_game(
                game_title=session.game_title,
                game_path=session.game_path,
                tools=resolve_wolf_tool_paths(setting),
            )
            game_warnings = _collect_wolf_game_warnings(
                game_path=session.game_path,
                engine_version=session.engine_version,
            )
        return _report_from_prepare_result(result, extra_warnings=game_warnings)

    async def dump_text(self, *, game_title: str) -> AgentReport:
        """Run WolfTL create for an already prepared game."""
        async with await self.game_registry.open_game(game_title) as session:
            self._require_wolf(session.engine_kind)
            setting = load_setting(self.setting_path, source_language=session.source_language)
            tools = resolve_wolf_tool_paths(setting)
            if tools.wolftl is None:
                return AgentReport.from_parts(
                    errors=[issue("wolftl_missing", "WolfTL.exe not found")],
                    warnings=[],
                    summary={},
                    details={},
                )
            prepared = require_prepared_wolf_game(session.game_title)
            result = run_wolftl_create(
                wolftl_path=tools.wolftl,
                data_dir=prepared.data_dir or Path(),
                output_dir=prepared.wolftl_output_dir or Path(),
            )
        errors = [] if result.ok else [issue("wolftl_create", result.stderr.strip() or result.stdout.strip())]
        return AgentReport.from_parts(
            errors=errors,
            warnings=[],
            summary={
                "dump_ready": result.ok,
                "returncode": result.returncode,
                "dump_dir": str((prepared.wolftl_output_dir or Path()) / "dump"),
            },
            details={
                "command": result.command,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
        )

    async def prepare_agent_workspace(self, *, game_title: str, output_dir: Path) -> AgentReport:
        """Export Wolf text scope and SExtractor handoff files."""
        async with await self.game_registry.open_game(game_title) as session:
            self._require_wolf(session.engine_kind)
            setting = load_setting(self.setting_path, source_language=session.source_language)
            text_rules = await self._wolf_text_rules(session=session, setting=setting)
            prepared = require_prepared_wolf_game(session.game_title)
            if prepared.dump_dir is None:
                raise RuntimeError("Prepared Wolf workspace has no dump directory")
            data_map = extract_wolf_translation_data_map(
                dump_dir=prepared.dump_dir,
                text_rules=text_rules,
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        items = [
            item
            for data in data_map.values()
            for item in data.translation_items
        ]
        text_scope_path = output_dir / "wolf_text_scope.json"
        sextractor_path = output_dir / "wolf_sextractor.json"
        text_map_path = output_dir / "wolf_text_map.json"
        runtime_rules_path = output_dir / "wolf_runtime_rules_draft.json"
        text_scope_path.write_text(
            json.dumps([item.model_dump(mode="json") for item in items], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8-sig",
        )
        sextractor_path.write_text(
            json.dumps(
                [
                    {
                        **({"name": item.role} if item.role else {}),
                        "message": "\n".join(item.original_lines),
                    }
                    for item in items
                ],
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8-sig",
        )
        text_map_path.write_text(
            json.dumps(
                [
                    {
                        "id": item.location_path,
                        "file": item.location_path.split("#", 1)[0],
                        "kind": item.role or "text",
                        "message": "\n".join(item.original_lines),
                    }
                    for item in items
                ],
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        runtime_rules_path.write_text(
            json.dumps(
                {
                    "placeholder_rules": [
                        {"pattern": pattern, "placeholder": template}
                        for pattern, template in WOLF_DEFAULT_PLACEHOLDER_RULES
                    ],
                    "runtime_policy": [
                        "Do not translate SetLabel or JumpLabel.",
                        "Do not translate CommonEventByName common event names.",
                        "Do not translate resource paths or runtime parameter keywords.",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return AgentReport.from_parts(
            errors=[],
            warnings=[],
            summary={
                "item_count": len(items),
                "output_dir": str(output_dir),
            },
            details={
                "text_scope": str(text_scope_path),
                "sextractor": str(sextractor_path),
                "text_map": str(text_map_path),
                "runtime_rules": str(runtime_rules_path),
            },
        )

    async def quality_report(self, *, game_title: str) -> AgentReport:
        """Build a Wolf text quality report."""
        async with await self.game_registry.open_game(game_title) as session:
            self._require_wolf(session.engine_kind)
            setting = load_setting(self.setting_path, source_language=session.source_language)
            text_rules = await self._wolf_text_rules(session=session, setting=setting)
            prepared = require_prepared_wolf_game(session.game_title)
            if prepared.dump_dir is None:
                raise RuntimeError("Prepared Wolf workspace has no dump directory")
            data_map = extract_wolf_translation_data_map(
                dump_dir=prepared.dump_dir,
                text_rules=text_rules,
            )
            expected_paths = {
                item.location_path
                for data in data_map.values()
                for item in data.translation_items
            }
            translated_items = await session.read_translated_items()
            game_path = session.game_path
            engine_version = session.engine_version
        translated_paths = {item.location_path for item in translated_items}
        missing_paths = sorted(expected_paths - translated_paths)
        stale_paths = sorted(translated_paths - expected_paths)
        runtime_issues = audit_wolf_runtime_translations(
            dump_dir=prepared.dump_dir,
            translated_items=translated_items,
        )
        placeholder_errors = _collect_placeholder_errors(
            translated_items=translated_items,
            text_rules=text_rules,
        )
        errors: list[AgentIssue] = []
        warnings: list[AgentIssue] = _collect_wolf_game_warnings(
            game_path=game_path,
            engine_version=engine_version,
        )
        if runtime_issues:
            errors.append(issue("runtime_sensitive_translation", f"{len(runtime_issues)} runtime-sensitive strings changed"))
        if placeholder_errors:
            errors.append(issue("placeholder_mismatch", f"{len(placeholder_errors)} translations broke control placeholders"))
        if missing_paths:
            errors.append(issue("missing_translations", f"{len(missing_paths)} Wolf text items are untranslated"))
        if stale_paths:
            warnings.append(issue("stale_translations", f"{len(stale_paths)} stored translations are no longer in current Wolf scope"))
        return AgentReport.from_parts(
            errors=errors,
            warnings=warnings,
            summary={
                "total_extracted_items": len(expected_paths),
                "translated_count": len(translated_paths & expected_paths),
                "missing_count": len(missing_paths),
                "stale_count": len(stale_paths),
                "runtime_issue_count": len(runtime_issues),
                "placeholder_error_count": len(placeholder_errors),
            },
            details={
                "missing_paths": missing_paths[:200],
                "stale_paths": stale_paths[:200],
                "runtime_issues": [asdict(issue_item) for issue_item in runtime_issues[:200]],
                "placeholder_errors": placeholder_errors[:200],
            },
        )

    async def translation_status(self, *, game_title: str) -> AgentReport:
        """Report latest Wolf translation run state and current pending count."""
        async with await self.game_registry.open_game(game_title) as session:
            self._require_wolf(session.engine_kind)
            latest_run = await session.read_latest_translation_run()
            if latest_run is None:
                return AgentReport.from_parts(
                    errors=[],
                    warnings=[issue("translation_run_missing", "No Wolf translation run has been recorded yet")],
                    summary={},
                    details={},
                )
            setting = load_setting(self.setting_path, source_language=session.source_language)
            text_rules = await self._wolf_text_rules(session=session, setting=setting)
            prepared = require_prepared_wolf_game(session.game_title)
            if prepared.dump_dir is None:
                raise RuntimeError("Prepared Wolf workspace has no dump directory")
            data_map = extract_wolf_translation_data_map(
                dump_dir=prepared.dump_dir,
                text_rules=text_rules,
            )
            active_paths = {
                item.location_path
                for data in data_map.values()
                for item in data.translation_items
            }
            translated_paths = await session.read_translation_location_paths()
            llm_failures = await session.read_llm_failures(latest_run.run_id)
            quality_errors = await session.read_translation_quality_errors(latest_run.run_id)
        pending_paths = active_paths - translated_paths
        current_quality_errors = [
            error for error in quality_errors if error.location_path in pending_paths
        ]
        return AgentReport.from_parts(
            errors=[],
            warnings=[],
            summary={
                "run_id": latest_run.run_id,
                "status": latest_run.status,
                "total_extracted": latest_run.total_extracted,
                "pending_count": len(pending_paths),
                "run_pending_count": latest_run.pending_count,
                "translated_count": len(translated_paths & active_paths),
                "extractable_count": len(active_paths),
                "deduplicated_count": latest_run.deduplicated_count,
                "batch_count": latest_run.batch_count,
                "success_count": latest_run.success_count,
                "quality_error_count": len(current_quality_errors),
                "run_quality_error_count": len(quality_errors),
                "llm_failure_count": len(llm_failures),
                "stop_reason": latest_run.stop_reason,
                "last_error": latest_run.last_error,
            },
            details={},
        )

    async def audit_runtime(self, *, game_title: str) -> AgentReport:
        """Audit stored translations and edited dumps for Wolf runtime risks."""
        async with await self.game_registry.open_game(game_title) as session:
            self._require_wolf(session.engine_kind)
            prepared = require_prepared_wolf_game(session.game_title)
            if prepared.dump_dir is None:
                raise RuntimeError("Prepared Wolf workspace has no dump directory")
            translated_items = await session.read_translated_items()
        issues = audit_wolf_runtime_translations(
            dump_dir=prepared.dump_dir,
            translated_items=translated_items,
        )
        translated_dump_dir = prepared.workspace_dir / TRANSLATED_OUTPUT_DIR_NAME / "dump"
        if translated_dump_dir.is_dir():
            issues.extend(
                audit_translated_dump_runtime_strings(
                    source_dump_dir=prepared.dump_dir,
                    translated_dump_dir=translated_dump_dir,
                )
            )
        report_path = prepared.workspace_dir / "runtime_audit_report.json"
        write_runtime_audit_report(report_path, issues)
        return AgentReport.from_parts(
            errors=[issue("runtime_sensitive_translation", f"{len(issues)} runtime-sensitive strings changed")] if issues else [],
            warnings=[],
            summary={
                "runtime_issue_count": len(issues),
                "report_path": str(report_path),
            },
            details={"issues": [asdict(item) for item in issues[:200]]},
        )

    async def restore_runtime(self, *, game_title: str) -> AgentReport:
        """Restore runtime-sensitive strings in the translated dump."""
        async with await self.game_registry.open_game(game_title) as session:
            self._require_wolf(session.engine_kind)
            prepared = require_prepared_wolf_game(session.game_title)
            if prepared.dump_dir is None:
                raise RuntimeError("Prepared Wolf workspace has no dump directory")
        translated_dump_dir = prepared.workspace_dir / TRANSLATED_OUTPUT_DIR_NAME / "dump"
        restored_count = restore_runtime_strings(
            source_dump_dir=prepared.dump_dir,
            translated_dump_dir=translated_dump_dir,
        )
        return AgentReport.from_parts(
            errors=[],
            warnings=[],
            summary={
                "restored_runtime_string_count": restored_count,
                "translated_dump_dir": str(translated_dump_dir),
            },
            details={},
        )

    async def make_patch(self, *, game_title: str) -> AgentReport:
        """Copy the latest WolfTL patched Data into G:\\wolf\\patches."""
        async with await self.game_registry.open_game(game_title) as session:
            self._require_wolf(session.engine_kind)
            game_dir = session.game_path
            prepared = require_prepared_wolf_game(session.game_title)
        patched_root = prepared.workspace_dir / TRANSLATED_OUTPUT_DIR_NAME / "patched"
        active_data_dir = game_dir / "Data"
        patched_data_dir = active_data_dir if active_data_dir.is_dir() else patched_root / "Data"
        if not patched_data_dir.is_dir() and (patched_root / "data").is_dir():
            patched_data_dir = patched_root / "data"
        if not patched_data_dir.is_dir():
            return AgentReport.from_parts(
                errors=[issue("patched_data_missing", "No patched Data found. Run write-back first.")],
                warnings=[],
                summary={},
                details={"expected_path": str(patched_data_dir)},
            )
        patch_dir = resolve_wolf_patches_root() / prepared.workspace_dir.name
        if patch_dir.exists():
            shutil.rmtree(patch_dir)
        shutil.copytree(patched_data_dir, patch_dir / "Data")
        runtime_files: list[str] = []
        for name in _WOLF_PRO_RUNTIME_FILES:
            source = game_dir / name
            if source.is_file():
                shutil.copy2(source, patch_dir / name)
                runtime_files.append(name)
        if (patch_dir / "GamePro.exe").is_file():
            (patch_dir / "启动汉化版.bat").write_text(
                '@echo off\r\ncd /d "%~dp0"\r\nstart "" GamePro.exe\r\n',
                encoding="mbcs",
            )
        return AgentReport.from_parts(
            errors=[],
            warnings=[],
            summary={
                "patch_dir": str(patch_dir),
                "runtime_files": runtime_files,
            },
            details={},
        )

    async def verify_feedback_text(self, *, game_title: str, input_path: Path) -> AgentReport:
        """Search feedback text snippets in Wolf dumps and saved translations."""
        snippets = _load_feedback_snippets(input_path)
        async with await self.game_registry.open_game(game_title) as session:
            self._require_wolf(session.engine_kind)
            prepared = require_prepared_wolf_game(session.game_title)
            if prepared.dump_dir is None:
                raise RuntimeError("Prepared Wolf workspace has no dump directory")
            translated_items = await session.read_translated_items()
        dump_hits = _search_dump_snippets(prepared.dump_dir, snippets)
        translation_hits = _search_translation_snippets(translated_items, snippets)
        missing = [
            snippet
            for snippet in snippets
            if snippet not in dump_hits and snippet not in translation_hits
        ]
        return AgentReport.from_parts(
            errors=[],
            warnings=[issue("feedback_text_not_found", f"{len(missing)} snippets were not found")] if missing else [],
            summary={
                "snippet_count": len(snippets),
                "missing_count": len(missing),
            },
            details={
                "dump_hits": dump_hits,
                "translation_hits": translation_hits,
                "missing": missing,
            },
        )

    async def _wolf_text_rules(self, *, session: Any, setting: Setting) -> TextRules:
        records = await session.read_placeholder_rules()
        custom_rules = tuple(
            CustomPlaceholderRule.create(
                pattern_text=record.pattern_text,
                placeholder_template=record.placeholder_template,
            )
            for record in records
        )
        return TextRules.from_setting(
            setting.text_rules,
            custom_placeholder_rules=(*wolf_default_placeholder_rules(), *custom_rules),
            structured_placeholder_rules=(),
        )

    def _require_wolf(self, engine_kind: str) -> None:
        if engine_kind != "wolf":
            raise RuntimeError(f"Command is only valid for Wolf games, got: {engine_kind}")


def _report_from_prepare_result(result: PrepareGameResult, *, extra_warnings: list[AgentIssue] | None = None) -> AgentReport:
    errors = [] if result.ok else [issue("prepare_game_failed", result.message)]
    warnings: list[AgentIssue] = list(extra_warnings or [])
    if result.ok and any(attempt.method == "wolfdec" and attempt.ok for attempt in result.attempts):
        warnings.append(issue("wolfdec_fallback", "UberWolf was unavailable or not parseable; WolfDec output was used."))
    return AgentReport.from_parts(
        errors=errors,
        warnings=warnings,
        summary={
            "prepared": result.ok,
            "game_title": result.game_title,
            "workspace_dir": str(result.workspace_dir),
            "data_dir": str(result.data_dir) if result.data_dir is not None else "",
            "dump_dir": str(result.dump_dir) if result.dump_dir is not None else "",
        },
        details={
            "message": result.message,
            "attempts": [
                {
                    "method": attempt.method,
                    "ok": attempt.ok,
                    "data_dir": attempt.data_dir,
                    "wolftl_output_dir": attempt.wolftl_output_dir,
                    "message": attempt.message,
                    "command": attempt.command,
                    "returncode": attempt.returncode,
                    "stdout": attempt.stdout,
                    "stderr": attempt.stderr,
                }
                for attempt in result.attempts
            ],
        },
    )


def _collect_wolf_game_warnings(*, game_path: Path, engine_version: str) -> list[AgentIssue]:
    warnings: list[AgentIssue] = []
    if is_wolf_engine_version_unsupported(engine_version):
        warnings.append(
            issue(
                "wolf_engine_version_risky",
                f"Wolf engine version {engine_version} is at or above the known risky threshold 3.595",
            )
        )
    archive_paths = iter_wolf_archives(game_path)
    if archive_paths:
        warnings.append(
            issue(
                "wolf_archives_present",
                f"{len(archive_paths)} .wolf archives remain under the game directory; move them out before write-back so the game loads patched Data",
            )
        )
    return warnings


def _collect_placeholder_errors(
    *,
    translated_items: list[TranslationItem],
    text_rules: TextRules,
) -> list[JsonObject]:
    errors: list[JsonObject] = []
    for item in translated_items:
        check_item = item.model_copy(deep=True)
        try:
            check_item.build_placeholders(text_rules)
            check_item.translation_lines_with_placeholders = _mask_known_translation_controls(
                item=check_item,
                translation_lines=check_item.translation_lines,
                text_rules=text_rules,
            )
            check_item.translation_lines_with_placeholders = [
                line.replace(REAL_LINE_BREAK_MARKER, REAL_LINE_BREAK_PLACEHOLDER)
                for line in check_item.translation_lines_with_placeholders
            ]
            check_item.verify_placeholders(text_rules)
        except Exception as error:
            errors.append(
                {
                    "location_path": item.location_path,
                    "message": f"{type(error).__name__}: {error}",
                }
            )
    return errors


_WOLF_PRO_RUNTIME_FILES = (
    "GamePro.exe",
    "EditorPro.exe",
    "LGBaseFont.ttf",
    "fontsoul.ttf",
    "Onryou.ttf",
    "AkazukinPop.ttf",
)


def _load_feedback_snippets(input_path: Path) -> list[str]:
    raw = json.loads(input_path.read_text(encoding="utf-8-sig"))
    if isinstance(raw, list):
        snippets: list[str] = []
        for item in raw:
            if isinstance(item, str):
                snippets.append(item)
            elif isinstance(item, dict):
                for key in ("text", "source", "message", "original"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        snippets.append(value)
                        break
        return snippets
    if isinstance(raw, dict):
        value = raw.get("texts") or raw.get("snippets")
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
    raise ValueError(f"Unsupported feedback text file: {input_path}")


def _search_dump_snippets(dump_dir: Path, snippets: list[str]) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {snippet: [] for snippet in snippets}
    for file in iter_wolftl_dump_files(dump_dir):
        raw = json.dumps(file.data, ensure_ascii=False)
        for snippet in snippets:
            if snippet in raw:
                hits[snippet].append(file.relative_path)
    return {snippet: paths for snippet, paths in hits.items() if paths}


def _search_translation_snippets(items: list[TranslationItem], snippets: list[str]) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {snippet: [] for snippet in snippets}
    for item in items:
        raw = "\n".join([*item.original_lines, *item.translation_lines])
        for snippet in snippets:
            if snippet in raw:
                hits[snippet].append(item.location_path)
    return {snippet: paths for snippet, paths in hits.items() if paths}


__all__ = ["WolfService"]
