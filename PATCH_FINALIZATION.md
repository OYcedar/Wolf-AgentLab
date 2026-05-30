# Wolf Patch Finalization

`make-patch` 生成的补丁目录是检查用中间产物。最终发布前，固定再打成双层加密 7z 包。

## 命令

```bat
G:\wolf\finalize-patch-package.bat "G:\wolf\patches\<补丁目录>"
```

默认密码：`sstm`

输出文件：

```text
G:\wolf\patches\<补丁目录>_汉化补丁_双层加密.7z
```

## 规则

- 使用两层 7z。
- 两层都启用密码。
- 两层都启用文件名加密。
- 打包后执行 `7z t` 验证。
- 不把 `workspace`、存档、原始解包素材、调试截图、测试日志或未修改的大封包放进发布包。
