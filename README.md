# dtline

AI Agent Image Generation CLI for Draw Things gRPC Server.

## Features

- Simple command-line interface for Draw Things image generation
- **Image editing with automatic edit model detection** (auto-sets strength=1.0 for Klein, Qwen Edit, etc.)
- **Moodboard support** - Combine multiple reference images for composition (person from image 1 + outfit from image 2)
- Preset and aspect ratio support from existing settings
- JSON output for agent consumption
- TLS support with automatic certificate handling
- Multiple subcommands for model/preset discovery

## Installation

### Standard Installation

```bash
git clone https://github.com/Alexthestampede/dtline.git
cd dtline
chmod +x install.sh
./install.sh
```

After installation, add to your PATH:

```bash
# For bash (add to ~/.bashrc)
export PATH="$HOME/.local/dtline/bin:$PATH"

# For zsh (add to ~/.zshrc)
export PATH="$HOME/.local/dtline/bin:$PATH"
```

### AI Agent Installation

For AI agents installing this tool autonomously:

```bash
cd /tmp && git clone https://github.com/Alexthestampede/dtline.git && cd dtline && ./install.sh
source ~/.local/dtline/bin/activate
```

**Note for AI agents:** If shell completions are needed, ask the user whether to auto-install
(modify `~/.bashrc`/`~/.zshrc`) or leave manual. Default to manual if unspecified.

### Verifying Installation

```bash
dtline --version
dtline list-presets
dtline list-aspect-ratios
```

## Configuration

dtline uses settings from `settings/config.json` and environment variables:

| Environment Variable | Description | Default |
|--------------------|-------------|---------|
| `DTLINE_SERVER` | gRPC server address | `localhost:7859` |
| `DTLINE_MODEL` | Default model | - |
| `DTLINE_SCHEDULER` | Default scheduler | `Euler A Trailing` |
| `DTLINE_STEPS` | Default steps | `16` |
| `DTLINE_CFG` | Default CFG scale | `5.0` |
| `DTLINE_SIZE` | Default image size | `1:1 1024x1024` |
| `DTLINE_INSECURE` | Disable TLS (0 or 1) | `0` |
| `DTLINE_VERIFY_SSL` | Verify TLS certs (0 or 1) | `0` |
| `DTLINE_SSL_CERT` | Path to root CA certificate | `~/.local/dtline/root_ca.crt` |
| `DTLINE_OUTPUT_DIR` | Default output directory | `~/.local/dtline/outputs` |
| `DTLINE_CLIP_SKIP` | Default CLIP skip layers | `1` |

## Usage

### Generate an Image

```bash
dtline generate "a beautiful landscape at sunset"
```

With options:

```bash
dtline generate "a cat" \
  --model "Z Image Turbo 1.0 (6-bit)" \
  --preset zimage_updated \
  --aspect-ratio 3:4 \
  --steps 8 \
  --seed 42 \
  --clip-skip 2  # Required for Pony/Illustrious models
```

**Note:** The `--model` argument accepts either the **display name** (e.g., `"Z Image Turbo 1.0 (6-bit)"`) or the **filename** (e.g., `z_image_turbo_1.0_q6p.ckpt`). Use `dtline list-models` to see available models.

For Pony/Illustrious models (SDXL-based), you must specify `--clip-skip 2`:

```bash
dtline generate "1girl" \
  --model "Wendigo2 (8-bit)" \
  --preset "Pony/SDXL (Official)" \
  --clip-skip 2 \
  --negative-preset "Straysignal's Chroma negative"
```

### Edit an Image

Edit an existing image using AI instructions (img2img with edit models):

```bash
dtline edit photo.png "make it sunset"
```

**Note:** For edit/kontext models (FLUX Klein, Qwen Image Edit, etc.), dtline **automatically sets strength=1.0** regardless of user input. This is required by these models - setting strength lower will corrupt the reference encoding and produce poor results.

```bash
dtline edit photo.png "make the car red" \
  --model "FLUX.2 [klein] 4B (6-bit)" \
  --preset klein_official
  # strength is automatically set to 1.0 for Klein models
```

With options:

```bash
dtline edit photo.png "add cyberpunk style" \
  --model "FLUX.2 [klein] 4B (6-bit)" \
  --preset klein_official \
  --steps 4 \
  --cfg 1.0 \
  --image-guidance-scale 1.5 \
  --seed 42
```

**Workflow Example:**

```bash
# Step 1: Generate base image with Z Image Turbo
dtline generate "a white sports car on mountain road" \
  --model "Z Image Turbo 1.0 (6-bit)" \
  --preset zimage_updated \
  --seed 42

# Step 2: Edit with FLUX Klein to change color
dtline edit outputs/dtline_*.png "make the car red" \
  --model "FLUX.2 [klein] 4B (6-bit)" \
  --preset klein_official
```

**Edit Model Detection:**

dtline automatically detects edit models and sets strength=1.0 for:
- FLUX Klein models (kontext)
- Qwen Image Edit models
- InstructPix2Pix models
- Other models with "edit", "kontext", "instruct", or "pix2pix" in the name

For standard img2img models (SD 1.5, SDXL, etc.), you can control strength manually:

```bash
dtline edit photo.png "add oil painting effect" \
  --model "Juggernaut XL v9" \
  --strength 0.75  # Works for standard img2img
```

### Moodboard / Multiple Reference Images

Generate images using multiple reference images (IP-Adapter style) for composition:

```bash
dtline moodboard "person from image 1 wearing outfit from image 2" person.png outfit.png
```

**Note:** For edit/kontext models (FLUX.2 Klein), use `hint_type="shuffle"` internally which properly encodes reference images as visual tokens. For IP-Adapter models, it uses `"ipadapterplus"`.

**Example - Car Showroom:**

```bash
# Generate base images first
dtline generate "white sports car" --model "Z Image Turbo 1.0 (6-bit)" --preset zimage_updated --seed 42
dtline edit outputs/dtline_*.png "make it red" --model "FLUX.2 [klein] 4B (6-bit)" --preset klein_official --seed 123
dtline edit outputs/dtline_*.png "make it blue" --model "FLUX.2 [klein] 4B (6-bit)" --preset klein_official --seed 456

# Then combine them with moodboard
dtline moodboard "the car from image 1 in a showroom, with the car from image 2 on the left and the car from image 3 on the right, keep the colors the same" \
  white_car.png red_car.png blue_car.png \
  --model "FLUX.2 [klein] 9B (6-bit)" \
  --preset klein_official \
  --seed 999
```

**Usage:**

```bash
dtline moodboard <instruction> <image1> [image2] [image3] [image4] [image5] [options]
```

- Supports 1-5 reference images
- Uses `"shuffle"` hint type for edit/kontext models (automatically detected)
- Reference images are weighted equally by default
- Best results with edit models like FLUX.2 Klein

### List Available Models

```bash
dtline list-models
dtline list-models --json
```

### Get Model Information

```bash
dtline info flux_1_schnell_q8p.ckpt
```

### List Presets

```bash
dtline list-presets
dtline list-presets --json
```

### List Aspect Ratios

```bash
dtline list-aspect-ratios
dtline list-aspect-ratios --json
```

### List Negative Prompt Presets

```bash
dtline list-negative-prompts
dtline list-negative-prompts --json
```

### Show Configuration

```bash
dtline config
dtline config --json
```

## Output Formats

### Human Output (Default)

```
Generating image...
Prompt: a beautiful landscape at sunset
Model: Z Image Turbo 1.0 (6-bit)
Size: 1024x1024
Preset: zimage_updated
✓ Generated: /home/user/.local/dtline/outputs/dtline_20250406_120000_12345.png (1.2MB, seed=12345, 12.3s)
```

### JSON Output

```bash
dtline generate "a cat" --json
```

```json
{
  "success": true,
  "images": [
    {
      "path": "/home/user/.local/dtline/outputs/dtline_20250406_120000_12345.png",
      "bytes": 1245184,
      "seed": 12345
    }
  ],
  "metadata": {
    "model": "Z Image Turbo 1.0 (6-bit)",
    "steps": 8,
    "cfg": 1.0,
    "scheduler": "UniPC Trailing",
    "width": 1024,
    "height": 1024,
    "seed": 12345,
    "duration_seconds": 12.3,
    "prompt": "a cat"
  }
}
```

### Error Output

```json
{
  "success": false,
  "error": {
    "code": "CONNECTION_ERROR",
    "message": "Failed to connect to Draw Things gRPC server",
    "details": "Connection refused"
  }
}
```

## TLS and Security

The Draw Things server uses a self-signed TLS certificate signed by "Draw Things Root CA".
The installer automatically downloads the root CA certificate to `~/.local/dtline/root_ca.crt`.

If TLS connection fails:

```bash
# Try with certificate verification
dtline generate "a cat" --verify-ssl --ssl-cert ~/.local/dtline/root_ca.crt

# Or disable TLS entirely (not recommended for production)
dtline generate "a cat" --insecure
```

## Updating

```bash
cd ~/.local/dtline
git pull
source bin/activate
pip install -e .
```

## Uninstalling

```bash
chmod +x uninstall.sh
./uninstall.sh
```

Then manually remove dtline-related lines from your `~/.bashrc` or `~/.zshrc`.

## Server Warning

> ⚠️  The Draw Things server processes ONE request at a time.
> Do not send parallel requests.

## License

MIT License

## Credits

- [Draw Things](https://drawthings.ai/) - Image generation app
- [Draw Things Community](https://github.com/drawthingsai/draw-things-community) - Open-source server implementation
