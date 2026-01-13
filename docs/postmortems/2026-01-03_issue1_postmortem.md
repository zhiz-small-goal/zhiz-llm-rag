# 2026-01-03 pyproject 门禁与环境安装异常复盘（Issue1）


> 目的：把一次“环境/门禁/安装链路”故障转化为可复用的工程资产（脚本入口 + 契约 + 文档），降低复发概率与定位成本。  
> 模板参考：`postmortem_os.md`（v1.0.0，2026-01-03）。

## 目录（Markdown 锚点目录）
- [1. TL;DR](#1-tldr)
- [2. 前提识别](#2-前提识别)
- [3. 问题定义](#3-问题定义)
- [4. 事实与时间线](#4-事实与时间线)
- [5. 因果分析](#5-因果分析)
- [6. 决策与权衡](#6-决策与权衡)
- [7. 行动项与验收](#7-行动项与验收)
- [8. 复用与沉淀](#8-复用与沉淀)
- [9. 度量与持续迭代](#9-度量与持续迭代)
- [10. 附录：MRE 与常用命令](#10-附录mre-与常用命令)

---

## 1. TL;DR

| 字段 | 填写 |
|---|---|
| 一句话结论 | `pyproject.toml` 被当作“说明文档”写入非 ASCII 字符，触发门禁失败并引发安装链路反复重试；通过“契约 ASCII-only + 预检脚本 + fail-fast 总入口 + 文档迁移”完成收敛。 |
| 影响（量化） | 安装/门禁无法一次通过，导致多次重建 venv 与重复执行 pip 安装；排障时间集中在“解释器选择/索引异常/门禁语义误解”。 |
| 根因（一句话） | 机器可解析契约（pyproject）与人类可读说明混写 + 门禁只提供退出码但缺少统一入口（新手易逐条执行绕过 fail-fast）。 |
| 下一步（1–3条） | 1) 固化 `check_pyproject_preflight.py --ascii-only` 与 `run_ci_gates.cmd`；2) 文档明确“一键入口”；3) 加入最小验收（pip show/import）与索引故障排查段落。 |

---

## 2. 前提识别

| 类型 | 陈述（可检验） | 可控？ | 验证方式 | 证据等级 | 备注 |
|---|---:|---:|---|---|---|
| 约束 | Windows + CMD 作为主运行环境 | 部分可控 | 统一脚本入口为 `.cmd` | P1 | 影响命令串联语义（ERRORLEVEL） |
| 不可变条件 | `pyproject.toml` 必须可被 pip 解析并支撑 editable 安装 | N | `pip install -e .`、TOML parse | P0 | 安装入口契约 |
| 假设 | 团队/多机器协作会反复触发“编码/复制粘贴”类漂移 | N | 复发统计 | P2 | 需要门禁与文档双保险 |
| 可控变量 | 是否采用 ASCII-only 契约；是否提供 fail-fast 总入口 | Y | 预检脚本 + 批处理 | P1 | 直接降低误用概率 |

---

## 3. 问题定义

- **现象（Observation）**  
  - `tools\check_pyproject_preflight.py --ascii-only` 报告 `pyproject.toml` 含非 ASCII 字符；或 pip 安装阶段出现解析/索引异常，导致安装失败。
- **可验证命题（Testable Claim）**  
  - 若 `pyproject.toml` 仅包含 ASCII 且能被 TOML 解析，同时提供“fail-fast 总入口”在 FAIL 时中止后续步骤，则安装与门禁链路能稳定收敛到可复现状态；否则新手在交互式 CMD 下逐条执行会绕过门禁语义，造成重复试错。
- **范围（In scope）**  
  - `pyproject.toml` 字符/编码契约；预检脚本与批处理入口；安装命令（editable + extras）；文档中的“一键命令”呈现方式。
- **不解决（Out of scope）**  
  - 业务功能（RAG 检索质量/embedding 模型效果）；模型推理服务稳定性。
- **成功判据（Done）**  
  - 预检 PASS（UTF-8 + TOML parse + ASCII-only）；一键入口能在 FAIL 时终止；在新 venv 中可完成 `pip install -e ".[embed]"` 且 `import chromadb, sentence_transformers` 通过。

---

## 4. 事实与时间线

| 时间 | 事件/决策 | 关键观测 | 证据/位置 |
|---|---|---|---|
| T0 | 运行 preflight，发现 `pyproject.toml` 含大量非 ASCII（中文说明/全角符号/箭头） | `[FAIL] suspicious characters detected ... L:C U+XXXX` | preflight 输出 |
| T1 | 采用替代方案：将中文策略说明迁移到 docs，`pyproject.toml` 保持 ASCII-only | preflight 转为 PASS | `pyproject.toml` 变更 |
| T2 | 在新 `.venv_ci` 内执行 `pip install -e ".[embed]"` 遇到 `JSONDecodeError` | 堆栈指向 pip 解析 index 响应 | pip 输出 |
| T3 | 固定解释器与索引策略，重跑安装并完成 `chromadb`、`sentence_transformers` 可 import | `pip show chromadb` 有版本与 location；import OK | 终端输出 |
| T4 | 发现“门禁脚本不会自动阻止下一步”的新手误用风险 | 交互式 CMD 逐条执行不会自动停 | 讨论结论 |
| T5 | 增加 fail-fast 总入口（`run_ci_gates.cmd`），并在文档中将其设为推荐入口 | 一条命令即可跑预检/安装/门禁；失败即停 | 新增脚本 + 文档 |

---

## 5. 因果分析

### 5.1 近因（Proximate causes）
1) `pyproject.toml` 被写入中文说明与全角符号，触发 ASCII-only 门禁直接 FAIL（可定位到行列与 codepoint）。  
2) 用户在交互式 CMD 中逐条执行命令，未使用 `&&` / `IF ERRORLEVEL` 进行控制流串联，导致“门禁失败仍继续安装”的误用风险。  

### 5.2 根因（Root causes / Contributing factors）
1) **契约与说明混写**：`pyproject.toml` 同时承担“机器契约”与“人类说明”，在复制粘贴/编辑器编码差异下放大漂移概率。  
2) **缺少单一入口**：门禁脚本只提供“退出码语义”，但项目未提供面向新手的一键入口（fail-fast 编排不在默认路径上）。  
3) **索引响应不可靠**（次要根因）：`JSONDecodeError` 类问题往往与代理/镜像返回非预期内容（如 HTML 或空响应）有关，使 pip 在解析索引响应时失败，造成安装不稳定。

### 5.3 结构性原因（Systemic causes）
- 文档主线未将“推荐入口=一键脚本”置顶；新手更倾向复制多行命令并逐条运行。  
- 对“退出码=控制流信号”的工程约定未显式写入 docs/howto 与 CI 说明，导致门禁意图无法通过默认路径传递给操作者。

---

## 6. 决策与权衡

| 决策点 | 备选方案 | 选择与理由 | 代价/机会成本 |
|---|---|---|---|
| pyproject 是否允许中文注释 | 允许 Unicode / 采用 ASCII-only | 选择 ASCII-only：把 pyproject 作为机器契约，最大化跨工具稳定性；中文说明迁移到 docs | pyproject 失去直接中文注释，但可用 docs/ 链接补足 |
| 门禁是否由单脚本承载后续步骤 | 预检脚本内部“自动跑后续命令” / 总入口编排 | 选择“预检保持单一职责 + 总入口编排”：避免平台差异与转义复杂度，便于长期维护 | 多一个入口脚本需要维护，但显著降低误用 |
| venv 依赖是否迁移旧环境 | 迁移 / 重新安装 | 选择重新安装并用 pip show/import 验收：避免把不可追溯状态带入新环境 | 初次安装耗时，但复现性更强 |

---

## 7. 行动项与验收

| ID | 行动项（What） | 为什么（关联原因） | Owner | 截止 | 验收指标/方法 | 状态 |
|---|---|---|---|---|---|---|
| A1 | 固化 `tools/check_pyproject_preflight.py --ascii-only` 并纳入 CI | 提前拦截契约漂移 | zhiz | 已完成 | PASS 输出 + 退出码 0；FAIL 返回非 0 | Done |
| A2 | 新增 `tools/run_ci_gates.cmd`（fail-fast 一键入口） | 消除交互式逐条执行误用 | zhiz | 已完成 | 预检 FAIL 时脚本退出且后续不执行 | Done |
| A3 | 文档置顶“一键入口”并保留手工模式（但明确不推荐） | 把正确路径放到默认路径 | zhiz | 已完成 | 新人只需 1 条命令即可跑门禁 | Done |
| A4 | 增加 pip 索引异常排障段落（JSONDecodeError） | 缩短索引/代理类故障定位 | zhiz | 待办 | 文档含：固定 index-url / 禁缓存 / 代理清理清单 | Open |

---

## 8. 复用与沉淀

### 可复用原则（原则化表述）
1) **机器契约与人类说明分离**：`pyproject.toml`/JSON/YAML 等作为“可解析契约”的文件尽量保持 ASCII-only 或至少保持可稳定解析；中文策略与说明放入 `docs/` 并由链接关联。  
2) **门禁=退出码；执行闭环=入口编排**：门禁脚本提供确定的退出码语义，总入口脚本负责控制流（fail-fast），并将其写入文档“默认路径”。  
3) **环境验收优先用硬证据**：`sys.executable`、`pip show`、`import ...` 是最短证据链，优先于 verbose 日志片段。  

### Guardrails（守护栏）
- `check_pyproject_preflight.py --ascii-only`：阻止非 ASCII 漂移进入安装链路。  
- `run_ci_gates.cmd`：把“预检→安装→测试”封装成一条命令，降低误用概率。  
- 文档把“一键入口”置顶；手工模式标注为“仅用于调试”。

---

## 9. 度量与持续迭代

- **Gate fail-fast 覆盖率**：新手是否主要使用 `run_ci_gates.cmd`（可通过文档/脚本引用次数与 CI 日志观察）。  
- **复发率**：未来 30 天内是否再次出现“pyproject 非 ASCII 引发安装失败”。  
- **定位时延**：从失败到定位根因（契约漂移/索引异常/解释器偏离）的时间，目标逐次下降。  

---

## 10. 附录：MRE 与常用命令

### MRE：验证 Stage-2 依赖已就绪
```cmd
cd /d <REPO_ROOT>
.venv_ci\Scripts\python -c "import sys; print(sys.executable)"
.venv_ci\Scripts\python -m pip show chromadb
.venv_ci\Scripts\python -c "import chromadb; import sentence_transformers; print('embed imports OK')"
```

### MRE：验证 fail-fast（需要人为制造 FAIL）
1) 在 `pyproject.toml` 某行加入一个全角冒号 `：` 或中文字符（仅用于测试）。  
2) 运行：
```cmd
tools\run_ci_gates.cmd
echo ERRORLEVEL=%ERRORLEVEL%
```
3) 期望：预检 FAIL 后脚本退出，后续 pip/pytest 不再执行。
