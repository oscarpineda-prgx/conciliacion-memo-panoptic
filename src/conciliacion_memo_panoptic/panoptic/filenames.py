from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]+')


def sanitize_filename(value: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", value).strip().strip(".")
    return cleaned or "panoptic_download.xlsx"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def build_target_path(
    download_dir: Path,
    suggested_filename: str,
    memo: str | None = None,
    vendor: str | None = None,
) -> Path:
    parts: list[str] = []
    if memo:
        parts.append(f"MEMO-{memo.zfill(3)}")
    if vendor:
        parts.append(f"VENDOR-{vendor}")
    parts.append(datetime.now().strftime("%Y%m%d_%H%M%S"))
    parts.append(sanitize_filename(suggested_filename))

    return unique_path(download_dir / "_".join(parts))
