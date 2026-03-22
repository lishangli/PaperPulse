"""Utility functions."""

from pathlib import Path
from typing import Any


def ensure_dir(path: str | Path) -> Path:
    """Ensure directory exists."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def sanitize_filename(name: str) -> str:
    """Remove invalid characters from filename."""
    invalid = '<>:"/\\|?*'
    for char in invalid:
        name = name.replace(char, '')
    return name.strip()