from pathlib import Path
ROOT=Path(__file__).parents[1]
SOURCE=ROOT/"src"/"ocr_assistant"/"main.py"

def test_vc_runtime_gate_and_official_link():
    text=SOURCE.read_text(encoding="utf-8")
    assert "def check_vc_runtime" in text
    assert "self.vc_runtime_ok" in text
    assert "and self.vc_runtime_ok" in text
    assert "https://aka.ms/vc14/vc_redist.x64.exe" in text
