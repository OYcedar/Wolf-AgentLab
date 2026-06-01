"""Extract safe translatable text from WolfTL dumps."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.rmmz.control_codes import CustomPlaceholderRule
from app.rmmz.schema import TranslationData, TranslationItem
from app.rmmz.text_rules import TextRules
from app.wolf.dump_loader import (
    WolfDumpFile,
    build_location_path,
    iter_wolftl_dump_files,
)

DIALOGUE_COMMANDS = {"Message", "Choices"}
VISIBLE_STRING_COMMANDS = {"SetString"}
RUNTIME_COMMANDS = {
    "SetLabel",
    "JumpLabel",
    "CommonEventByName",
    "Sound",
    "Picture",
    "Teleport",
    "Move",
    "Chip",
    "ChipSet",
    "Database",
    "ImportDatabase",
    "StringCondition",
    "SetTransition",
    "PrepareTransition",
    "ExecuteTransition",
}
RESOURCE_PREFIX_PATTERN = re.compile(
    r"^(?:BGM|SE|Picture|CharaChip|MapData|MapChip|BattleEffect|EnemyGraphic|SystemFile|Fog_BackGround|NC)[/\\]",
    re.IGNORECASE,
)
RESOURCE_SUFFIX_PATTERN = re.compile(
    r"\.(?:png|jpg|jpeg|bmp|webp|gif|ogg|wav|mp3|mps|dat|wolf)$",
    re.IGNORECASE,
)
CONTROL_TOKEN_PATTERN = re.compile(
    r"(?:\\(?:s|cself|self|v|i|f|r)\[[^\]\r\n]+\]|<[^>\r\n]*\\cself\[[^\]\r\n]+\][^>\r\n]*>)",
    re.IGNORECASE,
)
WOLF_DEFAULT_PLACEHOLDER_RULES: tuple[tuple[str, str], ...] = (
    (r"\\(?:s|cself|self|v|i|f|r)\[[^\]\r\n]+\]", "[CUSTOM_WOLF_CONTROL_{index}]"),
    (r"<[^>\r\n]*\\cself\[[^\]\r\n]+\][^>\r\n]*>", "[CUSTOM_WOLF_MARKER_{index}]"),
)
DB_FIELD_KEYWORDS = (
    "名",
    "名前",
    "名称",
    "説明",
    "文章",
    "文",
    "メッセージ",
    "表示",
    "テキスト",
    "セリフ",
    "項目",
    "コマンド",
    "技能",
    "アイテム",
    "スキル",
)


def wolf_default_placeholder_rules() -> tuple[CustomPlaceholderRule, ...]:
    """Return built-in Wolf control-code placeholder rules."""
    return tuple(
        CustomPlaceholderRule.create(pattern_text=pattern, placeholder_template=template)
        for pattern, template in WOLF_DEFAULT_PLACEHOLDER_RULES
    )


def extract_wolf_translation_data_map(
    *,
    dump_dir: Path,
    text_rules: TextRules,
) -> dict[str, TranslationData]:
    """Extract safe display text from a WolfTL dump."""
    grouped_items: dict[str, list[TranslationItem]] = defaultdict(list)
    display_names: dict[str, str | None] = {}
    for file in iter_wolftl_dump_files(dump_dir):
        display_names[file.relative_path] = _display_name_for_file(file)
        for item in _extract_file_items(file=file, text_rules=text_rules):
            grouped_items[file.relative_path].append(item)
    return {
        relative_path: TranslationData(
            display_name=display_names.get(relative_path),
            translation_items=items,
        )
        for relative_path, items in grouped_items.items()
    }


def _extract_file_items(*, file: WolfDumpFile, text_rules: TextRules) -> list[TranslationItem]:
    if file.section == "game":
        return _extract_game_items(file=file, text_rules=text_rules)
    if file.section == "common":
        return _extract_common_items(file=file, text_rules=text_rules)
    if file.section == "mps":
        return _extract_mps_items(file=file, text_rules=text_rules)
    if file.section == "db":
        return _extract_db_items(file=file, text_rules=text_rules)
    return []


def _extract_game_items(*, file: WolfDumpFile, text_rules: TextRules) -> list[TranslationItem]:
    data = file.data
    if not isinstance(data, dict):
        return []
    items: list[TranslationItem] = []
    for key in ("Title", "TitlePlus", "StartUpMsg", "TitleMsg"):
        value = data.get(key)
        if not isinstance(value, str):
            continue
        item = _build_text_item(
            file=file,
            pointer=f"/{key}",
            text=value,
            role="game",
            text_rules=text_rules,
        )
        if item is not None:
            items.append(item)
    return items


def _extract_common_items(*, file: WolfDumpFile, text_rules: TextRules) -> list[TranslationItem]:
    data = file.data
    if not isinstance(data, dict):
        return []
    commands = data.get("commands")
    if not isinstance(commands, list):
        return []
    return _extract_command_list_items(
        file=file,
        commands=commands,
        base_pointer="/commands",
        text_rules=text_rules,
    )


def _extract_mps_items(*, file: WolfDumpFile, text_rules: TextRules) -> list[TranslationItem]:
    data = file.data
    if not isinstance(data, dict):
        return []
    events = data.get("events")
    if not isinstance(events, list):
        return []
    items: list[TranslationItem] = []
    for event_index, event in enumerate(events):
        if not isinstance(event, dict):
            continue
        pages = event.get("pages")
        if not isinstance(pages, list):
            continue
        for page_index, page in enumerate(pages):
            if not isinstance(page, dict):
                continue
            commands = page.get("list")
            if not isinstance(commands, list):
                continue
            base_pointer = f"/events/{event_index}/pages/{page_index}/list"
            items.extend(
                _extract_command_list_items(
                    file=file,
                    commands=commands,
                    base_pointer=base_pointer,
                    text_rules=text_rules,
                )
            )
    return items


def _extract_command_list_items(
    *,
    file: WolfDumpFile,
    commands: list[Any],
    base_pointer: str,
    text_rules: TextRules,
) -> list[TranslationItem]:
    items: list[TranslationItem] = []
    for command_index, command in enumerate(commands):
        if not isinstance(command, dict):
            continue
        code_str = str(command.get("codeStr", ""))
        if code_str in RUNTIME_COMMANDS:
            continue
        if code_str not in DIALOGUE_COMMANDS and code_str not in VISIBLE_STRING_COMMANDS and code_str != "CommonEvent":
            continue
        string_args = command.get("stringArgs")
        if not isinstance(string_args, list):
            continue
        for arg_index, value in enumerate(string_args):
            if not isinstance(value, str):
                continue
            if code_str == "CommonEvent" and arg_index == 0:
                continue
            pointer = f"{base_pointer}/{command_index}/stringArgs/{arg_index}"
            role = _role_for_command_string(code_str=code_str, arg_index=arg_index)
            item = _build_text_item(
                file=file,
                pointer=pointer,
                text=value,
                role=role,
                text_rules=text_rules,
            )
            if item is not None:
                items.append(item)
    return items


def _role_for_command_string(*, code_str: str, arg_index: int) -> str | None:
    if code_str == "Choices":
        return "choice"
    if code_str == "SetString":
        return "variable_text"
    if code_str == "CommonEvent" and arg_index > 0:
        return "common_event_text"
    return None


def _extract_db_items(*, file: WolfDumpFile, text_rules: TextRules) -> list[TranslationItem]:
    data = file.data
    if not isinstance(data, dict):
        return []
    types = data.get("types")
    if not isinstance(types, list):
        return []
    items: list[TranslationItem] = []
    allow_schema_names = file.relative_path.endswith("/DataBase.json")
    for type_index, db_type in enumerate(types):
        if not isinstance(db_type, dict):
            continue
        if allow_schema_names:
            items.extend(
                _extract_optional_db_schema_text(
                    file=file,
                    pointer=f"/types/{type_index}/name",
                    text=db_type.get("name"),
                    text_rules=text_rules,
                )
            )
            items.extend(
                _extract_optional_db_schema_text(
                    file=file,
                    pointer=f"/types/{type_index}/description",
                    text=db_type.get("description"),
                    text_rules=text_rules,
                )
            )
            fields = db_type.get("fields")
            if isinstance(fields, list):
                for field_index, field in enumerate(fields):
                    if isinstance(field, dict):
                        items.extend(
                            _extract_optional_db_schema_text(
                                file=file,
                                pointer=f"/types/{type_index}/fields/{field_index}/name",
                                text=field.get("name"),
                                text_rules=text_rules,
                            )
                        )
        entries = db_type.get("data")
        if not isinstance(entries, list):
            continue
        for entry_index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            items.extend(
                _extract_optional_db_display_text(
                    file=file,
                    pointer=f"/types/{type_index}/data/{entry_index}/name",
                    text=entry.get("name"),
                    text_rules=text_rules,
                )
            )
            entry_fields = entry.get("data")
            if not isinstance(entry_fields, list):
                continue
            for field_index, field in enumerate(entry_fields):
                if not isinstance(field, dict):
                    continue
                value = field.get("value")
                if not isinstance(value, str):
                    continue
                field_name = str(field.get("name", ""))
                if not _is_display_database_field(field_name):
                    continue
                items.extend(
                    _extract_optional_db_display_text(
                        file=file,
                        pointer=f"/types/{type_index}/data/{entry_index}/data/{field_index}/value",
                        text=value,
                        text_rules=text_rules,
                    )
                )
    return items


def _extract_optional_db_schema_text(
    *,
    file: WolfDumpFile,
    pointer: str,
    text: object,
    text_rules: TextRules,
) -> list[TranslationItem]:
    if not isinstance(text, str):
        return []
    item = _build_text_item(
        file=file,
        pointer=pointer,
        text=text,
        role="database",
        text_rules=text_rules,
    )
    return [] if item is None else [item]


def _extract_optional_db_display_text(
    *,
    file: WolfDumpFile,
    pointer: str,
    text: object,
    text_rules: TextRules,
) -> list[TranslationItem]:
    if not isinstance(text, str):
        return []
    item = _build_text_item(
        file=file,
        pointer=pointer,
        text=text,
        role="database",
        text_rules=text_rules,
    )
    return [] if item is None else [item]


def _build_text_item(
    *,
    file: WolfDumpFile,
    pointer: str,
    text: str,
    role: str | None,
    text_rules: TextRules,
) -> TranslationItem | None:
    if not should_translate_wolf_text(text=text, text_rules=text_rules):
        return None
    location_path = build_location_path(file.section, file.relative_path, pointer)
    return TranslationItem(
        role=role,
        location_path=location_path,
        item_type="short_text",
        original_lines=[text],
        source_line_paths=[location_path],
    )


def should_translate_wolf_text(*, text: str, text_rules: TextRules) -> bool:
    """Return whether a raw Wolf string should enter normal translation."""
    stripped = text.strip()
    if not stripped:
        return False
    if RESOURCE_PREFIX_PATTERN.search(stripped) or RESOURCE_SUFFIX_PATTERN.search(stripped):
        return False
    if CONTROL_TOKEN_PATTERN.fullmatch(stripped):
        return False
    if stripped.startswith("<") and stripped.endswith(">") and len(stripped) <= 80:
        return False
    if not text_rules.should_translate_source_text(stripped):
        return False
    return True


def _is_display_database_field(field_name: str) -> bool:
    normalized = field_name.strip()
    return any(keyword in normalized for keyword in DB_FIELD_KEYWORDS)


def _display_name_for_file(file: WolfDumpFile) -> str | None:
    data = file.data
    if isinstance(data, dict):
        name = data.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return file.relative_path


__all__ = [
    "RUNTIME_COMMANDS",
    "VISIBLE_STRING_COMMANDS",
    "WOLF_DEFAULT_PLACEHOLDER_RULES",
    "extract_wolf_translation_data_map",
    "should_translate_wolf_text",
    "wolf_default_placeholder_rules",
]
