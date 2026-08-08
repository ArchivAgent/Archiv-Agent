from __future__ import annotations

import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from archiv_search import NameHit, export_hits, find_name_hits
from archiv_utils import image_files, write_csv

BASE_DIR = Path(os.environ.get("ARCHIVAGENT_HOME", Path(__file__).resolve().parent))


@dataclass
class PageResult:
    buchtitel: str
    seite: int
    bilddatei: str
    textdatei: str
    status: str
    zeichen: int
    trefferzahl: int
    beste_treffer: str
    meldung: str


def runtime_kraken() -> Path:
    scripts = BASE_DIR / "runtime" / "Scripts"
    python = scripts / "python.exe"
    kraken = scripts / "kraken.exe"
    if not python.exists():
        raise RuntimeError(
            "Die OCR-Laufzeit fehlt. Öffnen Sie im Startmenü "
            "„ArchivAgent – OCR-Assistent“."
        )
    if not kraken.exists():
        raise RuntimeError(
            "Die OCR-Laufzeit ist vorhanden, aber kraken.exe fehlt. "
            "Öffnen Sie den OCR-Assistenten und führen Sie den ausführlichen Test aus."
        )
    return kraken


def find_model(model_arg: str = "") -> Path:
    if model_arg:
        model = Path(model_arg).expanduser()
        if model.exists():
            return model
        raise RuntimeError(f"Modell nicht gefunden: {model}")

    roots = [
        BASE_DIR / "Models",
        BASE_DIR / "Modelle",
        Path.home() / "AppData" / "Local" / "htrmopo" / "htrmopo",
    ]
    models: list[Path] = []
    for folder in roots:
        if folder.exists():
            models.extend(folder.rglob("german_handwriting.mlmodel"))
            models.extend(folder.rglob("*.mlmodel"))
    if not models:
        raise RuntimeError("Kein Handschriftenmodell gefunden.")
    return sorted(set(models), key=lambda p: p.stat().st_mtime, reverse=True)[0]


def page_number(path: Path) -> int | None:
    match = re.search(r"(?:Seite|Viewer)[_-]?(\d+)", path.stem, re.IGNORECASE)
    if match:
        return int(match.group(1))
    numbers = re.findall(r"\d+", path.stem)
    return int(numbers[0]) if numbers else None


def run_book_htr(
    book_dir: Path,
    names: list[str],
    start: int = 1,
    limit: int = 5,
    model_arg: str = "",
    threshold: float = 0.72,
    force: bool = False,
) -> tuple[Path, Path, list[NameHit]]:
    originals = book_dir / "Originalseiten"
    if not originals.exists():
        raise RuntimeError(f"Originalseiten fehlen: {originals}")

    htr_dir = book_dir / "HTR"
    text_dir = htr_dir / "Texte"
    text_dir.mkdir(parents=True, exist_ok=True)
    pages_csv = htr_dir / "htr_ergebnisse.csv"
    hits_csv = htr_dir / "namens_treffer.csv"

    images = image_files(originals)
    last = start + limit - 1 if limit > 0 else None
    selected = [
        image for image in images
        if page_number(image) is not None
        and page_number(image) >= start
        and (last is None or page_number(image) <= last)
    ]
    if not selected:
        raise RuntimeError(
            f"Keine Seiten im Bereich {start} bis {last or 'Ende'} gefunden."
        )

    kraken = runtime_kraken()
    model = find_model(model_arg)
    rows: list[PageResult] = []
    all_hits: list[NameHit] = []
    env = os.environ.copy()
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

    total_pages = len(selected)
    for page_index, image in enumerate(selected, 1):
        page = page_number(image)
        output = text_dir / f"{image.stem}.txt"

        if output.exists() and output.stat().st_size > 0 and not force:
            print(
                f"[HTR START {page_index}/{total_pages}] "
                f"Seite {page}: vorhandenen Text auswerten"
            )
            text = output.read_text(encoding="utf-8", errors="replace")
            status, message = "vorhanden", ""
        else:
            print(
                f"[HTR START {page_index}/{total_pages}] "
                f"Seite {page}: {image.name} wird gelesen"
            )
            command = [
                str(kraken),
                "-i", str(image), str(output),
                "segment", "-bl", "ocr", "-m", str(model),
            ]
            result = subprocess.run(
                command,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode:
                message = (
                    result.stderr or result.stdout or "Unbekannter Fehler"
                ).strip()
                print(f"[FEHLER] Seite {page}: {message[-1500:]}")
                rows.append(
                    PageResult(
                        book_dir.name, page, image.name, "", "fehler",
                        0, 0, "", message[-1500:],
                    )
                )
                continue

            text = output.read_text(encoding="utf-8", errors="replace")
            status, message = "neu", ""

        hits = find_name_hits(
            text=text,
            names=names,
            threshold=threshold,
            book_title=book_dir.name,
            page_no=page,
            image_name=image.name,
            text_name=output.name,
        )
        all_hits.extend(hits)
        best = ", ".join(
            f"{hit.erkannt}→{hit.suchname} ({hit.aehnlichkeit:.0%})"
            for hit in hits[:5]
        )
        rows.append(
            PageResult(
                book_dir.name, page, image.name, output.name,
                status, len(text), len(hits), best, message,
            )
        )
        write_csv(
            pages_csv,
            list(asdict(rows[0]).keys()),
            (asdict(row) for row in rows),
        )
        export_hits(hits_csv, all_hits)
        print(
            f"[HTR FERTIG {page_index}/{total_pages}] "
            f"Seite {page}: {len(hits)} Treffer"
        )

    return pages_csv, hits_csv, all_hits
