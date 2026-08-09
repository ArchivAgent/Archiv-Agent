from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_all_mode_uses_imported_images_without_viewer_link():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert "if a=='all' and local_images:" in gui
    assert "a='htr'" in gui
    assert "eigene Bilddatei(en)" in gui
    assert "Für den Download fehlt ein METS-/DFG-Viewer-Link" in gui
