from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".jp2"}

def safe_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]+', "_", value)
    value = re.sub(r"\s+", " ", value).strip(" ._")
    return value[:160] or "Unbenannt"

def natural_key(path: Path):
    return [int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", path.name)]

def normalize_text(value: str) -> str:
    table = str.maketrans({
        "ſ": "s", "ẞ": "ss", "ß": "ss",
        "ä": "ae", "ö": "oe", "ü": "ue",
        "Ä": "ae", "Ö": "oe", "Ü": "ue",
        "æ": "ae", "œ": "oe",
    })
    value = value.translate(table).casefold()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def normalize_word(value: str) -> str:
    return normalize_text(value).replace(" ", "")

def image_files(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS),
        key=natural_key,
    )

def read_links(path: Path) -> list[tuple[str, str]]:
    books: list[tuple[str, str]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_no, line in enumerate(handle, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" not in line:
                print(f"[WARNUNG] links.txt, Zeile {line_no}: Trennzeichen | fehlt.")
                continue
            title, url = line.split("|", 1)
            books.append((safe_name(title), url.strip()))
    return books

def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
