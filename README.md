# dtline

AI Agent Image Generation CLI for Draw Things gRPC Server.

## Features

- Simple command-line interface for Draw Things image generation
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
