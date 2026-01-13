---
title: 完全离线运行 Policy Gate（Vendoring conftest / 内部镜像源）
version: v1.0
last_updated: 2026-01-11
---

# 完全离线运行 Policy Gate（Vendoring conftest / 内部镜像源）


> 目标：在**无外网**（air-gapped / 内网隔离）环境里仍能运行 `python tools/gate.py --profile ci` 的 policy 步骤。
>
> 关键原则：gate runner **不做任何联网行为**；所有依赖由“预置/镜像/内网制品库”提供。

## 目录
- [结论与推荐](#结论与推荐)
- [方案 1：Vendoring conftest 二进制到 repo（推荐）](#方案-1vendoring-conftest-二进制到-repo推荐)
- [方案 2：内部镜像源/制品库（企业内网）](#方案-2内部镜像源制品库企业内网)
- [校验与追溯](#校验与追溯)
- [常见坑](#常见坑)

## 结论与推荐

- **推荐默认方案：Vendoring 二进制到 repo**。优点是“clone 即可用”，最符合完全离线与隐私需求。
- 企业环境若不希望把二进制提交进 Git：用**内部制品库/镜像仓库**分发，然后在离线环境做“本地安装/解压到固定路径”。

gate runner 的 conftest 搜索顺序：
1) `CONFTEST_BIN`（显式指定二进制路径）
2) `third_party/conftest/v<version>/<system>_<arch>/conftest(.exe)`（vendored）
3) `PATH`（系统安装）

## 方案 1：Vendoring conftest 二进制到 repo（推荐）

### Step 1：确定版本（与 SSOT 对齐）
- 版本以 `docs/reference/reference.yaml` 的 `policy.conftest.version` 为准。

### Step 2：在“可联网机器”下载 release 资产并解压
- 参考官方安装文档/安装页的 release 方式，下载对应 OS/ARCH 的 tar.gz/zip。\
  （注意：Conftest 官方文档给了 Homebrew/Scoop/Docker/Release 二进制等多种安装方式。）

### Step 3：按约定目录放入 repo 并提交
在 repo 内创建目录并放入二进制：

```text
third_party/conftest/
  v0.61.0/
    windows_amd64/conftest.exe
    linux_amd64/conftest
    darwin_arm64/conftest
```

> 命名口径：
> - system：`windows|linux|darwin`
> - arch：`amd64|arm64`
> - 其他架构可按 `platform.machine()` 的小写原样追加（不建议太多）

### Step 4（可选）：强制本地也必须执行 policy
如果你希望“没 conftest 就 FAIL”：
- 在 `docs/reference/reference.yaml` 增加：`policy.conftest.required: true`

## 方案 2：内部镜像源/制品库（企业内网）

适用：
- 你不希望把二进制提交到 Git（repo 体积/合规/审计原因）；
- 但可以在内网提供一个可信分发点（Artifactory/Nexus/S3/minio/内网 Git Release 等）。

做法：
1) 在“可联网机器”下载 conftest release 资产
2) 上传到内部制品库并打版本（与 SSOT 对齐）
3) 在离线环境：把二进制安装到固定路径，并设置：

```bash
# Linux/macOS
export CONFTEST_BIN=/opt/tools/conftest/bin/conftest
```

```powershell
# Windows PowerShell, 这个路径是示例, 根据自己实际路径设置
$env:CONFTEST_BIN = "C:\\opt\\tools\\conftest\\conftest.exe"
```

## 校验与追溯

最小建议：
- 记录来源（release tag）、下载时间、二进制 SHA256。

实操提示：
- GitHub Releases 已支持显示 release 资产的 SHA256 digest（可用于校验下载未被篡改）。
- Homebrew 公式页也可看到 conftest 的 license（做合规审计时用）。

## 常见坑

- **系统/架构不匹配**：Windows 常见 `AMD64` -> `amd64`，ARM 机器常见 `aarch64` -> `arm64`。
- **可执行权限**：Linux/macOS 需要 `chmod +x conftest`。
- **repo 体积**：二进制较大时建议 Git LFS 或“内部制品库方案”。
