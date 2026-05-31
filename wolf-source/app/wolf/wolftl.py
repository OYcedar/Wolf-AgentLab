"""WolfTL create/patch wrapper."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WolfTLRunResult:
    """Captured result from one WolfTL invocation."""

    ok: bool
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


def run_wolftl_create(*, wolftl_path: Path, data_dir: Path, output_dir: Path) -> WolfTLRunResult:
    """Run ``WolfTL create`` and return whether a usable dump was produced."""
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result = _run_wolftl(wolftl_path, data_dir, output_dir, "create")
    if result.ok and not is_valid_wolftl_dump(output_dir):
        return WolfTLRunResult(
            ok=False,
            command=result.command,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr + "\nWolfTL did not create a complete dump directory.",
        )
    return result


def run_wolftl_patch(*, wolftl_path: Path, data_dir: Path, output_dir: Path) -> WolfTLRunResult:
    """Run ``WolfTL patch`` using ``output_dir/dump`` as the edited dump."""
    output_dir.mkdir(parents=True, exist_ok=True)
    return _run_wolftl(wolftl_path, data_dir, output_dir, "patch")


def is_valid_wolftl_dump(output_dir: Path) -> bool:
    """Return whether WolfTL output contains the expected dump layout."""
    dump_dir = output_dir / "dump"
    return (
        (dump_dir / "Game.json").is_file()
        and (dump_dir / "common").is_dir()
        and (dump_dir / "mps").is_dir()
        and (dump_dir / "db").is_dir()
    )


def require_wolftl_dump(output_dir: Path) -> Path:
    """Return ``output_dir/dump`` or raise if it is incomplete."""
    if not is_valid_wolftl_dump(output_dir):
        raise FileNotFoundError(f"WolfTL dump is missing or incomplete: {output_dir / 'dump'}")
    return output_dir / "dump"


def _run_wolftl(wolftl_path: Path, data_dir: Path, output_dir: Path, mode: str) -> WolfTLRunResult:
    operation = {"create": "--create", "patch": "--patch"}[mode]
    command = [str(wolftl_path), str(data_dir), str(output_dir), operation]
    if mode == "patch":
        command.append("--inplace")
    completed = subprocess.run(
        command,
        cwd=str(output_dir.parent),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    return WolfTLRunResult(
        ok=completed.returncode == 0,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


__all__ = [
    "WolfTLRunResult",
    "is_valid_wolftl_dump",
    "require_wolftl_dump",
    "run_wolftl_create",
    "run_wolftl_patch",
]
