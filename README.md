# Wolf AgentLab

Wolf AgentLab is a local Windows workflow for translating Wolf RPG Editor games with an Agent-driven pipeline.

The project is built around `att-wolf`, a CLI adapted from the A.T.T tooling line. It does not depend on existing `.trans` files. The normal flow is:

1. Register a Wolf game.
2. Prepare and unpack `Data` with UberWolf/WolfDec fallback.
3. Dump text through WolfTL.
4. Build a stable text index.
5. Translate with LLM batches.
6. Audit and restore runtime-sensitive strings.
7. Patch back through WolfTL.
8. Generate and finalize a clean patch package.

## Repository Layout

```text
.
├── wolf-source/              # Python/Rust source for att-wolf
├── scripts/                  # repository-level packaging helpers
├── game/                     # local input games, ignored by git
├── workspace/                # generated workspace, ignored by git
├── patches/                  # generated patch output, ignored by git
├── tools/                    # local WolfTL/UberWolf/WolfDec binaries, ignored by git
├── att-wolf-auto.bat         # Windows entry point
├── att-wolf-wizard.ps1       # safe workflow wizard
├── WOLF_FIXED_WORKFLOW.md    # fixed production workflow
└── PATCH_FINALIZATION.md     # release package finalization rules
```

## Requirements

- Windows
- Python 3.14
- uv
- Rust stable and MSVC build tools, for the native extension
- WolfTL.exe
- UberWolf.exe, optional but preferred
- WolfDec.exe, fallback unpacker
- An OpenAI-compatible model endpoint

Tool paths can be configured in `wolf-source\setting.toml`, through environment variables, or by placing binaries in `G:\wolf\tools`.

Environment variables:

- `ATT_WOLF_WOLFTL_PATH`
- `ATT_WOLF_UBERWOLF_PATH`
- `ATT_WOLF_WOLFDEC_PATH`

## Quick Start

```powershell
cd G:\wolf\wolf-source
uv sync --locked --dev
uv run maturin develop --release
uv run att-wolf --agent-mode doctor --no-check-llm --json
```

Prepare a game without translating or writing back:

```powershell
G:\wolf\att-wolf-auto.bat -GamePath "G:\wolf\game\<game-dir>" -PrepareOnly -SkipLlmCheck
```

Run a one-batch smoke translation:

```powershell
G:\wolf\att-wolf-auto.bat -GameTitle "<game-title>" -SmallBatchMaxBatches 1 -SkipLlmCheck
```

Run full translation without write-back:

```powershell
G:\wolf\att-wolf-auto.bat -GameTitle "<game-title>" -RunFullTranslation -SkipLlmCheck
```

Write back only after all quality gates pass:

```powershell
G:\wolf\att-wolf-auto.bat -GameTitle "<game-title>" -RunFullTranslation -WriteBack -SkipLlmCheck
```

## Safety Gates

The wizard intentionally does not write back by default.

Before write-back, the workflow runs or expects:

- `translation-status` with no pending text.
- `restore-runtime`.
- `quality-report`.
- `audit-runtime`.
- WolfTL re-dump after patching.
- Real game-window QA before release.

Runtime-sensitive strings are protected by default, including labels, common-event names, resource paths, map references, database internal IDs, common-event parameter keywords, and control tokens such as `\s[9]`, `\cself[...]`, `\self[...]`, `\v[...]`, `\i[...]`, and `<管理番号...>`.

## Development Checks

```powershell
cd G:\wolf\wolf-source
uv run python -m pytest tests/test_wolf_pipeline.py tests/test_cli_json_output.py::test_parser_commands_have_dispatch_handlers -q
uv run python -m compileall app
```

## Release Package

After `make-patch`, finalize the patch directory:

```bat
G:\wolf\finalize-patch-package.bat "G:\wolf\patches\<patch-dir>"
```

Default password: `sstm`

See `WOLF_FIXED_WORKFLOW.md` and `PATCH_FINALIZATION.md` for the fixed production process.
