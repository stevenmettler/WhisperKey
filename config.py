"""
Central config for WhisperKey. Keeping this as a simple module-level
dict for now — swap for a JSON file + settings UI once the core loop works.
"""

import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "settings.json")

DEFAULTS = {
    "model_size": "small.en",      # tiny.en, base.en, small.en, medium.en, large-v3
    "device": "cuda",              # "cuda" (NVIDIA GPU) or "cpu"
    "compute_type": "float16",     # float16 (GPU) or int8 (fast, CPU-friendly)
    "hotkey": "f9",                # push-to-talk key
    "language": "en",
    "sample_rate": 16000,          # Whisper's native rate — don't change
    "mic_device": None,            # None = system default input device
    # Priming prompt that ends in varied punctuation — nudges Whisper toward
    # producing '?' / '!' / ',' on short, fast utterances. Set to null to disable.
    "initial_prompt": "Hello, how are you? I'm doing great! Let's get started.",
    "show_overlay": True,          # small on-screen "recording" indicator
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            saved = json.load(f)
        merged = {**DEFAULTS, **saved}
        return merged
    return dict(DEFAULTS)


def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


config = load_config()
