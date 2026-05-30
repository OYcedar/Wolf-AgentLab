"""Build the att-wolf Windows release directory and ZIP package."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from io import TextIOWrapper
from pathlib import Path
from typing import cast


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
DEFAULT_OUTPUT_DIR = ROOT / "dist"
RELEASE_DIRECTORY_NAME = "att-wolf"
DEFAULT_ZIP_NAME = "att-wolf-windows-x86_64.zip"


@dataclass(frozen=True)
class BuildOptions:
    output_dir: Path
    zip_name: str


@dataclass(frozen=True)
class CopySpec:
    source: Path
    target_parts: tuple[str, ...]


def parse_args() -> BuildOptions:
    parser = argparse.ArgumentParser(description="Build att-wolf Windows release ZIP")
    _ = parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Release output directory. Defaults to dist.",
    )
    _ = parser.add_argument(
        "--zip-name",
        default=DEFAULT_ZIP_NAME,
        help=f"Generated ZIP file name. Defaults to {DEFAULT_ZIP_NAME}.",
    )
    namespace = parser.parse_args()
    output_dir = cast(str, namespace.output_dir)
    zip_name = cast(str, namespace.zip_name)
    return BuildOptions(output_dir=Path(output_dir).resolve(), zip_name=zip_name)


def configure_stdio_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")


def ensure_github_actions_environment() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Release builds are restricted to the GitHub Actions release workflow.")


def ensure_source_exists(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Release resource not found: {path}")


def reset_release_directory(release_dir: Path) -> None:
    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True)


def build_pex_scie(exe_path: Path) -> None:
    pex_output_path = exe_path.with_suffix(".pex")
    if pex_output_path.exists():
        pex_output_path.unlink()
    if exe_path.exists():
        exe_path.unlink()
    command = [
        "uv",
        "run",
        "--with",
        "pex",
        "pex",
        ".",
        "--script",
        "att-wolf",
        "--scie",
        "eager",
        "--scie-load-dotenv",
        "--output-file",
        str(pex_output_path),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    ensure_source_exists(exe_path)
    if pex_output_path.exists():
        pex_output_path.unlink()


def copy_file(source: Path, target: Path) -> None:
    ensure_source_exists(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = shutil.copy2(source, target)


def copy_release_resources(release_dir: Path) -> None:
    copy_specs = [
        CopySpec(REPO_ROOT / "README.md", ("README.md",)),
        CopySpec(REPO_ROOT / "WOLF_FIXED_WORKFLOW.md", ("WOLF_FIXED_WORKFLOW.md",)),
        CopySpec(REPO_ROOT / "PATCH_FINALIZATION.md", ("PATCH_FINALIZATION.md",)),
        CopySpec(REPO_ROOT / "att-wolf-auto.bat", ("att-wolf-auto.bat",)),
        CopySpec(REPO_ROOT / "att-wolf-wizard.ps1", ("att-wolf-wizard.ps1",)),
        CopySpec(REPO_ROOT / "finalize-patch-package.bat", ("finalize-patch-package.bat",)),
        CopySpec(REPO_ROOT / "scripts" / "finalize_patch_package.py", ("scripts", "finalize_patch_package.py")),
        CopySpec(ROOT / "LICENSE", ("LICENSE",)),
        CopySpec(ROOT / "setting.example.toml", ("setting.example.toml",)),
        CopySpec(ROOT / "setting.example.toml", ("setting.toml",)),
        CopySpec(ROOT / "custom_placeholder_rules.json", ("custom_placeholder_rules.json",)),
        CopySpec(ROOT / "prompts" / "text_translation_ja_to_zh_system.md", ("prompts", "text_translation_ja_to_zh_system.md")),
        CopySpec(ROOT / "prompts" / "text_translation_en_to_zh_system.md", ("prompts", "text_translation_en_to_zh_system.md")),
        CopySpec(ROOT / "fonts" / "NotoSansSC-Regular.ttf", ("fonts", "NotoSansSC-Regular.ttf")),
        CopySpec(REPO_ROOT / "tools" / "README.md", ("tools", "README.md")),
    ]
    for spec in copy_specs:
        copy_file(spec.source, release_dir.joinpath(*spec.target_parts))

    for directory_parts in (("data", "db"), ("logs",), ("outputs",), ("game",), ("workspace",), ("patches",), ("tools",)):
        release_dir.joinpath(*directory_parts).mkdir(parents=True, exist_ok=True)


def run_smoke_tests(release_dir: Path) -> None:
    exe_path = release_dir / "att-wolf.exe"
    subprocess.run(
        [str(exe_path), "--help"],
        cwd=release_dir,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    subprocess.run(
        [str(exe_path), "list", "--json"],
        cwd=release_dir,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def add_directory_entry(archive: zipfile.ZipFile, arcname: str) -> None:
    normalized_name = arcname.replace("\\", "/").rstrip("/") + "/"
    info = zipfile.ZipInfo(normalized_name)
    info.date_time = (2026, 1, 1, 0, 0, 0)
    info.external_attr = 0o755 << 16
    archive.writestr(info, b"")


def add_file_entry(archive: zipfile.ZipFile, source: Path, arcname: str) -> None:
    info = zipfile.ZipInfo(arcname.replace("\\", "/"))
    info.date_time = (2026, 1, 1, 0, 0, 0)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, source.read_bytes())


def create_release_zip(release_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        root_arcname = release_dir.name
        add_directory_entry(archive, root_arcname)
        for directory in sorted(path for path in release_dir.rglob("*") if path.is_dir()):
            add_directory_entry(archive, str(Path(root_arcname) / directory.relative_to(release_dir)))
        for file_path in sorted(path for path in release_dir.rglob("*") if path.is_file()):
            add_file_entry(archive, file_path, str(Path(root_arcname) / file_path.relative_to(release_dir)))


def main() -> int:
    configure_stdio_encoding()
    ensure_github_actions_environment()
    options = parse_args()
    release_dir = options.output_dir / RELEASE_DIRECTORY_NAME
    zip_path = options.output_dir / options.zip_name

    exe_path = release_dir / "att-wolf.exe"
    reset_release_directory(release_dir)
    build_pex_scie(exe_path)
    copy_release_resources(release_dir)
    run_smoke_tests(release_dir)
    create_release_zip(release_dir, zip_path)
    print(f"Release directory: {release_dir}")
    print(f"Release ZIP: {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
