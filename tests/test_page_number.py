import importlib.util
from pathlib import Path


def load_module():
    path = Path(__file__).parents[1] / "src" / "backend" / "archiv_htr.py"
    spec = importlib.util.spec_from_file_location("archiv_htr_under_test", path)
    module = importlib.util.module_from_spec(spec)
    return path, spec, module


def test_expected_page_names_are_present_in_source():
    path, _, _ = load_module()
    text = path.read_text(encoding="utf-8")
    assert "Seite|Viewer" in text
    assert "page_number" in text


def test_gui_selects_downloaded_pages_by_filename_number():
    path = Path(__file__).parents[1] / "src" / "archivagent" / "main.py"
    text = path.read_text(encoding="utf-8")
    htr = text.split("def htr(self):", 1)[1].split("# Mit der tatsächlich", 1)[0]
    assert "def image_page_number" in text
    assert "page>=start" in htr
    assert "page<=end" in htr
    assert "all(page is None" in htr
