"""WolfTL dump loading and JSON pointer helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

JsonValue = Any


@dataclass(slots=True)
class WolfDumpFile:
    """One JSON file inside a WolfTL dump."""

    section: str
    relative_path: str
    path: Path
    data: JsonValue


def iter_wolftl_dump_files(dump_dir: Path) -> list[WolfDumpFile]:
    """Load all JSON files from ``Game.json``, ``common``, ``mps``, and ``db``."""
    files: list[WolfDumpFile] = []
    game_json = dump_dir / "Game.json"
    if game_json.is_file():
        files.append(_load_dump_file("game", "Game.json", game_json))
    for section in ("common", "mps", "db"):
        section_dir = dump_dir / section
        if not section_dir.is_dir():
            continue
        for path in sorted(section_dir.glob("*.json"), key=lambda item: item.name):
            files.append(_load_dump_file(section, f"{section}/{path.name}", path))
    return files


def load_dump_file_by_relative_path(dump_dir: Path, relative_path: str) -> WolfDumpFile:
    """Load a single dump JSON file by relative path."""
    path = dump_dir / relative_path
    if not path.is_file():
        raise FileNotFoundError(f"WolfTL dump file not found: {path}")
    section = relative_path.split("/", 1)[0]
    if relative_path == "Game.json":
        section = "game"
    return _load_dump_file(section, relative_path, path)


def write_dump_file(file: WolfDumpFile) -> None:
    """Write a loaded dump file back as UTF-8 JSON."""
    file.path.parent.mkdir(parents=True, exist_ok=True)
    file.path.write_text(
        json.dumps(file.data, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )


def build_location_path(section: str, relative_path: str, pointer: str) -> str:
    """Build a stable location path for translation storage."""
    if not pointer.startswith("/"):
        raise ValueError(f"JSON pointer must start with '/': {pointer}")
    return f"wolf:{section}:{relative_path}#{pointer}"


def parse_location_path(location_path: str) -> tuple[str, str, str]:
    """Parse a location path produced by ``build_location_path``."""
    if not location_path.startswith("wolf:"):
        raise ValueError(f"Not a Wolf location path: {location_path}")
    before_pointer, separator, pointer = location_path.partition("#")
    if separator != "#":
        raise ValueError(f"Wolf location path has no JSON pointer: {location_path}")
    _, section, relative_path = before_pointer.split(":", 2)
    if not pointer.startswith("/"):
        raise ValueError(f"Wolf location pointer is invalid: {location_path}")
    return section, relative_path, pointer


def get_pointer_value(root: JsonValue, pointer: str) -> JsonValue:
    """Read a value by a minimal JSON pointer."""
    current = root
    for part in _pointer_parts(pointer):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise TypeError(f"Cannot descend into JSON scalar at {pointer}")
    return current


def set_pointer_value(root: JsonValue, pointer: str, value: JsonValue) -> None:
    """Set a value by a minimal JSON pointer."""
    parts = _pointer_parts(pointer)
    if not parts:
        raise ValueError("Cannot replace the root dump object")
    current = root
    for part in parts[:-1]:
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise TypeError(f"Cannot descend into JSON scalar at {pointer}")
    last = parts[-1]
    if isinstance(current, list):
        current[int(last)] = value
        return
    if isinstance(current, dict):
        current[last] = value
        return
    raise TypeError(f"Cannot set JSON scalar at {pointer}")


def _load_dump_file(section: str, relative_path: str, path: Path) -> WolfDumpFile:
    raw_text = path.read_text(encoding="utf-8-sig")
    return WolfDumpFile(
        section=section,
        relative_path=relative_path,
        path=path,
        data=json.loads(raw_text),
    )


def _pointer_parts(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError(f"Invalid JSON pointer: {pointer}")
    return [
        part.replace("~1", "/").replace("~0", "~")
        for part in pointer.split("/")[1:]
    ]


def escape_pointer_part(part: str | int) -> str:
    """Escape one JSON pointer segment."""
    return str(part).replace("~", "~0").replace("/", "~1")


__all__ = [
    "JsonValue",
    "WolfDumpFile",
    "build_location_path",
    "escape_pointer_part",
    "get_pointer_value",
    "iter_wolftl_dump_files",
    "load_dump_file_by_relative_path",
    "parse_location_path",
    "set_pointer_value",
    "write_dump_file",
]
