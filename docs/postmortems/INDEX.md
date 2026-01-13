# Postmortems Index


> 目的：按“时间 + 主题 + 关键字”快速定位复盘文档。细节请进入各文档正文。


## 相关资产（跨复盘复用）
- [Postmortem 提示词模板（参考）](../reference/postmortem_prompt_template.md)
- [Lessons / 经验库（可迁移）](../explanation/LESSONS.md)
- [Preflight Checklist（重构/换机/换环境后必跑）](../howto/PREFLIGHT_CHECKLIST.md)

<!-- AUTO-GENERATED:BEGIN postmortems-index -->
## 2026-01-11
- **Postmortem｜check_public_release_hygiene：rc=2（FAIL）与 report_written 信号误读**
  - 文件：[`docs/postmortems/2026-01-11_postmortem_public_release_hygiene_rc2_and_report_written_signal.md`](2026-01-11_postmortem_public_release_hygiene_rc2_and_report_written_signal.md)
  - 关键字：check_public_release_hygiene / rc=2 / FAIL / report_written / exitcode / Desktop / fallback / file-scope / respect-gitignore / public release hygiene
- **Postmortem｜门禁治理架构：SSOT → Gate 单入口 → JSON Schema →（可选）Conftest Policy**
  - 文件：[`docs/postmortems/2026-01-11_postmortem_ssot_gate_schema_policy_single_entrypoint.md`](2026-01-11_postmortem_ssot_gate_schema_policy_single_entrypoint.md)
  - 关键字：SSOT / gate / single entry / JSON Schema / conftest / rego / policy / CI only gate / drift guardrails


## 2026-01-09
- **Postmortem：开源项目补齐仓库健康文件（CHANGELOG/CITATION/.editorconfig + CoC 联系方式）**
  - 文件：[`docs/postmortems/2026-01-09_postmortem_open_source_repo_health_files.md`](2026-01-09_postmortem_open_source_repo_health_files.md)
  - 关键字：开源项目补齐仓库健康文件 / CHANGELOG / CITATION / editorconfig / CoC / 联系方式 / open / source / repo / health / files

## 2026-01-08
- **Postmortem｜公开项目的前置检查（Public Release Preflight）**
  - 文件：[`docs/postmortems/2026-01-08_postmortem_public_release_preflight.md`](2026-01-08_postmortem_public_release_preflight.md)
  - 关键字：公开项目的前置检查 / Public / Release / Preflight / public / release / preflight
- **Postmortem: tools/分层与全量 wrapper 生成门禁自举失败 + 退出码契约对齐**
  - 文件：[`docs/postmortems/2026-01-08_tools_layout_wrapper_gen_exitcode_contract.md`](2026-01-08_tools_layout_wrapper_gen_exitcode_contract.md)
  - 关键字：分层与全量 / wrapper / 生成门禁自举失败 / 退出码契约对齐 / layout / gen / exitcode / contract

## 2026-01-07
- **2026-01-07｜docs↔code 对齐 + 缺失脚本补齐 + 文档门禁增强 + 输出可读性优化｜Postmortem**
  - 文件：[`docs/postmortems/2026-01-07_postmortem_docs_code_alignment_and_doc_gates.md`](2026-01-07_postmortem_docs_code_alignment_and_doc_gates.md)
  - 关键字：2026 / 01 / 07 / code / 对齐 / 缺失脚本补齐 / 文档门禁增强 / 输出可读性优化 / alignment / gates

## 2026-01-05
- **事故复盘：E2E 回归中 LLM HTTP POST 错误取证缺失与模型身份不准确 — 2026-01-05**
  - 文件：[`docs/postmortems/2026-01-05_postmortem_llm_http_observability_and_model_identity.md`](2026-01-05_postmortem_llm_http_observability_and_model_identity.md)
  - 关键字：事故复盘 / E2E / 回归中 / LLM / HTTP / POST / 错误取证缺失与模型身份不准确 / 2026 / 01 / 05 / llm / http

## 2026-01-03
- **21h rag accept cli missing and doc encoding mismatch**
  - 文件：[`docs/postmortems/2026-01-03-21h_rag_accept_cli_missing_and_doc_encoding_mismatch.md`](2026-01-03-21h_rag_accept_cli_missing_and_doc_encoding_mismatch.md)
  - 关键字：21h / rag / accept / cli / missing / encoding / mismatch
- **2026-01-03 pyproject 门禁与环境安装异常复盘（Issue1）**
  - 文件：[`docs/postmortems/2026-01-03_issue1_postmortem.md`](2026-01-03_issue1_postmortem.md)
  - 关键字：2026 / 01 / 03 / pyproject / 门禁与环境安装异常复盘 / Issue1 / issue1

## 2026-01-02
- **18h status step6 check json stale false positive**
  - 文件：[`docs/postmortems/2026-01-02-18h_status_step6_check_json_stale_false_positive.md`](2026-01-02-18h_status_step6_check_json_stale_false_positive.md)
  - 关键字：18h / status / step6 / check / json / stale / false / positive

## 2025-12-30
- **postmortem ci optional dependency chromadb**
  - 文件：[`docs/postmortems/2025-12-30_postmortem_ci_optional_dependency_chromadb.md`](2025-12-30_postmortem_ci_optional_dependency_chromadb.md)
  - 关键字：ci / optional / dependency / chromadb
- **postmortem pip embed py314 numpy meson fail**
  - 文件：[`docs/postmortems/2025-12-30_postmortem_pip_embed_py314_numpy_meson_fail.md`](2025-12-30_postmortem_pip_embed_py314_numpy_meson_fail.md)
  - 关键字：pip / embed / py314 / numpy / meson / fail
- **units pipeline postmortem import contract cli entrypoints rg**
  - 文件：[`docs/postmortems/2025-12-30_units_pipeline_postmortem_import_contract_cli_entrypoints_rg.md`](2025-12-30_units_pipeline_postmortem_import_contract_cli_entrypoints_rg.md)
  - 关键字：src-layout, editable install, import drift, console_scripts, entrypoints, TypeError, signature drift, md refs, ripgrep, winget, PATH

## 2025-12-29
- **chroma build postmortem count mismatch 3728 vs 4433**
  - 文件：[`docs/postmortems/2025-12-29_chroma_build_postmortem_count_mismatch_3728_vs_4433.md`](2025-12-29_chroma_build_postmortem_count_mismatch_3728_vs_4433.md)
  - 关键字：chroma build, expected_chunks, count mismatch, residual data, plan-driven, include_media_stub, schemeB
- **units pipeline postmortem inventory units mismatch and extract units typeerror**
  - 文件：[`docs/postmortems/2025-12-29_units_pipeline_postmortem_inventory_units_mismatch_and_extract_units_typeerror.md`](2025-12-29_units_pipeline_postmortem_inventory_units_mismatch_and_extract_units_typeerror.md)
  - 关键字：inventory.csv, text_units.jsonl, validate_rag_units, extract_units, __pycache__, pyc, schemeB, profile runner, md refs

## 2025-12-28
- **Postmortem: LLM 请求被环境代理劫持到 127.0.0.1:7890 导致 ReadTimeout（LM Studio）— 2025-12-28**
  - 文件：[`docs/postmortems/2025-12-28_postmortem_llm_proxy_timeout_7890.md`](2025-12-28_postmortem_llm_proxy_timeout_7890.md)
  - 关键字：LM Studio, proxy hijack, 127.0.0.1:7890, ReadTimeout, requests trust_env, NO_PROXY, OpenAI-compatible, /v1/chat/completions

## 2025-12-27
- **Postmortem: RAG 闭环问答阶段 LLM Read Timeout（LM Studio）— 2025-12-27**
  - 文件：[`docs/postmortems/2025-12-27_postmortem_llm_timeout_lmstudio.md`](2025-12-27_postmortem_llm_timeout_lmstudio.md)
  - 关键字：LM Studio, read timeout=120, requests timeout, OpenAI-compatible, /v1/chat/completions, long generation
- **Postmortem: Torch not compiled with CUDA enabled, chroma_db 不一致 - 2025.12.27**
  - 文件：[`docs/postmortems/25-12-27_CPU-only_chroma-build_postmoretm.md`](25-12-27_CPU-only_chroma-build_postmoretm.md)
  - 关键字：CPU-only构建， PyTorch,  cuda:0, CUDA wheel, chroma_db, check计数漂移

## 2025-12-26
- **本次 Chroma 构建数量异常排查总结（705 vs 694）**
  - 文件：[`docs/postmortems/2025-12-26_chroma_build_postmortem.md`](2025-12-26_chroma_build_postmortem.md)
  - 关键字：chroma build, expected_chunks, count mismatch, media skip, include-media-stub, chunk_plan
<!-- AUTO-GENERATED:END postmortems-index -->
