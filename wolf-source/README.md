# A.T.T Wolf

面向 Wolf RPG Editor 游戏的 Agent 翻译闭环工具。它基于 A.T.T 工具链的注册游戏、工作区、术语、LLM 分批翻译、质量检查、写回和补丁打包流程改造，但主流程不依赖现成 `.trans` 文件。

## 目录布局

- `G:\wolf\wolf-source`：工具源码。
- `G:\wolf\game`：待翻译 Wolf 游戏。
- `G:\wolf\workspace`：每个游戏的解包、WolfTL dump、翻译缓存和质量报告。
- `G:\wolf\patches`：输出的独立汉化补丁。
- `G:\wolf\tools`：放 `WolfTL.exe`、`UberWolf.exe`、`WolfDec.exe`，并随仓库固定高版本 WOLF Pro 目录 `wolf-runtime-pro` 和免费版目录 `wolf-runtime`。

工具路径也可以写入 `setting.toml` 的 `[wolf_tools]`，或通过环境变量 `ATT_WOLF_WOLFTL_PATH`、`ATT_WOLF_UBERWOLF_PATH`、`ATT_WOLF_WOLFDEC_PATH`、`ATT_WOLF_RUNTIME_DIR` 指定。

仓库内置的 `G:\wolf\tools\wolf-runtime-pro` 固定为 WOLF RPG Editor Pro `3.595.2025.503`，这是默认优先使用的转换/运行基底。`G:\wolf\tools\wolf-runtime` 另保留 WOLF RPG Editor `v3.703 mini` 作为 fallback。也可以用 `wolf_runtime_dir` 或 `ATT_WOLF_RUNTIME_DIR` 指向其他含 `EditorPro.exe` / `GamePro.exe` 的目录。

## 主流程

```powershell
uv run python main.py --agent-mode doctor --no-check-llm --json
uv run python main.py --agent-mode add-game --path "G:\wolf\game\<游戏目录>" --json
uv run python main.py --agent-mode prepare-game --game "<游戏标题>" --json
uv run python main.py --agent-mode dump-text --game "<游戏标题>" --json
uv run python main.py --agent-mode prepare-agent-workspace --game "<游戏标题>" --output-dir "G:\wolf\workspace\<游戏标题>\agent" --json
uv run python main.py --agent-mode translate --game "<游戏标题>" --max-batches 1 --json
uv run python main.py --agent-mode translation-status --game "<游戏标题>" --json
uv run python main.py --agent-mode quality-report --game "<游戏标题>" --json
uv run python main.py --agent-mode audit-runtime --game "<游戏标题>" --json
uv run python main.py --agent-mode restore-runtime --game "<游戏标题>" --json
uv run python main.py --agent-mode write-back --game "<游戏标题>" --json
uv run python main.py --agent-mode make-patch --game "<游戏标题>" --json
```

`write-back` 对 Wolf 游戏执行成功后会自动同步 `G:\wolf\patches\<游戏标题>`。原则是任何写入游戏目录的 `Data` 更新都必须同时反映到 patch；需要手工修复文件时，修完 `game` 后立刻运行 `make-patch`，不要只改其中一个目录。

一键入口在 `G:\wolf`：

```powershell
G:\wolf\att-wolf-auto.bat -GamePath "G:\wolf\game\<游戏目录>" -MaxBatches 1
```

默认流程只做准备和小批量试译，不写回游戏目录。完整翻译和写回必须显式打开：

```powershell
G:\wolf\att-wolf-auto.bat -GameTitle "<游戏标题>" -RunFullTranslation
G:\wolf\att-wolf-auto.bat -GameTitle "<游戏标题>" -RunFullTranslation -WriteBack
```

只准备工作区、不调用翻译和写回：

```powershell
G:\wolf\att-wolf-auto.bat -GamePath "G:\wolf\game\<游戏目录>" -PrepareOnly
```

## 解包策略

建议使用干净游戏本体。已经被其他运行时翻译工具注入过的游戏，先换回原版再注册。

`prepare-game` 会先检查游戏是否已经有明文 `Data`。如果有，就复制到工作区并立即运行 `WolfTL create` 验证。

如果游戏只有 `.wolf` 包：

1. 优先用 `UberWolf` 解包。
2. 解包后立刻运行 `WolfTL create`。
3. 如果 WolfTL 解析 UberWolf 结果失败，自动改用 `WolfDec` 解包。
4. WolfDec 后再次运行 `WolfTL create`。
5. 如果仍失败，命令返回失败 JSON，并在工作区写入 `prepare_report.json`，该游戏放弃自动翻译。

如果游戏目录下仍存在 `.wolf` 包，`doctor` / `quality-report` 会提示；`write-back` 会阻止直接写回。请先把 `.wolf` 包移动到游戏目录外，避免游戏继续读取封包而不是补丁后的 `Data`。

`doctor` 会尝试读取 `GamePro.exe` / `Game.exe` 的文件版本。版本不低于 `3.595` 时会给出兼容性风险提示。

## Pro 转换固定流程

老版 Wolf 游戏不能把 WolfDec 解出的明文 `Data` 直接交给旧 `Game.exe` 运行。标准流程必须是：

1. 用原版 `Data.wolf` 重新解包出干净 `Data`。
2. 把 `Data.wolf` 移出游戏目录，确保目录内不再有 `.wolf`。
3. 优先从 `G:\wolf\tools\wolf-runtime-pro` 复制高版本 `GamePro.exe` / `EditorPro.exe`；必要时再使用 `wolf-runtime` 的 `Game.exe` / `Editor.exe` fallback。之后一律用高版本运行器启动。
4. 打开对应的高版本编辑器（`Editor.exe` 或 `EditorPro.exe`），依次确认风险提示、备份提示、开始转换提示，直到 `Backup_Before_Ver3\ConvertLog.txt` 出现并记录 `変換OK`。
5. 转换完成后必须重新运行 WolfTL create，以“转换后的 Data”作为新的 dump 基底。
6. 再把数据库里的译文写入这个新 dump，然后 WolfTL patch 回转换后的 `Data`。

不要把“转换前 dump”直接 patch 到“转换后 Data”。转换会覆盖旧写入，或者让 WolfTL 因结构差异静默不落盘。

数据库写回默认只写安全字段。`types/*/fields/*`、`types/*/name`、`types/*/description` 等数据库结构名保持日文原样；这些名字经常被公共事件当运行键使用，翻译后会触发 `data name does not exist` 或 `Data field name mismatch`。

## Wolf 运行安全

默认不会把这些内容送入正文翻译：

- `SetLabel` / `JumpLabel` 标签。
- `CommonEventByName` 的公共事件名。
- BGM、SE、Picture、CharaChip、MapData 等资源路径。
- 事件名、地图文件名、数据库内部 ID、公共事件参数关键词。
- 纯控制符或运行标记，例如 `\s[9]`、`\cself[...]`、`\self[...]`、`\v[...]`、`\i[...]`、`<管理番号...>`。

`audit-runtime` 会检查已保存译文和已生成的 translated dump；`restore-runtime` 会从原始 dump 恢复危险运行字符串，优先覆盖游戏厅黑屏这类控制流、淡入淡出、图片和公共事件参数风险。

如果写回后仍有运行问题，可以按文件做折半定位：只写入一半 dump/补丁范围测试，问题消失则风险在另一半，逐步缩小到具体公共事件或地图文件。

## Agent 输出文件

`prepare-agent-workspace` 会写出：

- `wolf_text_scope.json`：统一文本索引。
- `wolf_sextractor.json`：SExtractor 风格外部翻译交接文件。
- `wolf_text_map.json`：文本和 dump 位置映射。
- `wolf_runtime_rules_draft.json`：Wolf 默认控制符和运行安全规则草稿。

`wolf_sextractor.json` 只作为外部翻译交接文件。位置、行号、dump 节点和运行风险元数据保存在 `wolf_text_map.json` / `wolf_text_scope.json`，不要混进交给译者或模型的正文 JSON。

## 固定闸门

借鉴 A.T.T 工具链和 `E:\translate` 的稳定流程，att-wolf 固定采用这些闸门：

1. 先 `PrepareOnly`，确认 `wolf_text_scope.json` 和 `wolf_runtime_rules_draft.json` 没有把标签、资源、公共事件参数放进正文翻译。
2. 先 `translate --max-batches 1` 小批量试译，再跑 `translation-status` 和 `audit-runtime`。
3. 全量翻译时用 `translation-status` 追踪 `pending_count`，不要靠肉眼判断是否翻完。
4. 写回前必须先 `restore-runtime`，再让 `quality-report` 和 `audit-runtime` 都通过。
5. 写回后必须重新 `dump-text` 或重新跑一次 WolfTL create，确认补丁后的 Data 仍可解析。
6. 发补丁前做真实游戏窗口 QA：启动、标题菜单、开始、读档/存档、选择项、小游戏、跳过、CG/回想、BGM/黑屏反馈点都要至少走一遍。
7. 发布包只包含汉化变更，不包含 `workspace`、存档、原始素材、调试截图、测试日志或未修改的大封包。

发布打包见 `G:\wolf\PATCH_FINALIZATION.md`。

## 常用命令

| 目的 | 命令 |
| --- | --- |
| 检查环境 | `uv run python main.py --agent-mode doctor --no-check-llm --json` |
| 注册游戏 | `uv run python main.py --agent-mode add-game --path <游戏目录> --json` |
| 准备/解包 | `uv run python main.py --agent-mode prepare-game --game <游戏标题> --json` |
| 重新 dump | `uv run python main.py --agent-mode dump-text --game <游戏标题> --json` |
| 准备 Agent 工作区 | `uv run python main.py --agent-mode prepare-agent-workspace --game <游戏标题> --output-dir <目录> --json` |
| 小批量试译 | `uv run python main.py --agent-mode translate --game <游戏标题> --max-batches 1 --json` |
| 翻译状态 | `uv run python main.py --agent-mode translation-status --game <游戏标题> --json` |
| 质量检查 | `uv run python main.py --agent-mode quality-report --game <游戏标题> --json` |
| 运行风险审计 | `uv run python main.py --agent-mode audit-runtime --game <游戏标题> --json` |
| 恢复危险运行字符串 | `uv run python main.py --agent-mode restore-runtime --game <游戏标题> --json` |
| 写回游戏 Data | `uv run python main.py --agent-mode write-back --game <游戏标题> --json` |
| 生成补丁目录 | `uv run python main.py --agent-mode make-patch --game <游戏标题> --json` |
| 按试玩反馈反查文本 | `uv run python main.py --agent-mode verify-feedback-text --game <游戏标题> --input <反馈清单> --json` |

## 开发测试

```powershell
uv run python -m pytest tests/test_wolf_pipeline.py tests/test_cli_json_output.py::test_parser_commands_have_dispatch_handlers -q
```
