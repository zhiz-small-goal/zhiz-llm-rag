#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/reset_chroma_db.py

用途：
  当出现 Chroma collection count 与 plan.expected 不一致（尤其是混用旧库/旧参数导致的“多出来/少了”）时，
  通过“备份并重置 chroma_db 目录”来确保下一次 build 是干净构建。

策略（默认）：
  - 将 --db 指向的目录移动到 backup 目录（带时间戳）
  - 重新创建空的 db 目录（仅目录，不做 collection 创建）

退出码：
  0：PASS（完成备份/重置）
  2：FAIL（db 目录不存在，或移动失败）
  3：ERROR（脚本异常）

用法：
  python tools\reset_chroma_db.py --root . --db chroma_db --backup-dir data_processed\db_backups
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from datetime import datetime

def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--root", default=".")
        ap.add_argument("--db", default="chroma_db", help="Chroma 持久化目录（相对 root 或绝对）")
        ap.add_argument("--backup-dir", default="data_processed/db_backups", help="备份根目录")
        args = ap.parse_args()

        root = Path(args.root).resolve()
        db_path = Path(args.db)
        if not db_path.is_absolute():
            db_path = (root / db_path).resolve()

        backup_root = Path(args.backup_dir)
        if not backup_root.is_absolute():
            backup_root = (root / backup_root).resolve()
        backup_root.mkdir(parents=True, exist_ok=True)

        if not db_path.exists():
            print(f"[FAIL] db path not found: {db_path}")
            return 2

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = backup_root / f"{db_path.name}_bak_{ts}"

        print(f"[INFO] moving db: {db_path} -> {dest}")
        shutil.move(str(db_path), str(dest))

        db_path.mkdir(parents=True, exist_ok=True)
        print(f"[OK] reset db dir created: {db_path}")
        print(f"[OK] backup at: {dest}")
        return 0
    except Exception as e:
        print(f"[ERROR] {e}")
        return 3

if __name__ == "__main__":
    raise SystemExit(main())
