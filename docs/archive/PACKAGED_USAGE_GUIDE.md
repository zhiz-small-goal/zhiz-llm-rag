# PACKAGED_USAGE_GUIDE（Deprecated）

- 退役日期：2025-12-30
- 原因：该文档与 README/OPERATION_GUIDE/TROUBLESHOOTING 存在大量重复，易漂移；现按 **Diátaxis（按用途分型）** 重构后，权威入口已收敛到文档导航页。
- 当前权威入口：
  - 文档导航：[`docs/INDEX.md`](../INDEX.md)
  - 快速上手（教程）：[`docs/tutorials/01_getting_started.md`](../tutorials/01_getting_started.md)
  - 日常操作（How-to）：[`docs/howto/OPERATION_GUIDE.md`](../howto/OPERATION_GUIDE.md)
  - 排障手册（How-to）：[`docs/howto/TROUBLESHOOTING.md`](../howto/TROUBLESHOOTING.md)
  - 参考与契约（Reference）：[`docs/reference/REFERENCE.md`](../reference/REFERENCE.md)

> 说明：本文件仅保留为历史归档；如与上述入口出现冲突，以权威入口为准。
---
# PACKAGED_USAGE_GUIDE目录：
- [PACKAGED\_USAGE\_GUIDE目录：](#packaged_usage_guide目录)
  - [0) 元信息](#0-元信息)
  - [1) 详细指导（按 Step 组织）](#1-详细指导按-step-组织)
    - [Step 1：结论与适用范围](#step-1结论与适用范围)
    - [Step 2：前置条件与准备](#step-2前置条件与准备)
      - [Step 2.1：确认你在“项目根目录”](#step-21确认你在项目根目录)
      - [Step 2.2：准备 Python 虚拟环境（推荐 .venv\_rag）](#step-22准备-python-虚拟环境推荐-venv_rag)
      - [Step 2.3：安装项目为可编辑包（editable install）](#step-23安装项目为可编辑包editable-install)
      - [Step 2.4：安装完成后的最小验证](#step-24安装完成后的最小验证)
      - [Step 2.5：安装 rg（ripgrep，用于全文检索与快速定位，推荐）](#step-25安装-rgripgrep用于全文检索与快速定位推荐)
    - [Step 3：最短成功路径（建议新手先跑通一次）](#step-3最短成功路径建议新手先跑通一次)
      - [Step 3.1：一键全检（先确认工程结构没问题）](#step-31一键全检先确认工程结构没问题)
      - [Step 3.2：建表 inventory（扫描 data\_raw/ 生成 inventory.csv）](#step-32建表-inventory扫描-data_raw-生成-inventorycsv)
      - [Step 3.3：抽取 units（把多源资料统一成 text\_units.jsonl）](#step-33抽取-units把多源资料统一成-text_unitsjsonl)
      - [Step 3.4：校验 units（确保结构与字段满足下游）](#step-34校验-units确保结构与字段满足下游)
      - [Step 3.5：生成 chunk\_plan（把 expected 变成可计算、可复现的计划）](#step-35生成-chunk_plan把-expected-变成可计算可复现的计划)
      - [Step 3.6：build 入库（建议首次用 reset，跑通后再用 incremental）](#step-36build-入库建议首次用-reset跑通后再用-incremental)
      - [Step 3.7：check 验收（用 plan 驱动 expected）](#step-37check-验收用-plan-驱动-expected)
    - [Step 4：日常使用主线（rag-\* 命令）](#step-4日常使用主线rag--命令)
      - [Step 4.1：建表 inventory（rag-inventory）](#step-41建表-inventoryrag-inventory)
      - [Step 4.2：抽取 units（rag-extract-units）](#step-42抽取-unitsrag-extract-units)
      - [Step 4.3：校验 units（rag-validate-units）](#step-43校验-unitsrag-validate-units)
      - [Step 4.4：生成 chunk\_plan（rag-plan）](#step-44生成-chunk_planrag-plan)
      - [Step 4.5：增量构建入库（rag-build）](#step-45增量构建入库rag-build)
      - [Step 4.6：一致性验收（rag-check）](#step-46一致性验收rag-check)
    - [Step 5：一键全检（rag-check-all）](#step-5一键全检rag-check-all)
    - [Step 6：项目结构与“脚本在哪里”](#step-6项目结构与脚本在哪里)
    - [Step 7：常见问题与稳定排障](#step-7常见问题与稳定排障)
      - [Step 7.1：rag-\* 命令找不到](#step-71rag--命令找不到)
      - [Step 7.2：No module named 'tools' / 导入失败](#step-72no-module-named-tools--导入失败)
      - [Step 7.3：check FAIL：expected != got](#step-73check-failexpected--got)
      - [Step 7.4：inventory 行数不稳定](#step-74inventory-行数不稳定)
    - [Step 8：自检清单](#step-8自检清单)
    - [Step 9：失败模式与处置](#step-9失败模式与处置)
    - [Step 10：最小可复现（MRE）](#step-10最小可复现mre)
  - [2) 替代方案](#2-替代方案)
    - [方案 A：不安装包，只用 wrapper + 统一 `python -m`（最低改动）](#方案-a不安装包只用-wrapper--统一-python--m最低改动)
    - [方案 B：彻底移除 wrapper，只保留 rag-\*（一致性最强）](#方案-b彻底移除-wrapper只保留-rag-一致性最强)

## 0) 元信息
[关键词] src-layout, pyproject.toml, editable install, console_scripts, rag-cli, schemeB, include_media_stub, index_state, incremental sync

[阶段] 安装/运行/验收/排障

[适用] Windows（PowerShell/CMD），Python venv（.venv_rag），Chroma 本地持久化（chroma_db），FlagEmbedding

[权威实现路径] src/mhy_ai_rag_data/**（根目录与 tools/ 下同名脚本仅为 wrapper 兼容层）


## 1) 详细指导（按 Step 组织）
### Step 1：结论与适用范围

本教程覆盖“重构为可安装包（src-layout + pyproject.toml）”后的完整用法：你应当将日常操作固定为 **`pip install -e .` + 使用 `rag-*` 命令**。这样做的核心收益是：入口命令与导入路径由安装过程确定，不再依赖“你从哪里运行脚本、脚本文件放在哪”这种不稳定因素，能显著降低类似 `No module named 'tools'` 的工程性故障。与此同时，仓库仍保留了根目录与 `tools/` 下的同名脚本作为兼容入口（wrapper），用于过渡或应急，但从维护角度应当把它们视为“转发层”，不再在里面堆业务逻辑。

适用范围：如果你在 Windows 上用 PowerShell/CMD，项目中有 `.venv_rag`，并且你要跑的主线是 **inventory → units → plan → build → check**（含 `include_media_stub` 的 SchemeB），这份教程就是你可以直接照抄执行的“稳定路径”。如果你使用的是不同平台（Linux/macOS）或不同嵌入模型/数据库，步骤的思想仍适用，但命令细节需要改路径与设备参数。


### Step 2：前置条件与准备

#### Step 2.1：确认你在“项目根目录”
做什么：打开终端后先 `cd` 到仓库根目录（能看到 `pyproject.toml`、`data_raw/`、`tools/`、`src/` 的那个目录）。这是新手最常见的失败点：很多命令都支持 `--root`，但你如果在错误目录运行，脚本会用相对路径创建/读取 `data_processed/*`，最终表现为“文件找不到”或“生成在奇怪的位置”。建议你把“根目录”当作默认工作目录，并在所有命令里显式写 `--root .`，这样即使以后换机器/换 shell，你也能用同一套命令复现结果。

#### Step 2.2：准备 Python 虚拟环境（推荐 .venv_rag）
做什么：如果你已经有 `.venv_rag`，可以跳过创建；否则建议在根目录创建并使用它。新手常见问题是“多个 Python 环境混用”，导致 `pip install` 装到了 A 环境，运行时却用 B 环境的 python。解决策略是：要么激活 venv，要么始终用“绝对路径 python.exe”执行 pip 与脚本（两者选一即可，避免混搭）。
- 激活（PowerShell 可能受执行策略限制）：`.venv_rag\Scripts\Activate.ps1`
- 不激活（更稳）：直接用 `.\.venv_rag\Scripts\python.exe` 执行所有命令

#### Step 2.3：安装项目为可编辑包（editable install）
做什么：在项目根目录运行：
```powershell
.\.venv_rag\Scripts\python.exe -m pip install -e .
```
为何：`-e` 会把你的源码以“可编辑”方式安装，之后你改 `src/mhy_ai_rag_data/**` 的代码通常立刻生效；同时会生成 `rag-*` 命令入口（console scripts）。这一步是你从“脚本文件路径运行”切换到“稳定 CLI 入口”的关键。注意：如果你修改了 `pyproject.toml`（新增/改了 `rag-*` 入口、或改依赖列表），需要再次执行同一条安装命令以刷新入口点与依赖。

#### Step 2.4：安装完成后的最小验证
做什么：运行以下两条命令确认入口可用：
```powershell
rag-check-all --help
rag-build --help
```
为何：对新手来说，“能输出帮助信息”比“直接跑全流程”更能快速定位问题是入口层还是业务层。如果 `--help` 都失败，优先处理安装/环境/路径；如果 `--help` 成功，才进入数据与构建逻辑排查。注意：如果你没有把 venv Scripts 加到 PATH，可能需要先激活 venv，或用 `.\.venv_rag\Scripts\rag-check-all.exe --help` 这种形式运行（Windows 会生成 .exe shim）。



#### Step 2.5：安装 rg（ripgrep，用于全文检索与快速定位，推荐）

做什么：为你的 Windows 环境安装 `rg`（ripgrep），用于在仓库内快速搜索代码/日志/文档（例如定位 `No module named ...`、找某个参数在哪些脚本出现、排查重复/残留配置）。这一工具不影响构建流程本身，但能显著降低排障成本；因此建议在你第一次跑通 pipeline 之前就装好。

为何：在本项目里，你会频繁做“跨目录检索”（`src/`、`tools/`、`docs/`、`postmortems/`、`data_processed/`）。相比 Windows 自带 `findstr`，ripgrep 的性能、正则能力、glob 过滤与输出可读性更适合工程排障。

关键参数/注意（按推荐顺序给出安装路径，并附代价/限制）：

1) **优先：WinGet 仅使用社区源（避免触发 msstore 条款弹窗）**
   - 安装前确认源：
     ```powershell
     winget source list
     ```
   - 安装（显式指定社区源 `winget`，避免走 `msstore`）：
     ```powershell
     winget install -e --id BurntSushi.ripgrep.MSVC --source winget
     ```
   - 验证：
     ```powershell
     rg --version
     ```
   - 代价/限制：
     - 依赖你的系统已可用 `winget` 且社区源未被策略禁用；
     - 若你执行了会触发 `msstore` 的命令（例如某些环境下的源更新/搜索），仍可能出现“源协议确认”提示；此时要么坚持 `--source winget`，要么直接走下面的“官方二进制”方案。

2) **最可控：从 ripgrep 官方 Releases 下载 Windows 二进制（不依赖任何源协议交互）**
   - 做法（示例目录）：
     0. 下载链接：https://github.com/BurntSushi/ripgrep/releases/tag/15.1.0
     1. 下载 `ripgrep-<version>-x86_64-pc-windows-msvc.zip`（官方 Release 附件）。
     2. 解压得到 `rg.exe`，放到固定工具目录，例如：`<REPO_ROOT>
     3. 将 `<REPO_ROOT>
     4. 新开终端验证：
        ```powershell
        where rg
        rg --version
        ```
   - 代价/限制：
     - 升级需要你手动替换 `rg.exe`（但流程直观、可完全离线、可审计，且不会触发 Store 源协议交互）。

3) **Chocolatey（包管理体验好，但引入其自身的信任/策略模型）**
   - 安装：
     ```powershell
     choco install ripgrep
     rg --version
     ```
   - 代价/限制：
     - 需要先安装 Chocolatey，并遵循其仓库与执行策略；在受管机器上可能受限制。

4) **Scoop（面向开发者的轻量方案）**
   - 安装：
     ```powershell
     scoop install ripgrep
     rg --version
     ```
   - 代价/限制：
     - 需要 Scoop 环境；部分组织策略会限制 PowerShell 脚本执行与外部源。

常用示例（装好后你会高频用到）：
```powershell
# 查某个参数/开关
rg "strict-sync" -n .

# 查导入链路
rg "No module named|reportMissingImports" -n .

# 只查 Python 文件
rg "extract_refs_from_md" -n -g"*.py" src tools
```

### Step 3：最短成功路径（建议新手先跑通一次）

下面是一条“最短能成功验收”的路径：它不追求最省时间，而追求每一步都能观察到产物，且失败时能快速归因。你第一次跑通后，再去优化 batch、GPU、增量同步等性能参数。

#### Step 3.1：一键全检（先确认工程结构没问题）
做什么：
```powershell
rag-check-all --root .
```
为何：它会检查 src-layout 结构、关键模块是否缺失、能否编译、入口模块能否被导入、文档 TOC 头是否存在等。新手最容易“覆盖补丁时漏文件/放错目录”，这一步能把问题从“运行到一半才爆炸”提前到“几秒钟内就 FAIL”。注意：该脚本当前支持 `--root` 与 `--mode fast`（默认 fast），不需要任何额外参数。

#### Step 3.2：建表 inventory（扫描 data_raw/ 生成 inventory.csv）
做什么：
```powershell
rag-inventory --root .
```
为何：inventory 是后续 units 抽取的输入基准，它记录你本次纳入处理的文件清单（路径、类型、大小、时间戳等）。如果 inventory 生成行数异常或波动，后续 units/plan/build 的数量也会跟着波动，因此新手建议把 inventory 的输出作为第一层“输入稳定性”证据保留。注意：若你在同一份资料上多次跑 inventory 行数不同，优先检查：是否有临时文件（下载中的大文件）、是否有路径被忽略规则命中、是否在跑的同时文件仍在变化。

#### Step 3.3：抽取 units（把多源资料统一成 text_units.jsonl）
做什么：
```powershell
rag-extract-units --root .
```
为何：units 是“后续切分 chunk 的原材料”，它把 md / 图片stub / 视频stub 等统一写到一个 JSONL 里，便于后续按同一口径计划与构建。新手最常见错误是“只改了资料但没重跑 extract_units”，导致你以为在用新资料，实际 plan/build 仍在处理旧的 units 文件。注意：你可以把 `data_processed/text_units.jsonl` 当作一个“中间件产物”，每次资料变更后都应当重新生成它。

#### Step 3.4：校验 units（确保结构与字段满足下游）
做什么：
```powershell
rag-validate-units --root .
```
为何：validate 的价值是把“格式错误、字段缺失、空内容过多”等问题在入库前拦截掉。对新手而言，最麻烦的不是某条记录坏了，而是“坏记录进入后续流程后以很远的地方报错”，导致你很难关联回源文件。注意：如果 validate 报错，先修输入与抽取规则，不要直接跳过，否则 plan/build 的统计会出现不可解释的跳变。

#### Step 3.5：生成 chunk_plan（把 expected 变成可计算、可复现的计划）
做什么（示例参数按你当前工程基线）：
```powershell
rag-plan --root . --units data_processed/text_units.jsonl `
  --chunk-chars 1200 --overlap-chars 120 --min-chunk-chars 200 `
  --include-media-stub --out data_processed/chunk_plan.json
```
为何：plan 的产物 `chunk_plan.json` 是你的“验收口径来源”。新手最常犯的错误是手填 expected 或凭感觉判断“应该差不多”，但只要你启用媒体 stub 或调整 chunk 参数，expected 就会变化。用 plan 把 expected 固化下来后，你后续只需要问一件事：build 后 collection.count 是否等于 planned_chunks。注意：plan 与 build 的 chunk 参数、`include_media_stub` 必须一致，否则 check FAIL 是预期门禁，不应当当作数据库错误。

#### Step 3.6：build 入库（建议首次用 reset，跑通后再用 incremental）
做什么（首次建议更稳的 reset 语义，后续再切换 incremental）：
```powershell
rag-build build --root . --units data_processed/text_units.jsonl `
  --db chroma_db --collection rag_chunks `
  --embed-model BAAI/bge-m3 --device cuda:0 --embed-batch 32 --upsert-batch 256 `
  --chunk-chars 1200 --overlap-chars 120 --min-chunk-chars 200 --include-media-stub `
  --sync-mode reset --state-root data_processed/index_state --strict-sync true
```
为何：首次跑通时，你的目标是拿到“结构正确 + 可验收 PASS”。如果你之前同名 collection 里存在残留，incremental 会依赖 state 进行精确删除；而 reset 模式可以直接避免“旧残留导致 count mismatch”，更适合新手先跑通闭环。注意：你验证通过后，再切换到增量同步：
- `--sync-mode incremental`
- `--on-missing-state reset`：当发现库不为空但 state 缺失时自动重置（避免陷入不可定位删除）
- `--schema-change reset`：当 chunk 口径或 embed 模型变化时自动重置（避免跨口径污染）

#### Step 3.7：check 验收（用 plan 驱动 expected）
做什么：
```powershell
rag-check --db chroma_db --collection rag_chunks --plan data_processed/chunk_plan.json
```
为何：这一步把“感觉上没报错”升级为“可审计的强一致判据”。只要 FAIL，你就不要进入检索质量评估或 LLM 调用测试，因为上游库结构已经不满足不变量。注意：若 FAIL 且 `got > expected`，通常是残留没清；若 `got < expected`，通常是 build 中断或某批 upsert 失败；两者的处置路径不同（见第 9 节）。


### Step 4：日常使用主线（rag-* 命令）

这一节按“你日常会反复执行”的顺序介绍每个命令：做什么、为什么、参数如何选、产物在哪里。建议你把这一节当作日常 SOP：资料变更后按顺序执行，任何时候都不要跳过 plan/check。

#### Step 4.1：建表 inventory（rag-inventory）

做什么：扫描 `data_raw/`，生成或更新 `inventory.csv`（默认在项目根目录或 `data_processed/`，以你当前脚本实现为准），并输出总行数。你看到的 `Wrote XXXX rows to ...\inventory.csv` 就是这个阶段的指标。为何：inventory 是“输入集合”的第一层定义——只要它不稳定，你后续所有数量指标都会不稳定。对新手来说，inventory 的行数与文件类型分布（md/image/video/other）是最直观的稳定性信号。参数与注意：如果你的脚本支持排除/包含规则（如忽略临时后缀、忽略某些目录），建议把规则固定下来并写进仓库配置，避免每次人工临时修改导致结果漂移；并且尽量在“文件不再变化”的状态下运行（例如下载完成后再跑）。

#### Step 4.2：抽取 units（rag-extract-units）

做什么：读取 inventory（或直接扫描 data_raw），把每个源文件转成统一的“文本单元”记录，写入 `data_processed/text_units.jsonl`。为何：units 是你 pipeline 的“逻辑输入”，它把源文件差异屏蔽掉，后续 plan/build 只需要面向 units 做统一处理。参数与注意：如果你开启了媒体 stub，图片/视频通常会生成“占位文本”或“引用信息”以进入 chunk 计划；这会直接影响 planned_chunks。因此新手一定要把 `include_media_stub` 与 extract 的配置保持一致，并把 units 文件当作可审计产物保存（不要只靠终端输出判断）。

#### Step 4.3：校验 units（rag-validate-units）

做什么：对 `data_processed/text_units.jsonl` 做结构校验（必填字段、文本长度、非法字符等），并输出通过/失败统计。为何：validate 的价值是减少“坏数据把下游搞坏”的排障成本；它把错误从“构建入库阶段”提前到“数据准备阶段”。参数与注意：对新手更友好的策略是：校验失败时优先修复抽取逻辑或忽略规则，而不是让 build 忽略异常记录；因为忽略会造成 planned_chunks 与实际入库之间出现不可预测的缺口，最终反映为 check FAIL 或召回缺失。

#### Step 4.4：生成 chunk_plan（rag-plan）

做什么：根据 units 与 chunk 参数计算 planned chunks，输出 `data_processed/chunk_plan.json`，并提供 type breakdown（例如 image/md/video 贡献了多少 chunks）。为何：你要把“预期数量”变成可复现的计算结果；只要 plan 的输入（units）与参数（chunk_conf、include_media_stub）固定，expected 就固定。参数与注意：新手最应当注意的是“plan 与 build 必须同参数”，尤其是 `chunk-chars / overlap-chars / min-chunk-chars / include-media-stub`。如果你想做实验（比如改 chunk_chars），请先生成对应的新 plan 再 build，否则 check FAIL 是正常的口径门禁。

#### Step 4.5：增量构建入库（rag-build）

做什么：把 plan 口径下生成的 chunks 进行 embedding 并写入 Chroma collection，同时维护 `data_processed/index_state/` 用于增量同步与残留清理。为何：仅用 upsert（追加/更新）并不能处理“删除或缩短导致 chunk 减少”的情况，这就是你之前遇到 `count mismatch` 的直接原因之一；增量同步语义的关键就是：对变更/删除的 doc 先删除旧 chunk_ids，再写入新 chunks，从而保持 `collection.count == expected`。参数与注意（新手最关键的几条）：
- `--sync-mode reset`：最稳；每次都重建，不依赖 state（成本高，但最容易跑通）
- `--sync-mode incremental`：成本低；依赖 index_state 做差量删除与 upsert（推荐长期）
- `--on-missing-state reset`：当发现库不为空但 state 缺失时自动重置（避免“不知道该删哪些旧条目”的死局）
- `--schema-change reset`：当嵌入模型或 chunk 口径变化时自动重置（避免跨口径污染）
- `--strict-sync true`：构建结束立即做强一致断言，尽早发现 mismatch（避免把问题带入下一阶段）
- GPU/CPU：`--device cuda:0` 或 `--device cpu`；batch 过大可能 OOM，遇到显存不足按 32→16→8 递减 embed-batch，upsert-batch 也可按 256→128→64 递减以降低峰值压力

#### Step 4.6：一致性验收（rag-check）

做什么：读取 `chunk_plan.json` 的 expected，与 Chroma collection 的实际条目数对比，输出 PASS/FAIL。为何：它是你工程“强不变量”的执行者；无论你后续做检索质量评估还是 LLM answer，都必须在 check PASS 的前提下进行，否则你在评估的是一套结构不一致的索引，结论不可复盘。参数与注意：check 依赖你传的 `--plan`，因此如果你换了参数或 units 文件，一定要先重跑 plan；不要试图用旧 plan 去验新库（那会得到误报）。若你要自动化回归，建议把 plan 与 check 输出归档到固定目录（例如 `data_processed/build_reports/日期/`）。


### Step 5：一键全检（rag-check-all）

做什么：运行 `mhy_ai_rag_data.tools.check_all`，它会在几秒到十几秒内完成“工程门禁级检查”，包括：关键文件存在、Python 编译检查、关键模块导入检查、help 入口检查、文档 TOC 头检查等。为何：新手在覆盖补丁/合并改动后，最容易出现“漏文件、放错层级、入口名不一致、导入路径错”的问题，而这些问题在跑全流程时往往要等到中后段才暴露，浪费大量时间。check_all 把它们提前暴露，并且输出清晰的 FAIL 原因，便于你按条修复。参数与注意：当前 check_all 支持：
- `--root`：仓库根目录（默认当前目录）
- `--mode fast`：目前只有 fast（默认）
你可以把它当作“每次跑 build 之前必须先跑”的门禁。若 check_all FAIL，不建议继续跑 build，而应先修复结构/导入问题。


### Step 6：项目结构与“脚本在哪里”

对新手最重要的规则是：**实现只看 src/，入口与兼容只看根目录与 tools/ 的 wrapper**。你以后如果在根目录看到一个与 src 同名的脚本，默认它是 wrapper（转发层），它的职责是：把 `src/` 加到 Python 模块搜索路径中，然后用 `runpy.run_module` 执行包内模块的 `__main__`。这样做的好处是：你无论从“可安装包（rag-*）”还是“直接跑 wrapper（python tools/xxx.py）”，最终执行的都是同一份权威代码，避免“双源实现”造成的漂移与不可复盘。

推荐你用下面的认知模型理解目录：
- `src/mhy_ai_rag_data/**`：权威实现；你要改逻辑、查 bug、加功能，都在这里做
- `tools/*.py` 与根目录 `*.py`：过渡期兼容入口；不要在这里写业务逻辑
- `pyproject.toml`：依赖与 `rag-*` 入口定义；改完通常要 `pip install -e .` 刷新
- `data_raw/`：原始资料输入
- `data_processed/`：中间产物（inventory/units/plan/index_state/报告）
- `chroma_db/`：向量库持久化目录（你要做备份/迁移时重点关注）
当你遇到“我改了代码但怎么没生效”，第一时间检查：你是否在改 src；以及你是否在用同一个 venv 执行命令。


### Step 7：常见问题与稳定排障

#### Step 7.1：rag-* 命令找不到
现象：终端提示找不到 `rag-build` 或 `rag-check-all`。原因通常是你没有在当前 Python 环境记载 console scripts，或者你没有激活 venv 导致 PATH 中没有 venv 的 Scripts。稳定修复：在仓库根目录执行 `.\.venv_rag\Scripts\python.exe -m pip install -e .`，然后重新打开终端或激活 venv，再试 `rag-build --help`。备选：不依赖 rag-*，改用 `python -m mhy_ai_rag_data.tools.build_chroma_index_flagembedding --help` 验证入口。

#### Step 7.2：No module named 'tools' / 导入失败
现象：你之前贴过的 `[FATAL] cannot import tools/index_state.py: No module named 'tools'`。原因：用“脚本文件路径启动”导致 sys.path 指向 tools 目录而不是仓库根目录。稳定修复：不要再直接运行 `python tools\xxx.py` 作为主线；改用 `rag-*` 或 `python -m mhy_ai_rag_data...`。如果你必须用 wrapper，也要在仓库结构完整的前提下用它（它会注入 src 路径并转发）。建议：把 `rag-check-all` 固化为每次运行前门禁，以尽早发现入口层问题。

#### Step 7.3：check FAIL：expected != got
这是你项目里最重要的失败类型，需要根据“谁大谁小”分支处理：
- `got > expected`：更常见，通常是旧残留未清（历史写入的 chunk 仍在 collection 里）。稳妥修复：先用 `rag-build --sync-mode reset` 重建，确保 PASS；然后再回到 incremental 并确认 index_state 写入正常。
- `got < expected`：通常是 build 中断、embedding 失败、upsert 批次失败，导致计划中的部分 chunks 没写入。修复路径：查 build 日志中最后成功的批次位置，降低 batch（embed-batch、upsert-batch），必要时先用 cpu 跑通结构，再回到 gpu 优化性能。
新手建议：第一次先 reset 跑通 PASS，把“工程正确性”与“增量优化”拆开，避免同时排查两类变量。

#### Step 7.4：inventory 行数不稳定
原因通常是输入文件集合在变化（下载未完成、文件在写入、目录含临时文件、忽略规则变化、文件锁导致读取失败）。稳定策略：在你确认资料静止后再跑 inventory，并把忽略规则固定；对大文件下载过程，建议先把下载目录放到 data_raw 外部，下载完成再移动进来，减少被扫描到“半成品”的概率。


### Step 8：自检清单

建议你每次覆盖补丁、改脚本、换机迁移后，按下面顺序自检（从快到慢）：
1) `rag-check-all --root .`：工程结构与入口门禁
2) `rag-inventory --root .`：输入集合稳定性
3) `rag-extract-units --root .`：中间产物更新
4) `rag-validate-units --root .`：输入结构门禁
5) `rag-plan ...`：expected 口径固化
6) `rag-build ...`：写库（首次 reset，长期 incremental）
7) `rag-check ...`：强一致验收 PASS/FAIL
8) （可选）再跑检索回归与 LLM 测试（只有在 PASS 后才有意义）


### Step 9：失败模式与处置

1) 触发/现象：`rag-check-all` FAIL，提示缺少 `pyproject.toml` 或缺少 `src/mhy_ai_rag_data`。原因：补丁覆盖不完整或解压路径层级错（例如多了一层目录）。缓解：确认你是在仓库根目录解压覆盖，并且 `pyproject.toml` 与 `src/` 与 `tools/` 在同一级；重新解压补丁覆盖。备选：在终端执行 `dir pyproject.toml`、`dir src\mhy_ai_rag_data` 来快速确认结构。

2) 触发/现象：`rag-build` 报显存不足或进程被杀。原因：embed_batch/upsert_batch 太大导致 GPU/内存峰值超限。缓解：按 32→16→8 递减 embed-batch，并降低 upsert-batch；必要时先切到 cpu 跑通结构，再回到 gpu。备选：分阶段构建（先文本-only、再媒体 stub），降低一次性规模。

3) 触发/现象：增量模式下 `got > expected` 反复出现。原因：index_state 缺失或不同口径混写导致无法定位删除旧条目；或你更换了 embed_model/chunk_conf 但未触发 schema reset。缓解：启用 `--on-missing-state reset` 与 `--schema-change reset`；首次用 `sync-mode reset` 生成正确 state 后再转 incremental。备选：版本化 collection（不同 schema 用不同 collection 名）避免跨口径污染，但会增加磁盘占用与配置复杂度。


### Step 10：最小可复现（MRE）

运行环境：Windows；项目根目录；`.venv_rag` 已存在。  
核心命令（建议直接复制粘贴）：
```powershell
cd <REPO_ROOT>
.\.venv_rag\Scripts\python.exe -m pip install -e .

rag-check-all --root .

rag-inventory --root .
rag-extract-units --root .
rag-validate-units --root .

rag-plan --root . --units data_processed/text_units.jsonl `
  --chunk-chars 1200 --overlap-chars 120 --min-chunk-chars 200 --include-media-stub --out data_processed/chunk_plan.json

rag-build build --root . --units data_processed/text_units.jsonl `
  --db chroma_db --collection rag_chunks `
  --embed-model BAAI/bge-m3 --device cuda:0 --embed-batch 32 --upsert-batch 256 `
  --chunk-chars 1200 --overlap-chars 120 --min-chunk-chars 200 --include-media-stub `
  --sync-mode reset --state-root data_processed/index_state --strict-sync true

rag-check --db chroma_db --collection rag_chunks --plan data_processed/chunk_plan.json
```
期望：最后 `rag-check` 输出 PASS，并且 build 日志中 `strict-sync` 不触发 mismatch。


## 2) 替代方案

### 方案 A：不安装包，只用 wrapper + 统一 `python -m`（最低改动）
适用：你不想引入 `pip install -e .` 的流程，但又想避免“脚本路径启动导致导入漂移”。做法：统一用 `python -m mhy_ai_rag_data...` 运行包内模块，并且在所有命令里显式写 `--root`。代价：没有 `rag-*` 的短命令入口；对新手更容易写错长模块名，但仍比“直接跑脚本文件路径”稳定。

### 方案 B：彻底移除 wrapper，只保留 rag-*（一致性最强）
适用：你确定不会再用旧命令，且希望团队协作时所有人都只有一种入口。做法：删除根目录与 tools 下的 wrapper，只保留 `src/` 与 `pyproject.toml`，并要求所有人必须 `pip install -e .`。代价：迁移期会有一批旧脚本/批处理失效；你需要一次性更新全部文档与自动化脚本，但长期工程一致性最好。
