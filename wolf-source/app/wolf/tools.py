"""Wolf external tool path resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.wolf.paths import resolve_wolf_tools_root

WOLFTL_ENV_NAME = "ATT_WOLF_WOLFTL_PATH"
UBERWOLF_ENV_NAME = "ATT_WOLF_UBERWOLF_PATH"
WOLFDEC_ENV_NAME = "ATT_WOLF_WOLFDEC_PATH"
WOLF_RUNTIME_ENV_NAME = "ATT_WOLF_RUNTIME_DIR"
WOLF_RUNTIME_EDITOR_NAMES = ("EditorPro.exe", "Editor.exe")
WOLF_RUNTIME_GAME_NAMES = ("GamePro.exe", "Game.exe")


class WolfToolsSettingProtocol(Protocol):
    """Small protocol for settings that expose optional tool paths."""

    wolftl_path: str | None
    uberwolf_path: str | None
    wolfdec_path: str | None
    wolf_runtime_dir: str | None


@dataclass(frozen=True, slots=True)
class WolfToolPaths:
    """Resolved optional paths for Wolf tools."""

    wolftl: Path | None
    uberwolf: Path | None
    wolfdec: Path | None
    runtime_dir: Path | None = None


def resolve_wolf_tool_paths(setting: object | None = None) -> WolfToolPaths:
    """Resolve WolfTL, UberWolf, and WolfDec from config, env, and defaults."""
    tools_setting = getattr(setting, "wolf_tools", None)
    return WolfToolPaths(
        wolftl=_resolve_tool(
            configured=_setting_path(tools_setting, "wolftl_path"),
            env_name=WOLFTL_ENV_NAME,
            default_names=("WolfTL.exe",),
            extra_candidates=(
                Path(r"G:\WolfTL.exe"),
                Path(r"G:\MY ver2.10\WolfTL.exe"),
            ),
        ),
        uberwolf=_resolve_tool(
            configured=_setting_path(tools_setting, "uberwolf_path"),
            env_name=UBERWOLF_ENV_NAME,
            default_names=("UberWolf.exe",),
            extra_candidates=(),
        ),
        wolfdec=_resolve_tool(
            configured=_setting_path(tools_setting, "wolfdec_path"),
            env_name=WOLFDEC_ENV_NAME,
            default_names=("WolfDec.exe", "WolfDec_v0.3.3.exe"),
            extra_candidates=(Path(r"G:\翻译\my\WolfDec_v0.3.3.exe"),),
        ),
        runtime_dir=_resolve_runtime_dir(
            configured=_setting_path(tools_setting, "wolf_runtime_dir"),
            env_name=WOLF_RUNTIME_ENV_NAME,
            default_names=("wolf-runtime-pro", "wolf-runtime", "wolf-rpg-editor", "WolfRPGEditor"),
        ),
    )


def _setting_path(setting: object | None, field_name: str) -> str | None:
    if setting is None:
        return None
    value = getattr(setting, field_name, None)
    return value if isinstance(value, str) and value.strip() else None


def _resolve_tool(
    *,
    configured: str | None,
    env_name: str,
    default_names: tuple[str, ...],
    extra_candidates: tuple[Path, ...],
) -> Path | None:
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())
    env_value = os.environ.get(env_name)
    if env_value is not None and env_value.strip():
        candidates.append(Path(env_value).expanduser())
    tools_root = resolve_wolf_tools_root()
    candidates.extend(tools_root / name for name in default_names)
    candidates.extend(extra_candidates)
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_file():
            return resolved
    return None


def _resolve_runtime_dir(
    *,
    configured: str | None,
    env_name: str,
    default_names: tuple[str, ...],
) -> Path | None:
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())
    env_value = os.environ.get(env_name)
    if env_value is not None and env_value.strip():
        candidates.append(Path(env_value).expanduser())
    tools_root = resolve_wolf_tools_root()
    candidates.extend(tools_root / name for name in default_names)
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if is_wolf_runtime_dir(resolved):
            return resolved
    return None


def is_wolf_runtime_dir(path: Path) -> bool:
    """Return whether a directory has a usable high-version WOLF runtime/editor pair."""
    if not path.is_dir():
        return False
    has_editor = any((path / name).is_file() for name in WOLF_RUNTIME_EDITOR_NAMES)
    has_game = any((path / name).is_file() for name in WOLF_RUNTIME_GAME_NAMES)
    return has_editor and has_game


__all__ = [
    "UBERWOLF_ENV_NAME",
    "WOLFDEC_ENV_NAME",
    "WOLF_RUNTIME_ENV_NAME",
    "WOLF_RUNTIME_EDITOR_NAMES",
    "WOLF_RUNTIME_GAME_NAMES",
    "WOLFTL_ENV_NAME",
    "WolfToolPaths",
    "is_wolf_runtime_dir",
    "resolve_wolf_tool_paths",
]
