"""Wolf RPG Editor game detection and metadata helpers."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

from app.rmmz.schema import GameLayout

DATA_DIRECTORY_NAME = "Data"
GAME_EXE_NAMES = ("Game.exe", "GamePro.exe")
GAME_INI_NAME = "Game.ini"
UNSUPPORTED_ENGINE_VERSION = (3, 595)


class _VsFixedFileInfo(ctypes.Structure):
    _fields_ = [
        ("dwSignature", ctypes.c_uint32),
        ("dwStrucVersion", ctypes.c_uint32),
        ("dwFileVersionMS", ctypes.c_uint32),
        ("dwFileVersionLS", ctypes.c_uint32),
        ("dwProductVersionMS", ctypes.c_uint32),
        ("dwProductVersionLS", ctypes.c_uint32),
        ("dwFileFlagsMask", ctypes.c_uint32),
        ("dwFileFlags", ctypes.c_uint32),
        ("dwFileOS", ctypes.c_uint32),
        ("dwFileType", ctypes.c_uint32),
        ("dwFileSubtype", ctypes.c_uint32),
        ("dwFileDateMS", ctypes.c_uint32),
        ("dwFileDateLS", ctypes.c_uint32),
    ]


def is_wolf_game_directory(game_path: str | Path) -> bool:
    """Return whether a directory looks like a Wolf RPG Editor game."""
    root = Path(game_path).resolve()
    if not root.is_dir():
        return False
    if any((root / exe_name).is_file() for exe_name in GAME_EXE_NAMES):
        return True
    if (root / DATA_DIRECTORY_NAME).is_dir():
        return True
    return any(iter_wolf_archives(root))


def resolve_wolf_game_directory(game_path: str | Path) -> Path:
    """Resolve and validate a Wolf game root."""
    root = Path(game_path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Wolf game directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Wolf game path is not a directory: {root}")
    if not is_wolf_game_directory(root):
        raise FileNotFoundError(
            "Could not identify a Wolf RPG Editor game. Expected Game.exe, "
            "GamePro.exe, Data, or .wolf archives: "
            f"{root}"
        )
    return root


def read_wolf_game_title(game_path: str | Path) -> str:
    """Read a stable title for a Wolf game, falling back to the directory name."""
    root = resolve_wolf_game_directory(game_path)
    title = root.name.strip()
    if title:
        return title
    raise ValueError(f"Wolf game title is empty: {root}")


def find_wolf_launcher(game_path: str | Path) -> Path | None:
    """Return the preferred Wolf launcher executable if present."""
    root = Path(game_path).resolve()
    for exe_name in ("GamePro.exe", "Game.exe"):
        candidate = root / exe_name
        if candidate.is_file():
            return candidate
    return None


def iter_wolf_archives(game_path: str | Path) -> list[Path]:
    """Return all ``.wolf`` archives under a game root."""
    root = Path(game_path).resolve()
    if not root.is_dir():
        return []
    return sorted(path for path in root.rglob("*.wolf") if path.is_file())


def read_wolf_engine_version(game_path: str | Path) -> str:
    """Read the Windows file version from GamePro.exe/Game.exe when available."""
    launcher = find_wolf_launcher(game_path)
    if launcher is None:
        return "unknown"
    version = _read_windows_file_version(launcher)
    return version or "unknown"


def parse_wolf_engine_version(version: str) -> tuple[int, ...] | None:
    """Parse a Wolf version string into comparable integer parts."""
    cleaned = version.strip()
    if not cleaned or cleaned.lower() == "unknown":
        return None
    parts: list[int] = []
    for raw_part in cleaned.split("."):
        digits = "".join(char for char in raw_part if char.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    if not parts:
        return None
    return tuple(parts)


def is_wolf_engine_version_unsupported(version: str) -> bool:
    """Return whether the version is at or above the known risky threshold."""
    parsed = parse_wolf_engine_version(version)
    if parsed is None:
        return False
    threshold = UNSUPPORTED_ENGINE_VERSION
    return parsed[: len(threshold)] >= threshold


def resolve_wolf_game_layout(game_path: str | Path) -> GameLayout:
    """Build a minimal shared game layout record for a Wolf game."""
    root = resolve_wolf_game_directory(game_path)
    data_dir = root / DATA_DIRECTORY_NAME
    return GameLayout(
        game_root=root,
        content_root=root,
        data_dir=data_dir,
        data_origin_dir=root / "Origin_Data",
        js_dir=root,
        plugins_path=root / "__wolf_no_plugins__.js",
        plugins_origin_path=root / "__wolf_no_plugins_origin__.js",
        plugin_source_origin_dir=root / "__wolf_no_plugin_source_origin__",
        package_path=root / GAME_INI_NAME,
        engine_kind="wolf",
        engine_version=read_wolf_engine_version(root),
        is_www_layout=False,
    )


def _read_windows_file_version(exe_path: Path) -> str | None:
    if os.name != "nt" or not exe_path.is_file():
        return None
    try:
        version_dll = ctypes.WinDLL("version", use_last_error=True)
        handle = ctypes.c_uint32(0)
        size = version_dll.GetFileVersionInfoSizeW(str(exe_path), ctypes.byref(handle))
        if not size:
            return None
        buffer = ctypes.create_string_buffer(size)
        ok = version_dll.GetFileVersionInfoW(str(exe_path), 0, size, buffer)
        if not ok:
            return None
        value = ctypes.c_void_p()
        value_size = ctypes.c_uint32(0)
        ok = version_dll.VerQueryValueW(buffer, "\\", ctypes.byref(value), ctypes.byref(value_size))
        if not ok or not value.value:
            return None
        info = ctypes.cast(value, ctypes.POINTER(_VsFixedFileInfo)).contents
        major = info.dwFileVersionMS >> 16
        minor = info.dwFileVersionMS & 0xFFFF
        patch = info.dwFileVersionLS >> 16
        build = info.dwFileVersionLS & 0xFFFF
    except Exception:
        return None
    parts = [major, minor, patch, build]
    while len(parts) > 2 and parts[-1] == 0:
        parts.pop()
    return ".".join(str(part) for part in parts)


__all__ = [
    "DATA_DIRECTORY_NAME",
    "GAME_EXE_NAMES",
    "GAME_INI_NAME",
    "UNSUPPORTED_ENGINE_VERSION",
    "find_wolf_launcher",
    "is_wolf_game_directory",
    "is_wolf_engine_version_unsupported",
    "iter_wolf_archives",
    "parse_wolf_engine_version",
    "read_wolf_engine_version",
    "read_wolf_game_title",
    "resolve_wolf_game_directory",
    "resolve_wolf_game_layout",
]
