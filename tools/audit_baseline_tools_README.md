# `audit_baseline_tools.py` 使用说明（全仓静态审计：查找基线/快照/哈希/报告工具，避免冗余）

> **适用日期**：2025-12-28  
> **脚本位置建议**：`tools/audit_baseline_tools.py`  
> **输出位置**：默认写入 `data_processed/build_reports/audit_baseline_tools.json`

---

## 1. 目的与适用场景

该脚本用于对仓库做一次“静态扫描”，快速回答：

- 项目里是否已经存在某类功能（例如 baseline/snapshot/env_report/sha256/manifest）的脚本？
- 是否存在与某个新引入工具能力重叠的实现，从而需要合并/删除？

它通过关键词与典型实现痕迹定位候选文件，输出“命中行”清单，帮助你在 1～2 分钟内把排查范围缩小到少量文件。

---

## 2. 工具做什么 / 不做什么

### 2.1 做什么（Facts）

- 递归扫描 `<root>` 下常见文本文件（`.py/.md/.json/.yaml/...`）
- 跳过 `.venv`、`__pycache__`、`.git` 等目录
- 对每行文本匹配一组正则模式（默认包含 baseline/snapshot/sha256/hashlib/pip freeze 等）
- 输出：
  - stdout：`file:line: text`
  - JSON：包含 patterns、命中列表、统计计数

### 2.2 不做什么（Non-goals）

- 不保证语义等价（它只告诉你“在哪里出现过这些词/实现痕迹”）
- 不修改仓库文件
- 不执行任何项目脚本（纯静态扫描）

---

## 3. 快速开始

```bash
python tools/audit_baseline_tools.py --root .
```

你会得到：

- 控制台：命中摘要与命中行清单
- 文件：`data_processed/build_reports/audit_baseline_tools.json`

---

## 4. 参数详解

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--root` | `.` | 仓库根目录 |
| `--out` | `data_processed/build_reports/audit_baseline_tools.json` | 输出 JSON（相对 root） |
| `--pattern` | 可重复 | 追加自定义正则；可多次使用 |

示例：额外扫描 `stage1_baseline_snapshot` 与 `env_report.json`：

```bash
python tools/audit_baseline_tools.py --root . --pattern "stage1_baseline_snapshot" --pattern "env_report\.json"
```

---

## 5. 输出 JSON 说明

- `counts.files_scanned`：扫描的文件数量
- `counts.files_matched`：命中文件数量
- `counts.hit_lines`：命中行数
- `matches[]`：
  - `file`：相对路径
  - `hits[]`：每个命中包含 `line`、`pattern`、`text`

---

## 6. 常见用法建议

- 引入新工具前：先跑一次，确认仓库中是否已有类似实现。
- 清理/合并工具：根据命中结果，优先打开“命中 sha256/hashlib/manifest 的文件”，一般更接近功能实现核心。
- 维护模式：把该脚本作为“工具目录治理”的一部分，避免脚本越堆越多而无人能解释差异。

---

## 7. 退出码

- 退出码 `0`：完成扫描并写出报告（即使命中为空也算成功）
