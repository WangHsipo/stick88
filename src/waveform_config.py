import json
import sys
from pathlib import Path


APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", APP_ROOT))
CONFIG_PATH = APP_ROOT / "waveform_settings.json"

DEFAULT_CONFIG = {
    "tmctl_dir": str(RESOURCE_ROOT / "tmctl8020" / "dll"),
    "output_root": str(APP_ROOT / "waveforms"),
    "channels": [1, 2, 3],
    "max_points": None,
}


def load_config():
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        config = json.load(f)

    merged = DEFAULT_CONFIG.copy()
    merged.update(config)
    if not Path(merged["tmctl_dir"]).exists() and Path(DEFAULT_CONFIG["tmctl_dir"]).exists():
        merged["tmctl_dir"] = DEFAULT_CONFIG["tmctl_dir"]
    return merged


def save_config(config):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
