---
title: rag-accept 使用说明
version: v1.0
last_updated: 2026-01-12
---

# rag-accept 使用说明

## 目录
- [目标](#目标)
- [核心用法](#核心用法)
- [可选：Stage-1 verify（默认不跑 LLM）](#可选stage-1-verify默认不跑-llm)
- [可选：Stage-2 评测（更稳的默认）](#可选stage-2-评测更稳的默认)
- [参数说明（常用）](#参数说明常用)
- [产物路径（默认）](#产物路径默认)

## 目标
把 Stage-1 的“验收序列”固化成一条命令，并返回单一退出码，降低多机/多 venv 的操作漂移。

默认只跑**核心序列**（无行为变化，等价于手动串行执行）：
1) `rag-stamp`
2) `rag-check`
3) `snapshot_stage1_baseline`
4) `rag-status --strict`

其它步骤需要显式开启（例如 `verify` / Stage-2 评测）。

---

## 核心用法
```cmd
rag-accept
```

未安装 entrypoint 时可用：
```cmd
python -m mhy_ai_rag_data.tools.rag_accept
python tools/rag_accept.py
```

## 可选：Stage-1 verify（默认不跑 LLM）
```cmd
rag-accept --verify-stage1
```

如需连 LLM 探测：
```cmd
rag-accept --verify-stage1 --verify-llm --base-url http://127.0.0.1:8000/v1
```

## 可选：Stage-2 评测（更稳的默认）
只跑检索评测（retrieval-only）：
```cmd
rag-accept --stage2
```

完整评测（retrieval + rag，需 LLM）：
```cmd
rag-accept --stage2-full --base-url http://127.0.0.1:8000/v1
```

---

## 参数说明（常用）
- `--root`：项目根目录（默认自动检测）
- `--profile`：构建 profile（默认尝试 `build_profile_schemeB.json`）
- `--db` / `--collection` / `--plan` / `--reports-dir` / `--state-root`：覆盖 profile 中的路径
- `--verify-stage1`：启用 Stage-1 verify
- `--verify-llm`：verify 时启用 LLM 探测（默认跳过）
- `--stage2`：启用 Stage-2 检索评测
- `--stage2-full`：启用 Stage-2 完整评测（需要 LLM）
- `--cases`：评测用例路径（默认 `data_processed/eval/eval_cases.jsonl`）
- `--embed-model` / `--device`：Stage-2 评测的 embedding 相关参数
- `--base-url`：LLM 服务地址（verify/Stage-2 rag 需要）

---

## 产物路径（默认）
- `data_processed/build_reports/check.json`
- `data_processed/build_reports/stage1_baseline_snapshot.json`
- `data_processed/build_reports/status.json`
- Stage-2（开启时）：
  - `data_processed/build_reports/eval_cases_validation.json`
  - `data_processed/build_reports/eval_retrieval_report.json`
  - `data_processed/build_reports/eval_rag_report.json`（仅 `--stage2-full`）
  - `data_processed/build_reports/stage2_summary.md`
