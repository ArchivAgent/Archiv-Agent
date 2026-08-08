from pathlib import Path

SOURCE = Path(__file__).parents[1] / "src" / "ocr_assistant" / "main.py"


def test_checkbox_has_no_word_wrap_call():
    text = SOURCE.read_text(encoding="utf-8")
    assert "self.confirm.setWordWrap" not in text


def test_sources_are_explicit():
    text = SOURCE.read_text(encoding="utf-8")
    assert "python.org" in text
    assert "PyPI" in text
    assert "Stefan Weil" in text


def test_no_automatic_python_download():
    text = SOURCE.read_text(encoding="utf-8")
    assert "Invoke-WebRequest" not in text
    assert "winget install" not in text
