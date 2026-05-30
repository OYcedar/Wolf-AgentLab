"""Path helpers for att-wolf workspaces, tools, and patches."""

from __future__ import annotations

import os
import re
from pathlib import Path

from app.runtime_paths import resolve_app_home

ATT_WOLF_HOME_ENV_NAME = "ATT_WOLF_HOME"
ATT_WOLF_WORKSPACE_ENV_NAME = "ATT_WOLF_WORKSPACE"
ATT_WOLF_TOOLS_ENV_NAME = "ATT_WOLF_TOOLS"
ATT_WOLF_PATCHES_ENV_NAME = "ATT_WOLF_PATCHES"


def resolve_wolf_home() -> Path:
    """Return the att-wolf installation root, normally ``G:\\wolf``."""
    env_value = os.environ.get(ATT_WOLF_HOME_ENV_NAME)
    if env_value is not None and env_value.strip():
        return Path(env_value).expanduser().resolve()
    app_home = resolve_app_home()
    if app_home.name.lower() == "wolf-source":
        return app_home.parent.resolve()
    return app_home.resolve()


def resolve_wolf_workspace_root() -> Path:
    """Return the root directory used for per-game workspaces."""
    env_value = os.environ.get(ATT_WOLF_WORKSPACE_ENV_NAME)
    if env_value is not None and env_value.strip():
        return Path(env_value).expanduser().resolve()
    return (resolve_wolf_home() / "workspace").resolve()


def resolve_wolf_tools_root() -> Path:
    """Return the directory used for bundled Wolf tools."""
    env_value = os.environ.get(ATT_WOLF_TOOLS_ENV_NAME)
    if env_value is not None and env_value.strip():
        return Path(env_value).expanduser().resolve()
    return (resolve_wolf_home() / "tools").resolve()


def resolve_wolf_patches_root() -> Path:
    """Return the directory used for generated Chinese patches."""
    env_value = os.environ.get(ATT_WOLF_PATCHES_ENV_NAME)
    if env_value is not None and env_value.strip():
        return Path(env_value).expanduser().resolve()
    return (resolve_wolf_home() / "patches").resolve()


def safe_game_slug(game_title: str) -> str:
    """Return a Windows-safe directory name for a registered game title."""
    stripped = game_title.strip() or "wolf-game"
    slug = re.sub(r'[<>:"/\\|?*\x00-\x1F]+', "_", stripped)
    slug = re.sub(r"\s+", " ", slug).strip(" .")
    return slug or "wolf-game"


def resolve_game_workspace(game_title: str) -> Path:
    """Return the workspace directory for one game."""
    return (resolve_wolf_workspace_root() / safe_game_slug(game_title)).resolve()


__all__ = [
    "ATT_WOLF_HOME_ENV_NAME",
    "ATT_WOLF_PATCHES_ENV_NAME",
    "ATT_WOLF_TOOLS_ENV_NAME",
    "ATT_WOLF_WORKSPACE_ENV_NAME",
    "resolve_game_workspace",
    "resolve_wolf_home",
    "resolve_wolf_patches_root",
    "resolve_wolf_tools_root",
    "resolve_wolf_workspace_root",
    "safe_game_slug",
]
