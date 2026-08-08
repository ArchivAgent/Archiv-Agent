from __future__ import annotations

import argparse
from dataclasses import asdict
import os
from pathlib import Path

from archiv_htr import run_book_htr
from archiv_search import DEFAULT_NAMES
from archiv_utils import read_links, safe_name, write_csv

BASE_DIR = Path(os.environ.get("ARCHIVAGENT_HOME", Path(__file__).resolve().parent))
PROJECTS_DIR = BASE_DIR / "Projekte"

def resolve_books(project_dir: Path, book_filter: str):
    books = []
    links_path = project_dir / "links.txt"
    if links_path.exists():
        books = read_links(links_path)
    known = {title.casefold() for title, _ in books}
    if project_dir.exists():
        for folder in project_dir.iterdir():
            if folder.is_dir() and (folder / "Originalseiten").exists():
                if folder.name.casefold() not in known:
                    books.append((folder.name, ""))
    if book_filter:
        needle = book_filter.casefold()
        books = [(t, u) for t, u in books if needle in t.casefold()]
    return books

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--htr", action="store_true")
    p.add_argument("--projekt", default="")
    p.add_argument("--buch", default="")
    p.add_argument("--start", type=int, default=1)
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--modell", default="")
    p.add_argument("--schwelle", type=float, default=0.72)
    p.add_argument("--names", nargs="*", default=DEFAULT_NAMES)
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    project_dir = PROJECTS_DIR / safe_name(args.projekt)
    books = resolve_books(project_dir, args.buch)
    if not books:
        print(f"[FEHLER] Kein passendes Buch in {project_dir}")
        return 1

    if not args.htr:
        for title, _ in books:
            print(title)
        return 0

    project_hits = []
    failed = 0
    for title, _ in books:
        try:
            _, _, hits = run_book_htr(
                project_dir / safe_name(title), args.names, args.start,
                args.limit, args.modell, args.schwelle, args.force,
            )
            project_hits.extend(hits)
        except Exception as exc:
            failed += 1
            print(f"[FEHLER] {title}: {exc}")

    # Gemeinsame Trefferliste für alle durchsuchten Bücher.
    combined = project_dir / "Treffer" / "alle_namens_treffer.csv"
    fields = [
        "buchtitel", "seite", "suchname", "erkannt", "aehnlichkeit",
        "methode", "zeile", "kontext", "bilddatei", "textdatei",
    ]
    project_hits.sort(key=lambda h: (h.buchtitel.casefold(), h.seite, -h.aehnlichkeit))
    write_csv(combined, fields, (asdict(h) for h in project_hits))

    print("\n=== Fertig ===")
    print(f"Gemeinsame Trefferliste: {combined}")
    print(f"Treffer insgesamt: {len(project_hits)}")
    return 1 if failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
