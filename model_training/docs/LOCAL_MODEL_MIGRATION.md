# Local Formatter Model — Migration & Startup Guide

> **Goal:** Replace the cloud AI polish pass (Groq/Gemini) in the resource processing pipeline with a fine-tuned local model (`gemma2:2b`) served via Ollama on the production server. Zero cloud dependency for document processing.

## Why This Exists

The current pipeline calls a cloud AI (Groq `llama-3.3-70b-versatile`) to clean up extracted markdown — fixing heading levels, list formatting, and removing artifacts. This causes:
- **Slow processing:** 4–8 minutes per lecture (sequential cloud round-trips per 800-char chunk)
- **Inconsistent output:** cloud model leaks reasoning artifacts that must be stripped programmatically
- **Rate limits:** forced to `max_workers=1` to avoid Groq free-tier TPM limits
- **Cost & dependency:** every document upload hits an external API

A fine-tuned `gemma2:2b` (1.1 GB, ~1.5 GB RAM at runtime) on the production server eliminates all of these.

---

## Architecture: Before vs After

### Before
```
Document Upload
  → FontAwareExtractor (local)       ~5s
  → SignalMerger (local)             ~1s
  → Raw Markdown
  → _ai_polish() → Groq cloud API   ← 4–8 MINUTES (sequential chunks)
  → Final Markdown
```

### After
```
Document Upload
  → FontAwareExtractor (local)       ~5s
  → SignalMerger (local)             ~1s
  → Raw Markdown
  → _ai_polish() → Ollama local      ← 10–20 SECONDS
  → Final Markdown
```

---

## Server Requirements

| Requirement | Value |
|-------------|-------|
| Model | gemma2:2b (fine-tuned, 4-bit GGUF) |
| Disk space | ~1.1 GB |
| RAM at runtime | ~1.5–2 GB |
| GPU | Not required (CPU inference) |
| Ollama version | ≥ 0.3.0 |

The model runs entirely on CPU — no GPU needed.

## Dev Machine Requirements (for fine-tuning)

| Requirement | Value |
|-------------|-------|
| Chip | Apple Silicon (M1/M2/M3) |
| RAM | ≥ 16 GB unified memory |
| Storage | ~3 GB free (model + adapter) |
| Python | 3.11 (via uv venv — see below) |
| mlx-lm | ≥ 0.31 (installed in dedicated venv) |

---

## Phase 1 — Immediate Quick Start (No Training Required)

Get local, rate-limit-free processing running **today** using the base (untuned) model. Replace with the fine-tuned version later.

### On the production server

```bash
# 1. Pull the 2b model (~1.1 GB)
ollama pull gemma2:2b

# 2. Create the formatter model with style rules baked in
ollama create velonote-formatter -f models/llm/Modelfile

# 3. Verify it works
echo '# Test Topic\n\n## Overview\nSome content here.' | ollama run velonote-formatter
```

### In velonote `.env`

```env
# Point Tier 2 (the processing model) at local Ollama
GLOBAL_AI_TIER2_PROVIDER=ollama
GLOBAL_AI_TIER2_MODEL=velonote-formatter
GLOBAL_AI_TIER2_BASE_URL=http://localhost:11434
```

Restart the worker: `python -m app.worker_main`

---

## Phase 2 — Fine-tuning (for best quality)

### Step 1 — Set up the training environment (dev machine)

```bash
# Create an isolated venv with mlx-lm (avoids Anaconda NumPy 2.x conflict)
uv venv ~/mlx-finetune-env --python 3.11
source ~/mlx-finetune-env/bin/activate
uv pip install "mlx-lm>=0.31" "numpy<2" huggingface_hub

# Verify
python -m mlx_lm.lora --help | head -3
```

### Step 2 — Verify Model Configuration

You no longer need to manually download the model! 
Apple MLX will automatically pull the highly-optimized `mlx-community/gemma-2-2b-it-4bit` model from HuggingFace and cache it for you during training.

Just ensure your `lora_2b.yaml` has the correct `model` property.

### Step 3 — Collect training data
First, drop the PDFs, PPTXs, or images you want to use for training into `model_training/workspace/input/`.

```bash
# Extract raw markdown (AI polish disabled) from the files in the input folder
python model_training/scripts/generate_raw_from_workspace.py
# → writes to model_training/workspace/raw/*_raw.md
```

Then **manually polish** each `*_raw.md` file:
- Fix heading levels (single `# H1`, `## H2`, `### H3`)
- Convert pseudo-headings to `- ` bullet lists
- Remove university/course metadata from title
- Leave all content and exact words intact

Save each polished version as `model_training/workspace/polished/*_polished.md`.

**Target: 150–200 polished examples** (50 is enough to start a test run).

### Step 4 — Build JSONL training pairs

```bash
python model_training/scripts/build_training_pairs.py
# → writes model_training/workspace/train.jsonl and model_training/workspace/val.jsonl
```

### Step 5 — Train

```bash
source ~/mlx-finetune-env/bin/activate

# Dry run (10 iters, ~1 min) — check RAM stays < 16 GB
python -m mlx_lm lora --config model_training/config/lora_2b.yaml --iters 10

# Full training run (~20 min on M3 Pro)
# (All settings like the model name and data path are managed inside the yaml file)
python -m mlx_lm lora --config model_training/config/lora_2b.yaml
```

Expected output:
```
Iter 100: Train loss 1.12, Val loss 1.04, ~80 tok/sec, ~3.2 GB RAM
Iter 300: Train loss 0.68, Val loss 0.61
Iter 600: Train loss 0.38, Val loss 0.42  ← stop here
```

Stop early (Ctrl+C) when val loss plateaus or drops below 0.5.

### Step 6 — Evaluate

```bash
source ~/mlx-finetune-env/bin/activate

python -m mlx_lm.generate \
  --model models/llm/gemma-2-2b-it \
  --adapter-path models/llm/velonote-2b-adapter \
  --prompt "$(cat path/to/test_raw.md)" \
  --max-tokens 4096 \
  --temp 0.0
```

If the output looks correct → proceed to deployment.
If quality is insufficient → see **Upgrade to 3b** below.

### Step 7 — Deploy fine-tuned model to server

```bash
# On dev machine — fuse LoRA adapter into base model
source ~/mlx-finetune-env/bin/activate

python -m mlx_lm.fuse \
  --model models/llm/gemma-2-2b-it \
  --adapter-path models/llm/velonote-2b-adapter \
  --save-path models/llm/velonote-formatter-fused

# Convert to GGUF for Ollama
brew install llama.cpp
llama-quantize --type q4_k_m \
  models/llm/velonote-formatter-fused/model.gguf \
  models/llm/velonote-formatter.q4_k_m.gguf

# Copy to server and register with Ollama
scp models/llm/velonote-formatter.q4_k_m.gguf user@YOUR_SERVER:~/models/
ssh user@YOUR_SERVER

cat > ~/models/Modelfile << 'EOF'
FROM ./velonote-formatter.q4_k_m.gguf
PARAMETER temperature 0
PARAMETER num_ctx 8192
PARAMETER num_predict 2048
EOF

# This replaces the base model with the fine-tuned one — same name, zero downtime
ollama create velonote-formatter -f ~/models/Modelfile
```

---

## Upgrade Path: qwen2.5:3b

If 2b quality is not good enough after evaluation:

```bash
# Download 3b base (~2.5 GB, uses ~3–4 GB RAM on server)
python -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='mlx-community/Qwen2.5-3B-Instruct-4bit',
    local_dir='models/llm/qwen2.5-3b-4bit',
)
"

# Use the 3b config
python -m mlx_lm.lora \
  --model models/llm/qwen2.5-3b-4bit \
  --train \
  --data model_training/workspace \
  --config model_training/config/lora_3b.yaml
```

All other steps (fuse → GGUF → Ollama create) are identical.

---

## Key Files

| File | Purpose |
|------|---------|
| `models/llm/Modelfile` | Ollama Modelfile for base (untuned) model |
| `model_training/config/lora_2b.yaml` | MLX LoRA training config for 2b |
| `model_training/config/lora_3b.yaml` | MLX LoRA training config for 3b (upgrade path) |
| `model_training/scripts/generate_raw_from_workspace.py` | Extracts raw markdown from existing resources |
| `model_training/scripts/build_training_pairs.py` | Builds `train.jsonl` / `val.jsonl` from raw+polished pairs |
| `model_training/workspace/input/` | Drop PDFs/PPTXs here to generate raw markdown |
| `model_training/workspace/raw/` | Raw (pre-polish) markdown files |
| `model_training/workspace/polished/` | Manually curated target markdown files |
| `model_training/workspace/train.jsonl` | Training dataset (auto-generated) |
| `model_training/workspace/val.jsonl` | Validation dataset (auto-generated) |
| `models/llm/velonote-2b-adapter/` | LoRA adapter weights (dev machine only) |
| `models/llm/velonote-formatter.q4_k_m.gguf` | Final GGUF for deployment |

---

## Checklist

### Immediate (today)
- [ ] `ollama pull gemma2:2b` on server
- [ ] `ollama create velonote-formatter -f models/llm/Modelfile` on server
- [ ] Update `.env` → `GLOBAL_AI_TIER2_*` to point at local Ollama
- [ ] Restart worker, test a document upload

### This week (data collection)
- [ ] `python model_training/scripts/generate_raw_from_workspace.py`
- [ ] Manually polish first 50 examples → `model_training/workspace/polished/`
- [ ] `python model_training/scripts/build_training_pairs.py`
- [ ] Set up `~/mlx-finetune-env` on dev machine

### Next week (training)
- [ ] Polish remaining 100+ examples (150 total)
- [ ] Download `google/gemma-2-2b-it`
- [ ] Run 600-iter training (~20 min)
- [ ] Evaluate on 5 unseen documents

### Deploy week
- [ ] Fuse adapter → GGUF → `scp` to server
- [ ] `ollama create velonote-formatter` on server (replaces base)
- [ ] Monitor first 10 production uploads for quality
