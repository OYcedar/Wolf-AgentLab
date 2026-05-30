from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


DEFAULT_PASSWORD = "sstm"


def find_7z() -> str:
    for candidate in [
        shutil.which("7z"),
        shutil.which("7za"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        r"C:\Program Files\PeaZip\res\bin\7z\7z.exe",
    ]:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise SystemExit("7z.exe not found; install 7-Zip or add it to PATH")


def create_nested_encrypted_7z(
    patch_dir: Path,
    *,
    password: str = DEFAULT_PASSWORD,
    output: Path | None = None,
    verify: bool = True,
) -> Path:
    patch_dir = patch_dir.resolve()
    if not patch_dir.is_dir():
        raise SystemExit(f"patch directory not found: {patch_dir}")

    seven = find_7z()
    outer = output or patch_dir.parent / f"{patch_dir.name}_汉化补丁_双层加密.7z"
    outer.parent.mkdir(parents=True, exist_ok=True)
    if outer.exists():
        outer.unlink()

    with tempfile.TemporaryDirectory(prefix=f"{patch_dir.name}_package_", dir=str(outer.parent)) as tmp:
        inner = Path(tmp) / f"{patch_dir.name}_汉化补丁_inner.7z"
        subprocess.run(
            [seven, "a", "-t7z", str(inner), str(patch_dir), f"-p{password}", "-mhe=on", "-mx=9"],
            check=True,
        )
        subprocess.run(
            [seven, "a", "-t7z", str(outer), str(inner), f"-p{password}", "-mhe=on", "-mx=9"],
            check=True,
        )

    if verify:
        subprocess.run([seven, "t", str(outer), f"-p{password}"], check=True)

    return outer


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Finalize an att-wolf patch directory as a two-layer encrypted 7z package."
    )
    parser.add_argument("--patch-dir", type=Path, required=True, help="Patch directory to package")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Password for both 7z layers")
    parser.add_argument("--output", type=Path, help="Optional output .7z path")
    parser.add_argument("--no-verify", action="store_true", help="Skip final 7z test")
    args = parser.parse_args()

    package = create_nested_encrypted_7z(
        args.patch_dir,
        password=args.password,
        output=args.output,
        verify=not args.no_verify,
    )
    print(
        json.dumps(
            {
                "patch_dir": str(args.patch_dir),
                "nested_package": str(package),
                "password": args.password,
                "layers": 2,
                "encrypted_headers": True,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
