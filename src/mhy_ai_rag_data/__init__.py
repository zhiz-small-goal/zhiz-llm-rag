"""mhy_ai_rag_data

工程化目标：
- 以 src-layout 组织可安装包（pip install -e .），消除脚本路径/工作目录导致的导入不一致。
- 保留仓库根目录与 tools/ 下的 wrapper 以兼容旧用法。

权威执行入口：
- console scripts: rag-*（见 pyproject.toml [project.scripts]）
- 或 python -m mhy_ai_rag_data.<module>
"""

from __future__ import annotations

__all__ = ["__version__"]

# 版本建议由发布流程写入；此处给一个可读占位。
__version__ = "0.1.0"
