"""Wrapper around DrawThingsClient with error handling and dtline-specific logic."""

import sys
import time
import random
import os
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from typing import Any, Callable, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "DTgRPCconnector"))

from drawthings_client import (
    DrawThingsClient,
    ImageGenerationConfig,
    LoRAConfig,
)
from tensor_decoder import tensor_to_pil

from .errors import (
    DtlineError,
    connection_error,
    auth_error,
    model_not_found,
    generation_error,
    invalid_config,
    image_not_found,
    server_busy,
)
from .presets import PresetManager, SAMPLER_NAME_TO_ID


class ProgressTracker:
    def __init__(self, total_steps: int, verbose: bool = False):
        self.total_steps = total_steps
        self.verbose = verbose
        self.current_step = 0
        self.start_time = time.time()
        self._bar_width = 30

    def update(self, stage: str, step: int) -> None:
        self.current_step = step
        if self.verbose:
            pct = step / self.total_steps if self.total_steps > 0 else 0
            filled = int(self._bar_width * pct)
            bar = "█" * filled + "░" * (self._bar_width - filled)
            elapsed = time.time() - self.start_time
            sys.stderr.write(
                f"\r[sampling] {bar} {step}/{self.total_steps} steps | {elapsed:.1f}s    "
            )
            sys.stderr.flush()

    def finish(self) -> None:
        if self.verbose:
            sys.stderr.write("\n")
            sys.stderr.flush()


class DtlineClient:
    def __init__(
        self,
        server: str,
        insecure: bool = False,
        verify_ssl: bool = False,
        ssl_cert_path: str | None = None,
    ):
        self.server = server
        self.insecure = insecure
        self.verify_ssl = verify_ssl
        self.ssl_cert_path = ssl_cert_path
        self._client: DrawThingsClient | None = None
        self._preset_manager = PresetManager()
        self._model_cache: dict[str, list[dict]] | None = None

    def _fetch_model_metadata(self) -> dict[str, list[dict]]:
        if self._model_cache is not None:
            return self._model_cache
        try:
            import json

            client = self._get_client()
            response = client.echo("list_files")
            if response.HasField("override"):
                self._model_cache = json.loads(response.override.models)
            else:
                self._model_cache = []
        except Exception:
            self._model_cache = []
        return self._model_cache

    def _resolve_model_name(self, model_name: str) -> str:
        metadata = self._fetch_model_metadata()
        for m in metadata:
            if m.get("name") == model_name or m.get("file") == model_name:
                return m.get("file", model_name)
        return model_name

    def _get_model_latent_size(self, model_filename: str) -> int:
        """Get the latent size for a model. SDXL models have latent_size=128."""
        metadata = self._fetch_model_metadata()
        for m in metadata:
            if m.get("file") == model_filename or m.get("name") == model_filename:
                default_scale = m.get("default_scale")
                if default_scale:
                    return 1024 // default_scale
        return 64  # Default SD 1.5 latent size

    def _get_client(self) -> DrawThingsClient:
        if self._client is None:
            self._client = DrawThingsClient(
                server_address=self.server,
                insecure=self.insecure,
                verify_ssl=self.verify_ssl,
                ssl_cert_path=self.ssl_cert_path,
            )
        return self._client

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def connect(self) -> None:
        try:
            client = self._get_client()
            client.echo("dtline")
        except Exception as e:
            error_str = str(e).lower()
            if "ssl" in error_str or "tls" in error_str or "certificate" in error_str:
                raise auth_error(
                    "TLS/SSL connection failed",
                    "If using a self-signed certificate, ensure root_ca.crt is available. "
                    "Try: --ssl-cert ~/.local/dtline/root_ca.crt or --insecure",
                ) from e
            elif "connection refused" in error_str or "failed to connect" in error_str:
                raise connection_error(str(e)) from e
            else:
                raise connection_error(str(e)) from e

    def list_models(self) -> tuple[list[str], list[str]]:
        try:
            client = self._get_client()
            response = client.echo("list_models")
            models = []
            loras = []

            if response.HasField("override"):
                import json

                try:
                    models_data = (
                        json.loads(response.override.models)
                        if response.override.models
                        else []
                    )
                    loras_data = (
                        json.loads(response.override.loras)
                        if response.override.loras
                        else []
                    )

                    for m in models_data:
                        if m.get("file"):
                            models.append(m.get("name", m["file"]))

                    for l in loras_data:
                        if l.get("file"):
                            loras.append(l.get("name", l["file"]))
                except (json.JSONDecodeError, AttributeError):
                    pass

            if not models and response.files:
                for filename in response.files:
                    lower = filename.lower()
                    if ".ckpt" in lower or ".safetensors" in lower:
                        if "lora" not in lower:
                            models.append(filename)
                        else:
                            loras.append(filename)

            return sorted(models), sorted(loras)
        except Exception as e:
            raise connection_error(str(e)) from e

    def get_model_info(self, model_name: str) -> dict:
        models, _ = self.list_models()
        if model_name not in models:
            raise model_not_found(model_name)
        return {
            "name": model_name,
            "available": True,
        }

    def generate(
        self,
        prompt: str,
        model: str,
        steps: int,
        cfg: float,
        scheduler: str,
        width: int,
        height: int,
        seed: int | None = None,
        negative_prompt: str = "",
        input_image: str | None = None,
        mask_image: str | None = None,
        loras: list[tuple[str, float]] | None = None,
        controls: list[dict] | None = None,
        shift: float = 1.0,
        clip_skip: int = 1,
        seed_mode: int = 2,
        tea_cache: bool = False,
        hires_fix: bool = False,
        hires_fix_start_width: int = 0,
        hires_fix_start_height: int = 0,
        hires_fix_strength: float = 0.7,
        progress_callback: Callable[[str, int], None] | None = None,
        verbose: bool = False,
        output_dir: str | None = None,
    ) -> tuple[list[Path], dict]:
        if seed is None:
            seed = random.randint(0, 2**32 - 1)

        model_filename = self._resolve_model_name(model)

        if loras:
            lora_configs = [
                LoRAConfig(file=name, weight=weight) for name, weight in loras
            ]
        else:
            lora_configs = []

        config = ImageGenerationConfig(
            model=model_filename,
            steps=steps,
            width=width,
            height=height,
            cfg_scale=cfg,
            scheduler=scheduler,
            seed=seed,
            shift=shift,
            clip_skip=clip_skip,
            seed_mode=seed_mode,
            tea_cache=tea_cache,
            hires_fix=hires_fix,
            hires_fix_start_width=hires_fix_start_width // 64,
            hires_fix_start_height=hires_fix_start_height // 64,
            hires_fix_strength=hires_fix_strength,
            loras=lora_configs,
        )

        # SDXL conditioning: only set original/target dimensions for SDXL models (latent_size=128)
        latent_size = self._get_model_latent_size(model_filename)
        if latent_size == 128:  # SDXL models
            config.original_image_width = width
            config.original_image_height = height
            config.target_image_width = width
            config.target_image_height = height

        if hires_fix:
            config.original_image_width = width
            config.original_image_height = height
            config.target_image_width = width
            config.target_image_height = height

        if input_image:
            input_path = Path(input_image)
            if not input_path.exists():
                raise image_not_found(str(input_path))

        if mask_image:
            mask_path = Path(mask_image)
            if not mask_path.exists():
                raise image_not_found(str(mask_path))

        try:
            client = self._get_client()
            tracker = ProgressTracker(steps, verbose=verbose)

            def progress_wrapper(stage: str, step: int):
                tracker.update(stage, step)
                if progress_callback:
                    progress_callback(stage, step)

            generated_images = client.generate_image(
                prompt=prompt,
                config=config,
                negative_prompt=negative_prompt,
                input_image=input_image,
                mask_image=mask_image,
                progress_callback=progress_wrapper,
            )

            tracker.finish()

            if not generated_images:
                raise generation_error("No images were returned from the server")

            output_paths = []
            for i, image_data in enumerate(generated_images):
                buffer = StringIO()
                with redirect_stdout(buffer), redirect_stderr(buffer):
                    pil_img = tensor_to_pil(image_data)
                out_dir = Path(output_dir) if output_dir else Path("outputs")
                out_dir.mkdir(parents=True, exist_ok=True)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"dtline_{timestamp}_{seed}_{i + 1}.png"
                filepath = out_dir / filename
                pil_img.save(filepath, "PNG")
                output_paths.append(filepath)

            metadata = {
                "model": model,
                "steps": steps,
                "cfg": cfg,
                "scheduler": scheduler,
                "width": width,
                "height": height,
                "seed": seed,
                "duration_seconds": time.time() - tracker.start_time,
                "prompt": prompt,
                "negative_prompt": negative_prompt,
            }

            return output_paths, metadata

        except DtlineError:
            raise
        except Exception as e:
            error_str = str(e).lower()
            if "connection" in error_str or "refused" in error_str:
                raise connection_error(str(e)) from e
            elif "ssl" in error_str or "tls" in error_str or "certificate" in error_str:
                raise auth_error("TLS error during generation", str(e)) from e
            else:
                raise generation_error(str(e)) from e

    def apply_preset(
        self,
        preset_name: str,
        base_resolution: int = 1024,
    ) -> dict:
        preset = self._preset_manager.get_preset(preset_name)
        if not preset:
            from .errors import preset_not_found

            raise preset_not_found(preset_name)

        return {
            "steps": preset.recommended_steps,
            "cfg": preset.recommended_cfg,
            "scheduler": preset.sampler,
            "shift": preset.shift,
            "resolution_dependent_shift": preset.resolution_dependent_shift,
            "clip_skip": preset.clip_skip,
            "seed_mode": preset.seed_mode,
            "tea_cache": preset.tea_cache,
            "base_resolution": preset.base_resolution,
        }
