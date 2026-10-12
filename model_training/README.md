# Local Model Training

This directory contains configurations, documentation, and scripts for fine-tuning local models (e.g. Qwen2.5 1.5B/3B) using MLX on Apple Silicon.

## Structure
- `config/`: MLX LoRA YAML configuration files for different model sizes.
- `docs/`: Guides and plans for migrating to locally hosted models.
- `scripts/`: Utilities for extracting processed data and building JSONL training pairs.
- `workspace/`: A localized area to drop data in for training.
  - `workspace/input/`: Drop PDFs/PPTXs here to test run.
  - `workspace/raw/`: Extracted unpolished markdown is generated here.
  - `workspace/polished/`: Place your manually fixed files here to serve as training targets.

## Workflow
1. Drop files into `workspace/input/`.
2. Run `python model_training/scripts/generate_raw_from_workspace.py` to extract them to `workspace/raw/`.
3. Copy the raw files to `workspace/polished/` and manually format/fix them.
4. Run `python model_training/scripts/build_training_pairs.py` to generate `train.jsonl` and `val.jsonl` inside `workspace/`.
5. Run your MLX training command, pointing to `model_training/workspace` for the data.
