---
title: Contributing
version: 0.1
last_updated: 2026-01-09
---

# Contributing

当前阶段：维护者以独立开发为主，目标是保持项目节奏与一致性，因此 **通常不接收外部代码贡献（PR）**。

## 我们欢迎的输入（低打扰、高信噪比）

- **可复现 Bug 报告**：请使用 Issues 的 Bug 表单提交（必须包含版本/commit、MRE、日志）
- **问答**：请使用 Discussions → Q&A（社区可自助解答）
- **想法**：请使用 Discussions → Ideas（不承诺采纳）

## 不在范围内

- 仅“无法运行/怎么用”的泛问（请先看 README/文档，并到 Discussions 提问）
- 需要维护者提供定制化支持或远程协助的请求
- 未提供复现信息的缺陷报告

## 未来开放贡献的方向（占位）

当以下条件满足时，可能开放外部 PR：
- CI/Gates 稳定并文档化
- 贡献者可以一键跑通最小回归
- 代码结构与接口契约稳定（减少维护者 review 成本）

在此之前，如果你认为某个修复非常关键，请先创建 Bug Issue 讨论复现与验收口径。

## 约定
- 社区互动受 CODE_OF_CONDUCT.md 约束。
- 安全漏洞不要公开发 Issue, 请通过 Security Policy 中的私密渠道报告。
  - url: "https://github.com/zhiz-small-goal/zhiz-llm-rag/security/policy"

## Git 提交信息规范（Conventional Commits + Angular）

- 采用格式：
   <type>(<scope>): <subject>
   [空行]
   [可选 body]
   [空行]
   [可选 footer]

- 解析：
  - type：本次提交的类别，必须填写
  - scope：受影响的模块/范围，可选
  - subject：一句话描述「做了什么」，使用祈使语气英文动词（add/fix/refactor/...）
  - body：补充「为什么这么做」、「重要细节」
  - footer：BREAKING CHANGE、关联Issue（如Close #12）


- 常用 type：
  - `feat`           新增功能或重要内容
  - `fix`            修复错误（包括文档、示例中的错误）
  - `docs`           仅修改文档（Markdown、注释）
  - `refactor`       重构示例代码，不改变行为
  - `chore`          其他与学习内容无关的杂项
  - `test`           补充/修改测试
  - `style`          代码风格/格式调整（不影响逻辑）
  - `build`          构建系统或依赖项调整（Cmake、工具链）
  - `ci`             CI/CD 配置变更
  - `perf`           性能优化
  - `revert`         回滚某次提交

- 可选扩展类型（按需启用）：

`deps`               依赖升级/降级（也可归入 build/chore）
`security`           安全相关变更
`i18n`               国际化/本地化变更
`release`            发布相关（如自动生成的发版提交）
`wip`                work in progress，仅用于本地临时提交，不建议推送

- scope 示例：
  - `heap`           堆、存储期相关内容
  - `pointer`        指针与智能指针
  - `build`          构建相关
  - `core`           核心C++代码（主要练习代码）
  - `vscode`         VSCode配置（.vscode目录的文件）
  - `git`            Git相关（.gitignore、钩子等）
  - `docs`           文档与学习日志
  - `tests`          测试代码
  - `ci`             持续集成配置
  - `examples`       示例或演示代码

- 示例：
  - `docs(heap): 修正存储期的定义，贴近标准术语`
  - `fix(example): 修复 double delete 示例中的错误`
  - `feat(pointer): 增加 shared_ptr/unique_ptr 对比示例`
  - `feat(core): add Student struct and GPA calculation`
  - `fix(console): handle UTF-8 output for Chinese text`
  - `refactor(main): extract menu loop to run_menu()`
  - `docs(docs): add learning log for 2025-12-05`
  - `chore(script): rename learning log script to zhiz-learning-log`
  - `chore(git): ignore generated exe binaries`