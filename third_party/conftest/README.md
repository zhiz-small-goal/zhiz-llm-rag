---
title: third_party/conftest（离线 vendoring 目录）
version: v1.0
last_updated: 2026-01-11
---

# third_party/conftest（离线 vendoring 目录）

本目录用于**可选**存放 vendored 的 `conftest` 二进制，以支持完全离线运行 policy gate。

> gate runner 默认会按如下顺序找 conftest：
> 1) `CONFTEST_BIN` 环境变量
> 2) vendored 路径：`third_party/conftest/v<version>/<system>_<arch>/conftest(.exe)`
> 3) `PATH`（系统安装）

## 目录约定

```text
third_party/conftest/
  v<version>/
    <system>_<arch>/
      conftest        # macOS/Linux
      conftest.exe    # Windows
```

- `version`：建议与 `docs/reference/reference.yaml` 的 `policy.conftest.version` 对齐。
- `system`：`windows | linux | darwin`
- `arch`：`amd64 | arm64`

## 使用方式

- 如果你把二进制放入以上目录，**无需安装 conftest**，直接运行：

```bash
python tools/gate.py --profile ci --root .
```

- 如果你不想提交二进制到 repo：请改用内部制品库分发，并通过 `CONFTEST_BIN` 指定路径。
