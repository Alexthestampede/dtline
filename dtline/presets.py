"""Preset, aspect ratio, and negative prompt loading from settings/."""

import json
from pathlib import Path
from typing import NamedTuple


SAMPLER_ID_TO_NAME = {
    0: "DPM++ 2M Karras",
    1: "Euler A",
    2: "DDIM",
    3: "PLMS",
    4: "DPM++ SDE Karras",
    5: "UniPC",
    6: "LCM",
    7: "Euler A Substep",
    8: "DPM++ SDE Substep",
    9: "TCD",
    10: "Euler A Trailing",
    11: "DPM++ SDE Trailing",
    12: "DPM++ 2M AYS",
    13: "Euler A AYS",
    14: "DPM++ SDE AYS",
    15: "DPM++ 2M Trailing",
    16: "DDIM Trailing",
    17: "UniPC Trailing",
    18: "UniPC AYS",
}

SAMPLER_NAME_TO_ID = {v: k for k, v in SAMPLER_ID_TO_NAME.items()}


class AspectRatio(NamedTuple):
    label: str
    width: int
    height: int
    original: str


def _normalize_sampler(sampler_value) -> str:
    if isinstance(sampler_value, str):
        return sampler_value
    elif isinstance(sampler_value, int):
        return SAMPLER_ID_TO_NAME.get(sampler_value, "Euler A Trailing")
    else:
        return "Euler A Trailing"


class Preset:
    def __init__(self, name: str, data: dict, source_path: Path | None = None):
        self.name = name
        self.data = data
        self.source_path = source_path

    @property
    def description(self) -> str:
        return self.data.get("description", "")

    @property
    def base_resolution(self) -> int:
        return self.data.get("base_resolution", 1024)

    @property
    def recommended_steps(self) -> int:
        return self.data.get("steps", self.data.get("recommended_steps", 16))

    @property
    def recommended_cfg(self) -> float:
        return self.data.get("guidanceScale", self.data.get("recommended_cfg", 5.0))

    @property
    def sampler(self) -> str:
        return _normalize_sampler(self.data.get("sampler", 10))

    @property
    def shift(self) -> float:
        return float(self.data.get("shift", 1.0))

    @property
    def resolution_dependent_shift(self) -> bool:
        return bool(self.data.get("resolutionDependentShift", False))

    @property
    def clip_skip(self) -> int:
        return int(self.data.get("clip_skip", 1))

    @property
    def seed_mode(self) -> int:
        return int(self.data.get("seedMode", 2))

    @property
    def tea_cache(self) -> bool:
        return bool(self.data.get("teaCache", False))

    @property
    def loras(self) -> list:
        return self.data.get("loras", [])

    @property
    def controls(self) -> list:
        return self.data.get("controls", [])

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "base_resolution": self.base_resolution,
            "recommended_steps": self.recommended_steps,
            "recommended_cfg": self.recommended_cfg,
            "sampler": self.sampler,
            "shift": self.shift,
            "resolution_dependent_shift": self.resolution_dependent_shift,
            "clip_skip": self.clip_skip,
            "seed_mode": self.seed_mode,
            "tea_cache": self.tea_cache,
            "loras": self.loras,
            "controls": self.controls,
        }


class NegativePrompt:
    def __init__(self, name: str, data: dict, source_path: Path | None = None):
        self.name = name
        self.data = data
        self.source_path = source_path

    @property
    def negative_prompt(self) -> str:
        return self.data.get("negative_prompt", "")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "negative_prompt": self.negative_prompt,
        }


class PresetManager:
    def __init__(self, settings_dir: Path | None = None):
        if settings_dir is None:
            settings_dir = Path(__file__).parent.parent / "settings"
        self.settings_dir = settings_dir
        self.presets_dir = settings_dir / "presets"
        self.negative_prompts_dir = settings_dir / "negative_prompts"
        self.aspect_ratio_file = settings_dir / "aspectratio.txt"

        self._presets_cache: dict[str, Preset] | None = None
        self._negative_prompts_cache: dict[str, NegativePrompt] | None = None
        self._aspect_ratios_cache: list[AspectRatio] | None = None

    def _load_presets(self) -> dict[str, Preset]:
        presets = {}
        if not self.presets_dir.exists():
            return presets
        for filepath in self.presets_dir.glob("*.json"):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                name = data.get("name", filepath.stem)
                presets[name] = Preset(name, data, filepath)
                presets[filepath.stem] = Preset(name, data, filepath)
            except Exception:
                pass
        return presets

    def _load_negative_prompts(self) -> dict[str, NegativePrompt]:
        prompts = {}
        if not self.negative_prompts_dir.exists():
            return prompts
        for filepath in self.negative_prompts_dir.glob("*.json"):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                name = data.get("name", filepath.stem)
                prompts[name] = NegativePrompt(name, data, filepath)
            except Exception:
                pass
        return prompts

    def _load_aspect_ratios(self, base_resolution: int = 1024) -> list[AspectRatio]:
        ratios = []
        scale_factor = base_resolution / 1024.0
        if not self.aspect_ratio_file.exists():
            return [
                AspectRatio("1:1 1024x1024", 1024, 1024, "1:1 1024x1024"),
            ]
        for line in self.aspect_ratio_file.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                label = parts[0]
                dimensions = parts[1]
                if "x" in dimensions:
                    try:
                        w, h = dimensions.split("x")
                        w = int(int(w) * scale_factor)
                        h = int(int(h) * scale_factor)
                        display = f"{label} {w}x{h}"
                        ratios.append(AspectRatio(display, w, h, line))
                    except ValueError:
                        continue
        return ratios

    def get_preset(self, name: str) -> Preset | None:
        if self._presets_cache is None:
            self._presets_cache = self._load_presets()
        preset = self._presets_cache.get(name)
        if preset:
            return preset
        for p in self._presets_cache.values():
            if name.lower() in p.name.lower() or p.name.lower() in name.lower():
                return p
        return None

    def get_negative_prompt(self, name: str) -> NegativePrompt | None:
        if self._negative_prompts_cache is None:
            self._negative_prompts_cache = self._load_negative_prompts()
        prompt = self._negative_prompts_cache.get(name)
        if prompt:
            return prompt
        for p in self._negative_prompts_cache.values():
            if name.lower() in p.name.lower() or p.name.lower() in name.lower():
                return p
        return None

    def get_aspect_ratio(self, identifier: str | None) -> AspectRatio | None:
        if identifier is None:
            return None
        if self._aspect_ratios_cache is None:
            self._aspect_ratios_cache = self._load_aspect_ratios()
        for ar in self._aspect_ratios_cache:
            if identifier in ar.label or identifier == ar.original:
                return ar
        return None

    def list_presets(self) -> list[Preset]:
        if self._presets_cache is None:
            self._presets_cache = self._load_presets()
        seen = set()
        result = []
        for p in self._presets_cache.values():
            if p.name not in seen:
                seen.add(p.name)
                result.append(p)
        return result

    def list_negative_prompts(self) -> list[NegativePrompt]:
        if self._negative_prompts_cache is None:
            self._negative_prompts_cache = self._load_negative_prompts()
        seen = set()
        result = []
        for p in self._negative_prompts_cache.values():
            if p.name not in seen:
                seen.add(p.name)
                result.append(p)
        return result

    def list_aspect_ratios(self, base_resolution: int = 1024) -> list[AspectRatio]:
        if (
            self._aspect_ratios_cache is None
            or self._aspect_ratios_cache[0].width != base_resolution
        ):
            self._aspect_ratios_cache = self._load_aspect_ratios(base_resolution)
        return self._aspect_ratios_cache
