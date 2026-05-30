"""Runtime-risk audit and restore helpers for WolfTL dumps."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.rmmz.schema import TranslationItem
from app.wolf.dump_loader import (
    build_location_path,
    get_pointer_value,
    iter_wolftl_dump_files,
    load_dump_file_by_relative_path,
    parse_location_path,
    set_pointer_value,
    write_dump_file,
)
from app.wolf.extraction import RESOURCE_PREFIX_PATTERN, RESOURCE_SUFFIX_PATTERN, RUNTIME_COMMANDS

RUNTIME_PARAMETER_KEYWORDS = {
    "ピクチャ番号",
    "フェード時間",
    "不透明度",
    "BGM",
    "場所移動",
}


@dataclass(frozen=True, slots=True)
class RuntimeAuditIssue:
    """One runtime-sensitive changed string."""

    location_path: str
    reason: str
    original_text: str
    translated_text: str


def audit_wolf_runtime_translations(
    *,
    dump_dir: Path,
    translated_items: list[TranslationItem],
) -> list[RuntimeAuditIssue]:
    """Check stored translations for paths that should not be translated."""
    risky_paths = collect_runtime_sensitive_string_paths(dump_dir)
    issues: list[RuntimeAuditIssue] = []
    for item in translated_items:
        risk_reason = risky_paths.get(item.location_path)
        if risk_reason is None:
            continue
        translated_text = "\n".join(item.translation_lines)
        original_text = "\n".join(item.original_lines)
        if translated_text != original_text:
            issues.append(
                RuntimeAuditIssue(
                    location_path=item.location_path,
                    reason=risk_reason,
                    original_text=original_text,
                    translated_text=translated_text,
                )
            )
    return issues


def audit_translated_dump_runtime_strings(*, source_dump_dir: Path, translated_dump_dir: Path) -> list[RuntimeAuditIssue]:
    """Compare risky strings in an edited dump against the source dump."""
    risky_paths = collect_runtime_sensitive_string_paths(source_dump_dir)
    issues: list[RuntimeAuditIssue] = []
    cache: dict[str, tuple[Any, Any]] = {}
    for location_path, reason in risky_paths.items():
        _section, relative_path, pointer = parse_location_path(location_path)
        if relative_path not in cache:
            source_file = load_dump_file_by_relative_path(source_dump_dir, relative_path)
            translated_file = load_dump_file_by_relative_path(translated_dump_dir, relative_path)
            cache[relative_path] = (source_file.data, translated_file.data)
        source_data, translated_data = cache[relative_path]
        original_text = get_pointer_value(source_data, pointer)
        translated_text = get_pointer_value(translated_data, pointer)
        if isinstance(original_text, str) and isinstance(translated_text, str) and original_text != translated_text:
            issues.append(
                RuntimeAuditIssue(
                    location_path=location_path,
                    reason=reason,
                    original_text=original_text,
                    translated_text=translated_text,
                )
            )
    return issues


def restore_runtime_strings(*, source_dump_dir: Path, translated_dump_dir: Path) -> int:
    """Restore runtime-sensitive strings in an edited dump from the source dump."""
    if not translated_dump_dir.exists():
        shutil.copytree(source_dump_dir, translated_dump_dir)
        return 0
    risky_paths = collect_runtime_sensitive_string_paths(source_dump_dir)
    changed_files: dict[str, Any] = {}
    restored_count = 0
    for location_path in risky_paths:
        _section, relative_path, pointer = parse_location_path(location_path)
        source_file = load_dump_file_by_relative_path(source_dump_dir, relative_path)
        translated_file = load_dump_file_by_relative_path(translated_dump_dir, relative_path)
        source_value = get_pointer_value(source_file.data, pointer)
        translated_value = get_pointer_value(translated_file.data, pointer)
        if source_value != translated_value:
            set_pointer_value(translated_file.data, pointer, source_value)
            changed_files[relative_path] = translated_file
            restored_count += 1
    for file in changed_files.values():
        write_dump_file(file)
    return restored_count


def collect_runtime_sensitive_string_paths(dump_dir: Path) -> dict[str, str]:
    """Collect strings that should remain byte-for-byte from the source dump."""
    paths: dict[str, str] = {}
    for file in iter_wolftl_dump_files(dump_dir):
        data = file.data
        if file.section == "common" and isinstance(data, dict):
            commands = data.get("commands")
            if isinstance(commands, list):
                _collect_command_runtime_paths(
                    paths=paths,
                    section=file.section,
                    relative_path=file.relative_path,
                    commands=commands,
                    base_pointer="/commands",
                )
        elif file.section == "mps" and isinstance(data, dict):
            events = data.get("events")
            if isinstance(events, list):
                for event_index, event in enumerate(events):
                    if not isinstance(event, dict):
                        continue
                    _collect_named_runtime_path(
                        paths=paths,
                        section=file.section,
                        relative_path=file.relative_path,
                        pointer=f"/events/{event_index}/name",
                        value=event.get("name"),
                        reason="event-name-or-resource",
                    )
                    pages = event.get("pages")
                    if not isinstance(pages, list):
                        continue
                    for page_index, page in enumerate(pages):
                        if not isinstance(page, dict):
                            continue
                        commands = page.get("list")
                        if isinstance(commands, list):
                            _collect_command_runtime_paths(
                                paths=paths,
                                section=file.section,
                                relative_path=file.relative_path,
                                commands=commands,
                                base_pointer=f"/events/{event_index}/pages/{page_index}/list",
                            )
    return paths


def write_runtime_audit_report(path: Path, issues: list[RuntimeAuditIssue]) -> None:
    """Write a runtime audit report JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "issue_count": len(issues),
                "issues": [
                    {
                        "location_path": issue.location_path,
                        "reason": issue.reason,
                        "original_text": issue.original_text,
                        "translated_text": issue.translated_text,
                    }
                    for issue in issues
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _collect_command_runtime_paths(
    *,
    paths: dict[str, str],
    section: str,
    relative_path: str,
    commands: list[Any],
    base_pointer: str,
) -> None:
    for command_index, command in enumerate(commands):
        if not isinstance(command, dict):
            continue
        code_str = str(command.get("codeStr", ""))
        string_args = command.get("stringArgs")
        if not isinstance(string_args, list):
            continue
        for arg_index, value in enumerate(string_args):
            if not isinstance(value, str):
                continue
            reason = _runtime_reason_for_string(code_str=code_str, value=value, arg_index=arg_index)
            if reason is None:
                continue
            pointer = f"{base_pointer}/{command_index}/stringArgs/{arg_index}"
            paths[build_location_path(section, relative_path, pointer)] = reason


def _runtime_reason_for_string(*, code_str: str, value: str, arg_index: int) -> str | None:
    if code_str in {"SetLabel", "JumpLabel"}:
        return "label"
    if code_str == "CommonEventByName" and arg_index == 0:
        return "common-event-name"
    if code_str in RUNTIME_COMMANDS:
        return f"runtime-command:{code_str}"
    if RESOURCE_PREFIX_PATTERN.search(value) or RESOURCE_SUFFIX_PATTERN.search(value):
        return "resource-path"
    if value in RUNTIME_PARAMETER_KEYWORDS:
        return "runtime-parameter-keyword"
    return None


def _collect_named_runtime_path(
    *,
    paths: dict[str, str],
    section: str,
    relative_path: str,
    pointer: str,
    value: object,
    reason: str,
) -> None:
    if isinstance(value, str) and value.strip():
        paths[build_location_path(section, relative_path, pointer)] = reason


__all__ = [
    "RUNTIME_PARAMETER_KEYWORDS",
    "RuntimeAuditIssue",
    "audit_translated_dump_runtime_strings",
    "audit_wolf_runtime_translations",
    "collect_runtime_sensitive_string_paths",
    "restore_runtime_strings",
    "write_runtime_audit_report",
]
