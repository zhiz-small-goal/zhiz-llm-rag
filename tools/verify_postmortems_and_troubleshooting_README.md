---
title: verify_postmortems_and_troubleshooting 使用说明
version: v1
last_updated: 2026-01-07
tool_id: verify_postmortems_and_troubleshooting

impl:
  module: mhy_ai_rag_data.tools.verify_postmortems_and_troubleshooting
  wrapper: tools/verify_postmortems_and_troubleshooting.py

entrypoints:
  - python tools/verify_postmortems_and_troubleshooting.py
  - python -m mhy_ai_rag_data.tools.verify_postmortems_and_troubleshooting

contracts:
  output: none

generation:
  options: static-ast
  output_contract: none

mapping_status: ok
timezone: America/Los_Angeles
cli_framework: argparse
---
# verify_postmortems_and_troubleshooting_README目录：


- [适用范围与职责边界](#适用范围与职责边界)
- [快速开始](#快速开始)
- [运行模式与退出码](#运行模式与退出码)
- [命令行参数](#命令行参数)
- [配置文件 tools/link_check_config.json](#配置文件-toolslink_check_configjson)
- [解析规则](#解析规则)
- [自动修复策略](#自动修复策略)
- [推荐工作流](#推荐工作流)
- [常见问题与排障](#常见问题与排障)



# verify_postmortems_and_troubleshooting 使用说明

> 目标：让仓库内 Markdown 文档的本地引用（链接/图片/附件/脚本路径等）保持“可定位、可复现、可审计”，并在发现断链时提供可控的自动修复能力。

## 适用范围与职责边界
该工具用于扫描仓库内所有 `*.md` 文件，检查其中指向**仓库内文件**的本地引用是否可解析到真实文件，并在满足条件时给出自动修复。它解决的问题是“文档引用漂移”（改了文件路径/文件名，文档未同步）以及“计划项误导”（文档写成 `tools/foo.py` 但仓库并不存在）。

**它会检查的引用类型（覆盖面）**：
- 行内链接/图片：`[text](path)`、`![alt](path)`。
- 引用式链接定义：`[id]: path`。
- 自动链接：`<path>`。
- 反引号内的“像路径的 token”：`` `docs/howto/OPERATION_GUIDE.md` ``。
- 链接标题中的反引号：例如 `[``path``](...)` 里反引号内容也会被解析（用于发现“示例路径”误写成真实引用）。

**它不会检查/会跳过的内容（边界）**：
- URL（`http/https/mailto/tel`）、纯锚点（`#xxx`）、绝对路径（`<REPO_ROOT>
- fenced code block（``` 或 ~~~ 包裹的代码块）内部内容会被屏蔽，避免把代码样例里的字符串当作引用。
- 经过配置忽略的前缀（例如 `data_processed/`、`chroma_db/` 等运行时产物目录），以及显式占位符（包含 `<...>`、`...`、`*` 的路径）。

**文件位置**：
- 兼容入口（wrapper）：`tools/verify_postmortems_and_troubleshooting.py`（允许直接 `python tools/...`）。
- 权威实现：`src/mhy_ai_rag_data/tools/verify_postmortems_and_troubleshooting.py`（推荐 `python -m mhy_ai_rag_data.tools.verify_postmortems_and_troubleshooting ...`）。


## 快速开始
建议在**仓库根目录**运行。该工具会递归扫描仓库内的 `*.md`，并根据引用所在文档的目录（`md_file.parent`）去解析相对路径；如果你在子目录运行，`find_project_root` 仍会定位到仓库根，但“读者复制命令时的习惯”通常是从仓库根执行，因此文档也应以仓库根为默认上下文。

### 本地：一键修复（推荐的日常用法）
```bash
python tools/verify_postmortems_and_troubleshooting.py
```
- 默认会尝试**自动修复**可唯一定位的断链（例如旧路径能在仓库索引中唯一匹配到新路径）。
- 运行后请查看输出的 `[AUTO-FIXED]` 列表，并把变更纳入一次 commit，避免“修了但未提交”导致下次又复发。

### 本地：只检测，不改文件
```bash
python tools/verify_postmortems_and_troubleshooting.py --no-fix
```
- 用于你想先观察报告、再手工改文档的场景。

### CI/门禁：严格模式（建议搭配 --no-fix）
```bash
python tools/verify_postmortems_and_troubleshooting.py --no-fix --strict
```
- `--strict` 会让脚本通过退出码表达失败（便于 CI 阻断）。
- CI 中建议加 `--no-fix`，避免在 CI 机器上改写工作区文件（不可审计且难回滚）。

### 计划项占位：把缺失的 tools/*.py 引用自动转为占位写法
当文档中出现 `tools/foo.py` 但仓库确实没有该脚本，并且你希望表达“这是计划项，不是内置工具”，可显式启用：
```bash
python tools/verify_postmortems_and_troubleshooting.py --fix-missing-tools-to-placeholder
```
该开关只在“无法找到唯一候选文件”时生效，会把 `tools/foo.py` 自动改写为 `tools/<foo>.py`，并视为占位（后续检查会自动忽略包含 `<...>` 的路径）。


## 运行模式与退出码
该工具的输出以 `STATUS: ...` 为主，退出码用于在门禁（CI）中表达“是否阻断”。要点是：**非 strict 模式下，即使出现 FAIL/WARN，也会尽量返回 0**，让你可以先看报告再决定是否修改；而 strict 模式下会用非 0 退出码阻断。

### 输出块语义
- `[AUTO-FIXED]`：已对文档进行自动修复（你应把这些改动纳入一次 commit）。
- `[SUGGESTED]`：建议修复但没有自动改写（典型原因：引用出现在反引号里，脚本默认不改写反引号内容，以避免误修改示例文本）。
- `[AMBIGUOUS REFS]`：存在多个候选文件，脚本无法确定应选哪个；需要你手动指定更精确的路径。
- `[BROKEN MD REFS]`：没有任何候选文件（在既定索引与过滤规则下），属于真实断链或文档表达不符合约定。

### 退出码
- **默认（不带 `--strict`）**：
  - `STATUS: PASS` / `WARN` / `FAIL` 都可能返回 `0`，便于“先报告后修复”的交互式工作流。
- **严格模式（`--strict`）**：
  - `STATUS: PASS` → 退出码 `0`
  - `STATUS: WARN` → 退出码 `2`
  - `STATUS: FAIL` → 退出码 `2`

### 推荐做法
- 本地开发阶段：先跑无参（允许自动修复）→ 确认 `[AUTO-FIXED]` → commit。
- CI 阶段：固定跑 `--no-fix --strict`，只负责阻断，不在 CI 上产生不可审计改动。


## 命令行参数
脚本参数在 `src/mhy_ai_rag_data/tools/verify_postmortems_and_troubleshooting.py::_parse_args()` 定义。你在文档或 CI 中引用这些参数时，应尽量说明“为什么要开/不开”，避免团队成员只机械复制命令而不理解其副作用。

- `--no-fix`
  - 含义：只检测，不进行任何文本替换。
  - 何时使用：CI/门禁、或你希望先审阅报告再手工改文档时。
  - 关键影响：不会产生 `[AUTO-FIXED]`；若存在可唯一修复的断链，会出现在 `[SUGGESTED]` 或 `[BROKEN ...]`。

- `--strict`
  - 含义：用退出码表达 FAIL/WARN（便于 CI 阻断）。
  - 何时使用：CI/门禁、或你希望把“断链/歧义”作为强约束时。
  - 关键影响：`FAIL` 返回 `2`、`WARN` 返回 `1`。

- `--any-local`
  - 含义：忽略扩展名白名单，只要“看起来像路径”且不是 URL/绝对路径，就进行校验。
  - 何时使用：你在文档中引用了无后缀文件、或后缀不在白名单（例如自定义后缀、脚本片段等）。
  - 风险：会把更多 token 当作路径检查，若文档里有大量类似 `v1.2` 这种“带点”的普通字符串，可能增加噪声；此时建议改写文档或改用 fenced code block 包裹示例。

- `--config PATH`
  - 含义：指定 JSON 配置文件路径（默认 `tools/link_check_config.json`）。
  - 何时使用：你希望扩展允许检查的文件类型、或维护一份集中忽略规则时。
  - 关键影响：配置会覆盖默认扩展名列表/忽略规则。

- `--fix-missing-tools-to-placeholder`
  - 含义：当文档引用 `tools/*.py` 但仓库确实不存在、且脚本也找不到唯一候选文件时，将其自动改为占位：`tools/<name>.py`。
  - 何时使用：你希望把“计划项脚本”从“看似可运行”变为“显式占位”，减少误导与 strict 误报。
  - 关键影响：这是**文本改写行为**，建议仅在本地开启并配合 commit；CI 通常用 `--no-fix` 不会触发。


## 配置文件 `tools/link_check_config.json`
该工具默认读取 `tools/link_check_config.json`（可通过 `--config` 指定其它路径）。配置的作用是：
1) 控制“哪些后缀的本地引用需要被检查”（extensions）；
2) 对运行时产物、外部数据目录、以及模板占位符做忽略（ignore_*）；
3) 控制“是否扩展到扫描 code span / title backticks”（check_*）；
4) 对 GitHub 常见的 `/docs/...` 这类“仓库根目录相对路径”做语义对齐（treat_leading_slash_as_repo_root）。

### 字段说明（按优先级理解）
- `any_local`（bool）
  - 设为 true 相当于默认启用 `--any-local`。适合你希望“只要像路径就查”的场景（噪声也会更高）。

- `extensions`（list[str]）
  - 允许检查的扩展名白名单（例如 `.md`、`.png`、`.pdf`、`.jsonl` 等）。
  - 当 `any_local=false` 时，只有后缀在该列表中的引用才会被检查。

- `ignore_prefixes`（list[str]）
  - 忽略某些前缀的引用，例如 `data_processed/`、`chroma_db/`、`.venv/`。
  - 设计目的：运行产物/缓存/第三方依赖通常不应作为文档门禁。

- `ignore_contains`（list[str]）
  - 如果路径 token 里包含这些子串，则直接跳过检查（例如包含 `{{BASEURL}}`、`<...>` 等占位符语义）。

- `ignore_bare_filenames`（list[str]）
  - 仅对“裸文件名”（不含 `/` 或 `\`）生效，例如 `inventory.csv`。
  - 设计目的：文档里经常用裸文件名指代运行产物；在严格模式下，如果不忽略，会被当成 `docs/**/inventory.csv` 断链。
  - 推荐实践：文档中仍尽量写成带前缀的明确路径（例如 `data_processed/...`），该列表更多是“迁移期兜底”。

- `ignore_bare_regexes`（list[str]）
  - 对裸文件名生效的正则列表，适合 `run_123.events.jsonl`、`*.progress.json` 等“实例名随运行变化”的产物。
  - 注意：该列表使用 `re.fullmatch`；如果你写的是 `.*\.events\.jsonl$` 这类模式，就可以覆盖所有事件流文件名。

- `check_backticks`（bool，默认 false）
  - 是否扫描 Markdown 的 code span（反引号 \`...\`）内部，提取其中“像路径”的 token 进行检查。
  - 默认关闭：CommonMark 语义里 code span 是“字面量文本”，并不代表链接/引用；开启后更容易把示例文本当作断链信号。（若你确实把 code span 当“必须真实存在的文件路径”，再开启。）

- `check_title_backticks`（bool，默认 false）
  - 是否扫描链接 title 中的反引号 token，例如 `[txt](path "title: `docs/x.md`")`。
  - 默认关闭：title 常用于说明/示例文本，作为门禁信号容易误报。

- `treat_leading_slash_as_repo_root`（bool，默认 true）
  - 当路径以 `/` 开头时，是否按“仓库根目录相对路径”解析（例如 `/docs/howto/A.md` 解析为 `<repo>/docs/howto/A.md`）。
  - 说明：此规则与 GitHub 仓库 Markdown 的常见渲染语义对齐；如果你的文档里经常出现 OS 绝对路径示例（例如 `/usr/local/bin`）且恰好命中 `extensions/any_local`，可将该值设为 false 以减少噪声。

### 最小示例
```json
{
  "any_local": false,
  "extensions": [".md", ".png", ".pdf"],
  "ignore_prefixes": ["data_processed/", "chroma_db/"],
  "ignore_contains": ["{{BASEURL}}", "<", "..."],
  "ignore_bare_filenames": ["inventory.csv"],
  "ignore_bare_regexes": [".*\.events\.jsonl$", ".*\.progress\.json$"],
  "check_backticks": false,
  "check_title_backticks": false,
  "treat_leading_slash_as_repo_root": true
}
```

## 解析规则
理解解析规则可以帮助你写出“既清晰又不会误触发门禁”的文档。

### 解析到的引用来源
脚本会逐行扫描 Markdown 文本（先屏蔽 fenced code block 的内容），然后提取以下命中：
1) 行内链接/图片：`[title](dest)` 与 `![alt](dest)` 的 `dest`。
2) 引用式链接定义：`[id]: dest` 的 `dest`。
3) 自动链接：`<dest>`。

可选扩展（默认关闭，需要配置打开）：
4) code span（反引号）内 token：`` `docs/howto/OPERATION_GUIDE.md` ``（需 `check_backticks=true`）。
5) 链接 title 内的反引号 token：`[t](p "title: `docs/x.md`")`（需 `check_title_backticks=true`）。

### 哪些 token 会被当作“需要检查的路径”
脚本会做一层“像路径”的兜底判断：只要 token 中包含 `/` 或 `\`，或文件名部分包含点号（例如 `a.md`），才会进入后续检查；这能避免把普通词语误当路径。

### 路径语义（与 GitHub 常见渲染习惯对齐）
- 普通相对路径：相对当前 md 文件所在目录解析（CommonMark 行为）。
- 以 `/` 开头：当 `treat_leading_slash_as_repo_root=true` 时，按“仓库根目录相对路径”解析（例如 `/docs/A.md` -> `<repo>/docs/A.md`）；当该值为 false 时，此类 token 会被跳过。

### 会被跳过的情况（与“门禁噪声”直接相关）
- URL、纯锚点（`#...`）会被直接跳过。
- 操作系统绝对路径会被跳过：如 `<REPO_ROOT>
- fenced code block（``` 或 ~~~）内部会被屏蔽，避免把代码样例当作真实引用（CommonMark 语义：代码块内容不解析为内联结构）。
- 包含占位符语义的路径会被忽略：例如包含 `{{...}}`、`<...>`、`...`、`*` 的路径（用于表达“计划项/模板项/通配项”）。
- 通过 `tools/link_check_config.json` 配置忽略的前缀与裸文件名（用于运行时产物与迁移期兜底）。

补充：即使开启 `check_backticks=true`，脚本也不会自动改写 code span 文本，只会输出 `[SUGGESTED]` 建议（避免把“示例文本”误改）。

## 自动修复策略
自动修复的核心约束是：**只在“可以唯一定位目标文件”时才自动改写**，否则一律输出报告要求人工介入。这样可以避免脚本在文件名重复/目录结构复杂时做出“看似修复但实际修错”的高风险改动。

### 候选定位规则（概念级）
当某个引用 `path` 在引用文档的相对目录下不存在时，脚本会构建一个“仓库文件索引”，然后通过以下方式找候选：
1) 优先按“后缀匹配”：寻找 `relative_path` 以 `path` 结尾的文件。
2) 若无后缀匹配，则退化为“同文件名匹配”：寻找文件名与 `path` 的 basename 相同的文件。

### 自动改写的覆盖面
- 对于链接目标（`()`) 与引用式定义的 `dest`：若候选唯一且未关闭 `--no-fix`，会自动替换为新的路径（并保留原 `?query` 与 `#anchor` 后缀）：
  - 若原写法以 `/` 开头且 `treat_leading_slash_as_repo_root=true`，则保持“仓库根目录相对路径”风格（修复后仍以 `/` 开头）；
  - 否则写回为相对当前文档目录的相对路径。
- 对于反引号命中的 token：默认只给出 `[SUGGESTED]`，不自动改写，避免把“示例文本”误改。
- 对于 `tools/*.py` 缺失且无唯一候选：仅在显式启用 `--fix-missing-tools-to-placeholder` 时，自动改为 `tools/<name>.py` 占位（用于表达“计划项”）。

### 你在代码审查时应重点关注的副作用
- 自动修复会直接改写 `*.md` 文件内容；因此建议只在本地运行自动修复，并立刻以独立 commit 落盘。
- 如果输出出现 `[AMBIGUOUS REFS]`，说明仓库内存在多个同名/同尾路径文件；此时最稳妥的处理是把文档引用改为更长、更明确的相对路径（而不是希望脚本“猜”）。


## 推荐工作流
下面给出一套“能稳定落地、且符合可审计性”的推荐流程，你可以直接写进 `docs/howto/OPERATION_GUIDE.md` 或 CI gate。

### 本地写文档/改结构（推荐）
1) 先完成文档或目录调整后，运行：
   ```bash
   python tools/verify_postmortems_and_troubleshooting.py
   ```
   该步骤会在“可唯一定位”时自动修复断链。其关键机制是：让“引用修复”与“文档变更”发生在同一个工作区上下文中，且你能立刻 review 具体改动。
2) 检查输出的 `[AUTO-FIXED]` 与 `[BROKEN ...]`：
   - 若存在 `[AUTO-FIXED]`，用 `git diff` 查看改写是否符合预期；
   - 若存在 `[AMBIGUOUS REFS]`，优先把文档引用改为更明确的相对路径，避免未来又出现歧义。
3) 把文档修复作为一次独立 commit（建议）：
   - 这样当你未来回溯“为什么路径变成这样”时，有明确的版本边界。

### CI/门禁（推荐）
在 CI 中固定执行（不改文件、只阻断）：
```bash
python tools/verify_postmortems_and_troubleshooting.py --no-fix --strict
```
该组合的关键取舍是：CI 的职责是“验证而不是修复”；修复应在开发机上完成并通过 PR/commit 审核进入主干。

### 当你需要表达“计划项/模板项”
- 推荐写法：`tools/<script_name>.py` 或 `data_processed/.../<ts>_report.json`。
- 原理：脚本会忽略包含 `<...>` 的路径，从而把“计划项”显式标注为占位，避免读者误以为仓库内置。


## 常见问题与排障
### 1) `STATUS: FAIL`，但退出码仍为 0
**现象**：你本地跑脚本看到 `STATUS: FAIL`，但命令行返回值是 0，CI 没有阻断。
**原因**：未开启 `--strict`。脚本默认把“报告输出”与“门禁阻断”分离。
**缓解**：
- 本地要阻断：加 `--strict`。
- CI 推荐固定：`python tools/verify_postmortems_and_troubleshooting.py --no-fix --strict`。

### 2) `[AMBIGUOUS REFS]`：同名文件过多，脚本无法确定目标
**现象**：输出类似 `docs/...:123: `old/path.md` -> a/b/c.md, x/y/c.md`。
**原因**：候选文件不止一个（同名或同尾路径），脚本无法在不冒险的情况下自动选择。
**缓解**：
- 直接把文档引用改成更明确的相对路径（包含上级目录），例如从 `c.md` 改为 `reference/c.md`。
- 如果这是“计划项”，改为占位写法 `.../<name>.md` 或 `<...>`，避免读者误以为真实存在。

### 3) `[SUGGESTED]`：提示可修复，但没有自动改写
**现象**：你看到 `[SUGGESTED]`，但文件没有变更。
**常见原因**：引用出现在反引号中（示例/命令片段），脚本默认不自动改写反引号内容，以避免把“示例文本”误改为“真实路径”。
**缓解**：
- 若反引号中确实应为真实路径：手工改写；或者把示例放进 fenced code block，并在文字描述中提供真实链接。
- 若反引号中只是示意：把它改为占位（例如 `...` 或 `<name>`），让读者理解这是模板而不是内置文件。

### 4) `[WARN] invalid config: ... -> use defaults`
**现象**：脚本启动时打印配置文件无效并回退默认配置。
**原因**：`tools/link_check_config.json` 不是合法 JSON（常见是转义错误或多了注释）。
**缓解**：
- 用 `python -m json.tool tools/link_check_config.json` 验证 JSON 合法性。
- 若你需要注释，建议另建 `tools/link_check_config.md` 说明，不要在 JSON 里写注释。

### 5) 开启 `--any-local` 后噪声变多
**现象**：报告里出现大量“看似路径”的 token 被检查。
**原因**：`--any-local` 会绕过扩展名白名单，只要像路径就会检查；文档中带点号的普通字符串（例如版本号）可能被误判。
**缓解**：
- 优先把示例放入 fenced code block（```），让脚本屏蔽代码样例。
- 或者保持 `any_local=false`，通过 `extensions` 白名单精确控制检查范围。

---

## 自动生成参考（README↔源码对齐）

> 本节为派生内容：优先改源码或 SSOT，再运行 `python tools/check_readme_code_sync.py --root . --write` 写回。
> tool_id: `verify_postmortems_and_troubleshooting`
> entrypoints: `python tools/verify_postmortems_and_troubleshooting.py`, `python -m mhy_ai_rag_data.tools.verify_postmortems_and_troubleshooting`

<!-- AUTO:BEGIN options -->
| Flag | Required | Default | Notes |
|---|---:|---|---|
| `--any-local` | — | — | action=store_true；忽略扩展名列表，校验所有本地路径 |
| `--config` | — | str(DEFAULT_CONFIG_PATH) | 扩展名与模式配置文件路径（JSON） |
| `--fix-missing-tools-to-placeholder` | — | — | action=store_true；当引用 tools/*.py 但文件不存在且无唯一候选时，将其自动改为 tools/<name>.py 占位（避免误导与 strict 误报） |
| `--no-fix` | — | — | action=store_true；仅检测，不自动修复 |
| `--strict` | — | — | action=store_true；存在断链/歧义时返回非 0 |
<!-- AUTO:END options -->

<!-- AUTO:BEGIN output-contract -->
- `contracts.output`: `none`
<!-- AUTO:END output-contract -->

<!-- AUTO:BEGIN artifacts -->
（无可机读 artifacts 信息。）
<!-- AUTO:END artifacts -->
