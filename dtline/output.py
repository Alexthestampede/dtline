"""Output formatters for human and JSON output."""

import json
import sys
from pathlib import Path
from typing import Any


class OutputFormatter:
    def __init__(self, json_mode: bool = False, verbose: bool = False):
        self.json_mode = json_mode
        self.verbose = verbose

    def _json_output(self, data: dict) -> None:
        print(json.dumps(data, indent=2))

    def _human_output(self, data: dict) -> None:
        raise NotImplementedError


class HumanProgressFormatter:
    def __init__(self, desc: str = "", total: int | None = None, stream: Any = None):
        self.desc = desc
        self.total = total
        self.current = 0
        self.stream = stream or sys.stdout
        self._bar_width = 30

    def update(self, step: int | None = None, desc: str | None = None) -> None:
        if step is not None:
            self.current = step
        if desc is not None:
            self.desc = desc
        if self.total and self.total > 0:
            pct = self.current / self.total
            filled = int(self._bar_width * pct)
            bar = "█" * filled + "░" * (self._bar_width - filled)
            prefix = f"\r[{self.desc}] " if self.desc else ""
            self.stream.write(f"{prefix}{bar} {self.current}/{self.total} steps")
            self.stream.flush()

    def complete(self) -> None:
        if self.total and self.total > 0:
            self.stream.write("\n")
            self.stream.flush()


class GenerationOutput:
    def __init__(
        self,
        success: bool,
        images: list[dict] | None = None,
        metadata: dict | None = None,
        error: dict | None = None,
    ):
        self.success = success
        self.images = images or []
        self.metadata = metadata or {}
        self.error = error

    def to_dict(self) -> dict:
        result = {"success": self.success}
        if self.images:
            result["images"] = self.images
        if self.metadata:
            result["metadata"] = self.metadata
        if self.error:
            result["error"] = self.error
        return result

    def print_json(self) -> None:
        print(json.dumps(self.to_dict(), indent=2))

    def print_human(self, verbose: bool = False) -> None:
        if not self.success:
            print(
                f"ERROR: {self.error.get('code', 'UNKNOWN')}: {self.error.get('message', 'Unknown error')}"
            )
            if self.error.get("details"):
                print(f"  Details: {self.error['details']}")
            return

        for img in self.images:
            path = img.get("path", "unknown")
            size = img.get("bytes", 0)
            size_str = self._format_size(size)
            seed = img.get("seed", "N/A")
            duration = self.metadata.get("duration_seconds", 0)

            print(f"✓ Generated: {path} ({size_str}, seed={seed}, {duration:.1f}s)")

        if verbose:
            print(f"\nModel: {self.metadata.get('model', 'N/A')}")
            print(f"Steps: {self.metadata.get('steps', 'N/A')}")
            print(
                f"Size: {self.metadata.get('width', 'N/A')}x{self.metadata.get('height', 'N/A')}"
            )

    @staticmethod
    def _format_size(bytes_count: int) -> str:
        if bytes_count < 1024:
            return f"{bytes_count}B"
        elif bytes_count < 1024 * 1024:
            return f"{bytes_count / 1024:.1f}KB"
        else:
            return f"{bytes_count / (1024 * 1024):.1f}MB"


class ListModelsOutput:
    def __init__(
        self,
        models: list[str],
        loras: list[str] | None = None,
        error: dict | None = None,
    ):
        self.models = models
        self.loras = loras or []
        self.error = error

    def to_dict(self) -> dict:
        result: dict[str, Any] = {"success": True}
        result["models"] = self.models
        result["loras"] = self.loras
        return result

    def print_json(self) -> None:
        print(json.dumps(self.to_dict(), indent=2))

    def print_human(self) -> None:
        print(f"Models ({len(self.models)}):")
        for model in sorted(self.models):
            print(f"  • {model}")
        if self.loras:
            print(f"\nLoRAs ({len(self.loras)}):")
            for lora in sorted(self.loras):
                print(f"  • {lora}")


class ModelInfoOutput:
    def __init__(
        self, name: str, metadata: dict | None = None, error: dict | None = None
    ):
        self.name = name
        self.metadata = metadata or {}
        self.error = error

    def to_dict(self) -> dict:
        result: dict[str, Any] = {"success": True, "model": self.name}
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    def print_json(self) -> None:
        print(json.dumps(self.to_dict(), indent=2))

    def print_human(self) -> None:
        if self.error:
            print(f"ERROR: {self.error.get('message', 'Unknown error')}")
            return
        print(f"Model: {self.name}")
        for key, value in self.metadata.items():
            print(f"  {key}: {value}")


class PresetListOutput:
    def __init__(self, presets: list[dict], error: dict | None = None):
        self.presets = presets
        self.error = error

    def to_dict(self) -> dict:
        return {"success": True, "presets": self.presets}

    def print_json(self) -> None:
        print(json.dumps(self.to_dict(), indent=2))

    def print_human(self) -> None:
        for preset in self.presets:
            name = preset.get("name", "unknown")
            desc = preset.get("description", "")
            steps = preset.get("recommended_steps", "?")
            cfg = preset.get("recommended_cfg", "?")
            sampler = preset.get("sampler", "?")
            print(f"  • {name}")
            if desc:
                print(f"    {desc}")
            print(f"    Steps: {steps}, CFG: {cfg}, Sampler: {sampler}")


class AspectRatioListOutput:
    def __init__(self, aspect_ratios: list[dict], error: dict | None = None):
        self.aspect_ratios = aspect_ratios
        self.error = error

    def to_dict(self) -> dict:
        return {"success": True, "aspect_ratios": self.aspect_ratios}

    def print_json(self) -> None:
        print(json.dumps(self.to_dict(), indent=2))

    def print_human(self) -> None:
        for ar in self.aspect_ratios:
            print(f"  • {ar['label']} ({ar['width']}x{ar['height']})")


class NegativePromptListOutput:
    def __init__(self, prompts: list[dict], error: dict | None = None):
        self.prompts = prompts
        self.error = error

    def to_dict(self) -> dict:
        return {"success": True, "negative_prompts": self.prompts}

    def print_json(self) -> None:
        print(json.dumps(self.to_dict(), indent=2))

    def print_human(self) -> None:
        for prompt in self.prompts:
            name = prompt.get("name", "unknown")
            text = prompt.get("negative_prompt", "")
            preview = text[:60] + "..." if len(text) > 60 else text
            print(f"  • {name}: {preview}")


class ConfigOutput:
    def __init__(self, config: dict):
        self.config = config

    def to_dict(self) -> dict:
        return {"success": True, "config": self.config}

    def print_json(self) -> None:
        print(json.dumps(self.to_dict(), indent=2))

    def print_human(self) -> None:
        print("dtline Configuration:")
        print(f"  Server: {self.config.get('server', 'N/A')}")
        print(f"  Model: {self.config.get('model', 'N/A')}")
        print(f"  Scheduler: {self.config.get('scheduler', 'N/A')}")
        print(f"  Steps: {self.config.get('steps', 'N/A')}")
        print(f"  CFG: {self.config.get('cfg', 'N/A')}")
        print(f"  Size: {self.config.get('size', 'N/A')}")
        print(f"  Insecure: {self.config.get('insecure', 'N/A')}")
        print(f"  Verify SSL: {self.config.get('verify_ssl', 'N/A')}")
        print(f"  SSL Cert: {self.config.get('ssl_cert_path', 'N/A')}")
        print(f"  Output Dir: {self.config.get('output_dir', 'N/A')}")
