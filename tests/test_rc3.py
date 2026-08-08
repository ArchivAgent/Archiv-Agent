from pathlib import Path
ROOT=Path(__file__).parents[1]
def test_ssl_and_sandbox():
    gui=(ROOT/"src"/"archivagent"/"main.py").read_text(encoding="utf-8")
    ass=(ROOT/"src"/"ocr_assistant"/"main.py").read_text(encoding="utf-8")
    assert "certifi.where()" in gui and "context=context" in gui
    assert "20 bis 40 Minuten" in ass and "install_timer" in ass
