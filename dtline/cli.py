"""Command-line interface for dtline."""

import argparse
import sys
import os
from pathlib import Path

from .client import DtlineClient
from .config import ConfigLoader
from .presets import PresetManager
from .output import (
    GenerationOutput,
    ListModelsOutput,
    ModelInfoOutput,
    PresetListOutput,
    AspectRatioListOutput,
    NegativePromptListOutput,
    ConfigOutput,
)
from .errors import DtlineError


SERVER_WARNING = (
    "WARNING: The Draw Things server processes ONE request at a time. "
    "Do not send parallel requests."
)


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json", action="store_true", default=False, help="Output in JSON format"
    )


def _resolve_aspect_ratio(
    args: argparse.Namespace, config_loader: ConfigLoader
) -> tuple[int, int]:
    pm = PresetManager()
    ar = (
        pm.get_aspect_ratio(args.aspect_ratio)
        if hasattr(args, "aspect_ratio")
        else None
    )
    if ar:
        return ar.width, ar.height
    if (
        hasattr(args, "width")
        and hasattr(args, "height")
        and args.width
        and args.height
    ):
        return args.width, args.height
    default_config = config_loader.load()
    ar = pm.get_aspect_ratio(default_config.size)
    if ar:
        return ar.width, ar.height
    return 1024, 1024


def cmd_generate(args: argparse.Namespace, config_loader: ConfigLoader) -> int:
    if not args.quiet:
        print(f"Generating image...")
        print(f"Prompt: {args.prompt}")
        if args.verbose:
            print(SERVER_WARNING)

    cfg = config_loader.load()

    server = args.server or cfg.server
    insecure = args.insecure if args.insecure is not None else cfg.insecure
    verify_ssl = args.verify_ssl if args.verify_ssl is not None else cfg.verify_ssl
    ssl_cert_path = args.ssl_cert or cfg.ssl_cert_path
    output_dir = args.output_dir or cfg.output_dir

    if args.model:
        model = args.model
    elif cfg.model:
        model = cfg.model
    elif cfg.last_used_model:
        model = cfg.last_used_model
    else:
        print(
            "ERROR: No model specified. Use --model or set default in config.",
            file=sys.stderr,
        )
        return 1

    if args.preset:
        pm = PresetManager()
        preset = pm.get_preset(args.preset)
        if not preset:
            print(f"ERROR: Preset not found: {args.preset}", file=sys.stderr)
            return 1
        steps = args.steps or preset.recommended_steps
        cfg_value = args.cfg or preset.recommended_cfg
        scheduler = args.scheduler or preset.sampler
        shift = preset.shift
        clip_skip = preset.clip_skip
        if args.clip_skip is not None:
            clip_skip = args.clip_skip
        seed_mode = preset.seed_mode
        tea_cache = preset.tea_cache
        base_res = preset.base_resolution
    else:
        steps = args.steps or cfg.steps
        cfg_value = args.cfg or cfg.cfg
        scheduler = args.scheduler or cfg.scheduler
        shift = 1.0
        clip_skip = 1
        seed_mode = 2
        tea_cache = False
        base_res = 1024
        clip_skip = args.clip_skip if args.clip_skip is not None else 1

    width, height = _resolve_aspect_ratio(args, config_loader)

    negative_prompt = ""
    if args.negative_prompt:
        negative_prompt = args.negative_prompt
    elif args.negative_preset:
        pm = PresetManager()
        np_obj = pm.get_negative_prompt(args.negative_preset)
        if np_obj:
            negative_prompt = np_obj.negative_prompt

    loras = None
    if args.lora:
        loras = []
        for lora_arg in args.lora:
            if ":" in lora_arg:
                lora_name, weight_str = lora_arg.rsplit(":", 1)
                try:
                    weight = float(weight_str)
                except ValueError:
                    weight = 1.0
                loras.append((lora_name, weight))
            else:
                loras.append((lora_arg, 1.0))

    client = DtlineClient(
        server=server,
        insecure=insecure,
        verify_ssl=verify_ssl,
        ssl_cert_path=ssl_cert_path,
    )

    try:
        if args.dry_run:
            print("Dry run - configuration is valid:")
            print(f"  Server: {server}")
            print(f"  Model: {model}")
            print(f"  Steps: {steps}, CFG: {cfg_value}")
            print(f"  Scheduler: {scheduler}")
            print(f"  Size: {width}x{height}")
            return 0

        if not args.quiet:
            print(f"Model: {model}")
            print(f"Size: {width}x{height}")
            if args.preset:
                print(f"Preset: {args.preset}")

        paths, metadata = client.generate(
            prompt=args.prompt,
            model=model,
            steps=steps,
            cfg=cfg_value,
            scheduler=scheduler,
            width=width,
            height=height,
            seed=args.seed,
            negative_prompt=negative_prompt,
            input_image=args.input_image,
            mask_image=args.mask_image,
            loras=loras,
            shift=shift,
            clip_skip=clip_skip,
            seed_mode=seed_mode,
            tea_cache=tea_cache,
            verbose=args.verbose,
            output_dir=output_dir,
        )

        if args.json:
            output = GenerationOutput(
                success=True,
                images=[
                    {
                        "path": str(p),
                        "bytes": p.stat().st_size,
                        "seed": metadata.get("seed"),
                    }
                    for p in paths
                ],
                metadata=metadata,
            )
            output.print_json()
        else:
            output = GenerationOutput(success=True)
            output.images = [
                {
                    "path": str(p),
                    "bytes": p.stat().st_size,
                    "seed": metadata.get("seed"),
                }
                for p in paths
            ]
            output.metadata = metadata
            output.print_human(verbose=args.verbose)

        return 0

    except DtlineError as e:
        if args.json:
            import json

            print(json.dumps(e.to_dict(), indent=2))
        else:
            print(f"ERROR: {e.message}", file=sys.stderr)
            if e.details:
                print(f"  {e.details}", file=sys.stderr)
        return 1
    finally:
        client.close()


def cmd_list_models(args: argparse.Namespace, config_loader: ConfigLoader) -> int:
    cfg = config_loader.load()
    server = args.server or cfg.server
    insecure = args.insecure if args.insecure is not None else cfg.insecure
    verify_ssl = args.verify_ssl if args.verify_ssl is not None else cfg.verify_ssl
    ssl_cert_path = args.ssl_cert or cfg.ssl_cert_path

    client = DtlineClient(
        server=server,
        insecure=insecure,
        verify_ssl=verify_ssl,
        ssl_cert_path=ssl_cert_path,
    )

    try:
        models, loras = client.list_models()
        output = ListModelsOutput(models=models, loras=loras)
        if args.json:
            output.print_json()
        else:
            output.print_human()
        return 0
    except DtlineError as e:
        if args.json:
            import json

            print(json.dumps(e.to_dict(), indent=2))
        else:
            print(f"ERROR: {e.message}", file=sys.stderr)
        return 1
    finally:
        client.close()


def cmd_info(args: argparse.Namespace, config_loader: ConfigLoader) -> int:
    cfg = config_loader.load()
    server = args.server or cfg.server
    insecure = args.insecure if args.insecure is not None else cfg.insecure
    verify_ssl = args.verify_ssl if args.verify_ssl is not None else cfg.verify_ssl
    ssl_cert_path = args.ssl_cert or cfg.ssl_cert_path

    client = DtlineClient(
        server=server,
        insecure=insecure,
        verify_ssl=verify_ssl,
        ssl_cert_path=ssl_cert_path,
    )

    try:
        info = client.get_model_info(args.model)
        output = ModelInfoOutput(name=args.model, metadata=info)
        if args.json:
            output.print_json()
        else:
            output.print_human()
        return 0
    except DtlineError as e:
        if args.json:
            import json

            print(json.dumps(e.to_dict(), indent=2))
        else:
            print(f"ERROR: {e.message}", file=sys.stderr)
        return 1
    finally:
        client.close()


def cmd_list_presets(args: argparse.Namespace, config_loader: ConfigLoader) -> int:
    pm = PresetManager()
    presets = pm.list_presets()
    output = PresetListOutput([p.to_dict() for p in presets])
    if args.json:
        output.print_json()
    else:
        output.print_human()
    return 0


def cmd_list_aspect_ratios(
    args: argparse.Namespace, config_loader: ConfigLoader
) -> int:
    pm = PresetManager()
    base_res = args.base_resolution if hasattr(args, "base_resolution") else 1024
    ratios = pm.list_aspect_ratios(base_res)
    output = AspectRatioListOutput(
        [{"label": r.label, "width": r.width, "height": r.height} for r in ratios]
    )
    if args.json:
        output.print_json()
    else:
        output.print_human()
    return 0


def cmd_list_negative_prompts(
    args: argparse.Namespace, config_loader: ConfigLoader
) -> int:
    pm = PresetManager()
    prompts = pm.list_negative_prompts()
    output = NegativePromptListOutput([p.to_dict() for p in prompts])
    if args.json:
        output.print_json()
    else:
        output.print_human()
    return 0


def cmd_config(args: argparse.Namespace, config_loader: ConfigLoader) -> int:
    cfg = config_loader.load()
    output = ConfigOutput(cfg.to_dict())
    if args.json:
        output.print_json()
    else:
        output.print_human()
    return 0


def cmd_edit(args: argparse.Namespace, config_loader: ConfigLoader) -> int:
    """Edit an image using AI instructions."""
    if not args.quiet:
        print(f"Editing image...")
        print(f"Image: {args.image}")
        print(f"Instruction: {args.instruction}")
        if args.verbose:
            print(SERVER_WARNING)

    cfg = config_loader.load()

    server = args.server or cfg.server
    insecure = args.insecure if args.insecure is not None else cfg.insecure
    verify_ssl = args.verify_ssl if args.verify_ssl is not None else cfg.verify_ssl
    ssl_cert_path = args.ssl_cert or cfg.ssl_cert_path
    output_dir = args.output_dir or cfg.output_dir

    if args.model:
        model = args.model
    elif cfg.model:
        model = cfg.model
    elif cfg.last_used_model:
        model = cfg.last_used_model
    else:
        print(
            "ERROR: No model specified. Use --model or set default in config.",
            file=sys.stderr,
        )
        return 1

    if args.preset:
        pm = PresetManager()
        preset = pm.get_preset(args.preset)
        if not preset:
            print(f"ERROR: Preset not found: {args.preset}", file=sys.stderr)
            return 1
        steps = args.steps or preset.recommended_steps
        cfg_value = args.cfg or preset.recommended_cfg
        scheduler = args.scheduler or preset.sampler
        shift = preset.shift
        clip_skip = preset.clip_skip
        if args.clip_skip is not None:
            clip_skip = args.clip_skip
        seed_mode = preset.seed_mode
        tea_cache = preset.tea_cache
        resolution_dependent_shift = preset.resolution_dependent_shift
    else:
        steps = args.steps or cfg.steps
        cfg_value = args.cfg or cfg.cfg
        scheduler = args.scheduler or cfg.scheduler
        shift = 1.0
        clip_skip = 1
        seed_mode = 2
        tea_cache = False
        resolution_dependent_shift = False
        clip_skip = args.clip_skip if args.clip_skip is not None else 1

    # Get strength and image_guidance_scale
    # strength=None means auto-detect (0.75 for standard img2img, 1.0 for edit models)
    strength = args.strength if args.strength is not None else None
    image_guidance_scale = (
        args.image_guidance_scale if args.image_guidance_scale is not None else 1.5
    )

    negative_prompt = ""
    if args.negative_prompt:
        negative_prompt = args.negative_prompt
    elif args.negative_preset:
        pm = PresetManager()
        np_obj = pm.get_negative_prompt(args.negative_preset)
        if np_obj:
            negative_prompt = np_obj.negative_prompt

    loras = None
    if args.lora:
        loras = []
        for lora_arg in args.lora:
            if ":" in lora_arg:
                lora_name, weight_str = lora_arg.rsplit(":", 1)
                try:
                    weight = float(weight_str)
                except ValueError:
                    weight = 1.0
                loras.append((lora_name, weight))
            else:
                loras.append((lora_arg, 1.0))

    client = DtlineClient(
        server=server,
        insecure=insecure,
        verify_ssl=verify_ssl,
        ssl_cert_path=ssl_cert_path,
    )

    try:
        if args.dry_run:
            print("Dry run - configuration is valid:")
            print(f"  Server: {server}")
            print(f"  Model: {model}")
            print(f"  Steps: {steps}, CFG: {cfg_value}")
            print(f"  Scheduler: {scheduler}")
            print(f"  Strength: {strength}")
            print(f"  Image Guidance: {image_guidance_scale}")
            print(f"  Input Image: {args.image}")
            return 0

        if not args.quiet:
            print(f"Model: {model}")
            if strength is not None:
                print(f"Strength: {strength}")
            print(f"Image Guidance: {image_guidance_scale}")
            if args.preset:
                print(f"Preset: {args.preset}")

        paths, metadata = client.edit(
            input_image=args.image,
            instruction=args.instruction,
            model=model,
            steps=steps,
            cfg=cfg_value,
            scheduler=scheduler,
            strength=strength,
            image_guidance_scale=image_guidance_scale,
            seed=args.seed,
            negative_prompt=negative_prompt,
            loras=loras,
            shift=shift,
            clip_skip=clip_skip,
            seed_mode=seed_mode,
            tea_cache=tea_cache,
            resolution_dependent_shift=resolution_dependent_shift,
            verbose=args.verbose,
            output_dir=output_dir,
        )

        if args.json:
            output = GenerationOutput(
                success=True,
                images=[
                    {
                        "path": str(p),
                        "bytes": p.stat().st_size,
                        "seed": metadata.get("seed"),
                    }
                    for p in paths
                ],
                metadata=metadata,
            )
            output.print_json()
        else:
            output = GenerationOutput(success=True)
            output.images = [
                {
                    "path": str(p),
                    "bytes": p.stat().st_size,
                    "seed": metadata.get("seed"),
                }
                for p in paths
            ]
            output.metadata = metadata
            output.print_human(verbose=args.verbose)

        return 0

    except DtlineError as e:
        if args.json:
            import json

            print(json.dumps(e.to_dict(), indent=2))
        else:
            print(f"ERROR: {e.message}", file=sys.stderr)
            if e.details:
                print(f"  {e.details}", file=sys.stderr)
        return 1
    finally:
        client.close()


def cmd_moodboard(args: argparse.Namespace, config_loader: ConfigLoader) -> int:
    """Generate image using multiple reference images."""
    if not args.quiet:
        print(f"Generating moodboard image...")
        print(f"Instruction: {args.instruction}")
        print(f"Reference images: {len(args.images)}")
        if args.verbose:
            print(SERVER_WARNING)

    cfg = config_loader.load()

    server = args.server or cfg.server
    insecure = args.insecure if args.insecure is not None else cfg.insecure
    verify_ssl = args.verify_ssl if args.verify_ssl is not None else cfg.verify_ssl
    ssl_cert_path = args.ssl_cert or cfg.ssl_cert_path
    output_dir = args.output_dir or cfg.output_dir

    if args.model:
        model = args.model
    elif cfg.model:
        model = cfg.model
    elif cfg.last_used_model:
        model = cfg.last_used_model
    else:
        print(
            "ERROR: No model specified. Use --model or set default in config.",
            file=sys.stderr,
        )
        return 1

    if args.preset:
        pm = PresetManager()
        preset = pm.get_preset(args.preset)
        if not preset:
            print(f"ERROR: Preset not found: {args.preset}", file=sys.stderr)
            return 1
        steps = args.steps or preset.recommended_steps
        cfg_value = args.cfg or preset.recommended_cfg
        scheduler = args.scheduler or preset.sampler
        shift = preset.shift
        clip_skip = preset.clip_skip
        if args.clip_skip is not None:
            clip_skip = args.clip_skip
        seed_mode = preset.seed_mode
        tea_cache = preset.tea_cache
        resolution_dependent_shift = preset.resolution_dependent_shift
    else:
        steps = args.steps or cfg.steps
        cfg_value = args.cfg or cfg.cfg
        scheduler = args.scheduler or cfg.scheduler
        shift = 1.0
        clip_skip = 1
        seed_mode = 2
        tea_cache = False
        resolution_dependent_shift = False
        clip_skip = args.clip_skip if args.clip_skip is not None else 1

    negative_prompt = ""
    if args.negative_prompt:
        negative_prompt = args.negative_prompt
    elif args.negative_preset:
        pm = PresetManager()
        np_obj = pm.get_negative_prompt(args.negative_preset)
        if np_obj:
            negative_prompt = np_obj.negative_prompt

    loras = None
    if args.lora:
        loras = []
        for lora_arg in args.lora:
            if ":" in lora_arg:
                lora_name, weight_str = lora_arg.rsplit(":", 1)
                try:
                    weight = float(weight_str)
                except ValueError:
                    weight = 1.0
                loras.append((lora_name, weight))
            else:
                loras.append((lora_arg, 1.0))

    client = DtlineClient(
        server=server,
        insecure=insecure,
        verify_ssl=verify_ssl,
        ssl_cert_path=ssl_cert_path,
    )

    try:
        if args.dry_run:
            print("Dry run - configuration is valid:")
            print(f"  Server: {server}")
            print(f"  Model: {model}")
            print(f"  Steps: {steps}, CFG: {cfg_value}")
            print(f"  Scheduler: {scheduler}")
            print(f"  Reference images: {len(args.images)}")
            for i, img in enumerate(args.images):
                print(f"    {i + 1}. {img}")
            return 0

        if not args.quiet:
            print(f"Model: {model}")
            print(f"Processing {len(args.images)} reference images...")

        paths, metadata = client.moodboard(
            instruction=args.instruction,
            model=model,
            reference_images=args.images,
            steps=steps,
            cfg=cfg_value,
            scheduler=scheduler,
            seed=args.seed,
            negative_prompt=negative_prompt,
            loras=loras,
            shift=shift,
            clip_skip=clip_skip,
            seed_mode=seed_mode,
            tea_cache=tea_cache,
            resolution_dependent_shift=resolution_dependent_shift,
            verbose=args.verbose,
            output_dir=output_dir,
        )

        if args.json:
            output = GenerationOutput(
                success=True,
                images=[
                    {
                        "path": str(p),
                        "bytes": p.stat().st_size,
                        "seed": metadata.get("seed"),
                    }
                    for p in paths
                ],
                metadata=metadata,
            )
            output.print_json()
        else:
            output = GenerationOutput(success=True)
            output.images = [
                {
                    "path": str(p),
                    "bytes": p.stat().st_size,
                    "seed": metadata.get("seed"),
                }
                for p in paths
            ]
            output.metadata = metadata
            output.print_human(verbose=args.verbose)

        return 0

    except DtlineError as e:
        if args.json:
            import json

            print(json.dumps(e.to_dict(), indent=2))
        else:
            print(f"ERROR: {e.message}", file=sys.stderr)
            if e.details:
                print(f"  {e.details}", file=sys.stderr)
        return 1
    finally:
        client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dtline",
        description="AI Agent Image Generation CLI for Draw Things gRPC Server",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 1.2.0")

    subparsers = parser.add_subparsers(dest="command", required=True)

    gen_parser = subparsers.add_parser(
        "generate",
        help="Generate an image",
        description=f"{SERVER_WARNING}",
    )
    gen_parser.add_argument("prompt", help="Text prompt for image generation")
    gen_parser.add_argument("--model", help="Model filename")
    gen_parser.add_argument("--preset", help="Preset name (from settings/presets/)")
    gen_parser.add_argument("--aspect-ratio", help="Aspect ratio (e.g., 3:4, 1:1)")
    gen_parser.add_argument("--width", type=int, help="Image width in pixels")
    gen_parser.add_argument("--height", type=int, help="Image height in pixels")
    gen_parser.add_argument("--steps", type=int, help="Number of steps")
    gen_parser.add_argument("--cfg", type=float, help="CFG scale")
    gen_parser.add_argument("--scheduler", help="Sampler name")
    gen_parser.add_argument("--clip-skip", type=int, help="CLIP skip layers")
    gen_parser.add_argument("--seed", type=int, help="Random seed")
    gen_parser.add_argument("--negative-prompt", help="Negative prompt")
    gen_parser.add_argument("--negative-preset", help="Negative prompt preset name")
    gen_parser.add_argument("--input-image", help="Input image for img2img")
    gen_parser.add_argument("--mask-image", help="Mask image for inpainting")
    gen_parser.add_argument(
        "--lora", action="append", help="LoRA in file:weight format"
    )
    gen_parser.add_argument(
        "--control-net", action="append", help="ControlNet file:type format"
    )
    gen_parser.add_argument("--output", help="Output filename")
    gen_parser.add_argument("--output-dir", help="Output directory")
    gen_parser.add_argument("--insecure", action="store_true", help="Disable TLS")
    gen_parser.add_argument(
        "--verify-ssl", action="store_true", help="Verify TLS certificates"
    )
    gen_parser.add_argument("--ssl-cert", help="Path to root CA certificate")
    gen_parser.add_argument("--server", help="gRPC server address")
    gen_parser.add_argument("--retries", type=int, default=3, help="Number of retries")
    gen_parser.add_argument(
        "--json", action="store_true", default=False, help="JSON output"
    )
    gen_parser.add_argument(
        "--dry-run", action="store_true", help="Validate without generating"
    )
    gen_parser.add_argument("--verbose", action="store_true", help="Verbose output")
    gen_parser.add_argument(
        "--quiet", action="store_true", help="Suppress progress output"
    )
    gen_parser.set_defaults(func=cmd_generate)

    models_parser = subparsers.add_parser(
        "list-models",
        help="List available models",
    )
    models_parser.add_argument("--json", action="store_true", default=False)
    models_parser.add_argument("--server", help="gRPC server address")
    models_parser.add_argument("--insecure", action="store_true")
    models_parser.add_argument("--verify-ssl", action="store_true")
    models_parser.add_argument("--ssl-cert", help="Path to root CA certificate")
    models_parser.set_defaults(func=cmd_list_models)

    info_parser = subparsers.add_parser(
        "info",
        help="Get model information",
    )
    info_parser.add_argument("model", help="Model name")
    info_parser.add_argument("--json", action="store_true", default=False)
    info_parser.add_argument("--server", help="gRPC server address")
    info_parser.add_argument("--insecure", action="store_true")
    info_parser.add_argument("--verify-ssl", action="store_true")
    info_parser.add_argument("--ssl-cert", help="Path to root CA certificate")
    info_parser.set_defaults(func=cmd_info)

    presets_parser = subparsers.add_parser(
        "list-presets",
        help="List available presets",
    )
    presets_parser.add_argument("--json", action="store_true", default=False)
    presets_parser.set_defaults(func=cmd_list_presets)

    ar_parser = subparsers.add_parser(
        "list-aspect-ratios",
        help="List available aspect ratios",
    )
    ar_parser.add_argument("--json", action="store_true", default=False)
    ar_parser.add_argument("--base-resolution", type=int, default=1024)
    ar_parser.set_defaults(func=cmd_list_aspect_ratios)

    np_parser = subparsers.add_parser(
        "list-negative-prompts",
        help="List available negative prompt presets",
    )
    np_parser.add_argument("--json", action="store_true", default=False)
    np_parser.set_defaults(func=cmd_list_negative_prompts)

    config_parser = subparsers.add_parser(
        "config",
        help="Show current configuration",
    )
    config_parser.add_argument("--json", action="store_true", default=False)
    config_parser.set_defaults(func=cmd_config)

    # Edit subcommand
    edit_parser = subparsers.add_parser(
        "edit",
        help="Edit an image using AI instructions",
        description=f"Edit an image using AI instructions. {SERVER_WARNING}",
    )
    edit_parser.add_argument("image", help="Path to input image to edit")
    edit_parser.add_argument(
        "instruction", help="Edit instruction (e.g., 'make it sunset')"
    )
    edit_parser.add_argument("--model", help="Model filename")
    edit_parser.add_argument("--preset", help="Preset name (from settings/presets/)")
    edit_parser.add_argument("--steps", type=int, help="Number of steps")
    edit_parser.add_argument("--cfg", type=float, help="CFG scale")
    edit_parser.add_argument("--scheduler", help="Sampler name")
    edit_parser.add_argument(
        "--strength",
        type=float,
        help="Edit strength (0.0-1.0). Auto-set to 1.0 for edit models (Klein, Qwen Edit, etc.)",
    )
    edit_parser.add_argument(
        "--image-guidance-scale", type=float, help="Image guidance scale, default: 1.5"
    )
    edit_parser.add_argument("--clip-skip", type=int, help="CLIP skip layers")
    edit_parser.add_argument("--seed", type=int, help="Random seed")
    edit_parser.add_argument("--negative-prompt", help="Negative prompt")
    edit_parser.add_argument("--negative-preset", help="Negative prompt preset name")
    edit_parser.add_argument(
        "--lora", action="append", help="LoRA in file:weight format"
    )
    edit_parser.add_argument("--output-dir", help="Output directory")
    edit_parser.add_argument("--insecure", action="store_true", help="Disable TLS")
    edit_parser.add_argument(
        "--verify-ssl", action="store_true", help="Verify TLS certificates"
    )
    edit_parser.add_argument("--ssl-cert", help="Path to root CA certificate")
    edit_parser.add_argument("--server", help="gRPC server address")
    edit_parser.add_argument("--retries", type=int, default=3, help="Number of retries")
    edit_parser.add_argument(
        "--json", action="store_true", default=False, help="JSON output"
    )
    edit_parser.add_argument(
        "--dry-run", action="store_true", help="Validate without editing"
    )
    edit_parser.add_argument("--verbose", action="store_true", help="Verbose output")
    edit_parser.add_argument(
        "--quiet", action="store_true", help="Suppress progress output"
    )
    edit_parser.set_defaults(func=cmd_edit)

    # Moodboard subcommand
    moodboard_parser = subparsers.add_parser(
        "moodboard",
        help="Generate image using multiple reference images (IP-Adapter)",
        description=f"Generate image using multiple reference images. {SERVER_WARNING}",
    )
    moodboard_parser.add_argument(
        "instruction",
        help="Instruction combining references (e.g., 'person from image 1 wearing outfit from image 2')",
    )
    moodboard_parser.add_argument(
        "images", nargs="+", help="Reference image paths (2-5 images recommended)"
    )
    moodboard_parser.add_argument("--model", help="Model filename")
    moodboard_parser.add_argument(
        "--preset", help="Preset name (from settings/presets/)"
    )
    moodboard_parser.add_argument("--steps", type=int, help="Number of steps")
    moodboard_parser.add_argument("--cfg", type=float, help="CFG scale")
    moodboard_parser.add_argument("--scheduler", help="Sampler name")
    moodboard_parser.add_argument("--clip-skip", type=int, help="CLIP skip layers")
    moodboard_parser.add_argument("--seed", type=int, help="Random seed")
    moodboard_parser.add_argument("--negative-prompt", help="Negative prompt")
    moodboard_parser.add_argument(
        "--negative-preset", help="Negative prompt preset name"
    )
    moodboard_parser.add_argument(
        "--lora", action="append", help="LoRA in file:weight format"
    )
    moodboard_parser.add_argument("--output-dir", help="Output directory")
    moodboard_parser.add_argument("--insecure", action="store_true", help="Disable TLS")
    moodboard_parser.add_argument(
        "--verify-ssl", action="store_true", help="Verify TLS certificates"
    )
    moodboard_parser.add_argument("--ssl-cert", help="Path to root CA certificate")
    moodboard_parser.add_argument("--server", help="gRPC server address")
    moodboard_parser.add_argument(
        "--json", action="store_true", default=False, help="JSON output"
    )
    moodboard_parser.add_argument(
        "--dry-run", action="store_true", help="Validate without generating"
    )
    moodboard_parser.add_argument(
        "--verbose", action="store_true", help="Verbose output"
    )
    moodboard_parser.add_argument(
        "--quiet", action="store_true", help="Suppress progress output"
    )
    moodboard_parser.set_defaults(func=cmd_moodboard)

    args = parser.parse_args(argv)
    config_loader = ConfigLoader()

    return args.func(args, config_loader)


if __name__ == "__main__":
    sys.exit(main())
