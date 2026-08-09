from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Iterable


SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".jp2", ".webp",
}


def page_number(path: Path) -> int | None:
    match = re.search(r"(?:Seite|Viewer)[_-]?(\d+)", path.stem, re.IGNORECASE)
    if match:
        return int(match.group(1))
    numbers = re.findall(r"\d+", path.stem)
    return int(numbers[0]) if numbers else None


def import_image_files(sources: Iterable[str | Path], book_dir: str | Path) -> list[Path]:
    """Copies images into Originalseiten and assigns consecutive page numbers."""
    book_dir = Path(book_dir)
    originals = book_dir / "Originalseiten"
    originals.mkdir(parents=True, exist_ok=True)

    existing = [
        path for path in originals.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    ]
    numbers = [page_number(path) for path in existing]
    next_page = max((number for number in numbers if number is not None), default=0) + 1
    imported: list[Path] = []

    for source in sorted((Path(path) for path in sources), key=lambda path: path.name.casefold()):
        suffix = source.suffix.lower()
        if not source.is_file() or suffix not in SUPPORTED_IMAGE_EXTENSIONS:
            continue
        while True:
            target = originals / f"Seite_{next_page:04d}{suffix}"
            next_page += 1
            if not target.exists():
                break
        shutil.copy2(source, target)
        imported.append(target)

    return imported
