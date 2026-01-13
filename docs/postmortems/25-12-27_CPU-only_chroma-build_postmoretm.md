[关键词] CPU-only构建， PyTorch,  cuda:0, CUDA wheel, chroma_db, check计数漂移


[阶段] chunks / embedding /chroma

[工具] verify_torch_cuda.py， verify_sentence_transformer_cuda.py

[复现] 

``` cmd
python tools\capture_rag_env.py --out data_processed\env_report.json
python extract_units.py
python validate_rag_units.py --max-samples 50

python tools\plan_chunks_from_units.py --root . --units data_processed\text_units.jsonl --include-media-stub true --out data_processed\chunk_plan.json
python build_chroma_index.py build --root . --units data_processed\text_units.jsonl --db chroma_db --collection rag_chunks --device cuda:0 --embed-model BAAI/bge-m3 --embed-batch 32 --upsert-batch 256 --include-media-stub
python check_chroma_build.py --db chroma_db --collection rag_chunks --plan data_processed\chunk_plan.json
```

[验收] 
``` cmd
python build_chroma_index.py build --root . --units data_processed\text_units.jsonl --db chroma_db --collection rag_chunks ^
  --device cuda:0 --embed-model BAAI/bge-m3 --embed-batch 32 --upsert-batch 256 --include-media-stub

python check_chroma_build.py --db chroma_db --collection rag_chunks --plan data_processed\chunk_plan.json
```

# Postmortem: Torch not compiled with CUDA enabled, chroma_db 不一致 - 2025.12.27

## 摘要
- 当前 venv 里的 PyTorch 是 CPU-only 构建，因此 `--device cuda:0` 必然报 `Torch not compiled with CUDA enabled`；
- chroma_db/rag_chunks 里已经存在上一轮残留（或 chunk ID/参数口径漂移导致“追加而非覆盖”），所以即便本次 build 崩溃，


## 影响范围（Impact）
- 影响命令：看上方[工具]
- 影响程度：GPU（cuda:0）来跑 BAAI/bge-m3 embedding失败，build崩溃
- 触发条件：使用 `-device cuda:0` 参数时


## 错误与现象特征（Symptoms）
- 典型报错（stdout/exception）：
  - `Torch not compiled with CUDA enabled`
  - `AssertionError: Torch not compiled with CUDA enabled`
  - `STATUS: FAIL (count mismatch; expected=3712 got=3720)` （实际 expected 与 got 跟具体项目有关）

- 关键观察：
  - 使用脚本 `tools/verify_torch_cuda.py` 检测，输出 `torch_cuda_build=None`, 等价于 `CPU-only torch`
  - `chroma_db/rag_chunks` 里已经存在上一轮残留（或 chunk ID/参数口径漂移导致“追加而非覆盖”），所以即便本次 build 崩溃，check_chroma_build 仍读到了 3720 条旧 embedding，和本轮 plan 的 3712 不一致


## 排查过程（TimeLine/Diagnosis）
### 1）确认 torch 是否由 CUDA 构建， CUDA runtime 是否可用
- 命令：`python tools\verify_torch_cuda.py`
- 结果：输出 `torch_cuda_build=None` , 说明 CPU-torch only


## 解决方案（Resolution）与验证
### 方案：
- 按官方命令重装 CUDA-enabled PyTorch
  - 命令：
  ``` cmd
  pip uninstall -y torch torchvision torchaudio

  REM 例：CUDA 12.8（官方 index-url: cu128）
  pip install torch==2.9.0 torchvision==0.24.0 torchaudio==2.9.0 --index-url https://download.pytorch.org/whl/cu128
  ```
  - 装完立刻复验：
  ``` cmd
  python tools\verify_torch_cuda.py
  ```
  - 说明；如果输出 `torch_cuda_build=12.8` `[RESULT] PASS`, 即表示可用 （12.8 是 CUDA 版本号）
  - 再加一道“SentenceTransformer 能否在 CUDA 上 encode”的验收
    - `python tools\verify_sentence_transformer_cuda.py --model BAAI/bge-m3 --device cuda:0 --text "hello"`

- 在 build 前重置 chroma_db
  - 命令：`python tools\reset_chroma_db.py --root . --db chroma_db --backup-dir data_processed\db_backups`
  - 说明：这一步会丢失旧库（但已备份到 backups）

  - 用“plan 同口径参数”重新 build，并用 check 作为最终验收
  ``` cmd
  python build_chroma_index.py build --root . --units data_processed\text_units.jsonl --db chroma_db --collection rag_chunks ^
  --device cuda:0 --embed-model BAAI/bge-m3 --embed-batch 32 --upsert-batch 256 --include-media-stub

  python check_chroma_build.py --db chroma_db --collection rag_chunks --plan data_processed\chunk_plan.json
  ```