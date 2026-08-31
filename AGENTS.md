# AGENTS.md — dtline

AI Agent Image Generation CLI for Draw Things gRPC Server.

## ALWAYS Check Available Models First

> ⚠️ **Model names vary per server.** Between versions and quantizations
> (e.g. `LTX-2.3 22B [distilled] 1.1 (6-bit)` vs `LTX-2.3 22B [distilled] (6-bit)`),
> never assume a model exists. **Run `dtline list-models` before generating.**
> Requesting a missing model can crash the Draw Things server.

Same for LoRAs — wrong names fail **silently** server-side; check `list-models`
output for exact filenames.

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
├── drawthings_client.py # Core client: DrawThingsClient, ImageGenerationConfig, video
├── tensor_encoder.py    # CCV tensor format encoding
├── tensor_decoder.py    # CCV tensor → PIL Image
└── *Service_pb2*.py    # Generated protobuf code

settings/               # Configuration presets
├── config.json         # User settings (gitignored)
├── presets/*.json      # Model presets (24 files, incl. video + expander presets)
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

### LoRAs

- `--lora` accepts display name OR full filename (extension required for direct file use)
- Presets can bundle LoRAs under `"loras"` — applied automatically; CLI `--lora` adds more
- Wrong LoRA names fail silently server-side; check `list-models` output for exact filenames

### Model Name Resolution

`--model` accepts display name OR filename:
- `"Z Image Turbo 1.0 (8-bit S)"` → resolves via `list-models` metadata
- `z_image_turbo_1.0_q6p.ckpt` → used directly

But ALWAYS verify against `list-models` first — names differ per server.

### Pony/SDXL Models

Must specify `--clip-skip 2` or model crashes:

```bash
dtline generate "1girl" --model "Wendigo2 (8-bit)" --preset "Pony/SDXL (Official)" --clip-skip 2
```

### Video Generation (LTX 2.3)

Video models set `num_frames` in their preset. When `num_frames > 1`, dtline uses
`generate_media()` + `save_video()` from DTgRPCconnector and outputs an mp4
(with audio when the model provides it). Requires the `video` extra:

```bash
pip install -e ".[video]"   # imageio + imageio-ffmpeg
dtline generate "prompt" --model "LTX-2.3 22B [distilled] 1.1 (6-bit)" --preset ltx23_official --num-frames 9
```

Key video constraints:
- **Frames: 9 to 257** (9 = 8 latent + 1; DT stops at 257). Use `--num-frames 9` for quick tests — the official preset default is 121 (slow)
- **LTX outputs fixed 25 fps** regardless of settings
- **Audio arrives as CCV tensor blobs** (68-byte header + fpzip float32), NOT raw PCM — must be decompressed before muxing; LTX's AudioVAE can emit NaN/Inf samples that break AAC encoding (DTgRPCconnector's `_sanitize_audio_for_mux` handles this)
- Frames are also CCV tensors — decode with `tensor_to_pil()` before writing to video
- Preset can also set explicit `width`/`height` (used when no --aspect-ratio/--width/--height given)

### Prompt Expander Models (Ernie, Ideogram 4)

Some models require prompts in an expanded/structured format. The full system
prompt lives in the preset under `prompt_expander_system`:

- **Ernie**: long-form detailed image description (~1000 tokens)
- **Ideogram 4 Instant**: strict minified JSON `{"aspect_ratio":"W:H","high_level_description":"...",...}`

AI agents MUST run `dtline preset-info <name> --json` and apply the expander
to the user's prompt BEFORE passing it to `dtline generate`.

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

`DTgRPCconnector/` is vendored here (not a submodule). It includes video/audio
fixes: `_sanitize_audio_for_mux()` (handles NaN/Inf, WAV/raw PCM ambiguity,
duration matching) — synced from the MuddleMeThis dev version.

If moodboard/edit/video issues appear, update DTgRPCconnector first:

```bash
cd DTgRPCconnector && git pull && cd ..
```

Then test with the examples from `DTgRPCconnector/examples/`.
