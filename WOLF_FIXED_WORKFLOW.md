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
