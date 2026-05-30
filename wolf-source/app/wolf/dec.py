"""Wolf game preparation and unpacker fallback workflow."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app.wolf.paths import resolve_game_workspace
from app.wolf.tools import WolfToolPaths
from app.wolf.wolftl import WolfTLRunResult, run_wolftl_create

DATA_DIR_NAME = "Data"
UNPACKED_DIR_NAME = "unpacked"
WOLFTL_OUTPUT_DIR_NAME = "wolftl"
PREPARE_REPORT_NAME = "prepare_report.json"


@dataclass(frozen=True, slots=True)
class UnpackAttempt:
    """One unpack/parse attempt."""

    method: str
    ok: bool
    data_dir: str
    wolftl_output_dir: str
    message: str
    command: list[str] = field(default_factory=list)
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True, slots=True)
class PrepareGameResult:
    """Result of preparing one Wolf game."""

    ok: bool
    game_title: str
    workspace_dir: Path
    data_dir: Path | None
    wolftl_output_dir: Path | None
    attempts: list[UnpackAttempt]
    message: str

    @property
    def dump_dir(self) -> Path | None:
        if self.wolftl_output_dir is None:
            return None
        return self.wolftl_output_dir / "dump"


def prepare_wolf_game(
    *,
    game_title: str,
    game_path: Path,
    tools: WolfToolPaths,
) -> PrepareGameResult:
    """Prepare a Wolf game and validate the result with WolfTL.

    Already-unpacked ``Data`` directories are copied and validated directly.
    Packed games try UberWolf first, then WolfDec if WolfTL cannot parse the
    UberWolf output. If WolfDec output also fails WolfTL parsing, translation is
    abandoned for this game until the extraction problem is fixed.
    """
    workspace_dir = resolve_game_workspace(game_title)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    attempts: list[UnpackAttempt] = []
    if tools.wolftl is None:
        result = PrepareGameResult(
            ok=False,
            game_title=game_title,
            workspace_dir=workspace_dir,
            data_dir=None,
            wolftl_output_dir=None,
            attempts=[],
            message="WolfTL.exe not found. Put it in G:\\wolf\\tools or configure setting.toml/env.",
        )
        _write_prepare_report(result)
        return result

    existing_data_dir = game_path / DATA_DIR_NAME
    if _looks_like_unpacked_data(existing_data_dir):
        data_dir = _copy_data_dir(existing_data_dir, workspace_dir / UNPACKED_DIR_NAME / DATA_DIR_NAME)
        wolftl_output_dir = workspace_dir / WOLFTL_OUTPUT_DIR_NAME
        wolftl_result = run_wolftl_create(
            wolftl_path=tools.wolftl,
            data_dir=data_dir,
            output_dir=wolftl_output_dir,
        )
        attempts.append(_attempt_from_wolftl("existing-data", data_dir, wolftl_output_dir, wolftl_result))
        if wolftl_result.ok:
            result = PrepareGameResult(
                ok=True,
                game_title=game_title,
                workspace_dir=workspace_dir,
                data_dir=data_dir,
                wolftl_output_dir=wolftl_output_dir,
                attempts=attempts,
                message="Prepared from existing unpacked Data.",
            )
            _write_prepare_report(result)
            return result

    wolf_archives = sorted(game_path.glob("*.wolf"))
    if tools.uberwolf is not None and wolf_archives:
        data_dir = workspace_dir / "uberwolf" / DATA_DIR_NAME
        unpack_result = _run_uberwolf(
            uberwolf_path=tools.uberwolf,
            game_path=game_path,
            output_dir=data_dir.parent,
        )
        parsed_data_dir = _find_data_dir(data_dir.parent)
        if unpack_result.returncode == 0 and parsed_data_dir is not None:
            wolftl_output_dir = workspace_dir / "wolftl_uberwolf"
            wolftl_result = run_wolftl_create(
                wolftl_path=tools.wolftl,
                data_dir=parsed_data_dir,
                output_dir=wolftl_output_dir,
            )
            attempts.append(_attempt_from_wolftl("uberwolf", parsed_data_dir, wolftl_output_dir, wolftl_result))
            if wolftl_result.ok:
                _promote_successful_attempt(wolftl_output_dir, workspace_dir / WOLFTL_OUTPUT_DIR_NAME)
                result = PrepareGameResult(
                    ok=True,
                    game_title=game_title,
                    workspace_dir=workspace_dir,
                    data_dir=parsed_data_dir,
                    wolftl_output_dir=workspace_dir / WOLFTL_OUTPUT_DIR_NAME,
                    attempts=attempts,
                    message="Prepared with UberWolf and validated by WolfTL.",
                )
                _write_prepare_report(result)
                return result
        else:
            attempts.append(
                UnpackAttempt(
                    method="uberwolf",
                    ok=False,
                    data_dir=str(data_dir),
                    wolftl_output_dir="",
                    message="UberWolf unpack failed or produced no Data directory.",
                    command=unpack_result.command,
                    returncode=unpack_result.returncode,
                    stdout=unpack_result.stdout,
                    stderr=unpack_result.stderr,
                )
            )

    if tools.wolfdec is not None and wolf_archives:
        wolfdec_root = workspace_dir / "wolfdec"
        if wolfdec_root.exists():
            shutil.rmtree(wolfdec_root)
        wolfdec_root.mkdir(parents=True, exist_ok=True)
        unpack_result = _run_wolfdec(
            wolfdec_path=tools.wolfdec,
            wolf_archives=wolf_archives,
            output_dir=wolfdec_root,
        )
        parsed_data_dir = _find_data_dir(wolfdec_root)
        if unpack_result.returncode == 0 and parsed_data_dir is not None:
            wolftl_output_dir = workspace_dir / "wolftl_wolfdec"
            wolftl_result = run_wolftl_create(
                wolftl_path=tools.wolftl,
                data_dir=parsed_data_dir,
                output_dir=wolftl_output_dir,
            )
            attempts.append(_attempt_from_wolftl("wolfdec", parsed_data_dir, wolftl_output_dir, wolftl_result))
            if wolftl_result.ok:
                _promote_successful_attempt(wolftl_output_dir, workspace_dir / WOLFTL_OUTPUT_DIR_NAME)
                result = PrepareGameResult(
                    ok=True,
                    game_title=game_title,
                    workspace_dir=workspace_dir,
                    data_dir=parsed_data_dir,
                    wolftl_output_dir=workspace_dir / WOLFTL_OUTPUT_DIR_NAME,
                    attempts=attempts,
                    message="Prepared with WolfDec and validated by WolfTL.",
                )
                _write_prepare_report(result)
                return result
        else:
            attempts.append(
                UnpackAttempt(
                    method="wolfdec",
                    ok=False,
                    data_dir=str(wolfdec_root),
                    wolftl_output_dir="",
                    message="WolfDec unpack failed or produced no Data directory.",
                    command=unpack_result.command,
                    returncode=unpack_result.returncode,
                    stdout=unpack_result.stdout,
                    stderr=unpack_result.stderr,
                )
            )

    result = PrepareGameResult(
        ok=False,
        game_title=game_title,
        workspace_dir=workspace_dir,
        data_dir=None,
        wolftl_output_dir=None,
        attempts=attempts,
        message="WolfTL could not parse the available unpacked data; translation is abandoned for this game.",
    )
    _write_prepare_report(result)
    return result


def load_prepare_report(game_title: str) -> PrepareGameResult | None:
    """Load the latest prepare report if it exists."""
    report_path = resolve_game_workspace(game_title) / PREPARE_REPORT_NAME
    if not report_path.is_file():
        return None
    raw = json.loads(report_path.read_text(encoding="utf-8"))
    return PrepareGameResult(
        ok=bool(raw.get("ok")),
        game_title=str(raw.get("game_title", game_title)),
        workspace_dir=Path(str(raw.get("workspace_dir"))),
        data_dir=Path(str(raw["data_dir"])) if raw.get("data_dir") else None,
        wolftl_output_dir=Path(str(raw["wolftl_output_dir"])) if raw.get("wolftl_output_dir") else None,
        attempts=[
            UnpackAttempt(
                method=str(item.get("method", "")),
                ok=bool(item.get("ok")),
                data_dir=str(item.get("data_dir", "")),
                wolftl_output_dir=str(item.get("wolftl_output_dir", "")),
                message=str(item.get("message", "")),
                command=[str(part) for part in item.get("command", [])],
                returncode=item.get("returncode") if isinstance(item.get("returncode"), int) else None,
                stdout=str(item.get("stdout", "")),
                stderr=str(item.get("stderr", "")),
            )
            for item in raw.get("attempts", [])
            if isinstance(item, dict)
        ],
        message=str(raw.get("message", "")),
    )


def require_prepared_wolf_game(game_title: str) -> PrepareGameResult:
    """Return a successful prepare report or raise."""
    report = load_prepare_report(game_title)
    if report is None or not report.ok or report.data_dir is None or report.wolftl_output_dir is None:
        raise RuntimeError(f"Wolf game is not prepared. Run prepare-game first: {game_title}")
    if not report.data_dir.is_dir():
        raise FileNotFoundError(f"Prepared Wolf data directory is missing: {report.data_dir}")
    if not (report.wolftl_output_dir / "dump").is_dir():
        raise FileNotFoundError(f"Prepared WolfTL dump is missing: {report.wolftl_output_dir / 'dump'}")
    return report


@dataclass(frozen=True, slots=True)
class ProcessResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


def _looks_like_unpacked_data(data_dir: Path) -> bool:
    if not data_dir.is_dir():
        return False
    names = {child.name for child in data_dir.iterdir()}
    if {"BasicData", "MapData", "SystemFile"}.intersection(names):
        return True
    return any(child.suffix.lower() in {".dat", ".mps"} for child in data_dir.rglob("*") if child.is_file())


def _copy_data_dir(source: Path, target: Path) -> Path:
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    return target


def _attempt_from_wolftl(
    method: str,
    data_dir: Path,
    wolftl_output_dir: Path,
    result: WolfTLRunResult,
) -> UnpackAttempt:
    return UnpackAttempt(
        method=method,
        ok=result.ok,
        data_dir=str(data_dir),
        wolftl_output_dir=str(wolftl_output_dir),
        message="WolfTL create succeeded." if result.ok else "WolfTL create failed.",
        command=result.command,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _run_uberwolf(*, uberwolf_path: Path, game_path: Path, output_dir: Path) -> ProcessResult:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    command_variants = [
        [str(uberwolf_path), str(game_path), str(output_dir)],
        [str(uberwolf_path), "-i", str(game_path), "-o", str(output_dir)],
        [str(uberwolf_path), "extract", str(game_path), str(output_dir)],
    ]
    last_result: ProcessResult | None = None
    for command in command_variants:
        last_result = _run_process(command, cwd=output_dir)
        if last_result.returncode == 0 and _find_data_dir(output_dir) is not None:
            return last_result
    if last_result is None:
        raise RuntimeError("No UberWolf command variants were attempted")
    return last_result


def _run_wolfdec(*, wolfdec_path: Path, wolf_archives: list[Path], output_dir: Path) -> ProcessResult:
    staged_archives: list[Path] = []
    for archive in wolf_archives:
        staged = output_dir / archive.name
        shutil.copy2(archive, staged)
        staged_archives.append(staged)
    command = [str(wolfdec_path), *(str(path) for path in staged_archives)]
    return _run_process(command, cwd=output_dir)


def _run_process(command: list[str], *, cwd: Path) -> ProcessResult:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    return ProcessResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _find_data_dir(root: Path) -> Path | None:
    candidates = [root / DATA_DIR_NAME, root]
    candidates.extend(path for path in root.rglob(DATA_DIR_NAME) if path.is_dir())
    for candidate in candidates:
        if _looks_like_unpacked_data(candidate):
            return candidate
    return None


def _promote_successful_attempt(source_output_dir: Path, target_output_dir: Path) -> None:
    if target_output_dir.exists():
        shutil.rmtree(target_output_dir)
    shutil.copytree(source_output_dir, target_output_dir)


def _write_prepare_report(result: PrepareGameResult) -> None:
    report_path = result.workspace_dir / PREPARE_REPORT_NAME
    payload = {
        "ok": result.ok,
        "game_title": result.game_title,
        "workspace_dir": str(result.workspace_dir),
        "data_dir": str(result.data_dir) if result.data_dir is not None else "",
        "wolftl_output_dir": str(result.wolftl_output_dir) if result.wolftl_output_dir is not None else "",
        "dump_dir": str(result.dump_dir) if result.dump_dir is not None else "",
        "message": result.message,
        "attempts": [
            {
                "method": attempt.method,
                "ok": attempt.ok,
                "data_dir": attempt.data_dir,
                "wolftl_output_dir": attempt.wolftl_output_dir,
                "message": attempt.message,
                "command": attempt.command,
                "returncode": attempt.returncode,
                "stdout": attempt.stdout,
                "stderr": attempt.stderr,
            }
            for attempt in result.attempts
        ],
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


__all__ = [
    "DATA_DIR_NAME",
    "PREPARE_REPORT_NAME",
    "PrepareGameResult",
    "UnpackAttempt",
    "load_prepare_report",
    "prepare_wolf_game",
    "require_prepared_wolf_game",
]
