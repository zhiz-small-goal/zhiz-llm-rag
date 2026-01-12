---
title: validate_review_spec 使用说明
version: v1.0
last_updated: 2026-01-12
---

# validate_review_spec 使用说明

## 目的
对审查规范 SSOT 执行结构校验，并校验生成产物与 SSOT 一致，用于 PR/CI 门禁，防止口径漂移。

## 输入 / 输出
- 输入：`docs/reference/review/review_spec.v1.json`（SSOT）
- 输出：无（仅 stdout 诊断与退出码）；同时会读取 `docs/reference/review/REVIEW_SPEC.md` 做一致性比较

## 运行命令
```bash
# 默认路径（推荐在仓库根目录执行）
python tools/validate_review_spec.py

# 显式指定仓库根目录
python tools/validate_review_spec.py --root .
```

## 期望结果
- 退出码 `0`：PASS（结构合法且生成文档一致）
- 退出码 `2`：FAIL（缺字段/枚举错误/优先级覆盖缺失/生成文档不一致）
- 退出码 `3`：ERROR（脚本异常）

## 常见失败与处理
1) 现象：`missing required key` / `meta.version not semver`  
   原因：SSOT 字段缺失或格式不符合约束  
   缓解：按输出修复字段（版本遵循 SemVer；日期为 YYYY-MM-DD）  
   备选：若需要新增维度，优先放入 `extensions` 预留区

2) 现象：`priority_order not covered by checklists`  
   原因：优先级列表中的维度没有对应 checklist 区块  
   缓解：补齐对应 area（或调整 priority_order 口径）  
   备选：先在 `extensions` 里标注迁移说明，并在下一次改动补齐

3) 现象：`generated doc out-of-date`  
   原因：SSOT 变更后未运行生成器刷新 `REVIEW_SPEC.md`  
   缓解：运行 `python tools/generate_review_spec_docs.py --write` 并提交生成文件  
   备选：如果你暂时不想提交生成文件，需要同时从门禁中移除该一致性检查（不推荐）
