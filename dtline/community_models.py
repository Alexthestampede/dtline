"""Fallback model knowledge from drawthingsai/community-models.

Fetches models.txt / loras.txt / builtin.txt (cached 24h in DTLINE_HOME) so
dtline can validate names even when the connected server exposes no metadata,
and to normalize display names to the community-models catalog.
"""

import os
import re
import time
from pathlib import Path

BASE_URL = "https://raw.githubusercontent.com/drawthingsai/community-models/main/"
LIST_FILES = {
    "models": "models.txt",
    "loras": "loras.txt",
    "builtin": "builtin.txt",
    "uncurated_models": "uncurated_models.txt",
}
CACHE_TTL = 86400.0  # 24h

# Quantization / precision suffixes seen in DT checkpoint filenames
_QUANT_SUFFIXES = (
    "i8x", "i6x", "i4x", "q8p", "q6p", "q5p", "q4p", "f16", "f32", "bf16", "bf",
)


def _cache_path() -> Path:
    home = Path(os.environ.get("DTLINE_HOME", os.path.expanduser("~/.local/dtline")))
    return home / ".community_models_cache"


def _normalize(name: str) -> str:
    """Normalize a model name for comparison: lowercase alphanumerics only."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _file_core(filename: str) -> str:
    """'qwen_image_2.1_i4x.ckpt' -> normalized core 'qwenimage21'."""
    stem = Path(filename).stem
    parts = stem.split("_")
    if parts and parts[-1].lower() in _QUANT_SUFFIXES:
        parts = parts[:-1]
    # Also strip double-quant combos like 'q6p_q8p'
    while len(parts) > 1 and parts[-1].lower() in _QUANT_SUFFIXES:
        parts = parts[:-1]
    return _normalize("_".join(parts))


def _display_core(name: str) -> str:
    """'Qwen Image 2.1 (6-bit)' -> 'qwenimage21'; drops parens/brackets/quant."""
    cleaned = re.sub(r"\[.*?\]|\(.*?\)", "", name)
    return _normalize(cleaned)


def _fetch_list(kind: str) -> list[str]:
    import urllib.request

    url = BASE_URL + LIST_FILES[kind]
    with urllib.request.urlopen(url, timeout=5.0) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    return [line.strip() for line in text.splitlines() if line.strip()]


def _common_head(a: str, b: str) -> str:
    """Longest common leading substring of two normalized names."""
    out = []
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        out.append(ca)
    return "".join(out)


def _entry_core(entry: str) -> str:
    """Strip only a real file extension, keep dotted version numbers intact.

    'anima-base-1.0' -> 'animabase10' (Path.stem would eat '.0' as extension).
    'sd_v1.5_f16.ckpt' -> 'sd15' (quant/precision tokens also stripped).
    """
    name = entry.strip()
    # Only strip suffix if the name actually looks like a file (has .ckpt/.safetensors etc.)
    for ext in (".ckpt", ".safetensors", ".pth", ".sft"):
        if name.endswith(ext):
            name = name[: -len(ext)]
            break
    # Strip quant/precision tokens from the tail (f16, q8p, q6p_q8p, i8x, bf16...)
    parts = name.split("_")
    while len(parts) > 1 and parts[-1].lower().lstrip("qifd") in (
        "",
        "8p",
        "6p",
        "5p",
        "4p",
        "16",
        "32",
    ) or (len(parts) > 1 and parts[-1].lower() in _QUANT_SUFFIXES):
        parts = parts[:-1]
    return _normalize("_".join(parts))


def get_known_lists(force_reload: bool = False) -> dict[str, set[str]]:
    """Return {'models': set, 'loras': set, 'builtin': set} of normalized keys.

    Cached to disk for 24h; returns empty sets on any failure (offline etc.).
    """
    cache = _cache_path()
    now = time.time()
    if not force_reload and cache.exists() and now - cache.stat().st_mtime < CACHE_TTL:
        try:
            import json

            raw = json.loads(cache.read_text())
            return {k: set(v) for k, v in raw.items()}
        except Exception:
            pass

    result: dict[str, set[str]] = {k: set() for k in LIST_FILES}
    try:
        for kind, _ in LIST_FILES.items():
            for entry in _fetch_list(kind):
                result[kind].add(_entry_core(entry))
        cache.parent.mkdir(parents=True, exist_ok=True)
        import json

        cache.write_text(json.dumps({k: sorted(v) for k, v in result.items()}))
    except Exception:
        pass
    return result


def is_known_model(name_or_file: str) -> bool:
    """Heuristic: does this model name/filename match the DT community catalog?"""
    known = get_known_lists()
    candidates = {_display_core(name_or_file), _file_core(name_or_file)}
    all_models = (
        known.get("models", set())
        | known.get("builtin", set())
        | known.get("uncurated_models", set())
    )
    if not all_models:
        return True  # offline / no catalog: don't warn
    # 'v' is noise in version tokens: 'sd15' vs 'sdv15', 'animabasev10' vs 'animabase10'
    def variants(c: str) -> set[str]:
        out = {c}
        if c:
            out.add(c.replace("v", ""))
        return out

    def match_one(cand: str, pool: set[str]) -> bool:
        if not cand:
            return False
        for cv in variants(cand):
            if cv in pool:
                return True
            for p in pool:
                pv = p.replace("v", "") if len(p) < 40 else p
                if cv == pv or cv.startswith(pv) or pv.startswith(cv):
                    return True
                # Bracketed qualifiers ([distilled], [dev]) vanish from display
                # cores; match on the longest common leading segment instead.
                head = _common_head(cv, pv)
                if len(head) >= 8:
                    return True
        return False

    for cand in candidates:
        if match_one(cand, all_models):
            return True
    return False


def is_known_lora(name_or_file: str) -> bool:
    known = get_known_lists()
    candidates = {_display_core(name_or_file), _file_core(name_or_file)}
    loras = known.get("loras", set())
    if not loras:
        return True
    all_loras = loras
    # 'v' is noise in version tokens (see is_known_model)
    def variants(c: str) -> set[str]:
        out = {c}
        if c:
            out.add(c.replace("v", ""))
        return out

    for cand in candidates:
        for cv in variants(cand):
            if cv in all_loras:
                return True
            for p in all_loras:
                pv = p.replace("v", "") if len(p) < 40 else p
                if cv == pv or cv.startswith(pv) or pv.startswith(cv):
                    return True
    return False