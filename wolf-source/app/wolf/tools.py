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


class WolfToolsSettingProtocol(Protocol):
    """Small protocol for settings that expose optional tool paths."""

    wolftl_path: str | None
    uberwolf_path: str | None
    wolfdec_path: str | None


@dataclass(frozen=True, slots=True)
class WolfToolPaths:
    """Resolved optional paths for Wolf tools."""

    wolftl: Path | None
    uberwolf: Path | None
    wolfdec: Path | None


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


__all__ = [
    "UBERWOLF_ENV_NAME",
    "WOLFDEC_ENV_NAME",
    "WOLFTL_ENV_NAME",
    "WolfToolPaths",
    "resolve_wolf_tool_paths",
]
