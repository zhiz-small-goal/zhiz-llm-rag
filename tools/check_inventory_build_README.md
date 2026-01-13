# check_inventory_build_README


目的：为 `inventory.csv` 提供**可审计快照（snapshot）**与**前后差异对比（diff）**，用于定位“输入集合漂移”的根因。

## 适用场景
- 你怀疑 `inventory.csv` 行数/内容发生变化，导致下游 `extract_units/plan/build/check` 的结果波动。
- 你希望把某次 inventory 作为“基线证据”固化下来，并在后续运行中做可重复对比。

## 输入/输出
- 输入：`inventory.csv`（默认：仓库根目录下的 `inventory.csv`）
- 输出：
  - snapshot：`inventory_snapshot_v1` JSON（你指定路径）
  - diff：`inventory_diff_v1` JSON（你指定路径或自动生成）

## 运行命令

### 1) 生成快照
```cmd
python tools\check_inventory_build.py --snapshot-out data_processed\build_reports\inventory_snapshot.json
```

### 2) 对比当前 inventory 与历史快照
```cmd
python tools\check_inventory_build.py --compare-snapshot data_processed\build_reports\inventory_snapshot.json ^
  --diff-out data_processed\build_reports\inventory_diff.json
```

### 3) 严格模式（用于 CI/门禁）
```cmd
python tools\check_inventory_build.py --compare-snapshot data_processed\build_reports\inventory_snapshot.json --strict
```

### 可选：把 updated_at 的变化也视为“内容漂移”
```cmd
python tools\check_inventory_build.py --compare-snapshot data_processed\build_reports\inventory_snapshot.json --compare-updated-at
```

## 期望结果
- 无漂移：控制台输出 `compare=PASS`，diff 报告中 `has_diff=false`。
- 有漂移：diff 报告中会给出 `added/removed/changed_content/changed_meta/doc_id_changed` 的统计与样例。

## 常见失败与处理

1) `missing inventory.csv`
- 原因：未在仓库根目录运行，或文件路径不同。
- 处理：`python make_inventory.py` 先生成，或用 `--inventory <path>` 指定。

2) 对比结果变化很大，但你预期不应变化
- 原因：`data_raw/` 内容确有变动；或你删除过旧的 `inventory.csv` 导致 `doc_id` 全量刷新。
- 处理：优先看 diff 中的 `added/removed/changed_content`；如果主要是 `doc_id_changed`，说明输入集合本身可能未变但 ID 口径变了。

3) diff 报告被截断
- 原因：默认 `--max-details 200` 限制明细体积。
- 处理：增大 `--max-details`，或只看 `summary.counts` 与 `truncated.*_more`。
