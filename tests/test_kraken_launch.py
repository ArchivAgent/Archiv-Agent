from pathlib import Path
ROOT=Path(__file__).parents[1]
SOURCE=ROOT/"src"/"ocr_assistant"/"main.py"

def test_kraken_console_executable_is_used():
    text=SOURCE.read_text(encoding="utf-8")
    assert "kraken.exe" in text
    assert '"-m", "kraken", "--version"' not in text

def test_missing_and_broken_kraken_are_distinguished():
    text=SOURCE.read_text(encoding="utf-8")
    assert "if not exist" in text
    assert "kraken.exe fehlt" in text
    assert "Kraken startet nicht" in text
    assert "PyTorch-Abhängigkeit" in text

def test_backend_uses_console_executable():
    backend=(ROOT/"src"/"backend"/"archiv_htr.py").read_text(encoding="utf-8")
    assert "runtime_kraken" in backend
    assert 'str(kraken),' in backend
    assert '"-m", "kraken"' not in backend

def test_page_without_detected_lines_is_skipped_instead_of_aborting_book():
    backend=(ROOT/"src"/"backend"/"archiv_htr.py").read_text(encoding="utf-8")
    assert '"übersprungen"' in backend
    assert "[HTR ÜBERSPRUNGEN" in backend
    assert 'raise RuntimeError(f"ALTO-Ausgabe konnte nicht gelesen werden' not in backend
