# Postmortems Index

> 目的：按“时间 + 主题 + 关键字”快速定位复盘文档。细节请进入各文档正文。


## 相关资产（跨复盘复用）
- [Postmortem 提示词模板（参考）](../reference/postmortem_prompt_template.md)
- [Lessons / 经验库（可迁移）](../explanation/LESSONS.md)
- [Preflight Checklist（重构/换机/换环境后必跑）](../howto/PREFLIGHT_CHECKLIST.md)

## 2026-01-07
- **docs↔code 对齐 + 缺失脚本补齐 + 文档门禁增强 + 输出可读性优化**
  - 文件：[`docs/postmortems/2026-01-07_postmortem_docs_code_alignment_and_doc_gates.md`](2026-01-07_postmortem_docs_code_alignment_and_doc_gates.md)
  - 关键字：docs / code alignment / doc-gate / placeholder / runtime artifacts / readability


## 2026-01-05
- **E2E 回归中 LLM HTTP POST 错误取证缺失与模型身份不准确**
  - 文件：[`docs/postmortems/2026-01-05_postmortem_llm_http_observability_and_model_identity.md`](2026-01-05_postmortem_llm_http_observability_and_model_identity.md)
  - 关键字：llm / http / observability / model identity / error_detail / /v1/models


## 2026-01-03
- **rag-accept 命令缺失与文档编码乱码复盘**
  - 文件：[`docs/postmortems/2026-01-03-21h_rag_accept_cli_missing_and_doc_encoding_mismatch.md`](2026-01-03-21h_rag_accept_cli_missing_and_doc_encoding_mismatch.md)
  - 关键字：rag-accept / console_scripts / entrypoints / UTF-8 / docs
- **pyproject 门禁与环境安装异常复盘（Issue1）**
  - 文件：[`docs/postmortems/2026-01-03_issue1_postmortem.md`](2026-01-03_issue1_postmortem.md)
  - 关键字：pyproject / ascii-only / preflight / run_ci_gates / pip install


## 2026-01-02
- **rag-status 对 chroma_db/ 的 mtime 进行判定导致对 check.json 判定过期**
  - 文件：[`docs/postmortems/2026-01-02-18h_status_step6_check_json_stale_false_positive.md`](2026-01-02-18h_status_step6_check_json_stale_false_positive.md)
  - 关键词: status / chroma_db / mtime / check.json / STALE

## 2025-12-30
- **本次问题排查总结（导入漂移 + 重构契约漂移 + 工具链 PATH 分叉）**
  - 文件: [`2025-12-30_units_pipeline_postmortem_import_contract_cli_entrypoints_rg.md`](2025-12-30_units_pipeline_postmortem_import_contract_cli_entrypoints_rg.md)
  - 关键词: src-layout / editable install / import drift / console_scripts / entrypoints / TypeError / signature drift / md refs / ripgrep / winget / PATH
- **CI 轻量环境 plan 阶段因 chromadb 缺失失败（可选依赖分层）**
  - 文件: [`2025-12-30_postmortem_ci_optional_dependency_chromadb.md`](2025-12-30_postmortem_ci_optional_dependency_chromadb.md)
  - 关键词: chromadb / .venv_ci / plan_chunks_from_units.py / ModuleNotFoundError / 可选依赖 / lazy import
- **pip embed 在 py3.14 下触发 NumPy Meson 构建失败**
  - 文件: [`2025-12-30_postmortem_pip_embed_py314_numpy_meson_fail.md`](2025-12-30_postmortem_pip_embed_py314_numpy_meson_fail.md)
  - 关键词: pip / embed / py3.14 / numpy / meson / metadata-generation-failed / ccache gcc / wheel

## 2025-12-29
- **Chroma 构建数量异常排查总结（expected=3728 vs got=4433）**
  - 文件: [`2025-12-29_chroma_build_postmortem_count_mismatch_3728_vs_4433.md`](2025-12-29_chroma_build_postmortem_count_mismatch_3728_vs_4433.md)
  - 关键词: chunks / chroma / plan
- **本次 Units 阶段失败排查总结（inventory→units 对账失败 + extract_units TypeError）**
  - 文件: [`2025-12-29_units_pipeline_postmortem_inventory_units_mismatch_and_extract_units_typeerror.md`](2025-12-29_units_pipeline_postmortem_inventory_units_mismatch_and_extract_units_typeerror.md)
  - 关键词: inventory.csv / text_units.jsonl / validate_rag_units / extract_units / __pycache__ / pyc / schemeB / profile runner / md refs

## 2025-12-28
- **LLM 请求被环境代理劫持到 127.0.0.1:7890 导致 ReadTimeout**
  - 文件: [`2025-12-28_postmortem_llm_proxy_timeout_7890.md`](2025-12-28_postmortem_llm_proxy_timeout_7890.md)
  - 关键词: ReadTimeout / read timeout=XX / llm_http_client.py

## 2025-12-27
- **LLM Read Timeout（LM Studio / OpenAI-compatible）**
  - 文件：[`2025-12-27_postmortem_llm_timeout_lmstudio.md`](2025-12-27_postmortem_llm_timeout_lmstudio.md)
  - 关键词：read timeout=120 / requests timeout / LM Studio / /v1/chat/completions
- **Postmortem: Torch not compiled with CUDA enabled, chroma_db 不一致 - 2025.12.27**
  - 文件：[`25-12-27_CPU-only_chroma-build_postmoretm.md`](25-12-27_CPU-only_chroma-build_postmoretm.md)
  - 关键词：CPU-only 构建 / PyTorch / cuda:0 / CUDA wheel / chroma_db / check 计数漂移
chat/completions

## 2025-12-26
- **Chroma 构建数量异常（expected_chunks 口径不一致：705 vs 694）**
  - 文件：[`2025-12-26_chroma_build_postmortem.md`](2025-12-26_chroma_build_postmortem.md)
  - 关键词：expected_chunks / include-media-stub / plan_chunks / media skip / source diff
