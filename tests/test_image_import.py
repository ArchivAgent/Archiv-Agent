from pathlib import Path
import sys


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from archivagent.image_import import import_image_files


def test_import_creates_originalseiten_and_numbers_images(tmp_path):
    source_dir = tmp_path / "input"
    source_dir.mkdir()
    (source_dir / "zweite.png").write_bytes(b"png-2")
    (source_dir / "erste.jpg").write_bytes(b"jpg-1")

    book = tmp_path / "Projekte" / "Test" / "Mein Buch"
    imported = import_image_files(
        [source_dir / "zweite.png", source_dir / "erste.jpg"], book
    )

    assert [path.name for path in imported] == ["Seite_0001.jpg", "Seite_0002.png"]
    assert imported[0].read_bytes() == b"jpg-1"
    assert imported[1].read_bytes() == b"png-2"


def test_import_continues_after_existing_page_and_ignores_other_files(tmp_path):
    originals = tmp_path / "book" / "Originalseiten"
    originals.mkdir(parents=True)
    (originals / "Seite_0012.png").write_bytes(b"old")
    scan = tmp_path / "scan.tiff"
    scan.write_bytes(b"new")
    note = tmp_path / "note.txt"
    note.write_text("ignore", encoding="utf-8")

    imported = import_image_files([note, scan], tmp_path / "book")

    assert [path.name for path in imported] == ["Seite_0013.tiff"]
    assert imported[0].read_bytes() == b"new"


def test_gui_exposes_own_image_import():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert "Eigene Scans/Bilder hinzufügen" in gui
    assert "QFileDialog.getOpenFileNames" in gui
    assert "import_image_files(files,self.bkd())" in gui
