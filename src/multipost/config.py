"""Persistent user paths; never write mutable data inside a frozen executable."""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def data_path() -> Path:
    override = os.environ.get("MULTIPOST_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "MultiPost"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "MultiPost"


def configure_logging(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("multipost")
    if logger.handlers:
        return
    handler = RotatingFileHandler(directory / "multipost.log", maxBytes=1_000_000, backupCount=3,
                                  encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
