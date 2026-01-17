---
title: 报告输出契约（Report Output Contract）
version: v2
last_updated: 2026-01-17
timezone: Asia/Shanghai
ssot: true
status: stable
---

# 报告输出契约（Report Output Contract）


> 目的：统一项目所有诊断报告的输出格式，确保可读性、可点击、可恢复、可排序。  
> 规则：本文档是报告输出的**单一真源（SSOT）**，所有报告工具必须遵循本契约。

## 目录

1. [概述](#概述)
2. [核心契约 - Item 模型](#核心契约---item-模型)
3. [输出通道规则](#输出通道规则)
4. [VS Code 可点击跳转](#vs-code-可点击跳转)
5. [高耗时任务特性](#高耗时任务特性)
6. [进度反馈规范](#进度反馈规范)
7. [迁移指南 v1→v2](#迁移指南-v1v2)
8. [参考实现](#参考实现)

---

## 概述

### 目标

- **可读性**：控制台输出优化滚动体验，Markdown 输出优化人类阅读
- **可点击**：Markdown 中的路径自动生成 VS Code 跳转链接
- **可恢复**：高耗时任务支持中断恢复
- **可排序**：基于数值 `severity_level` 统一排序，非字符串标签

### 演进历史

- **v1** (schema_version=1): 旧格式，基于 `status` 字符串，缺少统一 items 模型
- **v2** (schema_version=2): 当前稳定版本，items model + severity_level 排序

### 适用范围

本契约适用于所有**诊断类报告**，包括：
- 评估报告：`run_eval_retrieval`, `run_eval_rag`
- 门禁报告：`gate.py`
- 探测报告：`probe_llm_server`
- 检查报告：`check_*` 系列工具

**不适用**：
- 状态检查工具：`rag_status` (保持 v1，但兼容读取 v2)
- 构建元数据：`db_build_stamp.json` (可选升级)

---

## 核心契约 - Item 模型

### 顶层结构

```json
{
  "schema_version": 2,
  "generated_at": "2026-01-17T17:00:00+0800",
  "tool": "tool_name",
  "root": "/absolute/path/to/project",
  "summary": { ... },
  "items": [ ... ],
  "data": { ... }
}
```

#### 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `schema_version` | int | 固定值 `2` |
| `generated_at` | string | ISO 8601 时间戳（含时区） |
| `tool` | string | 工具名称，如 `"run_eval_rag"` |
| `root` | string | 项目根目录绝对路径 |
| `summary` | object | 聚合统计，见下文 |
| `items` | array | 诊断条目数组，见下文 |

#### 可选字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `data` | object | 工具特定的原始数据（向后兼容） |

---

### Item 模型

每个 `items` 数组元素必须包含以下字段：

```json
{
  "tool": "tool_name",
  "title": "item_identifier",
  "status_label": "PASS",
  "severity_level": 0,
  "message": "human readable message",
  "detail": { ... },
  "loc": "path/to/file.py:123:45",
  "loc_uri": "vscode://file//abs/path/to/file.py:123:45",
  "duration_ms": 1234
}
```

#### 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `tool` | string | 产生该 item 的工具名 |
| `title` | string | item 标识符（如 case_id, check_name） |
| `status_label` | string | 状态标签：`PASS`, `INFO`, `WARN`, `FAIL`, `ERROR` |
| `severity_level` | **int** | **严重度数值，越大越严重** |
| `message` | string | 人类可读描述 |

#### severity_level 映射表

| status_label | severity_level | 说明 |
|--------------|----------------|------|
| `PASS` | 0 | 通过 |
| `INFO` | 1 | 信息 |
| `WARN` | 2 | 警告 |
| `FAIL` | 3 | 失败 |
| `ERROR` | 4 | 错误 |

> **重要**: `severity_level` **必须**显式指定为 int。工具内部可提供兜底映射（`status_label → severity_level`），但外部调用者应始终提供显式值。

#### 可选字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `detail` | object | 详细信息（自由格式） |
| `loc` | string | 纯文本定位 `path:line:col` |
| `loc_uri` | string | VS Code 跳转 URI（自动生成） |
| `duration_ms` | int | 执行耗时（毫秒） |

---

### Summary 模型

由 `compute_summary(items)` 自动计算：

```json
{
  "overall_status_label": "FAIL",
  "overall_rc": 2,
  "max_severity_level": 3,
  "counts": {
    "PASS": 45,
    "INFO": 2,
    "WARN": 3,
    "FAIL": 5,
    "ERROR": 0
  },
  "total_items": 55
}
```

#### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `overall_status_label` | string | 整体状态（取最严重 item 的 status_label） |
| `overall_rc` | int | 推荐退出码：0=PASS, 1=INFO/WARN, 2=FAIL, 3=ERROR |
| `max_severity_level` | int | 最大 severity_level |
| `counts` | object | 各状态计数 |
| `total_items` | int | 总 item 数 |

---

## 输出通道规则

### 落盘文件（JSON + Markdown）

#### 排序规则
- **summary 在顶部**
- **items 按 severity_level 从大到小**（最严重在前）
- **同 severity_level 内稳定排序**（保持生成顺序）

#### 路径分隔符
- 统一使用 **`/`** （正斜杠）
- Windows 路径 `C:\foo\bar` → `C:/foo/bar`
- 相对路径 `src\tools\file.py` → `src/tools/file.py`

#### Markdown 渲染
- `loc` 保持纯文本：`src/mhy_ai_rag_data/tools/gate.py:123:45`
- `loc_uri` 自动生成为 VS Code 链接
- Markdown 格式：`[loc](loc_uri)`

示例：
```markdown
### 4.1 Errors (severity=4)

- **case_001** `[ERROR]`: LLM call failed
  - Location: [src/tools/run_eval_rag.py:234:15](vscode://file//f:/project/src/tools/run_eval_rag.py:234:15)
  - Message: connection timeout
```

---

### 控制台输出（stdout/stderr）

#### 排序规则
- **items 按 severity_level 从小到大**（最严重在最后）
- **summary 在末尾**
- **末尾额外空行** `\n\n`（便于滚动）

#### 空行规范
- 每个 item 之间：**1 行空行**
- severity 分组之间：**2 行空行**
- 禁止连续超过 2 行空行

#### 示例

```
[PASS] case_001: retrieval hit

[PASS] case_002: retrieval hit

[FAIL] case_003: retrieval miss

== Summary ==
PASS: 2
FAIL: 1
Overall: FAIL

<换行>
<换行>
```

---

## VS Code 可点击跳转

### loc vs loc_uri

| 字段 | 用途 | 格式 | 示例 |
|------|------|------|------|
| `loc` | 纯文本定位 | `path:line:col` | `src/tools/gate.py:123:45` |
| `loc_uri` | VS Code 跳转 | `vscode://file/<abs_path>:line:col` | `vscode://file//f:/project/src/tools/gate.py:123:45` |

### 自动生成

调用 `write_json_report()` 时自动处理：
1. 检测 item 中的 `loc` 字段
2. 解析为 `(file, line, col)`
3. 转为绝对路径
4. 生成 `loc_uri`
5. 写入 JSON

### 手动生成

```python
from mhy_ai_rag_data.tools.vscode_links import to_vscode_file_uri

uri = to_vscode_file_uri(
    repo_root=Path("/f:/project"),
    file_str="src/tools/gate.py",
    line=123,
    col=45
)
# 结果: "vscode://file//f:/project/src/tools/gate.py:123:45"
```

---

## 高耗时任务特性

### 即时落盘 + 可恢复

#### 事件流（Events Stream）

高耗时任务（如 `gate.py`, `run_eval_*`）支持：
- **append-only JSONL 写入** `.events.jsonl`
- **每条 item 立即 flush** 到磁盘
- **中断后可重建** 最终报告

#### 实现

```python
from mhy_ai_rag_data.tools.report_events import ItemEventsWriter

writer = ItemEventsWriter(
    path=Path("report.events.jsonl"),
    durability_mode="flush"  # none | flush | fsync
).open(truncate=True)

for item in items:
    writer.emit_item(item)  # 立即写入 + flush

writer.close()
```

#### Durability 模式

| 模式 | 持久性 | 性能 | 说明 |
|------|--------|------|------|
| `none` | 无保证 | 最快 | 仅写缓冲区，不 flush |
| `flush` | OS 缓冲 | 平衡 | **默认**，调用 `flush()` |
| `fsync` | 磁盘保证 | 最慢 | 调用 `fsync()`，带节流（默认1000ms） |

#### 中断处理

```python
try:
    for item in process():
        writer.emit_item(item)
except KeyboardInterrupt:
    # 追加终止 item
    writer.emit_item({
        "tool": "gate",
        "title": "INTERRUPTED",
        "status_label": "ERROR",
        "severity_level": 4,
        "message": "User interrupted (Ctrl+C)"
    })
    writer.close()
```

#### 恢复

```python
from mhy_ai_rag_data.tools.report_events import iter_item_events

items = list(iter_item_events(Path("report.events.jsonl")))
summary = compute_summary(items)
# 重建完整报告
```

---

### 原子性写入

Markdown 报告使用 **`.tmp` + `rename()`** 防止部分写入：

```python
def _atomic_write_text(path: Path, content: str):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)  # 原子性操作
```

---

## 进度反馈规范

### 控制参数

```bash
--progress {auto|on|off}  # 默认 auto
```

| 值 | 说明 |
|----|------|
| `auto` | TTY 交互式环境 **且** 非 CI 环境时启用 |
| `on` | 强制启用 |
| `off` | 强制禁用 |

### 判定逻辑

```python
def should_enable(mode: str) -> bool:
    if mode == "off":
        return False
    if mode == "on":
        return True
    # auto: 仅在 TTY 且非 CI 启用
    if not sys.stderr.isatty():
        return False
    if os.getenv("CI"):
        return False
    return True
```

### 输出通道

- **stderr**（不污染 stdout）
- **单行重绘**（`\r` 覆盖）
- **节流更新**（默认 200ms）

### 样式

#### 已知总量
```
[gate] ██████████████░░░░░░░░ 70% (7/10) ETA: 5s
```

#### 未知总量
```
[gate] ⠋ Step: check_chroma_build (3/?)
```

### 清理

任务完成后：
1. 清空进度行（`\r` + 空格）
2. 输出 1 次换行 `\n`
3. 后续输出 detail/summary

---

## 迁移指南 v1→v2

### 快速对照

| 项目 | v1 | v2 |
|------|----|----|
| schema_version | `1` 或 `"1"` | `2` (int) |
| 顶层状态 | `status` | `summary.overall_status_label` |
| 诊断条目 | `errors` 数组（非标准） | `items` 数组（标准模型） |
| 排序依据 | 字符串标签 | `severity_level` (int) |
| 路径分隔符 | 平台相关 | 统一 `/` |
| VS Code 跳转 | 不支持 | `loc_uri` 自动生成 |

### 改造步骤

#### 1. 修改 schema_version

```python
# v1
report = {"schema_version": 1, "status": "FAIL", ...}

# v2
from mhy_ai_rag_data.tools.report_contract import compute_summary

items = [...]  # 见下一步
summary = compute_summary(items)
report = {
    "schema_version": 2,
    "generated_at": iso_now(),
    "tool": "my_tool",
    "root": str(root),
    "summary": summary.to_dict(),
    "items": items
}
```

#### 2. 转换诊断条目为 items

```python
# v1: 自由格式
errors = [
    {"code": "E001", "message": "something wrong"}
]

# v2: 标准 item 模型
items = [
    {
        "tool": "my_tool",
        "title": "E001",
        "status_label": "FAIL",
        "severity_level": 3,  # 必须显式指定
        "message": "something wrong"
    }
]
```

#### 3. 使用 write_json_report

```python
# v1
from mhy_ai_rag_data.tools.reporting import write_report
write_report(report, json_out=args.json_out, default_name="report.json")

# v2
from mhy_ai_rag_data.tools.report_order import write_json_report
write_json_report(Path(args.json_out or "report.json"), report)
```

#### 4. 保留原始数据（向后兼容）

```python
report = {
    "schema_version": 2,
    "summary": summary.to_dict(),
    "items": items,
    "data": {
        # 保留 v1 格式数据供旧消费者使用
        "errors": errors,
        "metrics": metrics,
        ...
    }
}
```

---

## 参考实现

### 核心模块

| 模块 | 职责 |
|------|------|
| `report_contract.py` | Item 模型定义、summary 计算 |
| `report_order.py` | 排序、路径归一化、write_json_report |
| `view_gate_report.py` | 控制台+Markdown 渲染 |
| `report_events.py` | 事件流写入/恢复 |
| `runtime_feedback.py` | 进度条/spinner |
| `vscode_links.py` | VS Code URI 生成 |

### 已升级工具

| 工具 | 版本 | 说明 |
|------|------|------|
| `gate.py` | v2 | 门禁报告 |
| `run_eval_retrieval.py` | v2 | 检索评估 |
| `run_eval_rag.py` | v2 | RAG 评估 |
| `probe_llm_server.py` | v2 | LLM 探测 |
| `rag_status.py` | v1 (读v1/v2) | 状态检查（特例） |

### 示例代码

完整示例见：
- [gate.py L540-680](file:///f:/zhiz-c++/zhiz-llm-rag/src/mhy_ai_rag_data/tools/gate.py#L540-L680)
- [run_eval_retrieval.py L347-419](file:///f:/zhiz-c++/zhiz-llm-rag/src/mhy_ai_rag_data/tools/run_eval_retrieval.py#L347-L419)

---

## 常见问题

### Q: 为什么 severity_level 必须是 int？
A: 数值排序稳定且高效，避免字符串比较的歧义（如 "FAIL" vs "ERROR" 谁更严重）。

### Q: 可以省略 severity_level 吗？
A: 不建议。虽然有兜底映射（`status_label → severity_level`），但显式指定确保准确性。

### Q: rag_status 为什么还用 v1？
A: rag_status 是"状态检查工具"而非"诊断报告工具"，其输出更侧重"进度+建议"。已升级其检查逻辑以兼容 v1/v2 报告。

### Q: data 块是必须的吗？
A: 可选。但强烈建议保留原始数据用于向后兼容和调试。

### Q: 如何验证 v2 报告？
A: 运行 `python tools/verify_reports_schema.py <report.json>`

---

## 版本历史与变更日志

### v2.0 (2026-01-17)
- 初始稳定版本
- 核心特性：
  - schema_version=2 契约定义
  - Item 模型统一（tool, title, status_label, severity_level, message）
  - severity_level 数值排序（int，非字符串）
  - compute_summary() 自动计算
  - VS Code 跳转 loc_uri 自动生成
  - 路径归一化统一使用 `/`
  - 高耗时任务支持（events stream + durability modes）
  - 进度反馈规范（--progress auto|on|off）
- 参考实现：gate.py, run_eval_retrieval.py, run_eval_rag.py, probe_llm_server.py
- 迁移指南：v1 → v2 完整流程

### v1.x (历史)
- 旧格式（schema_version=1）
- 已废弃，不再推荐使用

---

**维护**: 项目团队  
**反馈**: 请在 PR/Issue 中提出  
**相关文档**: [`HANDOFF.md`](../explanation/HANDOFF.md) | [`reference.yaml`](reference.yaml)
