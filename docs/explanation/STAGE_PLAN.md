# STAGE_PLAN

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
