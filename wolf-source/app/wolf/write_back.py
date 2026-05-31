"""Write translated WolfTL dump files and generate patched Data."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
import re

from app.rmmz.schema import TranslationItem
from app.wolf.dump_loader import (
    load_dump_file_by_relative_path,
    parse_location_path,
    set_pointer_value,
    write_dump_file,
)
from app.wolf.runtime_audit import collect_runtime_sensitive_string_paths
from app.wolf.wolftl import run_wolftl_patch

TRANSLATED_OUTPUT_DIR_NAME = "translated_wolftl"

_DB_STRUCTURAL_POINTER_PATTERN = re.compile(
    r"/types/\d+/(?:fields/|name$|description$)"
)


@dataclass(frozen=True, slots=True)
class WolfWriteBackResult:
    """Summary of a Wolf write-back run."""

    written_item_count: int
    restored_runtime_string_count: int
    patched_data_dir: Path
    translated_output_dir: Path


def write_wolf_translations(
    *,
    source_dump_dir: Path,
    data_dir: Path,
    workspace_dir: Path,
    wolftl_path: Path,
    translated_items: list[TranslationItem],
) -> WolfWriteBackResult:
    """Apply stored translations to a dump and run WolfTL patch."""
    translated_output_dir = workspace_dir / TRANSLATED_OUTPUT_DIR_NAME
    translated_dump_dir = translated_output_dir / "dump"
    if translated_output_dir.exists():
        shutil.rmtree(translated_output_dir)
    shutil.copytree(source_dump_dir, translated_dump_dir)
    runtime_sensitive_paths = collect_runtime_sensitive_string_paths(source_dump_dir)

    files_by_relative_path: dict[str, object] = {}
    written_count = 0
    for item in translated_items:
        section, relative_path, pointer = parse_location_path(item.location_path)
        if item.location_path in runtime_sensitive_paths:
            continue
        if _skip_wolf_write_back_item(section=section, location_path=item.location_path):
            continue
        file = files_by_relative_path.get(relative_path)
        if file is None:
            file = load_dump_file_by_relative_path(translated_dump_dir, relative_path)
            files_by_relative_path[relative_path] = file
        translated_text = "\n".join(item.translation_lines)
        set_pointer_value(file.data, pointer, translated_text)
        written_count += 1

    for file in files_by_relative_path.values():
        write_dump_file(file)

    restored_count = 0

    patched_data_dir = translated_output_dir / "patched" / "Data"
    if patched_data_dir.parent.exists():
        shutil.rmtree(patched_data_dir.parent)
    shutil.copytree(data_dir, patched_data_dir)

    patch_result = run_wolftl_patch(
        wolftl_path=wolftl_path,
        data_dir=patched_data_dir,
        output_dir=translated_output_dir,
    )
    if not patch_result.ok:
        raise RuntimeError(
            "WolfTL patch failed: "
            + (patch_result.stderr.strip() or patch_result.stdout.strip() or str(patch_result.returncode))
        )
    if not patched_data_dir.is_dir():
        raise FileNotFoundError(f"WolfTL patch did not create patched data: {patched_data_dir}")
    return WolfWriteBackResult(
        written_item_count=written_count,
        restored_runtime_string_count=restored_count,
        patched_data_dir=patched_data_dir,
        translated_output_dir=translated_output_dir,
    )


def _skip_wolf_write_back_item(*, section: str, location_path: str) -> bool:
    """Return whether a translated item is unsafe to write into Wolf data."""
    if section != "db":
        return False
    return bool(_DB_STRUCTURAL_POINTER_PATTERN.search(location_path))


__all__ = [
    "TRANSLATED_OUTPUT_DIR_NAME",
    "WolfWriteBackResult",
    "_skip_wolf_write_back_item",
    "write_wolf_translations",
]
