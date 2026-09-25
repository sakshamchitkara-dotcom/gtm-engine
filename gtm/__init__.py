import os
from pathlib import Path

__version__ = "0.4.0"


def config_path(name):
    """Bundled config (gtm/config/<name>), or $GTM_CONFIG_DIR/<name> when set."""
    return Path(os.environ.get("GTM_CONFIG_DIR") or Path(__file__).resolve().parent / "config") / name
