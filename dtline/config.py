"""Configuration loading from environment, config file, and defaults."""

import json
import os
from pathlib import Path
from dataclasses import dataclass, field


DEFAULT_VALUES = {
    "server": "localhost:7859",
    "model": None,
    "scheduler": "Euler A Trailing",
    "steps": 16,
    "cfg": 5.0,
    "size": "1:1 1024x1024",
    "insecure": False,
    "verify_ssl": False,
    "ssl_cert_path": None,
    "output_dir": None,
}


@dataclass
class DtlineConfig:
    server: str = DEFAULT_VALUES["server"]
    model: str | None = DEFAULT_VALUES["model"]
    scheduler: str = DEFAULT_VALUES["scheduler"]
    steps: int = DEFAULT_VALUES["steps"]
    cfg: float = DEFAULT_VALUES["cfg"]
    size: str = DEFAULT_VALUES["size"]
    insecure: bool = DEFAULT_VALUES["insecure"]
    verify_ssl: bool = DEFAULT_VALUES["verify_ssl"]
    ssl_cert_path: str | None = DEFAULT_VALUES["ssl_cert_path"]
    output_dir: str = DEFAULT_VALUES["output_dir"]

    last_used_model: str | None = None
    last_used_lora: str | None = None

    def to_dict(self) -> dict:
        return {
            "server": self.server,
            "model": self.model,
            "scheduler": self.scheduler,
            "steps": self.steps,
            "cfg": self.cfg,
            "size": self.size,
            "insecure": self.insecure,
            "verify_ssl": self.verify_ssl,
            "ssl_cert_path": self.ssl_cert_path,
            "output_dir": self.output_dir,
            "last_used_model": self.last_used_model,
            "last_used_lora": self.last_used_lora,
        }


class ConfigLoader:
    def __init__(
        self, settings_dir: Path | None = None, install_dir: Path | None = None
    ):
        if settings_dir is None:
            settings_dir = Path(__file__).parent.parent / "settings"
        if install_dir is None:
            install_dir = Path(
                os.environ.get("DTLINE_HOME", os.path.expanduser("~/.local/dtline"))
            )
        self.settings_dir = settings_dir
        self.install_dir = install_dir
        self.config_file = settings_dir / "config.json"
        self.root_ca_path = install_dir / "root_ca.crt"

    def _load_from_file(self) -> dict:
        if not self.config_file.exists():
            return {}
        try:
            with open(self.config_file) as f:
                return json.load(f)
        except Exception:
            return {}

    def _env_override(self, base: dict) -> dict:
        env_mappings = {
            "DTLINE_SERVER": "server",
            "DTLINE_MODEL": "model",
            "DTLINE_SCHEDULER": "scheduler",
            "DTLINE_STEPS": "steps",
            "DTLINE_CFG": "cfg",
            "DTLINE_SIZE": "size",
            "DTLINE_INSECURE": "insecure",
            "DTLINE_VERIFY_SSL": "verify_ssl",
            "DTLINE_SSL_CERT": "ssl_cert_path",
            "DTLINE_OUTPUT_DIR": "output_dir",
        }
        for env_key, config_key in env_mappings.items():
            value = os.environ.get(env_key)
            if value is not None:
                if config_key in ("insecure", "verify_ssl"):
                    value = value.lower() in ("1", "true", "yes")
                elif config_key in ("steps",):
                    value = int(value)
                elif config_key in ("cfg",):
                    value = float(value)
                base[config_key] = value
        return base

    def load(self) -> DtlineConfig:
        defaults = dict(DEFAULT_VALUES)
        file_config = self._load_from_file()

        config_dict = {**defaults}
        config_dict["server"] = file_config.get("grpc_server", defaults["server"])
        config_dict["model"] = file_config.get("last_used_model", defaults["model"])
        config_dict["last_used_model"] = file_config.get("last_used_model")
        config_dict["last_used_lora"] = file_config.get("last_used_lora")
        config_dict["steps"] = file_config.get("default_steps", defaults["steps"])
        config_dict["cfg"] = file_config.get("default_cfg", defaults["cfg"])
        config_dict["size"] = file_config.get("default_aspect_ratio", defaults["size"])

        config_dict = self._env_override(config_dict)

        if config_dict["output_dir"] is None:
            config_dict["output_dir"] = str(self.install_dir / "outputs")

        if config_dict["ssl_cert_path"] is None and self.root_ca_path.exists():
            config_dict["ssl_cert_path"] = str(self.root_ca_path)

        return DtlineConfig(
            **{
                k: v
                for k, v in config_dict.items()
                if k in DtlineConfig.__dataclass_fields__
            }
        )

    def save(self, config: DtlineConfig) -> None:
        self.settings_dir.mkdir(parents=True, exist_ok=True)
        file_data = {
            "grpc_server": config.server,
            "last_used_model": config.last_used_model or config.model,
            "last_used_lora": config.last_used_lora,
            "default_steps": config.steps,
            "default_cfg": config.cfg,
            "default_aspect_ratio": config.size,
        }
        with open(self.config_file, "w") as f:
            json.dump(file_data, f, indent=2)


def get_default_config() -> DtlineConfig:
    return ConfigLoader().load()
