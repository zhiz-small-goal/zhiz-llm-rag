# Report Output Upgrade Progress

截至：2026-01-18

## 已完成

- [x] 统一报告契约 schema_version=2（items + severity_level）
- [x] 统一排序/可点击 loc_uri（VS Code 跳转）
- [x] events.jsonl 事件流 + 最终渲染（高耗时任务可恢复）
- [x] runtime_feedback（progress/spinner）输出到 stderr
- [x] view_report.py / view_gate_report.py 渲染规则（console 轻->重，summary 末尾，末尾空行）

## 2.1 “全局一致”迁移（脚本级）

目标：每个脚本最终调用 `write_report_bundle(...)`（或等价入口），并将运行时进度输出到 stderr。

本批次已迁移（调用 write_report_bundle）

- src/mhy_ai_rag_data/tools/audit_baseline_tools.py
- src/mhy_ai_rag_data/tools/capture_rag_env.py
- src/mhy_ai_rag_data/tools/check_docs_conventions.py
- src/mhy_ai_rag_data/tools/check_inventory_build.py（compare 分支输出已统一为 report bundle；snapshot 仍为专用 schema）
- src/mhy_ai_rag_data/tools/check_repo_health_files.py
- src/mhy_ai_rag_data/tools/check_tools_layout.py
- src/mhy_ai_rag_data/tools/compare_stage1_baseline_snapshots.py
- src/mhy_ai_rag_data/tools/plan_chunks_from_units.py
- src/mhy_ai_rag_data/tools/probe_llm_server.py
- src/mhy_ai_rag_data/tools/run_profile_with_timing.py（新增 --progress auto|on|off）
- src/mhy_ai_rag_data/tools/snapshot_stage1_baseline.py（保留 baseline snapshot schema；新增 snapshot_report.json/.md）
- src/mhy_ai_rag_data/tools/update_postmortems_index.py（json_out 改为 write_report_bundle）
- src/mhy_ai_rag_data/tools/verify_stage1_pipeline.py

## 待确认（可选）

- gate.py：已具备“等价统一输出入口”，未强制改写为 `write_report_bundle`（避免破坏 gate 的 events/阶段输出语义）。
