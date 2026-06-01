# Local Wolf Tools

Put local third-party binaries here when running att-wolf:

- `WolfTL.exe`
- `UberWolf.exe`
- `WolfDec.exe`
- `wolf-runtime\Editor.exe` and `wolf-runtime\Game.exe`

These binaries are intentionally not committed. You can also configure their paths in `wolf-source\setting.toml` or through environment variables:

- `ATT_WOLF_WOLFTL_PATH`
- `ATT_WOLF_UBERWOLF_PATH`
- `ATT_WOLF_WOLFDEC_PATH`
- `ATT_WOLF_RUNTIME_DIR`

Install the fixed high-version WOLF runtime/editor package with:

```powershell
Set-Location G:\wolf\wolf-source
.\scripts\install_wolf_runtime.ps1 -Force
```

The default installer downloads WOLF RPG Editor v3.703 mini from the official GitHub Release and extracts it to `G:\wolf\tools\wolf-runtime`.
