from __future__ import annotations

import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from PIL import Image, ImageOps

from archiv_layout import read_alto_lines, spatial_text_from_alto
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
            models.extend(folder.rglob("*.safetensors"))
    if not models:
        raise RuntimeError("Kein Handschriftenmodell gefunden.")
    return sorted(set(models), key=lambda p: p.stat().st_mtime, reverse=True)[0]


def page_number(path: Path) -> int | None:
    match = re.search(r"(?:Seite|Viewer)[_-]?(\d+)", path.stem, re.IGNORECASE)
    if match:
        return int(match.group(1))
    numbers = re.findall(r"\d+", path.stem)
    return int(numbers[0]) if numbers else None


def image_needs_preparation(image: Path) -> bool:
    try:
        with Image.open(image) as opened:
            width, height = opened.size
            return height < 1000 or width / max(height, 1) > 2.4
    except Exception:
        return False


def prepare_cropped_image(image: Path, work_dir: Path) -> tuple[Path, bool]:
    """Gibt kleinen/breiten Ausschnitten mehr Rand und eine OCR-taugliche Höhe."""
    try:
        with Image.open(image) as opened:
            prepared = ImageOps.exif_transpose(opened).convert("RGB")
            width, height = prepared.size
            if not image_needs_preparation(image):
                return image, False
            scale = min(3.0, max(1.0, 1200.0 / max(height, 1)))
            if scale > 1.05:
                prepared = prepared.resize(
                    (round(width * scale), round(height * scale)),
                    Image.Resampling.LANCZOS,
                )
            margin = max(60, round(prepared.height * 0.06))
            prepared = ImageOps.expand(prepared, border=margin, fill="white")
            work_dir.mkdir(parents=True, exist_ok=True)
            target = work_dir / f"{image.stem}_vorbereitet.png"
            prepared.save(target, format="PNG")
            return target, True
    except Exception:
        return image, False


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
    alto_dir = htr_dir / "ALTO"
    layout_dir = htr_dir / "Layout"
    prepared_dir = htr_dir / "Vorbereitet"
    text_dir.mkdir(parents=True, exist_ok=True)
    alto_dir.mkdir(parents=True, exist_ok=True)
    layout_dir.mkdir(parents=True, exist_ok=True)
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
        alto_output = alto_dir / f"{image.stem}.xml"
        layout_output = layout_dir / f"{image.stem}.txt"
        prepared_output = prepared_dir / f"{image.stem}_vorbereitet.png"
        preparation_ready = not image_needs_preparation(image) or (
            prepared_output.exists() and prepared_output.stat().st_size > 0
        )

        if (output.exists() and output.stat().st_size > 0 and
                alto_output.exists() and alto_output.stat().st_size > 0 and
                layout_output.exists() and layout_output.stat().st_size > 0 and
                preparation_ready and not force):
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
            ocr_input, was_prepared = prepare_cropped_image(image, prepared_dir)
            if was_prepared:
                print(f"[BILDVORBEREITUNG] Seite {page}: kleiner oder breiter Ausschnitt wurde vergrößert und mit Rand versehen")
            command = [
                str(kraken),
                "-a", "-i", str(ocr_input), str(alto_output),
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

            try:
                _, _, recognized_lines = read_alto_lines(alto_output)
                if not recognized_lines:
                    raise RuntimeError("Kraken hat auf dieser Seite keine Textzeilen erkannt. Bitte einen größeren Bildausschnitt oder den vollständigen Scan verwenden.")
                text = "\n".join(line.text for line in recognized_lines) + "\n"
                layout_text = spatial_text_from_alto(alto_output)
            except Exception as exc:
                message = f"ALTO-Ausgabe konnte nicht gelesen werden: {exc}"
                print(f"[HTR ÜBERSPRUNGEN {page_index}/{total_pages}] Seite {page}: {message}")
                rows.append(
                    PageResult(
                        book_dir.name, page, image.name, "", "übersprungen",
                        0, 0, "", message,
                    )
                )
                write_csv(
                    pages_csv,
                    list(asdict(rows[0]).keys()),
                    (asdict(row) for row in rows),
                )
                continue
            output.write_text(text, encoding="utf-8")
            layout_output.write_text(layout_text, encoding="utf-8")
            status, message = "neu", ""

        if alto_output.exists() and (not layout_output.exists() or layout_output.stat().st_size == 0):
            layout_output.write_text(spatial_text_from_alto(alto_output), encoding="utf-8")

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
        if names:
            export_hits(hits_csv, all_hits)
        print(
            f"[HTR FERTIG {page_index}/{total_pages}] "
            f"Seite {page}: {len(hits)} Treffer"
        )

    return pages_csv, hits_csv, all_hits
