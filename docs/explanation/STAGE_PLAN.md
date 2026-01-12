# STAGE_PLAN

### [021] 2026-01-12 修复 pre-commit rag-ruff 传参错误

日期：2026-01-12  
状态：已完成  

**变更类型：**  
- Bug 修复

**目标：**  
- pre-commit 仅检查暂存 Python 文件，避免 %* 被当作参数
- 保持 check_ruff 全仓模式不变（无 files 时）

**触发原因：**  
- pre-commit 报错：check_ruff.py 收到未展开的 %* 参数

**涉及文件：**  
- .pre-commit-config.yaml  
- tools/check_ruff.py  
- tools/check_ruff_README.md  
- docs/explanation/STAGE_PLAN.md  

**改动概览：**  
- .pre-commit-config.yaml  
  - 使用 entry + args 由 pre-commit 追加文件列表  
- tools/check_ruff.py  
  - 支持 files 参数按列表执行 ruff  
- tools/check_ruff_README.md  
  - 补充 files 参数说明  

**关键点说明：**  
- 无 files 时仍对全仓执行，CI/门禁行为不变  

**测试验证：**  
- [ ] 提交少量 .py 文件，确认 rag-ruff 不再报 %* 参数  
- [ ] `python tools/check_ruff.py --root . --format` 仍可全仓检查  

**后续 TODO：**  
- 无

### [020] 2026-01-12 补齐 LLM_API_KEY 注入方式说明

日期：2026-01-12  
状态：已完成  

**变更类型：**  
- 行为调整
- 文档补充

**目标：**  
- LLM_API_KEY 支持环境变量注入（LLM_API_KEY/OPENAI_API_KEY）
- 提供 .env.example 与文档指引，避免把密钥写进仓库

**触发原因：**  
- 审查项 S5-2：LLM_API_KEY 使用常量占位，缺少明确注入方式说明

**涉及文件：**  
- src/mhy_ai_rag_data/rag_config.py  
- .env.example  
- .gitignore  
- docs/howto/TROUBLESHOOTING.md  
- docs/howto/OPERATION_GUIDE.md  
- docs/reference/REFERENCE.md  
- docs/explanation/STAGE_PLAN.md  

**改动概览：**  
- src/mhy_ai_rag_data/rag_config.py  
  - 读取环境变量覆盖 LLM_API_KEY  
- .env.example  
  - 新增密钥注入示例  
- .gitignore  
  - 忽略 .env 本地密钥文件  
- docs/howto/TROUBLESHOOTING.md / docs/howto/OPERATION_GUIDE.md / docs/reference/REFERENCE.md  
  - 补充环境变量注入说明与引用  

**关键点说明：**  
- 默认行为不变：未设置环境变量时回退为 "EMPTY"  
- 不自动加载 .env，需要由 shell/IDE 注入  

**测试验证：**  
- [ ] `set LLM_API_KEY=***` 后运行 `python -c "from mhy_ai_rag_data.rag_config import LLM_API_KEY; print(LLM_API_KEY)"`  
- [ ] 不设置环境变量时仍为 `EMPTY`  

**后续 TODO：**  
- 无

### [019] 2026-01-12 pre-commit 补齐 ruff/mypy 门禁

日期：2026-01-12  
状态：已完成  

**变更类型：**  
- 行为调整

**目标：**  
- pre-commit 覆盖 lint/format/type（check_ruff --format + check_mypy）
- 保持 fast gate 作为快速入口

**触发原因：**  
- 审查项 S3-1：pre-commit 仅 fast profile，未覆盖 lint/format/type

**涉及文件：**  
- .pre-commit-config.yaml  
- docs/howto/ci_pr_gates.md  
- docs/explanation/STAGE_PLAN.md  

**改动概览：**  
- .pre-commit-config.yaml  
  - 新增 rag-ruff（--format）与 rag-mypy hooks  
- docs/howto/ci_pr_gates.md  
  - pre-commit 示例同步新增 hooks  
- docs/explanation/STAGE_PLAN.md  
  - 追加本次变更记录  

**关键点说明：**  
- ruff format 以 --format 启用，确保 format 也在 pre-commit 覆盖  
- gate runner 行为不变，仅扩展提交前门禁  

**测试验证：**  
- [ ] `pre-commit run rag-ruff -a`  
- [ ] `pre-commit run rag-mypy -a`  
- [ ] `pre-commit run rag-gate-fast -a`  

**后续 TODO：**  
- 无

### [018] 2026-01-12 view_gate_report 文档补齐与语法修复

日期：2026-01-12  
状态：已完成  

**变更类型：**  
- Bug 修复

**目标：**  
- 修复 view_gate_report 统计输出的语法错误，确保脚本可运行
- 新增 view_gate_report 使用说明文档

**触发原因：**  
- Pylance 报错提示括号未关闭，脚本无法通过解析

**涉及文件：**  
- src/mhy_ai_rag_data/tools/view_gate_report.py  
- tools/view_gate_report_README.md  
- docs/explanation/STAGE_PLAN.md  

**改动概览：**  
- src/mhy_ai_rag_data/tools/view_gate_report.py  
  - 修复 counts 输出的 format 关键字语法错误  
- tools/view_gate_report_README.md  
  - 新增脚本说明、参数与输出约定  

**关键点说明：**  
- 输出格式不变，仅修复语法问题  
- README 不改变工具行为  

**测试验证：**  
- [ ] `python tools/view_gate_report.py --root . --md-out data_processed/build_reports/gate_report.md`  
- [ ] `python tools/view_gate_report.py -h`  

**后续 TODO：**  
- 无

### [017] 2026-01-12 Gate 报告人类可读摘要约定

日期：2026-01-12  
状态：已完成  

**变更类型：**  
- 功能新增

**目标：**  
- 约定 gate_report 人类可读摘要生成方式与落盘路径
- 提供 view_gate_report 工具用于从 gate_report.json 生成 Markdown 摘要

**触发原因：**  
- 审查项 S6-1：gate 产物缺少人类可读报告约定

**涉及文件：**  
- src/mhy_ai_rag_data/tools/view_gate_report.py  
- tools/view_gate_report.py  
- tools/gate_README.md  
- docs/howto/ci_pr_gates.md  
- docs/explanation/STAGE_PLAN.md  

**改动概览：**  
- src/mhy_ai_rag_data/tools/view_gate_report.py  
  - 新增 gate_report 人类可读摘要生成脚本（支持 --md-out）  
- tools/view_gate_report.py  
  - tools 侧兼容入口转发至 src  
- tools/gate_README.md / docs/howto/ci_pr_gates.md  
  - 增加人类可读报告约定与示例命令  

**关键点说明：**  
- gate_report.json 仍为主契约；摘要仅从 JSON 派生  
- 默认不改变 gate runner 的产物与退出码  

**测试验证：**  
- [ ] `python tools/view_gate_report.py --root . --md-out data_processed/build_reports/gate_report.md`  
- [ ] `python tools/gate.py --profile ci --root .`，确认 gate_report.json 可解析  

**后续 TODO：**  
- 无
### [016] 2026-01-12 Gate report schema 补齐 per-finding 字段

日期：2026-01-12  
状态：已完成  

**变更类型：**  
- 契约/可读性增强

**目标：**  
- gate_report schema 增加统一 finding 字段定义（id/category/severity/loc/fix/owner/status）
- 支持 gate 步骤在 report 中附带 findings 列表（可选）

**触发原因：**  
- 审查项 S6-2：schema 未定义 per-finding 统一字段，影响报告可读性与可汇总性

**涉及文件：**  
- schemas/gate_report_v1.schema.json  
- docs/explanation/STAGE_PLAN.md  

**改动概览：**  
- schemas/gate_report_v1.schema.json  
  - 新增 `finding` 定义，并在 results 项中增加可选 `findings` 数组  
- docs/explanation/STAGE_PLAN.md  
  - 追加本次变更记录  

**关键点说明：**  
- 仅扩展 schema，旧版 gate_report 仍兼容  
- `findings` 为可选字段，现有 gate runner 行为不变  

**测试验证：**  
- [ ] `python tools/schema_validate.py --schema schemas/gate_report_v1.schema.json --instance data_processed/build_reports/gate_report.json`  
- [ ] `python tools/gate.py --profile ci --root .`，确认 gate_report 仍可通过 schema 校验  

**后续 TODO：**  
- 无
### [015] 2026-01-12 修复 Ruff/mypy 报错并补齐 stub 依赖

日期：2026-01-12  
状态：已完成  

**变更类型：**  
- Bug 修复

**目标：**  
- 清理 Ruff/mypy 报错，恢复 ci gate 通过  
- 为 requests/PyYAML 补齐 stub 依赖以消除 import-untyped  

**触发原因：**  
- 新增 Ruff/mypy 门禁后，旧代码在未使用导入、类型不明确与可达性方面触发 FAIL  

**涉及文件：**  
- pyproject.toml  
- src/mhy_ai_rag_data/tools/suggest_expected_sources.py  
- src/mhy_ai_rag_data/tools/update_postmortems_index.py  
- src/mhy_ai_rag_data/tools/*  
- src/mhy_ai_rag_data/*  
- tools/*  

**改动概览：**  
- pyproject.toml  
  - `[project.optional-dependencies].ci` 增加 `types-requests` 与 `types-PyYAML`  
- src/mhy_ai_rag_data/tools/suggest_expected_sources.py  
  - `main()` 确保所有路径返回退出码 0  
- src/mhy_ai_rag_data/tools/update_postmortems_index.py  
  - 可选依赖 `yaml` 使用 `Optional[ModuleType]` 以兼容未安装场景  
- src/mhy_ai_rag_data/tools/* 与 src/mhy_ai_rag_data/*  
  - 修复 ruff/mypy 报错（未使用导入、重复定义、类型标注与可达性）  

**关键点说明：**  
- 仅处理静态检查报错，不引入功能行为变化  
- 仍保留 “无依赖可运行” 的可选导入策略  

**测试验证：**  
- [ ] `pip install -e ".[ci]"`  
- [ ] `python tools/check_ruff.py --root .`  
- [ ] `python tools/check_mypy.py --root .`  
- [ ] `rag-gate --profile ci --root .`  

**后续 TODO：**  
- 无

### [014] 2026-01-12 新增 Ruff/mypy 门禁（保留可选开关）

日期：2026-01-12  
状态：已完成  

**变更类型：**  
- 行为调整

**目标：**  
- 在 PR/CI Lite 中加入 Ruff lint 与 mypy type check  
- 保留 ruff format / mypy strict 的可选开关，避免一次性收紧  

**触发原因：**  
- 需要把静态规范与类型检查纳入统一 gate，且保留收紧开关  

**涉及文件：**  
- pyproject.toml  
- tools/check_ruff.py  
- tools/check_mypy.py  
- tools/check_ruff_README.md  
- tools/check_mypy_README.md  
- docs/reference/reference.yaml  
- docs/howto/ci_pr_gates.md  
- tools/gate_README.md  
- docs/explanation/HANDOFF.md  
- docs/explanation/STAGE_PLAN.md  

**改动概览：**  
- pyproject.toml  
  - 增加 Ruff/mypy 依赖与配置（target-version/line-length/ignore）  
- tools/check_ruff.py  
  - 新增 Ruff lint + 可选 format check，遵循退出码契约  
- tools/check_mypy.py  
  - 新增 mypy type check + 可选 strict 模式，遵循退出码契约  
- docs/reference/reference.yaml  
  - `profile=ci/release` 增加 `check_ruff` / `check_mypy` 步骤  
- docs/howto/ci_pr_gates.md / tools/gate_README.md / docs/explanation/HANDOFF.md  
  - 同步门禁说明与可选开关  

**关键点说明：**  
- Gate 入口仍统一由 `rag-gate` / `tools/gate.py` 驱动，新增步骤只在 `ci/release` 运行  
- 默认不启用 format/strict，避免一次性收紧；需要时用 `RAG_RUFF_FORMAT=1`、`RAG_MYPY_STRICT=1` 或 CLI 参数  

**测试验证：**  
- [ ] `pip install -e ".[ci]"` 后运行 `python tools/check_ruff.py --root .`  
- [ ] `RAG_RUFF_FORMAT=1 python tools/check_ruff.py --root .`（可选）  
- [ ] `python tools/check_mypy.py --root .`  
- [ ] `RAG_MYPY_STRICT=1 python tools/check_mypy.py --root .`（可选）  
- [ ] `rag-gate --profile ci --root .`，确认 gate_report 含 ruff/mypy 结果  

**后续 TODO：**  
- 无

### [013] 2026-01-11 pre-commit 使用显式解释器路径

日期：2026-01-11  
状态：已完成  

**变更类型：**  
- 行为调整

**目标：**  
- pre-commit 固定使用仓库内虚拟环境的 Python，避免提交时落到系统 Python  
- 保证 `rag-gate --profile fast` 在提交阶段可稳定找到依赖

**触发原因：**  
- 提交阶段使用 system python 导致 `PyYAML` 缺失报错

**涉及文件：**  
- .pre-commit-config.yaml  
- docs/howto/ci_pr_gates.md  
- docs/explanation/STAGE_PLAN.md

**改动概览：**  
- .pre-commit-config.yaml  
  - `entry` 改为 `.venv\Scripts\python.exe tools/gate.py --profile fast --root .`  
  - `language` 改为 `unsupported`  
- docs/howto/ci_pr_gates.md  
  - pre-commit 示例同步为显式解释器路径，并提示按实际 venv 路径调整

**关键点说明：**  
- 该配置依赖 `.venv` 的固定路径；若团队使用其他 venv 目录需同步调整  
- 仅改变 pre-commit 的解释器选择，不影响 gate 逻辑

**测试验证：**  
- [ ] 运行 `pre-commit run rag-gate-fast -a`，确认能够通过并生成 gate_report

**后续 TODO：**  
- 无

### [012] 2026-01-11 gate_report summary 放到最前

日期：2026-01-11  
状态：已完成  

**变更类型：**  
- 行为调整

**目标：**  
- 把 gate_report.json 的 summary 放到最前，便于优先阅读总结果  
- 保持 schema 字段不变，仅调整输出字段顺序

**触发原因：**  
- 当前 summary 输出在 results 之后，阅读不便

**涉及文件：**  
- src/mhy_ai_rag_data/tools/gate.py  
- docs/explanation/STAGE_PLAN.md

**改动概览：**  
- src/mhy_ai_rag_data/tools/gate.py  
  - report 字典构建时将 `summary` 放在 `results` 之前

**关键点说明：**  
- JSON 对象本身无序，但大多数阅读器按插入顺序展示；调整输出顺序提升可读性  
- schema 仍允许任意顺序，工具解析不受影响

**测试验证：**  
- [ ] 运行 `python tools/gate.py --profile ci --root .`，检查 `data_processed/build_reports/gate_report.json` 中 `summary` 在前

**后续 TODO：**  
- 无

### [009] 2026-01-11 补齐 repo health 门禁与 check_repo_health_files 工具

日期：2026-01-11  
状态：已完成  

**变更类型：**  
- 行为调整

**目标：**  
- 补齐 Public Release Preflight 的 repo health 门禁，补充 check_repo_health_files 工具  
- 在 `profile=release` 中新增 repo health 步骤

**触发原因：**  
- 公开发布前需要校验社区/治理文件的存在性与占位符风险

**涉及文件：**  
- src/mhy_ai_rag_data/tools/check_repo_health_files.py  
- tools/check_repo_health_files.py  
- tools/check_repo_health_files_README.md  
- src/mhy_ai_rag_data/tools/gate.py  
- docs/reference/reference.yaml  
- docs/howto/ci_pr_gates.md  
- tools/gate_README.md  
- docs/explanation/STAGE_PLAN.md

**改动概览：**  
- src/mhy_ai_rag_data/tools/check_repo_health_files.py  
  - stdlib-only 实现 repo health 扫描与 JSON 报告  
  - 输出 `result=...` / `required_missing=...` / `placeholders=...` / `report_written=...`  
- tools/check_repo_health_files.py  
  - wrapper，统一从 src 执行  
- tools/check_repo_health_files_README.md  
  - 补齐参数说明、输出格式与示例  
- src/mhy_ai_rag_data/tools/gate.py  
  - `--profile` 增加 `release` 选项  
- docs/reference/reference.yaml  
  - 新增 `profile=release` 以及 `check_repo_health_files` 步骤  
- docs/howto/ci_pr_gates.md / tools/gate_README.md  
  - 增加 release profile 说明与示例

**关键点说明：**  
- `public-release` 模式下，必要文件缺失或占位符将触发 FAIL  
- `profile=release` 在 `ci` 基础上追加 repo health 检查

**测试验证：**  
- [ ] 运行 `python tools/check_repo_health_files.py --repo . --mode public-release --out data_processed/build_reports/repo_health_report.json`，确认 `result=PASS` 且输出报告  
- [ ] 运行 `rag-gate --profile release --root .`，确认 gate 报告包含 repo health 结果

**后续 TODO：**  
- 无

### [001] 2025-12-27 全仓库 Markdown 引用校验改为通用扫描



日期：2025-12-27  

状态：已完成  



**变更类型：**  

- 行为调整



**目标：**  

- 覆盖仓库内所有 .md 文件的本地 .md 引用校验  

- 保留反引号内路径的校验能力  

- 输出可定位的断链清单



**触发原因：**  

- 现有脚本仅检查特定文件与目录，无法适配当前 docs/ 布局与全量校验需求



**涉及文件：**  

- tools/verify_postmortems_and_troubleshooting.py  

- docs/STAGE_PLAN.md



**改动概览：**  

- tools/verify_postmortems_and_troubleshooting.py  

  - 遍历所有 .md 文件并解析 Markdown 链接/图片、引用式定义与反引号路径  

  - 仅校验指向本地 .md 的相对路径，忽略 URL/锚点/绝对路径与 fenced code block  

  - 以当前文件目录为基准解析路径并输出缺失清单



**关键点说明：**  

- 只检查 .md 目标，其他文件类型不纳入断链判定  

- 路径按“所在文件目录”解析，避免全局根目录误判  

- fenced code block 中的内容不参与解析，降低误报



**测试验证：**  

- [ ] 运行 `python tools/verify_postmortems_and_troubleshooting.py`，检查 STATUS 与断链列表是否符合预期  



**后续 TODO：**  

- 无



### [008] 2026-01-02 工具参数与文档对齐（source_uri + append-to 选项）



日期：2026-01-02  

状态：已完成  



**变更类型：**  

- 行为调整



**目标：**  

- 统一 Stage-2 工具默认来源字段为 `source_uri|source|path|file`  

- 修复 `suggest_expected_sources.py` 的 append-to 参数缺失，保证可直接使用  

- 同步 tools 文档参数与示例，避免误用与报错



**触发原因：**  

- 文档与脚本参数不一致，导致默认来源字段解析为空或 append-to 报错



**涉及文件：**  

- src/mhy_ai_rag_data/tools/suggest_expected_sources.py  

- src/mhy_ai_rag_data/tools/run_eval_rag.py  

- src/mhy_ai_rag_data/tools/suggest_eval_case.py  

- tools/suggest_expected_sources_README_v2.md  

- tools/run_eval_rag_README.md  

- tools/run_eval_retrieval_README.md  

- tools/suggest_eval_case_README.md  

- tools/llm_http_client_README.md  

- tools/view_stage2_reports_README.md  

- docs/explanation/STAGE_PLAN.md



**改动概览：**  

- src/mhy_ai_rag_data/tools/suggest_expected_sources.py  

  - argparse：补齐 `--must-pick` / `--auto-must-include`，更新 `--append-to` 说明  

- src/mhy_ai_rag_data/tools/run_eval_rag.py  

  - argparse：`--meta-field` 默认值改为 `source_uri|source|path|file`  

- src/mhy_ai_rag_data/tools/suggest_eval_case.py  

  - argparse：`--meta-field` 默认值改为 `source_uri|source|path|file`  

- tools/suggest_expected_sources_README_v2.md  

  - 参数表/示例/故障处理更新，补充 append-to 相关参数  

- tools/run_eval_rag_README.md / tools/run_eval_retrieval_README.md  

  - `--meta-field` 默认值同步  

- tools/suggest_eval_case_README.md  

  - 参数表补齐缺失项并同步默认值  

- tools/llm_http_client_README.md  

  - 修正导入示例为包路径  

- tools/view_stage2_reports_README.md  

  - 补充 `--cases` / `--validation` / `--show-fails` 参数说明



**关键点说明：**  

- 当前索引主来源字段为 `source_uri`，默认优先级必须包含该字段  

- append-to 自动生成 must_include；`--must-pick` 控制数量，`--auto-must-include` 强制不写 TODO



**测试验证：**  

- [ ] 运行 `python tools/suggest_expected_sources.py --root . --query "xxx" --append-to data_processed/eval/eval_cases.jsonl`，确认不再报缺参数  

- [ ] 运行 `python tools/run_eval_rag.py -h` 与 `python tools/suggest_eval_case.py -h`，确认 `--meta-field` 默认值包含 `source_uri`



**后续 TODO：**  

- 无



### [002] 2025-12-27 断链报告增加行号定位



日期：2025-12-27  

状态：已完成  



**变更类型：**  

- 行为调整



**目标：**  

- 在断链清单中输出“文件第几行”便于定位



**触发原因：**  

- 需要快速定位引用来源，降低排查成本



**涉及文件：**  

- tools/verify_postmortems_and_troubleshooting.py  

- docs/STAGE_PLAN.md



**改动概览：**  

- tools/verify_postmortems_and_troubleshooting.py  

  - 逐行解析引用并在输出中包含行号  

  - fenced code block 仍保持不参与解析



**关键点说明：**  

- 行号基于原始文本行号，便于直接定位  



**测试验证：**  

- [ ] 运行 `python tools/verify_postmortems_and_troubleshooting.py`，确认输出包含 `文件:行号`  



**后续 TODO：**  

- 无



### [003] 2025-12-27 断链自动修复与兜底策略



日期：2025-12-27  

状态：已完成  



**变更类型：**  

- 行为调整



**目标：**  

- 断链时自动定位唯一候选并修复跳转路径  

- 过滤反引号内纯扩展名（如 `.md`）的误报  

- 增加歧义/建议清单作为兜底输出



**触发原因：**  

- 需要把“检测”升级为“可自动修复”，并降低误判带来的噪声



**涉及文件：**  

- tools/verify_postmortems_and_troubleshooting.py  

- docs/STAGE_PLAN.md



**改动概览：**  

- tools/verify_postmortems_and_troubleshooting.py  

  - 解析引用时保留路径/锚点并区分类型（link/ref/autolink/backtick）  

  - 建立全仓库 .md 索引，用于断链候选定位  

  - 自动修复仅对可跳转链接生效，backtick 仅给出建议  

  - 输出 AUTO-FIXED / SUGGESTED / AMBIGUOUS / BROKEN 分类



**关键点说明：**  

- 只在“候选唯一”时自动修复，避免误改  

- backtick 不属于可点击跳转，默认只提示不改动  



**测试验证：**  

- [ ] 运行 `python tools/verify_postmortems_and_troubleshooting.py`，确认断链能被自动修复并分类输出  

- [ ] 运行 `python tools/verify_postmortems_and_troubleshooting.py --no-fix`，确认仅输出建议/断链列表  



**后续 TODO：**  

- 无



### [004] 2025-12-27 默认不以断链退出非 0



日期：2025-12-27  

状态：已完成  



**变更类型：**  

- 行为调整



**目标：**  

- 默认有断链/歧义也返回 0，便于在 IDE/调试中不中断  

- 通过 `--strict` 可恢复非 0 退出码



**触发原因：**  

- 调试时希望保留输出但避免异常退出提示



**涉及文件：**  

- tools/verify_postmortems_and_troubleshooting.py  

- docs/STAGE_PLAN.md



**改动概览：**  

- tools/verify_postmortems_and_troubleshooting.py  

  - 增加 `--strict` 参数  

  - 非严格模式下断链/歧义仅影响 STATUS，不影响退出码



**关键点说明：**  

- `STATUS: FAIL/WARN` 仍保留，可用于人工判断  

- 需要 CI/脚本严格失败时使用 `--strict`



**测试验证：**  

- [ ] 运行 `python tools/verify_postmortems_and_troubleshooting.py`，确认断链时退出码为 0  

- [ ] 运行 `python tools/verify_postmortems_and_troubleshooting.py --strict`，确认断链时退出码非 0  



**后续 TODO：**  

- 无



### [005] 2025-12-27 链接标题内路径自动修复



日期：2025-12-27  

状态：已完成  



**变更类型：**  

- 行为调整



**目标：**  

- 在链接标题（例如 `[``path``](...)`）中的路径也支持自动修复  

- 避免标题路径误报仅提示不修复



**触发原因：**  

- 标题路径同样会影响阅读与一致性，需要与目标路径同步



**涉及文件：**  

- tools/verify_postmortems_and_troubleshooting.py  

- docs/STAGE_PLAN.md



**改动概览：**  

- tools/verify_postmortems_and_troubleshooting.py  

  - 解析链接标题里的反引号路径，并允许自动修复  

  - 替换按字符区间进行，避免误改链接目标



**关键点说明：**  

- 只对“标题内的反引号路径”自动修复；其他反引号仍只提示  



**测试验证：**  

- [ ] 运行 `python tools/verify_postmortems_and_troubleshooting.py`，确认标题内路径能被自动修复  



**后续 TODO：**  

- 无



### [006] 2025-12-27 普通反引号路径按根目录兜底



日期：2025-12-27  

状态：已完成  



**变更类型：**  

- 行为调整



**目标：**  

- 普通反引号中的路径按“根目录”进行兜底校验，减少误报  

- 保留相对路径的原有校验逻辑



**触发原因：**  

- 反引号多用于描述项目内路径，通常以项目根目录为基准  



**涉及文件：**  

- tools/verify_postmortems_and_troubleshooting.py  

- docs/STAGE_PLAN.md



**改动概览：**  

- tools/verify_postmortems_and_troubleshooting.py  

  - 对 backtick/backtick_title 路径增加根目录存在性检查  

  - 仅在不以 `./` 或 `../` 开头时启用兜底



**关键点说明：**  

- 根目录兜底仅针对 backtick 路径，链接目标仍按“文件目录”解析  



**测试验证：**  

- [ ] 运行 `python tools/verify_postmortems_and_troubleshooting.py`，确认 `data_raw/...` 不再被误报  



**后续 TODO：**  

- 无



### [007] 2025-12-27 链接类型可配置与全量检验模式



日期：2025-12-27  

状态：已完成  



**变更类型：**  

- 行为调整



**目标：**  

- 支持通过配置文件扩展可检测的文件类型  

- 提供全量本地链接检测模式（any_local）



**触发原因：**  

- 需要在图片/视频/其他文件链接上做跳转校验  

- 便于后续统一管理配置文件



**涉及文件：**  

- tools/verify_postmortems_and_troubleshooting.py  

- tools/link_check_config.json  

- docs/STAGE_PLAN.md



**改动概览：**  

- tools/verify_postmortems_and_troubleshooting.py  

  - 读取 JSON 配置并支持 `--config` / `--any-local`  

  - 按扩展名白名单或全量模式进行链接校验  

- tools/link_check_config.json  

  - 默认扩展名列表（含图片/视频/文档类型）



**关键点说明：**  

- 默认按扩展名白名单校验，减少误报  

- `--any-local` 或 `any_local=true` 将忽略扩展名限制



**测试验证：**  

- [ ] 运行 `python tools/verify_postmortems_and_troubleshooting.py`，确认新增类型能被校验  

- [ ] 运行 `python tools/verify_postmortems_and_troubleshooting.py --any-local`，确认全量模式生效  



**后续 TODO：**  

- 无



### [009] 2026-01-03 增加 rag-accept 一键验收入口（核心序列 + 可选评测）



日期：2026-01-03  

状态：待确认  



**变更类型：**  

- 功能新增



**目标：**  

- 用单一命令固化 Stage-1 验收序列并返回单一退出码  

- 可选启用 Stage-1 verify 与 Stage-2 评测，默认保持轻量稳定  

- 统一产物落盘路径，便于回归与审计



**触发原因：**  

- 缺少 `rag-accept` 入口导致多机/多 venv 的命令序列易漂移



**涉及文件：**  

- src/mhy_ai_rag_data/tools/rag_accept.py  

- src/mhy_ai_rag_data/cli.py  

- pyproject.toml  

- tools/rag_accept.py  

- docs/howto/rag_accept.md  

- docs/howto/OPERATION_GUIDE.md  

- docs/howto/rag_status.md  

- docs/INDEX.md



**改动概览：**  

- src/mhy_ai_rag_data/tools/rag_accept.py  

  - 新增核心序列：stamp -> check -> snapshot -> rag-status --strict  

  - 支持 `--verify-stage1` 与 `--stage2/--stage2-full` 作为显式可选步骤  

  - 统一使用 profile/参数解析并通过 `sys.executable -m` 调用各子命令  

- src/mhy_ai_rag_data/cli.py / pyproject.toml  

  - 注册 `rag-accept` console_scripts 入口  

- tools/rag_accept.py  

  - 增加仓库根目录兼容入口  

- docs/howto/rag_accept.md / docs/howto/OPERATION_GUIDE.md / docs/howto/rag_status.md / docs/INDEX.md  

  - 补充一键验收说明与导航入口



**关键点说明：**  

- 默认只跑核心序列，避免引入非必要的网络/LLM依赖  

- Stage-2 默认仅检索评测，完整评测需显式启用 `--stage2-full`  

- 不改变现有工具行为，仅进行命令编排与入口固化



**测试验证：**  

- [ ] 运行 `rag-accept`，确认按顺序输出 stamp/check/snapshot/status  

- [ ] 运行 `rag-accept --verify-stage1`，确认生成 `stage1_verify.json`  

- [ ] 运行 `rag-accept --stage2`，确认生成 Stage-2 报告与 summary



**后续 TODO：**  

- 无



### [010] 2026-01-08 补齐 rag-init-eval-cases 入口注册链路



日期：2026-01-08  

状态：已完成  



**变更类型：**  

- Bug 修复



**目标：**  

- 统一 rag-init-eval-cases 与其他 rag-* 入口的注册方式（通过 cli.py）  

- 降低 entrypoints 漂移/遗漏风险  

- 保持行为与 python -m 一致  



**触发原因：**  

- rag-init-eval-cases 在注册时缺少 cli.py 入口，入口链路与其他 rag-* 不一致



**涉及文件：**  

- pyproject.toml  

- src/mhy_ai_rag_data/cli.py  

- docs/explanation/STAGE_PLAN.md



**改动概览：**  

- pyproject.toml  

  - rag-init-eval-cases 入口改为指向 `mhy_ai_rag_data.cli:init_eval_cases`  

- src/mhy_ai_rag_data/cli.py  

  - 新增 `init_eval_cases()`，以 runpy 执行 `mhy_ai_rag_data.tools.init_eval_cases`  

- docs/explanation/STAGE_PLAN.md  

  - 追加本次变更记录



**关键点说明：**  

- rag-* 入口统一经过 cli.py，行为与 `python -m` 方式保持一致  

- 仅调整入口映射，不改动 init_eval_cases.py 的功能逻辑



**测试验证：**  

- [ ] 运行 `python tools/check_cli_entrypoints.py`，确认能列出 `rag-init-eval-cases`  

- [ ] 运行 `rag-init-eval-cases -h`，确认帮助信息可达  



**后续 TODO：**  

- 无



### [002] 2026-01-05 Stage-2 引入分桶回归契约（oral vs official）



日期：2026-01-05  

状态：已完成  



**变更类型：**  

- 契约/可观测性增强（Stage-2 retrieval）



**目标：**  

- 将“口语 vs 官方术语导致 topK 漏召回”的风险面显式建模为 `bucket` 分桶  

- 让 `run_eval_retrieval.py` 产出 `buckets.*` 指标与 `warnings`，支持门禁触发器  

- 增强 `validate_eval_cases.py`：bucket 枚举校验 + pair_id 缺失提示（先 warning 后可升级为 error）



**涉及文件：**  

- `src/mhy_ai_rag_data/tools/run_eval_retrieval.py`  

- `src/mhy_ai_rag_data/tools/validate_eval_cases.py`  

- `src/mhy_ai_rag_data/tools/suggest_eval_case.py`  

- `src/mhy_ai_rag_data/tools/init_eval_cases.py`  

- `src/mhy_ai_rag_data/tools/view_stage2_reports.py`  

- `tools/*_README.md`（同步说明）  

- `docs/reference/EVAL_CASES_SCHEMA.md`  

- `docs/howto/ORAL_OFFICIAL_RETRIEVAL_REGRESSION.md`  

- `docs/INDEX.md`



**改动概览：**

- eval case 新增可选字段：`bucket/pair_id/concept_id`

- eval retrieval 报告 schema 升级：`schema_version=2`，新增 `buckets` 与 `warnings`

- Stage-2 汇总工具显示分桶指标（若存在）



### [011] 2026-01-08 补充 fsspec 依赖冲突处理说明



日期：2026-01-08  

状态：已完成  



**变更类型：**  

- 行为调整



**目标：**  

- 明确 CUDA 版 torch 安装后可能触发 datasets/fsspec 冲突  

- 给出最短可执行的修复命令  

- 避免误判为 torch 版本过高



**触发原因：**  

- 用户安装 CUDA torch 后出现 pip resolver 冲突警告



**涉及文件：**  

- docs/howto/OPERATION_GUIDE.md  

- docs/explanation/STAGE_PLAN.md



**改动概览：**  

- docs/howto/OPERATION_GUIDE.md  

  - Step 0：新增 fsspec 冲突提示与单指令约束安装



**关键点说明：**  

- 冲突来自 datasets 对 fsspec 的版本上限，不是 torch 版本问题  

- 以降级 fsspec 为默认稳态处理；升级 datasets 需自行确认兼容性



**测试验证：**  

- [ ] 在 `.venv_embed` 中运行 `python -m pip check`，确认无冲突  

- [ ] 重新执行相关命令后确保 `verify_torch_cuda.py` 通过（若 GPU 可用）



**后续 TODO：**  

- 无


