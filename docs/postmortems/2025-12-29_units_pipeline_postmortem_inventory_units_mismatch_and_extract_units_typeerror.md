# 2025-12-29_units_pipeline_postmortem_inventory_units_mismatch_and_extract_units_typeerror.md目录：
- [0. 元信息](#0-元信息)
- [1. 现象与触发](#1-现象与触发)
  - [1.1 validate_rag_units.py 对账失败（inventory>units）](#1-1-validateragunitspy-对账失败-inventoryunits)
  - [1.2 extract_units.py 运行时 TypeError（md refs 解析调用签名不一致）](#1-2-extractunitspy-运行时-typeerror-md-refs-解析调用签名不一致)
- [2. 问题定义](#2-问题定义)
- [3. 关键证据与排查过程](#3-关键证据与排查过程)
  - [3.1 inventory 收录了运行时产物（__pycache__/*.pyc）](#3-1-inventory-收录了运行时产物-__pycache__pyc)
  - [3.2 units 与 inventory 的对齐逻辑为何必然失败](#3-2-units-与-inventory-的对齐逻辑为何必然失败)
  - [3.3 extract_refs_from_md 调用参数与实际签名冲突](#3-3-extractrefsfrommd-调用参数与实际签名冲突)
  - [3.4 profile 执行顺序导致“先失败后暴露第二个错误”](#3-4-profile-执行顺序导致先失败后暴露第二个错误)
- [4. 根因分析（RCA）](#4-根因分析-rca)
  - [4.1 直接根因 A：输入集合定义不稳定](#4-1-直接根因-a输入集合定义不稳定)
  - [4.2 直接根因 B：模块化重构后的函数签名漂移](#4-2-直接根因-b模块化重构后的函数签名漂移)
  - [4.3 促成因素：缺少“口径契约”的单点配置与门禁测试](#4-3-促成因素缺少口径契约的单点配置与门禁测试)
- [5. 修复与处置](#5-修复与处置)
  - [5.1 一次性止血：清理 data_raw 下运行时产物](#5-1-一次性止血清理-dataraw-下运行时产物)
  - [5.2 稳定修复：inventory 阶段统一忽略规则（推荐）](#5-2-稳定修复inventory-阶段统一忽略规则-推荐)
  - [5.3 稳定修复：修正 extract_units 的 md refs 调用](#5-3-稳定修复修正-extractunits-的-md-refs-调用)
  - [5.4 稳定修复：profile 在 inventory 变更时强制重建 units](#5-4-稳定修复profile-在-inventory-变更时强制重建-units)
- [6. 预防与回归测试](#6-预防与回归测试)
- [7. 最小可复现（MRE）](#7-最小可复现-mre)
- [8. 一句话复盘](#8-一句话复盘)


## 0) 元信息

[关键词] inventory.csv, text_units.jsonl, validate_rag_units, extract_units, __pycache__, pyc, schemeB, profile runner, md refs

[阶段] inventory / units / validate / profile

[工具] make_inventory.py, extract_units.py, validate_rag_units.py, tools/run_build_profile.py

[复现] python tools/run_build_profile.py --profile build_profile_schemeB.json（在 data_raw 含 __pycache__/pyc 且 extract_units 存在调用签名错误时）

[验收] validate_rag_units.py 结果 PASS（missing_units_for_inventory=0）且 extract_units.py 可成功生成 units（无 TypeError）


# 本次 Units 阶段失败排查总结（inventory→units 对账失败 + extract_units TypeError）

> 日期：2025-12-29  
> 项目目录：`<REPO_ROOT>
> 虚拟环境：`.venv_rag`  
> 关注点：你已经“删库重跑”，但在进入 chunk/embedding 前，在 **units 校验阶段**与 **md refs 解析阶段**连续失败。


## 1. 现象与触发

### 1.1 validate_rag_units.py 对账失败（inventory>units）

你在 `tools/run_build_profile.py` 的一次运行中先执行了校验：

- `Inventory: ...\inventory.csv (rows=3229)`
- `Units: ...\data_processed\text_units.jsonl (units=3228)`
- `missing_units_for_inventory=1`
- 样例：`data_raw/__pycache__/clean_md_private_use_fiex.cpython-310.pyc`
- 最终：`FAIL (fix the issues above before proceeding to chunking/embedding).`

这说明：inventory 认为它是“需要入库的资料”，但 units 侧并没有（也不应该）为 `.pyc` 生成 unit，因此对账必然失败。

### 1.2 extract_units.py 运行时 TypeError（md refs 解析调用签名不一致）

在下一次运行 profile 时，脚本进入 `extract_units.py`，并在解析 md refs 时抛出：

- `TypeError: extract_refs_from_md() missing 1 required positional argument: 'md_text'`

堆栈显示调用位置在 `src/mhy_ai_rag_data/extract_units.py` 的 `_build_unit_text()` 中：
- `refs = extract_refs_from_md(md_text, project_root=root)`

该错误属于“运行时参数绑定失败”，会阻断 units 的生成，因此即使你修掉了 inventory 噪声，也会卡在 extract_units 阶段。


## 2. 问题定义

本次问题可以拆成两个互相独立但连续触发的门禁失败：

1) **输入集合定义问题**：inventory 扫描口径把 `data_raw/__pycache__/*.pyc` 这种运行时产物当作资料收录，导致 `inventory.csv` 与 `text_units.jsonl` 无法对齐。  
2) **代码回归问题**：模块化重构后，`extract_units.py` 对 `extract_refs_from_md()` 的调用与该函数实际签名不一致，导致运行时 TypeError。

其中第 (1) 属于“数据口径/工程约束”问题；第 (2) 属于“代码接口契约”问题。两者都必须修复，否则 profile 无法稳定进入 chunk/embedding。


## 3. 关键证据与排查过程

### 3.1 inventory 收录了运行时产物（__pycache__/*.pyc）

证据来自 validate 输出的样例问题：
- `sample=['data_raw/__pycache__/...cpython-310.pyc']`

这类文件并非知识资料，而是 Python 运行过程中自动生成的字节码缓存；它会在你执行脚本时被创建/更新，因此**非常容易造成 inventory 行数波动**（你之前观察到“同样资料多次跑第一步数量不同”的现象，与此机制高度一致）。

### 3.2 units 与 inventory 的对齐逻辑为何必然失败

校验器的核心不变量是：
- 对于 inventory 中每一个可处理的源文件，都应该在 units 中存在对应记录；
- 否则 `missing_units_for_inventory > 0` 必然 FAIL。

当 inventory 把 `.pyc` 纳入时，units 生成器通常会忽略该类型（它不是文本资料/媒体资料），于是就形成了“inventory 有、units 无”的差异。这不是抽取器坏了，而是**上游集合定义出了问题**。

### 3.3 extract_refs_from_md 调用参数与实际签名冲突

`TypeError` 的含义非常明确：被调用函数要求一个名为 `md_text` 的位置参数，但调用方并没有按其签名提供。结合你当前调用形式 `extract_refs_from_md(md_text, project_root=root)`，最典型的情况是：

- 实际签名类似 `extract_refs_from_md(md_path, md_text, project_root=...)` 或 `extract_refs_from_md(*, md_text, md_path, project_root=...)`；
- 但调用者只传了一个位置参数，导致 `md_text` 并未被绑定（或被错误绑定到另一个参数），最终抛出缺参异常。

该类问题属于“接口漂移”：重构把函数移动/改参后，上游调用点未同步更新。

### 3.4 profile 执行顺序导致“先失败后暴露第二个错误”

你两次运行 profile 的日志显示：

- 第一次：进入 `validate_rag_units.py` 即 FAIL（因此没有进入 extract_units）。
- 第二次：进入 `extract_units.py`，在 md refs 阶段 FAIL。

这类“先失败掩盖后失败”的现象很常见：修掉第一个门禁后，才会暴露第二个门禁。因此在整改策略上，应当把修复拆成两条独立验收线：
- 先让 `validate_rag_units.py` 对账稳定 PASS；
- 再让 `extract_units.py` 能完整跑完并产出 units；
- 最后再回到 profile 一键跑通。


## 4. 根因分析（RCA）

### 4.1 直接根因 A：输入集合定义不稳定

- `data_raw/` 被当作“原始资料输入目录”，但目录内混入了会随运行自动生成的 `__pycache__/*.pyc`；
- inventory 扫描口径未统一忽略该类路径，导致 inventory 行数与内容随运行波动；
- 进一步导致 units 对账失败，阻断 pipeline。

### 4.2 直接根因 B：模块化重构后的函数签名漂移

- `extract_refs_from_md()` 在重构后具有不同签名；
- `extract_units.py` 调用点未同步更新；
- 运行时抛出 TypeError，阻断 units 生成。

### 4.3 促成因素：缺少“口径契约”的单点配置与门禁测试

- “哪些文件算资料、哪些必须忽略”的规则没有沉淀为单一真相源（例如统一 ignore 列表/配置文件），导致不同阶段各自为政；
- 缺少最小化的接口契约测试（例如 `python -m py_compile` + 一个 `extract_units --dry-run` 的 smoke），导致签名漂移没有在合并时被拦截；
- profile runner 没有做依赖触发（inventory 变化 → 强制重建 units），导致“旧 units + 新 inventory”更容易制造假失败。


## 5. 修复与处置

### 5.1 一次性止血：清理 data_raw 下运行时产物

**动作：**
- 删除：`data_raw/__pycache__/` 目录（以及任何 `.pyc/.pyo` 文件）。
- 然后从头执行：`make_inventory → extract_units → validate_rag_units`。

**为何：**
- 这是最小动作，能立刻把“输入集合波动”因素从资料集中移除，让你继续推进排查与构建。

### 5.2 稳定修复：inventory 阶段统一忽略规则（推荐）

**动作（建议策略）：**
- 在 inventory 生成时默认忽略：
  - 目录：`__pycache__/`
  - 后缀：`.pyc`, `.pyo`
  - 常见临时文件：`*.tmp`, `~$*`, `.DS_Store`, `Thumbs.db`（按你的平台酌情）
- 并把这份规则作为“口径契约”的一部分固化（配置或常量），让 inventory/units/validate 共用同一口径。

**为何：**
- 让“资料集合定义”在最上游稳定下来，后续所有数量指标（units/chunks/count）才具备可复现性。

### 5.3 稳定修复：修正 extract_units 的 md refs 调用

**动作：**
- 根据 `extract_refs_from_md()` 的实际签名，修正调用为“显式命名参数 + 同时传入 md_path 与 md_text”（若签名要求两者）。
- 产物层面保证：md unit 必须产出 refs 字段（如 `asset_refs/doc_refs`），以满足下游校验器。

**为何：**
- 这属于硬错误：不修复无法产出 units，即使输入集合稳定也无法进入 plan/build。

### 5.4 稳定修复：profile 在 inventory 变更时强制重建 units

**动作：**
- profile runner 在运行前比较 `inventory.csv` 与 `text_units.jsonl` 的更新时间（或更稳的内容 hash）：
  - 若 inventory 更新，则强制运行 `extract_units.py` 生成新 units；
  - 避免使用“旧 units”对齐“新 inventory”。

**为何：**
- 这是工程上最常见的成熟做法：把依赖关系显式化，避免人工记忆“哪些中间产物需要重建”，从而让 `run_build_profile` 成为真正可靠的一键入口。


## 6. 预防与回归测试

建议固化以下门禁（至少本地 smoke）：

1) **输入集合门禁**：inventory 生成后，统计“被忽略的噪声文件数量”，并在发现 `__pycache__/pyc` 被纳入时直接 FAIL。  
2) **接口契约门禁**：对关键模块做 `python -m py_compile` + 运行 `extract_units.py --help`（或 `--dry-run`）验证导入与调用链无 TypeError。  
3) **对账门禁**：`validate_rag_units.py` 必须 PASS 才允许进入 chunking/embedding（你现有 profile 已经这样做，建议保持）。  
4) **可复现性门禁**：连续跑两次 `make_inventory` 行数应一致；否则提示“data_raw 仍在变化或含运行时产物”。


## 7. 最小可复现（MRE）

在项目根目录（示意）：

```powershell
# 1) 清理噪声（仅当你确定 data_raw 内没有应保留的运行时文件）
rmdir /s /q data_raw\__pycache__

# 2) 重建 inventory/units 并校验对账
python make_inventory.py
python extract_units.py
python validate_rag_units.py --max-samples 20

# 3) 再跑一键 profile
python tools\run_build_profile.py --profile build_profile_schemeB.json
```

期望：
- validate 输出 `missing_units_for_inventory=0` 且最终 PASS；
- extract_units 无 TypeError；
- profile 能继续进入 plan/build/check 阶段。


## 8. 一句话复盘

- 本次失败不是 Chroma/embedding 的问题，而是 **更上游的输入口径与接口契约**：inventory 错把 `__pycache__/pyc` 纳入资料集导致对账失败，同时 extract_units 对 md refs 的函数调用签名漂移导致 TypeError；修复的成熟路径是“上游统一忽略规则 + 修正调用签名 + profile 显式触发重建”。
