"""Agent 临时工作区命令。

本模块负责准备、校验和清理供外部 Agent 使用的规则分析工作区。
"""

from __future__ import annotations

import argparse

from app.agent_toolkit import AgentToolkitService
from app.cli.arguments import read_int_set_arg, read_required_path_arg
from app.cli.runtime import resolve_target_game_title
from app.cli.reports import build_sampled_stdout_report, write_report_outputs
from app.persistence import GameRegistry
from app.cli.commands.wolf import run_wolf_prepare_agent_workspace_command


async def run_prepare_agent_workspace_command(args: argparse.Namespace) -> int:
    """执行 `prepare-agent-workspace` 命令。"""
    game_title = await resolve_target_game_title(args)
    async with await GameRegistry().open_game(game_title) as session:
        if session.engine_kind == "wolf":
            return await run_wolf_prepare_agent_workspace_command(args)
    output_dir = read_required_path_arg(args, "output_dir")
    command_codes = read_int_set_arg(args, "codes")
    service = AgentToolkitService()
    report = await service.prepare_agent_workspace(
        game_title=game_title,
        output_dir=output_dir,
        command_codes=command_codes,
    )
    write_report_outputs(report=report, args=args, title="Agent 工作区准备报告")
    return 1 if report.status == "error" else 0


async def run_validate_agent_workspace_command(args: argparse.Namespace) -> int:
    """执行 `validate-agent-workspace` 命令。"""
    game_title = await resolve_target_game_title(args)
    workspace = read_required_path_arg(args, "workspace")
    service = AgentToolkitService()
    report = await service.validate_agent_workspace(game_title=game_title, workspace=workspace)
    write_report_outputs(
        report=report,
        args=args,
        title="Agent 工作区校验报告",
        stdout_report=build_sampled_stdout_report(report),
    )
    return 1 if report.status == "error" else 0


async def run_cleanup_agent_workspace_command(args: argparse.Namespace) -> int:
    """执行 `cleanup-agent-workspace` 命令。"""
    workspace = read_required_path_arg(args, "workspace")
    service = AgentToolkitService()
    report = await service.cleanup_agent_workspace(workspace=workspace)
    write_report_outputs(report=report, args=args, title="Agent 工作区清理报告")
    return 1 if report.status == "error" else 0
