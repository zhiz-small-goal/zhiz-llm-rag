# 2026-01-03-21h_rag_accept_cli_missing_and_doc_encoding_mismatch.md目录：
- [2026-01-03-21h_rag_accept_cli_missing_and_doc_encoding_mismatch.md目录：](#2026-01-03-21h_rag_accept_cli_missing_and_doc_encoding_mismatchmd目录)
  - [0) 元信息](#0-元信息)
  - [1) 现象与触发](#1-现象与触发)
    - [1.1 现象：rag-accept 提示“不是内部或外部命令”](#11-现象rag-accept-提示不是内部或外部命令)
    - [1.2 现象：文档中新增说明出现“????”乱码](#12-现象文档中新增说明出现乱码)
    - [1.3 触发：尝试使用 rag-accept 与补文档说明](#13-触发尝试使用-rag-accept-与补文档说明)
  - [2) 问题定义](#2-问题定义)
  - [3) 关键证据与排查过程](#3-关键证据与排查过程)
    - [3.1 入口点缺失：pyproject 没有 rag-accept](#31-入口点缺失pyproject-没有-rag-accept)
    - [3.2 代码与文档不一致：仅文档提及 rag-accept](#32-代码与文档不一致仅文档提及-rag-accept)
    - [3.3 文档乱码被写入：实际内容变为“?”](#33-文档乱码被写入实际内容变为)
  - [4) 根因分析（RCA）](#4-根因分析rca)
    - [4.1 根因：入口补全步骤缺失](#41-根因入口补全步骤缺失)
    - [4.2 根因：非 UTF-8 写入链导致中文被替换为 ?](#42-根因非-utf-8-写入链导致中文被替换为)
  - [5) 修复与处置（止血→稳定修复→工程固化）](#5-修复与处置止血稳定修复工程固化)
    - [5.1 止血](#51-止血)
    - [5.2 稳定修复](#52-稳定修复)
    - [5.3 工程固化](#53-工程固化)
  - [6) 预防与回归测试](#6-预防与回归测试)
  - [7) 最小可复现（MRE）](#7-最小可复现mre)
  - [8) 一句话复盘](#8-一句话复盘)
  - [9) 方法论迁移（可复用工程经验）](#9-方法论迁移可复用工程经验)


## 0) 元信息
- [Fact] 发生日期：2026-01-03（用户交互当日）。  
- [Fact] 仓库路径：`<REPO_ROOT>
- [Fact] 关联文件：`pyproject.toml`、`src/mhy_ai_rag_data/cli.py`、`src/mhy_ai_rag_data/tools/rag_accept.py`、`docs/howto/rag_accept.md`、`docs/howto/OPERATION_GUIDE.md`、`docs/howto/rag_status.md`、`docs/INDEX.md`。  
- [Inference] 当时的 Python 版本与 venv 状态未提供，需要以实际现场日志为准。

---

## 1) 现象与触发
### 1.1 现象：rag-accept 提示“不是内部或外部命令”
- [Fact] 用户在本机 shell 中执行 `rag-accept`，提示“不是内部或外部命令，也不是可运行的程序”。

### 1.2 现象：文档中新增说明出现“????”乱码
- [Fact] `docs/howto/OPERATION_GUIDE.md`、`docs/howto/rag_status.md`、`docs/INDEX.md` 与 `docs/explanation/STAGE_PLAN.md` 中新增的中文出现 “????”。

### 1.3 触发：尝试使用 rag-accept 与补文档说明
- [Fact] 触发点来自“希望有一键验收入口”的需求，因此先尝试执行命令并同步补充文档。

---

## 2) 问题定义
需要一条**稳定可达**的 `rag-accept` 验收入口，但实际没有注册 console_scripts，导致命令不可用；同时文档更新在非 UTF-8 写入链中被破坏，影响可读性与复用性。

---

## 3) 关键证据与排查过程
### 3.1 入口点缺失：pyproject 没有 rag-accept
- [Fact] `pyproject.toml` 的 `[project.scripts]` 中未包含 `rag-accept`（导致命令无法在 PATH 中出现）。

### 3.2 代码与文档不一致：仅文档提及 rag-accept
- [Fact] 全仓搜索 `rag-accept` 只命中文档内容，未命中任何实现代码。

### 3.3 文档乱码被写入：实际内容变为“?”
- [Fact] 新增段落被写成 “????”，说明写入链没有保持 UTF-8。

---

## 4) 根因分析（RCA）
### 4.1 根因：入口补全步骤缺失
- [Inference] `rag-accept` 作为规划动作仅在文档中被提及，缺少“入口注册 + wrapper + 说明文档”这一工程化闭环。
- 如何验证：检查 `pyproject.toml` 与 `src/mhy_ai_rag_data/cli.py` 是否包含对应入口即可确认。

### 4.2 根因：非 UTF-8 写入链导致中文被替换为 ?
- [Inference] 在 Windows/PowerShell 默认代码页下，通过 here-string 传递中文给脚本时发生编码降级，导致“?”写入文件。
- 如何验证：对比相同文本在“明确指定 UTF-8”的写入链（编辑器保存或 `encoding="utf-8"`）是否能正常落盘。

---

## 5) 修复与处置（止血→稳定修复→工程固化）
### 5.1 止血
- 使用现有命令手动串行执行核心序列：`rag-stamp` → `rag-check` → `snapshot_stage1_baseline` → `rag-status --strict`。

### 5.2 稳定修复
- 新增 `rag-accept` 实现与 console_scripts 入口，确保命令可达。  
- 增加 `tools/rag_accept.py` 兼容入口，并补充专门说明文档与导航链接。

### 5.3 工程固化
- 明确“文档更新必须保持 UTF-8”的编辑规范。  
- 在合并前执行 `tools/check_cli_entrypoints.py`，确保 entrypoints 完整。

---

## 6) 预防与回归测试
- [ ] 执行 `python tools/check_cli_entrypoints.py`，确认 `rag-accept` 能被发现。  
- [ ] 执行 `rag-accept`，确认核心序列顺序与退出码稳定。  
- [ ] 用编辑器或脚本显式 UTF-8 保存文档，再检查是否出现 “????”。

---

## 7) 最小可复现（MRE）
1) 在不含 `rag-accept` entrypoint 的环境执行 `rag-accept` → 触发“命令找不到”。  
2) 在未设置 UTF-8 的写入链中写入中文文本 → 文档出现 “????”。

---

## 8) 一句话复盘
**缺少 entrypoint 的“只写文档不落实现”会导致命令不可达，而非 UTF-8 写入链会破坏文档可复用性。**

---

## 9) 方法论迁移（可复用工程经验）
- 任意“新命令/新入口”必须完成三件事：入口注册、兼容 wrapper、使用说明。  
- 文档编写链路应统一为 UTF-8，避免跨平台字符集差异。  
- 以“单一命令 + 单一退出码”固化验收流程，便于迁移到其它工程。  
