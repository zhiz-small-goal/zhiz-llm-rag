# check_tools_layout_README


目的：把「tools/ 作为入口层（wrapper + repo-only 工具）」与「src/ 作为权威实现层（SSOT）」这一结构约定，固化为可执行的审计检查，避免重构或新增脚本时出现 **双实现漂移**、**同名冲突（import shadowing）**、或 **入口语义不清**。

## 适用场景
- 新增/移动/重命名 `tools/*.py` 后，想快速确认：它是 wrapper 还是 repo-only。
- 你发现 `tools/` 与 `src/mhy_ai_rag_data/tools/` 出现同名文件，担心运行路径解析错误。
- PR/CI Lite 需要一个低成本信号：仓库工具层布局是否被破坏（先 warn，成熟后 fail）。

## 输入/输出
- 输入：仓库根目录下的 `tools/*.py`（默认不递归；可加 `--recursive`）。
- 输出：
  - 控制台摘要（wrappers/repo_only/unknown 数量与样例）。
  - 可选 JSON 报告：你指定 `--out <path>`（相对于仓库根目录）。

## 工具布局契约（本检查执行的规则）

### 1) marker-first：每个 tools 脚本必须显式标记
- wrapper：文件中必须包含 `AUTO-GENERATED WRAPPER`
- repo-only：文件中必须包含 `REPO-ONLY TOOL`
- 未标记：视为 `unknown`，并在 `--mode fail` 下导致失败。


## 与 wrapper 自动生成器的关系（推荐默认使用）
- 本仓库建议 **受管 wrapper 由生成器统一生成**，避免手写模板漂移。
- 生成器脚本：`tools/gen_tools_wrappers.py`（受管清单见 `tools/wrapper_gen_config.json` 的 `managed_wrappers`）
  - CI/门禁校验：`python tools/gen_tools_wrappers.py --check`
  - 刷新/生成（会改文件，需要提交）：`python tools/gen_tools_wrappers.py --write`
- 本检查（check_tools_layout）负责“结构契约”：脚本是否有 marker、是否触发 tools/src 同名冲突等；而生成器负责“内容契约”：wrapper 文件内容是否仍等于标准模板。

迁移建议：
- 先把需要纳入自动生成的入口脚本加入 `tools/wrapper_gen_config.json` 的 `managed_wrappers`（不要手改 wrapper）。
- 生成器 `--check` 先以 warn 运行；当连续多次无差异后，再升级为 CI fail gate。

### 2) SSOT：src/ 的同名 peer 存在时，tools 必须是 wrapper
- 若 `src/mhy_ai_rag_data/tools/<name>.py` 存在，则 `tools/<name>.py` 必须是 wrapper。
- 否则会报告 `name_conflict_tools_vs_src`（高风险：同名导致 import/执行歧义）。

### 3) wrapper sanity（弱启发式，仅警告）
- 若文件标记为 wrapper，但未检测到 `runpy.run_module('mhy_ai_rag_data.tools.*')` 的转发模式，会产生 WARN（不默认阻断）。

## 运行命令

### 1) 迁移期（推荐默认：warn，不阻断）
```cmd
python tools\check_tools_layout.py --mode warn
```

### 2) 严格模式（用于 CI/门禁：fail 会返回退出码 2）
```cmd
python tools\check_tools_layout.py --mode fail
```

### 3) 输出 JSON 报告（便于归档/CI artifact）
```cmd
python tools\check_tools_layout.py --mode warn --out data_processed\build_reports\tools_layout_report.json
```

### 4) 递归扫描（只有在 tools/ 存在子目录时才需要）
```cmd
python tools\check_tools_layout.py --recursive --mode warn
```

## 期望结果
> 退出码约定：遵循项目统一契约（见 docs/REFERENCE.md 的 "3.1 退出码"）：0=PASS/WARN，2=FAIL，3=ERROR（脚本异常/未捕获异常）。

- 无问题：输出 `STATUS: PASS`，退出码 0。
- 有问题：
  - `--mode warn`：输出 `STATUS: WARN`，退出码仍为 0（用于迁移期）。
  - `--mode fail`：输出 `STATUS: FAIL`，退出码 2（用于门禁）。
  - 脚本异常（未捕获异常）：输出 `STATUS: ERROR` 或打印 `[ERROR]`，退出码 3（用于区分异常 vs 门禁失败）。

## 常见失败与处理

1) `unknown_tool_kind`
- 现象：提示某个 `tools/<name>.py` 缺少 marker。
- 原因：新增脚本未按约定声明其角色。
- 处理：在文件头添加 `REPO-ONLY TOOL`（若是仓库内检查/修复工具）或改造成 wrapper 并添加 `AUTO-GENERATED WRAPPER`。

2) `name_conflict_tools_vs_src`
- 现象：提示 `tools/<name>.py` 与 `src/mhy_ai_rag_data/tools/<name>.py` 同名，但 tools 侧不是 wrapper。
- 原因：出现双实现/影子覆盖风险，运行时可能导入或执行到错误版本。
- 处理：将 `tools/<name>.py` 改为 wrapper（转发到 `mhy_ai_rag_data.tools.<name>`），确保 SSOT 在 src。

3) wrapper sanity WARN
- 现象：标记为 wrapper，但未检测到 runpy 转发。
- 原因：wrapper 模板不一致或是手写入口。
- 处理：对齐到项目统一 wrapper 模板（参照现有 `tools/run_eval_rag.py` 等）。
