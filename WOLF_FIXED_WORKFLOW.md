# att-wolf Fixed Workflow

这个文件把当前固定下来的 Wolf 引擎翻译流程写死，来源是 A.T.T 工具链的 CLI 闸门经验和 `E:\translate` 的发布 QA / 交接文件纪律。

## 1. 准备阶段

```powershell
G:\wolf\att-wolf-auto.bat -GamePath "G:\wolf\game\<游戏目录>" -PrepareOnly -SkipLlmCheck
```

检查：

- `G:\wolf\workspace\<游戏标题>\agent\wolf_text_scope.json`
- `G:\wolf\workspace\<游戏标题>\agent\wolf_text_map.json`
- `G:\wolf\workspace\<游戏标题>\agent\wolf_runtime_rules_draft.json`

如果标签、资源路径、公共事件参数、地图名、数据库内部 ID 被列进正文翻译，先修规则，不进入翻译。

## 2. 小批量试译

```powershell
G:\wolf\att-wolf-auto.bat -GameTitle "<游戏标题>" -SmallBatchMaxBatches 1 -SkipLlmCheck
```

固定检查：

```powershell
cd /d G:\wolf\wolf-source
uv run python main.py --agent-mode translation-status --game "<游戏标题>" --json
uv run python main.py --agent-mode audit-runtime --game "<游戏标题>" --json
```

小批量阶段的目标不是翻完，而是确认控制符、称呼、变量、资源名和公共事件参数没有被模型破坏。

## 3. 全量翻译

```powershell
G:\wolf\att-wolf-auto.bat -GameTitle "<游戏标题>" -RunFullTranslation -SkipLlmCheck
```

全量翻译以 `translation-status.summary.pending_count == 0` 为准。不要用文件大小或肉眼抽查判断是否完成。

## 4. 写回闸门

### Pro/Ver3 转换闸门

对老版 Wolf 游戏，写回前必须先完成 Pro 转换：

1. 从原版 `Data.wolf` 解包出干净 `Data`。
2. 把 `Data.wolf` 移到游戏目录外。
3. 复制 `GamePro.exe` / `EditorPro.exe` 到游戏目录。
4. 打开 `EditorPro.exe`，点击 `コンバート(データ変換)`。
5. 依次处理所有确认窗口，包括：
   - Ver3 风险确认。
   - 开始备份确认。
   - 备份完成确认。
   - 开始文件转换确认。
   - 文件转换完成确认。
6. 确认 `Backup_Before_Ver3\ConvertLog.txt` 存在，且没有 `エラー` / `失敗`。
7. 转换结束后重新对当前游戏目录 `Data` 执行 WolfTL create。

只有基于“转换后的 Data dump”写入译文才有效。不要复用转换前 dump 写回；否则会出现游戏能启动但文本仍是日文。

写回前手动确认：

```powershell
cd /d G:\wolf\wolf-source
uv run python main.py --agent-mode restore-runtime --game "<游戏标题>" --json
uv run python main.py --agent-mode quality-report --game "<游戏标题>" --json
uv run python main.py --agent-mode audit-runtime --game "<游戏标题>" --json
```

只有三个命令都通过，才执行：

```powershell
G:\wolf\att-wolf-auto.bat -GameTitle "<游戏标题>" -RunFullTranslation -WriteBack -SkipLlmCheck
```

写回后重新 dump：

```powershell
cd /d G:\wolf\wolf-source
uv run python main.py --agent-mode dump-text --game "<游戏标题>" --json
```

WolfTL 重新解析失败时，不发布补丁。

数据库固定规则：

- 默认不翻译 `types/*/fields/*`、`types/*/name`、`types/*/description`。
- 数据库内部键名和字段名即使可见也先保留原文。
- 若要翻译物品、技能、状态等数据库显示文本，必须走白名单并重新启动游戏验证。
- 如果 WolfTL patch 输出 `Data field name mismatch`，说明数据库结构名被翻译或 dump 基底不一致，必须回滚 DB 结构译文。

## 5. 发布 QA

真实窗口至少验证：

- 启动和标题菜单。
- New Game。
- Load / Save。
- 菜单、道具、技能、状态、设置。
- 选择项和变量名显示。
- 小游戏和特殊演出。
- 跳过/快进。
- CG、回想、额外模式。
- 已知黑屏点、BGM 切换点、淡入淡出点、图片显示点。

截图、日志和临时测试文件留在 `workspace`，不要放进 `patches`。

## 6. 发布包

```bat
G:\wolf\finalize-patch-package.bat "G:\wolf\patches\<补丁目录>"
```

默认密码：`sstm`

发布包不包含：

- `workspace`
- 存档
- 原始解包素材
- 调试截图
- 测试日志
- 未修改的大封包
