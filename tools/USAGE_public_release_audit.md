# Public Release Hygiene Audit (v2) - 使用说明

## 你遇到的两个报错，对应修复点
1) `re.error: missing ), unterminated subpattern`  
   - 原因：旧版 absolute_path_regexes 过于脆弱，某些环境/编辑器改动后容易丢反斜杠导致正则失效。  
   - 处理：v2 已将绝对路径正则简化（无需复杂转义），并且正则编译失败会降级为 INFO，不再崩溃。

2) `run_public_release_audit.cmd` 运行时把注释当命令执行  
   - 原因：cmd.exe 对非 ASCII 内容/编码很敏感（尤其带中文注释时）。  
   - 处理：v2 的 .cmd 包装器使用 ASCII-only 内容，避免编码导致的误解析。

## 放置位置
- `tools/check_public_release_hygiene.py`
- `tools/run_public_release_audit.cmd`（可选）
- `public_release_check_config.json`（可选）
- `USAGE_public_release_audit.md`（本说明）

## 运行（推荐）
```bat
cd <REPO_ROOT>
python tools\check_public_release_hygiene.py --repo . --history 0
```

或使用包装器：
```bat
tools\run_public_release_audit.cmd
```

## 需要检查历史时（更慢）
```bat
python tools\check_public_release_hygiene.py --repo . --history 1 --max-history-lines 200000
```

## 输出
- 默认输出到：`%USERPROFILE%\Desktop\public_release_hygiene_report_YYYYMMDD_HHMMSS.md`
- 若桌面不存在，回退到 home；再失败回退到仓库根目录。

## 退出码
- 0：未发现 HIGH
- 2：发现 HIGH（适合 CI 门禁）
