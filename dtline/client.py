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
    ReferenceImage,
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

    def _is_edit_model(self, model_name: str) -> bool:
        """Check if a model is an edit/kontext model that requires strength=1.0.

        Edit models include:
        - Flux Klein (kontext models)
        - Qwen Image Edit
        - InstructPix2Pix models
        - Other reference-based edit models
        """
        name_lower = model_name.lower()
        edit_keywords = [
            "klein",
            "kontext",
            "edit",
            "instruct",
            "pix2pix",
        ]
        return any(keyword in name_lower for keyword in edit_keywords)

    def _encode_reference_image(
        self, image_path: str, target_size: int = 1024
    ) -> tuple[bytes, bytes]:
        """Encode a reference image for moodboard/IP-Adapter.

        Args:
            image_path: Path to the reference image
            target_size: Target size for resizing (default 1024)

        Returns:
            Tuple of (image_tensor, sha256_hash)
        """
        from PIL import Image as PILImage
        import hashlib

        img = PILImage.open(image_path)
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Resize if too large (preserving aspect ratio)
        if max(img.size) > target_size:
            ratio = target_size / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, PILImage.Resampling.LANCZOS)

        # Round to 64 pixels
        width = ((img.width + 32) // 64) * 64
        height = ((img.height + 32) // 64) * 64
        if img.size != (width, height):
            img = img.resize((width, height), PILImage.Resampling.LANCZOS)

        # Encode to tensor
        client = self._get_client()
        tensor = client._encode_image(img, width, height)
        sha256 = hashlib.sha256(tensor).digest()

        return tensor, sha256

    def edit(
        self,
        input_image: str,
        instruction: str,
        model: str,
        steps: int,
        cfg: float,
        scheduler: str,
        strength: float | None = None,
        image_guidance_scale: float = 1.5,
        seed: int | None = None,
        negative_prompt: str = "",
        loras: list[tuple[str, float]] | None = None,
        shift: float = 1.0,
        clip_skip: int = 1,
        seed_mode: int = 2,
        tea_cache: bool = False,
        resolution_dependent_shift: bool = False,
        progress_callback: Callable[[str, int], None] | None = None,
        verbose: bool = False,
        output_dir: str | None = None,
    ) -> tuple[list[Path], dict]:
        """Edit an image using AI instructions (img2img/edit models).

        For edit/kontext models (Klein, Qwen Edit, etc.), strength is automatically
        set to 1.0 regardless of user input, as required by these models.

        Args:
            input_image: Path to input image to edit
            instruction: Text instruction for the edit (e.g., "make it sunset")
            model: Model name/filename to use
            steps: Number of generation steps
            cfg: CFG scale
            scheduler: Scheduler/sampler name
            strength: Edit strength (0.0-1.0). Default is 0.75 for standard img2img,
                     automatically set to 1.0 for edit/kontext models.
            image_guidance_scale: Image guidance for edit models, default 1.5
            seed: Random seed (None for random)
            negative_prompt: Negative prompt
            loras: List of (name, weight) tuples
            shift: Shift parameter
            clip_skip: CLIP skip layers
            seed_mode: Seed mode
            tea_cache: Enable TeaCache
            resolution_dependent_shift: Auto-calculate shift from resolution
            progress_callback: Progress callback
            verbose: Verbose output
            output_dir: Output directory

        Returns:
            Tuple of (list of output paths, metadata dict)
        """
        import math

        if seed is None:
            seed = random.randint(0, 2**32 - 1)

        model_filename = self._resolve_model_name(model)

        # Auto-detect edit models and enforce strength=1.0
        if self._is_edit_model(model_filename):
            effective_strength = 1.0
            if strength is not None and strength != 1.0 and verbose:
                print(
                    f"Note: Edit model detected ({model}), forcing strength=1.0 (was {strength})"
                )
        else:
            effective_strength = strength if strength is not None else 0.75

        # Load and validate input image
        input_path = Path(input_image)
        if not input_path.exists():
            raise image_not_found(str(input_path))

        # Load image to get dimensions
        from PIL import Image as PILImage

        pil_img = PILImage.open(input_path)
        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")

        # Cap to max resolution (edit models work best at 1024-1536px)
        MAX_EDIT_PIXELS = 2048
        longest_side = max(pil_img.width, pil_img.height)
        if longest_side > MAX_EDIT_PIXELS:
            scale_down = MAX_EDIT_PIXELS / longest_side
            new_w = int(pil_img.width * scale_down)
            new_h = int(pil_img.height * scale_down)
            pil_img = pil_img.resize((new_w, new_h), PILImage.Resampling.LANCZOS)

        # Round to nearest 64 pixels (required for VAE)
        width = ((pil_img.width + 32) // 64) * 64
        height = ((pil_img.height + 32) // 64) * 64

        if pil_img.size != (width, height):
            pil_img = pil_img.resize((width, height), PILImage.Resampling.LANCZOS)

        # Calculate resolution-dependent shift if enabled
        final_shift = float(shift)
        if resolution_dependent_shift:
            resolution_factor = (width * height) / 256
            final_shift = math.exp(
                ((resolution_factor - 256) * (1.15 - 0.5) / (4096 - 256)) + 0.5
            )

        if loras:
            lora_configs = [
                LoRAConfig(file=name, weight=weight) for name, weight in loras
            ]
        else:
            lora_configs = []

        # Build generation config
        config = ImageGenerationConfig(
            model=model_filename,
            steps=steps,
            width=width,
            height=height,
            cfg_scale=cfg,
            scheduler=scheduler,
            seed=seed,
            strength=effective_strength,
            image_guidance_scale=image_guidance_scale,
            shift=final_shift,
            clip_skip=clip_skip,
            seed_mode=seed_mode,
            tea_cache=tea_cache,
            resolution_dependent_shift=resolution_dependent_shift,
            loras=lora_configs,
        )

        # Set original/target dimensions for edit models
        config.original_image_width = width
        config.original_image_height = height
        config.target_image_width = width
        config.target_image_height = height

        try:
            client = self._get_client()
            tracker = ProgressTracker(steps, verbose=verbose)

            def progress_wrapper(stage: str, step: int):
                tracker.update(stage, step)
                if progress_callback:
                    progress_callback(stage, step)

            # Encode image and send request
            image_tensor = client._encode_image(pil_img, width, height)
            image_hash = __import__("hashlib").sha256(image_tensor).digest()

            import imageService_pb2

            config_bytes = config.to_flatbuffer()

            request = imageService_pb2.ImageGenerationRequest(
                prompt=instruction,
                negativePrompt=negative_prompt if negative_prompt else "",
                configuration=config_bytes,
                scaleFactor=1,
                user="dtline",
                device=imageService_pb2.LAPTOP,
                chunked=True,
                image=image_hash,
                contents=[image_tensor],
            )

            # Stream response
            generated_images = []
            image_chunks = []

            for response in client.stub.GenerateImage(request):
                # Handle progress signposts
                if response.HasField("currentSignpost"):
                    signpost = response.currentSignpost
                    if signpost.HasField("sampling"):
                        progress_wrapper("Sampling", signpost.sampling.step)
                    elif signpost.HasField("textEncoded"):
                        progress_wrapper("Text Encoded", 0)
                    elif signpost.HasField("imageEncoded"):
                        progress_wrapper("Image Encoded", 0)
                    elif signpost.HasField("imageDecoded"):
                        progress_wrapper("Image Decoded", 0)

                # Handle chunked responses
                if response.generatedImages:
                    for img_data in response.generatedImages:
                        image_chunks.append(img_data)

                    if response.chunkState == imageService_pb2.LAST_CHUNK:
                        if len(image_chunks) > 1:
                            combined = b"".join(image_chunks)
                            generated_images.append(combined)
                        elif len(image_chunks) == 1:
                            generated_images.append(image_chunks[0])
                        image_chunks = []

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
                filename = f"dtline_edit_{timestamp}_{seed}_{i + 1}.png"
                filepath = out_dir / filename
                pil_img.save(filepath, "PNG")
                output_paths.append(filepath)

            metadata = {
                "model": model,
                "steps": steps,
                "cfg": cfg,
                "scheduler": scheduler,
                "strength": effective_strength,
                "image_guidance_scale": image_guidance_scale,
                "width": width,
                "height": height,
                "seed": seed,
                "duration_seconds": time.time() - tracker.start_time,
                "instruction": instruction,
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

    def moodboard(
        self,
        instruction: str,
        model: str,
        reference_images: list[str],
        steps: int,
        cfg: float,
        scheduler: str,
        seed: int | None = None,
        negative_prompt: str = "",
        loras: list[tuple[str, float]] | None = None,
        shift: float = 1.0,
        clip_skip: int = 1,
        seed_mode: int = 2,
        tea_cache: bool = False,
        resolution_dependent_shift: bool = False,
        progress_callback: Callable[[str, int], None] | None = None,
        verbose: bool = False,
        output_dir: str | None = None,
    ) -> tuple[list[Path], dict]:
        """Generate image using multiple reference images (moodboard/IP-Adapter).

        This combines multiple reference images (person from image 1, suit from image 2,
        background from image 3, etc.) using IP-Adapter Plus for style/composition reference.

        Args:
            instruction: Text instruction combining the references
                       (e.g., "person from image 1 with the suit from image 2")
            model: Model name/filename to use
            reference_images: List of paths to reference images (2-4 recommended)
            steps: Number of generation steps
            cfg: CFG scale
            scheduler: Scheduler/sampler name
            seed: Random seed (None for random)
            negative_prompt: Negative prompt
            loras: List of (name, weight) tuples
            shift: Shift parameter
            clip_skip: CLIP skip layers
            seed_mode: Seed mode
            tea_cache: Enable TeaCache
            resolution_dependent_shift: Auto-calculate shift from resolution
            progress_callback: Progress callback
            verbose: Verbose output
            output_dir: Output directory

        Returns:
            Tuple of (list of output paths, metadata dict)
        """
        import math

        if seed is None:
            seed = random.randint(0, 2**32 - 1)

        model_filename = self._resolve_model_name(model)

        # Validate reference images
        if len(reference_images) < 1:
            raise invalid_config("At least one reference image is required")
        if len(reference_images) > 5:
            raise invalid_config("Maximum 5 reference images supported")

        # Build LoRA configs
        if loras:
            lora_configs = [
                LoRAConfig(file=name, weight=weight) for name, weight in loras
            ]
        else:
            lora_configs = []

        # Default size for moodboard (1024x1024 is standard)
        width, height = 1024, 1024

        # Calculate shift
        final_shift = float(shift)
        if resolution_dependent_shift:
            resolution_factor = (width * height) / 256
            final_shift = math.exp(
                ((resolution_factor - 256) * (1.15 - 0.5) / (4096 - 256)) + 0.5
            )

        try:
            client = self._get_client()
            tracker = ProgressTracker(steps, verbose=verbose)

            def progress_wrapper(stage: str, step: int):
                tracker.update(stage, step)
                if progress_callback:
                    progress_callback(stage, step)

            # Build generation config
            config = ImageGenerationConfig(
                model=model_filename,
                steps=steps,
                width=width,
                height=height,
                cfg_scale=cfg,
                scheduler=scheduler,
                seed=seed,
                shift=final_shift,
                clip_skip=clip_skip,
                seed_mode=seed_mode,
                tea_cache=tea_cache,
                resolution_dependent_shift=resolution_dependent_shift,
                loras=lora_configs,
            )

            # Build reference images using new DTgRPCconnector ReferenceImage
            reference_image_objects = []
            for img_path in reference_images:
                ref = ReferenceImage(
                    image=img_path,
                    weight=1.0 / len(reference_images),
                    hint_type="shuffle",  # Use "shuffle" for edit models like Klein
                )
                reference_image_objects.append(ref)

            # Use the updated generate_image with reference_images support
            generated_images = client.generate_image(
                prompt=instruction,
                config=config,
                negative_prompt=negative_prompt,
                reference_images=reference_image_objects,
                progress_callback=progress_wrapper,
            )

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
                filename = f"dtline_moodboard_{timestamp}_{seed}_{i + 1}.png"
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
                "reference_images": len(reference_image_objects),
                "duration_seconds": time.time() - tracker.start_time,
                "instruction": instruction,
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
