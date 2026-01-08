# 文档体系第一性原理与写作规范（可复用）

> 目标：把“项目说明文档”当成系统接口（Contract）来维护：可执行、可验证、可演进，避免重构后文档漂移。

## 目录
- [1) 第一性原理（5 条）](#1-第一性原理5-条)
- [2) 信息架构（Diátaxis 分型）](#2-信息架构diátaxis-分型)
- [3) 清晰/准确/必要（CAN）检查表](#3-清晰准确必要can检查表)
- [4) 文档与代码的边界（SSOT 规则）](#4-文档与代码的边界ssot-规则)
- [5) Docs-as-Code 门禁建议](#5-docs-as-code-门禁建议)
- [6) 可复制模板（Quickstart / How-to / Reference / Explanation / Postmortem）](#6-可复制模板quickstart--how-to--reference--explanation--postmortem)

## 1) 第一性原理（5 条）

1. **文档是系统对人的 API（Contract）**：必须写清输入/输出/不变量/退出码/产物路径，而不是只写解释。
2. **没有证据就等于没有（Evidence）**：关键结论必须能用命令复现，并能观察到可核验输出（stdout、JSON、文件计数）。
3. **变化率决定落点（Change Rate）**：越常变的越靠近代码与 CI；越稳定的越靠近入口（README）。
4. **最短成功路径优先（Golden Path）**：任何人都应能在 3–5 分钟内跑通一个 PASS 的基线回归。
5. **分层排障（Do not skip layers）**：先 data → plan → store → retrieve → LLM；排障写成决策树，不写成散文。

## 2) 信息架构（Diátaxis 分型）

- **Tutorials（教程）**：面向学习，带你从 0 到 1 跑通一次（强调顺序与理解）。
- **How-to（操作指南）**：面向任务，告诉你“如何做 X”（强调目标与步骤）。
- **Reference（参考）**：面向查阅，给出参数、契约、格式、约束（强调完整与精确）。
- **Explanation（解释）**：面向理解，解释架构、取舍与历史演进（强调因果与上下文）。

## 3) 清晰/准确/必要（CAN）检查表

- **清晰**：步骤可执行；每步有“做什么+为何+关键参数/注意”；避免混写多个故障/目标。
- **准确**：命令、路径、产物名与实际一致；标注版本/日期；引用权威来源（标准/官方/源码）。
- **必要**：只写完成目标所需信息；非关键背景移到“解释/附录”；避免重复内容。

## 4) 文档与代码的边界（SSOT 规则）

- README：入口 + Golden Path + 链接导航；不承载长篇操作细节。
- OPERATION / TROUBLESHOOTING：运行手册与决策树（SSOT for ops）。
- REFERENCE：契约/参数/格式（SSOT for contracts）。
- Postmortems：审计记录，不作为操作指南。
- Deprecated/Archive：只做重定向，避免断链。

## 5) Docs-as-Code 门禁建议

- 将 Golden Path 纳入 CI：安装 → 门禁脚本 → pytest 最小集成。
- 增加文档链接/锚点检查：避免目录或相对链接断裂。
- 对外接口（console_scripts、extras 名称、产物路径）出现于文档时必须在 CI 中验证。

## 6) 可复制模板（Quickstart / How-to / Reference / Explanation / Postmortem）

> 建议：在新项目中先落地模板，再填内容，减少“结构争论”成本。

### 6.1 Quickstart（Golden Path）
- 环境：Python 版本、OS、前置条件
- 安装：最短命令
- 回归：门禁脚本 + pytest
- 期望输出：PASS 标志、产物路径

### 6.2 How-to
- 目标：如何完成 X
- 前置：依赖/权限/输入文件
- 步骤：Step 1..N（每步含“做什么+为何+参数/注意”）
- 验收：如何判定成功
- 失败：常见失败与缓解

### 6.3 Reference
- 命令/参数表
- JSON/文件格式契约
- 退出码语义
- 版本兼容性

### 6.4 Explanation
- 架构图（数据流/控制流）
- 关键取舍与原因
- 变更历史与迁移策略

### 6.5 Postmortem
- 现象 → 证据 → RCA → 修复 → 预防 → 回归 → MRE
