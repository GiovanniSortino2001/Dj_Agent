"""Strict numeric validation and atomic JSON output."""
import json
import math
import os
from pathlib import Path
import tempfile


def finite(value, name, low=None, high=None):
    if isinstance(value, bool):
        raise ValueError(f"{name}: booleano non ammesso")
    value = float(value)
    if not math.isfinite(value) or (low is not None and value < low) or (high is not None and value > high):
        raise ValueError(f"{name}: valore non finito o fuori intervallo [{low}, {high}]")
    return value


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".dj-")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def read_json(path):
    def invalid(x):
        raise ValueError(f"JSON non finito: {x}")
    return json.loads(Path(path).read_text(), parse_constant=invalid)
