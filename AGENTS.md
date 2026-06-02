# AGENTS.md — dtline

AI Agent Image Generation CLI for Draw Things gRPC Server.

## Architecture

```
dtline/                 # Main CLI package
├── cli.py              # Entry point: argparse subcommands
├── client.py           # DtlineClient wrapper around DrawThingsClient
├── config.py           # Settings loader (env + settings/config.json)
├── presets.py          # Preset/aspect-ratio/negative-prompt loading
├── errors.py           # Error classes with codes
└── output.py           # Human + JSON formatters

DTgRPCconnector/         # gRPC client library (subdirectory, not pip)
├── drawthings_client.py # Core client: DrawThingsClient, ImageGenerationConfig
├── tensor_encoder.py    # CCV tensor format encoding
└── *Service_pb2*.py    # Generated protobuf code

settings/               # Configuration presets
├── config.json         # User settings (gitignored)
├── presets/*.json      # Model presets (18 files)
└── negative_prompts/*.json
```

## Entry Point

```python
# pyproject.toml
[project.scripts]
dtline = "dtline.cli:main"
```

## Key Dependencies

- `DTgRPCconnector/` is imported directly (path inserted at runtime in `client.py`)
- No pytest, no linting, no typecheck config — just manual testing
- Outputs go to `outputs/` (gitignored)

## Critical Implementation Details

### Edit Models — Auto strength=1.0

For FLUX Klein, Qwen Edit, etc., strength **must** be 1.0. dtline auto-detects these:

```python
# client.py _is_edit_model()
edit_keywords = ["klein", "kontext", "edit", "instruct", "pix2pix"]
```

If user passes `--strength`, it's ignored for edit models (with verbose notice).

### Moodboard / Reference Images

Uses `DTgRPCconnector.ReferenceImage` with `hint_type="shuffle"` for edit models:

```python
from drawthings_client import ReferenceImage

ref = ReferenceImage(
    image=path,
    weight=1.0 / num_images,
    hint_type="shuffle",  # NOT "ipadapterplus" for edit models
)
```

The `shuffle` type VAE-encodes references as visual tokens — required for Klein models to produce actual subject content vs generic style transfer.

### Model Name Resolution

`--model` accepts display name OR filename:
- `"Z Image Turbo 1.0 (6-bit)"` → resolves via `list-models` metadata
- `z_image_turbo_1.0_q6p.ckpt` → used directly

### Pony/SDXL Models

Must specify `--clip-skip 2` or model crashes:

```bash
dtline generate "1girl" --model "Wendigo2 (8-bit)" --preset "Pony/SDXL (Official)" --clip-skip 2
```

## Server Constraint

Draw Things gRPC server processes **ONE request at a time**. Parallel requests will fail or corrupt.

## Quick Test

```bash
# After install
python -m dtline list-models
python -m dtline list-presets
dtline generate "a cat" --dry-run
```

## DTgRPCconnector Updates

If moodboard/edit quality issues appear, update DTgRPCconnector first:

```bash
cd DTgRPCconnector && git pull && cd ..
```

Then test with the examples from `DTgRPCconnector/examples/`.
