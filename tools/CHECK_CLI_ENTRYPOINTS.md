# check_cli_entrypoints 使用说明


## 目的

在 Windows 多环境/多设备场景下，快速定位并门禁常见问题：

- `rag-make-inventory` / `rag-inventory` “命令找不到”
- venv 已激活但 PATH 未生效（或 shell 未刷新）
- 包装已安装但 console_scripts 入口点缺失（安装到别的 Python/别的 venv）
- 项目升级后入口点改名（旧设备仍是旧版本）

该脚本属于 **关键不变量 + 高频复用 + 人工不可靠** 的交叉区，适合固化为一键验收的前置检查。

## 放置位置

- `tools/check_cli_entrypoints.py`

## 运行方式

在项目根目录执行：

```powershell
python tools/check_cli_entrypoints.py
```

## 输出解释

脚本会输出四类信息：

1) `sys.executable`：当前 shell 实际使用的 Python 解释器路径  
2) `scripts_dir`：理论上 rag-*.exe/rg-*.exe 等 wrapper 所在目录（Windows venv 通常是 `.venv_rag\Scripts`）  
3) `entrypoints (metadata)`：从已安装包元数据读取到的 `console_scripts` 列表（以 `rag-` 开头）  
4) `wrappers in scripts_dir`：在 scripts_dir 下实际存在的 `rag-*.exe/.cmd/.bat` 文件

### PASS 典型形态

- metadata 中能看到 `rag-extract-units`、`rag-validate-units`
- inventory 命令能看到：`rag-inventory`
- scripts_dir on PATH: YES

### FAIL 常见原因与修复

1) **baseline entrypoints missing**
   - 现象：metadata 中没有 `rag-extract-units` 等
   - 原因：包没装到这个 venv，或装的是旧版本（入口点尚未定义）
   - 修复：
     ```powershell
     python -m pip install -e .
     # 或者先卸载再装
     python -m pip uninstall -y mhy-ai-rag-data
     python -m pip install -e .
     ```

2) **no inventory CLI found**
   - 现象：metadata 有其他 rag-*，但没有 `rag-inventory` / `rag-make-inventory`
   - 原因：入口点名称变更/未发布到该设备所装版本
   - 修复：升级到与你主力机器一致的仓库版本后重新 `pip install -e .`；并以 `python -c` 打印 entrypoints 作为证据。

3) **scripts_dir is not on PATH**
   - 现象：metadata 有，scripts_dir 下也有 exe，但 shell 运行仍提示命令找不到
   - 原因：shell 进程 PATH 没刷新或 venv 未真正激活（仅仅看到提示符不等价于 PATH 已更新）
   - 修复：关闭当前终端，重新打开再激活 venv；或直接用绝对路径运行 scripts_dir 下的 exe 验证。

## 推荐挂载点（工程化）

建议把该脚本放入你的一键检查入口（例如 `rag-check-all` 或 `tools/run_build_profile.py` 的 preflight）中，位于所有 pipeline 阶段之前。
