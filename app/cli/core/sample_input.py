"""Multi-modal sample input parsing for CLI commands.

Supports:
- Inline JSON/text (original behavior)
- @file syntax: reads from a file path (JSON, text, or binary)
- Stdin pipe: '-' reads from sys.stdin

Binary extensions (.png, .jpg, .jpeg, .wav, .mp3, .npy) are loaded as raw bytes.
All other files are read as text and parsed as JSON, falling back to plain string.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Extensions treated as binary (loaded as raw bytes, not text)
_BINARY_EXTENSIONS = frozenset((".png", ".jpg", ".jpeg", ".wav", ".mp3", ".npy"))


def parse_sample_input(raw: str):
    """Parse a raw sample input string into a Python object.

    Resolution order:
    1. If raw == '-', read from stdin
    2. If raw starts with '@', treat remainder as a file path
       - Binary extensions -> bytes
       - Other files -> read text, attempt JSON parse, fall back to string
    3. Otherwise, attempt JSON parse, fall back to raw string

    Args:
        raw: The raw string from --sample-input or interactive prompt.

    Returns:
        Parsed value: list, dict, int, float, bool, None, str, or bytes.

    Raises:
        FileNotFoundError: If @file path does not exist.
    """
    # 1. Stdin pipe
    if raw == "-":
        raw = sys.stdin.read().strip()
        return _parse_text(raw)

    # 2. @file syntax
    if raw.startswith("@"):
        file_path = Path(raw[1:])
        if not file_path.is_file():
            raise FileNotFoundError(f"Sample input file not found: {file_path}")

        # Binary files - return raw bytes
        if file_path.suffix.lower() in _BINARY_EXTENSIONS:
            return file_path.read_bytes()

        # Text files - read, strip, parse as JSON or return as string
        text = file_path.read_text(encoding="utf-8").strip()
        return _parse_text(text)

    # 3. Inline string - attempt JSON parse, fall back to string
    return _parse_text(raw)


def _parse_text(raw: str):
    """Attempt JSON parse; fall back to the raw string."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw
