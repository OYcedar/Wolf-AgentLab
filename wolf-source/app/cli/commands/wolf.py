"""Wolf-specific CLI commands."""

from __future__ import annotations

import argparse

from app.cli.arguments import read_required_path_arg
from app.cli.reports import write_report_outputs
from app.cli.runtime import resolve_target_game_title
from app.wolf.service import WolfService


async def run_prepare_game_command(args: argparse.Namespace) -> int:
    """Run ``prepare-game`` for a Wolf game."""
    game_title = await resolve_target_game_title(args)
    report = await WolfService().prepare_game(game_title=game_title)
    write_report_outputs(report=report, args=args, title="Wolf 游戏准备报告")
    return 1 if report.status == "error" else 0


async def run_dump_text_command(args: argparse.Namespace) -> int:
    """Run ``dump-text`` for a Wolf game."""
    game_title = await resolve_target_game_title(args)
    report = await WolfService().dump_text(game_title=game_title)
    write_report_outputs(report=report, args=args, title="WolfTL 文本解析报告")
    return 1 if report.status == "error" else 0


async def run_audit_runtime_command(args: argparse.Namespace) -> int:
    """Run ``audit-runtime`` for a Wolf game."""
    game_title = await resolve_target_game_title(args)
    report = await WolfService().audit_runtime(game_title=game_title)
    write_report_outputs(report=report, args=args, title="Wolf 运行风险审计报告")
    return 1 if report.status == "error" else 0


async def run_restore_runtime_command(args: argparse.Namespace) -> int:
    """Run ``restore-runtime`` for a Wolf game."""
    game_title = await resolve_target_game_title(args)
    report = await WolfService().restore_runtime(game_title=game_title)
    write_report_outputs(report=report, args=args, title="Wolf 运行字符串恢复报告")
    return 1 if report.status == "error" else 0


async def run_make_patch_command(args: argparse.Namespace) -> int:
    """Run ``make-patch`` for a Wolf game."""
    game_title = await resolve_target_game_title(args)
    report = await WolfService().make_patch(game_title=game_title)
    write_report_outputs(report=report, args=args, title="Wolf 补丁生成报告")
    return 1 if report.status == "error" else 0


async def run_wolf_prepare_agent_workspace_command(args: argparse.Namespace) -> int:
    """Prepare a lightweight Wolf agent workspace."""
    game_title = await resolve_target_game_title(args)
    output_dir = read_required_path_arg(args, "output_dir")
    report = await WolfService().prepare_agent_workspace(game_title=game_title, output_dir=output_dir)
    write_report_outputs(report=report, args=args, title="Wolf Agent 工作区准备报告")
    return 1 if report.status == "error" else 0


async def run_wolf_quality_report_command(args: argparse.Namespace) -> int:
    """Run Wolf quality report."""
    game_title = await resolve_target_game_title(args)
    report = await WolfService().quality_report(game_title=game_title)
    write_report_outputs(report=report, args=args, title="Wolf 翻译质量报告")
    return 1 if report.status == "error" else 0


async def run_wolf_verify_feedback_text_command(args: argparse.Namespace) -> int:
    """Run Wolf feedback text lookup."""
    game_title = await resolve_target_game_title(args)
    input_path = read_required_path_arg(args, "input")
    report = await WolfService().verify_feedback_text(game_title=game_title, input_path=input_path)
    write_report_outputs(report=report, args=args, title="Wolf 反馈文本反查报告")
    return 1 if report.status == "error" else 0


__all__ = [
    "run_audit_runtime_command",
    "run_dump_text_command",
    "run_make_patch_command",
    "run_prepare_game_command",
    "run_restore_runtime_command",
    "run_wolf_prepare_agent_workspace_command",
    "run_wolf_quality_report_command",
    "run_wolf_verify_feedback_text_command",
]
