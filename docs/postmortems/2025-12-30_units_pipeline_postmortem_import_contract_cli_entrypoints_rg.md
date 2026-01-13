# 2025-12-30_units_pipeline_postmortem_import_contract_cli_entrypoints_rg.md目录：


- [2025-12-30\_units\_pipeline\_postmortem\_import\_contract\_cli\_entrypoints\_rg.md目录：](#2025-12-30_units_pipeline_postmortem_import_contract_cli_entrypoints_rgmd目录)
  - [0) 元信息](#0-元信息)
- [本次问题排查总结（导入漂移 + 重构契约漂移 + 工具链 PATH 分叉）](#本次问题排查总结导入漂移--重构契约漂移--工具链-path-分叉)
  - [1. 现象与触发](#1-现象与触发)
    - [1.1 make\_inventory.py 报 ModuleNotFoundError（mhy\_ai\_rag\_data）](#11-make_inventorypy-报-modulenotfounderrormhy_ai_rag_data)
    - [1.2 rag-extract-units 报 TypeError（md refs 调用签名不一致）](#12-rag-extract-units-报-typeerrormd-refs-调用签名不一致)
    - [1.3 rg 安装后 where rg 路径与预期不一致](#13-rg-安装后-where-rg-路径与预期不一致)
    - [1.4 另一台设备 rag-\* “命令找不到”但实际是输入错误](#14-另一台设备-rag--命令找不到但实际是输入错误)
  - [2. 问题定义](#2-问题定义)
  - [3. 关键证据与排查过程](#3-关键证据与排查过程)
    - [3.1 src-layout + 未在当前解释器安装导致 import 失败](#31-src-layout--未在当前解释器安装导致-import-失败)
    - [3.2 extract\_refs\_from\_md 的签名与调用点不匹配](#32-extract_refs_from_md-的签名与调用点不匹配)
    - [3.3 where/Path 优先级导致命中 WinGet 版本 rg.exe](#33-wherepath-优先级导致命中-winget-版本-rgexe)
    - [3.4 多设备下命令名依赖记忆导致误判](#34-多设备下命令名依赖记忆导致误判)
  - [4. 根因分析（RCA）](#4-根因分析rca)
    - [4.1 直接根因 A：Packaging/解释器一致性未门禁化](#41-直接根因-apackaging解释器一致性未门禁化)
    - [4.2 直接根因 B：重构后缺少“接口契约门禁”](#42-直接根因-b重构后缺少接口契约门禁)
    - [4.3 直接根因 C：工具链多来源并存缺少“可达性证据链”](#43-直接根因-c工具链多来源并存缺少可达性证据链)
    - [4.4 设计阶段的遗漏：最初构思为什么没覆盖这次问题](#44-设计阶段的遗漏最初构思为什么没覆盖这次问题)
  - [5. 修复与处置](#5-修复与处置)
    - [5.1 止血：用 editable install 固化导入路径](#51-止血用-editable-install-固化导入路径)
    - [5.2 稳定修复：修正 extract\_units 中 md refs 调用为关键字参数](#52-稳定修复修正-extract_units-中-md-refs-调用为关键字参数)
    - [5.3 稳定修复：新增 contract gate（md\_refs 契约门禁）](#53-稳定修复新增-contract-gatemd_refs-契约门禁)
    - [5.4 稳定修复：新增 CLI entrypoints gate（rag-\* 入口点门禁）](#54-稳定修复新增-cli-entrypoints-gaterag--入口点门禁)
    - [5.5 工具链处置：rg 安装策略与 PATH 顺序管理](#55-工具链处置rg-安装策略与-path-顺序管理)
  - [6. 预防与回归测试](#6-预防与回归测试)
    - [6.1 重构后必须执行的门禁清单（建议固化到 rag-check-all）](#61-重构后必须执行的门禁清单建议固化到-rag-check-all)
    - [6.2 多设备/多 venv 稳定操作规程](#62-多设备多-venv-稳定操作规程)
    - [6.3 “写检测脚本时”应该优先覆盖哪些维度](#63-写检测脚本时应该优先覆盖哪些维度)
  - [7. 最小可复现（MRE）](#7-最小可复现mre)
    - [MRE-1：导入漂移](#mre-1导入漂移)


## 0) 元信息

[关键词] src-layout, editable install, import drift, console_scripts, entrypoints, TypeError, signature drift, md refs, ripgrep, winget, PATH

[阶段] packaging / units / tools / docs

[工具] python -m pip install -e . / pip install -e \".[ci]\"（跑门禁+pytest）/ pip install -e \".[embed]\"（仅 Stage-2：embedding/chroma）, rag-extract-units, make_inventory.py, src/mhy_ai_rag_data/extract_units.py, tools/check_md_refs_contract.py, tools/check_cli_entrypoints.py, pytest -q

[复现]
- `python make_inventory.py` → `ModuleNotFoundError: No module named 'mhy_ai_rag_data'`
- `rag-extract-units --root .` → `TypeError: extract_refs_from_md() missing 1 required positional argument: 'md_text'`
- `where rg` → 命中 WinGet Packages 路径而非 <REPO_ROOT>
- 另一台设备 `rag-make-inventory` “命令找不到” → 最终确认是命令输入错误（非安装缺失）

[验收]
- `python -m pip install -e .` 后：`python -c "import mhy_ai_rag_data; print(mhy_ai_rag_data.__file__)"` 可输出路径
- `python tools/check_md_refs_contract.py` PASS（签名+调用点+smoke）
- `python tools/check_cli_entrypoints.py` PASS（entrypoints+Scripts+PATH）
- `rag-extract-units --root .` 不再抛 TypeError
- `pip install -e ".[ci]"` 后：`python tools/check_cli_entrypoints.py` PASS（scripts_dir on PATH: YES；rag-* 可达）
- `pytest -q` PASS（最小轻集成：1 passed）
- 通过证据（终端输出摘录）：

  ```text
  [INFO] scripts_dir on PATH: YES
  [PASS] rag-* entrypoints appear installed and reachable

  (.venv_ci) <REPO_ROOT>>pytest -q
  .
  1 passed in 1.33s
  ```
- （可选）若需要跑 embedding/chroma：再执行 `pip install -e ".[embed]"`；PR/轻量门禁阶段不强制


# 本次问题排查总结（导入漂移 + 重构契约漂移 + 工具链 PATH 分叉）

> 日期：2025-12-30  
> 背景：在“删库重跑/跨设备运行/重构后再跑”的组合场景中，出现了导入失败、运行时 TypeError、工具链命中路径不一致等问题。  
> 目标：把这些问题从“跑到中段才炸”前移到“启动前门禁即可拦截”。


## 1. 现象与触发

### 1.1 make_inventory.py 报 ModuleNotFoundError（mhy_ai_rag_data）

- [Fact] 报错：`ModuleNotFoundError: No module named 'mhy_ai_rag_data'`，发生于 `make_inventory.py` 的 `from mhy_ai_rag_data.project_paths import ...`。
- [Fact] VSCode/Pylance 同时出现 `reportMissingImports`（无法解析导入）。
- 影响：inventory 阶段阻断，后续 pipeline 无法推进。

### 1.2 rag-extract-units 报 TypeError（md refs 调用签名不一致）

- [Fact] `rag-extract-units --root .` 进入 `src/mhy_ai_rag_data/extract_units.py` 后抛出：
  `TypeError: extract_refs_from_md() missing 1 required positional argument: 'md_text'`。
- [Fact] 堆栈定位到 `_build_unit_text()` 内调用 `extract_refs_from_md(...)` 的行。
- 影响：units 无法生成，阻断 chunk/embedding 下游。

### 1.3 rg 安装后 where rg 路径与预期不一致

- [Fact] `where rg` 命中 `<REPO_ROOT>
- 影响：排障工具链存在“多来源并存 + PATH 顺序/缓存”不确定性（影响定位效率，不直接影响构建，但会放大排障成本）。

### 1.4 另一台设备 rag-* “命令找不到”但实际是输入错误

- [Fact] 另一台设备报：`'rag-make-inventory' is not recognized...`
- [Fact] 后续确认：是命令输入错误导致的误判（并非 entrypoints 缺失）。
- 影响：暴露“命令名靠记忆/手输”在多设备场景不可控，需要用可验证手段替代。


## 2. 问题定义

本次问题是三条链路分别出现缺口：

1) **Packaging/导入链路缺口**：src-layout 项目如果未在“当前解释器”完成安装（或 VSCode 选择了别的解释器），则导入 `mhy_ai_rag_data` 失败。
2) **接口契约缺口**：重构后，`extract_refs_from_md()` 的实际签名与 `extract_units.py` 调用点不一致，触发运行时 TypeError。
3) **工具链/入口点可达性缺口**：rg 与 rag-* 命令的实际命中取决于 PATH 与 entrypoints 包装器；多设备/多来源情况下，如果没有证据链，很容易误判“没装/坏了/路径错”。


## 3. 关键证据与排查过程

### 3.1 src-layout + 未在当前解释器安装导致 import 失败

- [Fact] `ModuleNotFoundError` 是“解释器 sys.path 未包含包”的直接表现。
- [Inference] 典型原因是：没有在该 venv 执行 `python -m pip install -e .`，或 VSCode 选错解释器。
- [验证方式] 在同一终端执行：
  - `python -c "import sys; print(sys.executable)"`
  - `python -m pip -V`
  - `python -c "import mhy_ai_rag_data; print(mhy_ai_rag_data.__file__)"`
  三者一致且能输出文件路径，则导入链路闭环成立。

### 3.2 extract_refs_from_md 的签名与调用点不匹配

- [Fact] 报错语义明确：函数需要 `md_text`，但调用绑定时缺失。
- [Inference] 位置参数/参数顺序被重构改变后，调用点未更新；属于“接口契约漂移”。
- [验证方式]：
  - `python -c "import inspect; from mhy_ai_rag_data.md_refs import extract_refs_from_md; print(inspect.signature(extract_refs_from_md))"`
  - 与 `extract_units.py` 调用点进行对照，确认是否 `md_path/md_text/project_root` 都被传入（最好是关键字传参）。

### 3.3 where/Path 优先级导致命中 WinGet 版本 rg.exe

- [Fact] `where rg` 会按 PATH 顺序返回最先命中的可执行文件。
- [Inference] 你把 `<REPO_ROOT>
- [验证方式]：
  - 新开终端后再 `where rg`
  - PowerShell 用 `Get-Command rg -All` 查看所有命中来源与顺序。

### 3.4 多设备下命令名依赖记忆导致误判

- [Fact] “命令找不到”既可能是安装问题，也可能是手输错误。
- [Inference] 依赖记忆而非“机器可验证事实”（entrypoints 列表）会在多设备场景频繁误判。
- [验证方式]：用门禁脚本输出“元数据 entrypoints + Scripts 下 wrapper + PATH 可见性”，把问题收敛到唯一类别（或直接排除安装问题）。


## 4. 根因分析（RCA）

### 4.1 直接根因 A：Packaging/解释器一致性未门禁化

- [Fact] 导入失败发生在最上游（inventory）。
- [Inference] 最初的验收更多关注“数据产物对账”（inventory/units/plan/chroma），没有把“解释器一致性/安装状态”作为必经门禁；导致换机器或换 venv 时，问题以 ModuleNotFoundError 的形式出现。

### 4.2 直接根因 B：重构后缺少“接口契约门禁”

- [Fact] 运行时 TypeError 属于契约断裂。
- [Inference] 原验收脚本偏产物门禁，不会主动做 `inspect.signature + bind + smoke`，因此无法在运行前拦截“签名漂移”。

### 4.3 直接根因 C：工具链多来源并存缺少“可达性证据链”

- [Fact] rg 与 rag-* 的实际命中受 PATH 与 wrapper 影响。
- [Inference] 如果不输出“可达性证据链”，就容易把 PATH/刷新/顺序问题误判为安装问题，从而产生不必要的重装/折腾。

### 4.4 设计阶段的遗漏：最初构思为什么没覆盖这次问题

从最初构思出发，验收设计的中心是“资料→向量库”的可审计闭环，因此重点放在：
- 数据口径（inventory/units）
- 产物对账（plan/chroma count）
- 增量同步语义（state/manifest）

但当“重构 + 多设备”出现时，最先暴露的往往是更上游的两层：
- **Packaging 层**（入口点/解释器一致性/导入路径）
- **契约层**（模块 API / 函数签名）

这两层若不做门禁，会出现：产物门禁尚未开始，流程已在更上游爆炸；且错误定位容易被“环境噪声”放大。


## 5. 修复与处置

### 5.1 止血：用 editable install 固化导入路径

- 动作：
  - 激活目标 venv（确保是你要用的那一个）
  - 执行：`python -m pip install -e .`
- 验收：
  - `python -c "import mhy_ai_rag_data; print(mhy_ai_rag_data.__file__)"` 输出为仓库 `src\mhy_ai_rag_data\...` 路径。

### 5.2 稳定修复：修正 extract_units 中 md refs 调用为关键字参数

- 动作：将对 `extract_refs_from_md` 的调用改为关键字传参，显式传入 `md_path` 与 `md_text`（以及 `project_root`）。
- 验收：`rag-extract-units --root .` 不再抛 TypeError，并能生成 units 产物。

### 5.3 稳定修复：新增 contract gate（md_refs 契约门禁）

- 动作：新增 `tools/check_md_refs_contract.py`（签名检查 + 调用点静态检查/禁止位置参数 + 最小 smoke bind），并建议在 PR/CI 阶段作为前置门禁执行。
- 验收：脚本 PASS；若未来重构导致签名/调用点漂移，脚本应 FAIL 且给出原因（在进入 units 生成前）。

### 5.4 稳定修复：新增 CLI entrypoints gate（rag-* 入口点门禁）

- 动作：新增 `tools/check_cli_entrypoints.py`，输出并检查：
  - 元数据 console_scripts 中的 rag-* 列表
  - venv Scripts 下 rag-* wrapper 是否存在
  - Scripts 是否在 PATH（对当前 shell 生效）
- 验收：脚本 PASS；多设备下先跑此脚本，避免把“输入错误/PATH 未刷新”误判为“没安装”。

### 5.5 工具链处置：rg 安装策略与 PATH 顺序管理

- 动作：选择单一权威来源（WinGet 社区源或官方二进制），并保证 PATH 排序与刷新；必要时卸载重复来源或使用 wrapper 固定优先级。
- 验收：新开 shell 后 `where rg` 第一条命中预期路径；`rg --version` 可用。


## 6. 预防与回归测试

### 6.1 重构后必须执行的门禁清单（建议固化到 rag-check-all）

建议每次重构（尤其涉及：移动模块、改函数参数、改 CLI 入口点）后，按顺序执行：

0) `pip install -e ".[ci]"`（确保解释器/依赖集合与 CI 一致；或至少 `pip install -e .`）
1) `python -m py_compile ...`（至少覆盖 src 与 tools 关键脚本）
2) `python tools/check_cli_entrypoints.py`（入口点/脚本生成/PATH/解释器）
3) `python tools/check_md_refs_contract.py`（契约 + 最小 smoke）
4) `rag-extract-units --root .`（关键路径）
5) `rag-validate-units --root .`（对账门禁）
6) `pytest -q`（最小轻集成：tmp_path 样例闭环，避免跑到中段才炸）
7) 再进入 plan/build/chroma 的产物对账门禁

### 6.2 多设备/多 venv 稳定操作规程

- 永远使用 `python -m pip ...`（避免 pip/python 漂移）
- 任何机器第一步打印：`sys.executable` 与 `pip -V`
- 命令名不靠记忆：以 entrypoints 列表/门禁脚本输出为准（防止输入错误或命令改名造成误判）
- 改完 PATH 必须“新开终端”再验证（避免进程缓存造成错觉）

### 6.3 “写检测脚本时”应该优先覆盖哪些维度

按“清晰/准确/必要”原则，优先覆盖能带来最大收益的三类不变量：

- **可达性不变量**：入口点存在、脚本 wrapper 存在、PATH 可见、解释器一致
- **契约不变量**：函数签名/Schema/协议字段能绑定并通过最小 smoke
- **口径不变量**：输入集合定义稳定（忽略规则/白名单），对账逻辑必然 PASS

避免把“概率低/成本高/不可确定性强”的外部波动做成强门禁（例如网络抖动），更适合做“诊断输出”。


## 7. 最小可复现（MRE）

### MRE-1：导入漂移

```powershell
python -c "import mhy_ai_rag_data"
# 若失败：ModuleNotFoundError
python -m pip install -e .
python -c "import mhy_ai_rag_data; print(mhy_ai_rag_data.__file__)"
```