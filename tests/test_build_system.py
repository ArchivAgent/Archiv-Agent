from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_builder_installs_missing_pytest_before_running_tests():
    text = (ROOT / "build_release.py").read_text(encoding="utf-8")
    assert '("pytest", "pytest")' in text
    assert "ensure_dev_tools()" in text


def test_builder_has_no_continue_after_failed_tests_prompt():
    text = (ROOT / "build_release.py").read_text(encoding="utf-8")
    assert "Trotzdem mit dem Build fortfahren" not in text


def test_batch_preserves_build_exit_code():
    text = (ROOT / "BUILD_RELEASE.bat").read_text(encoding="utf-8")
    assert 'set "BUILD_CODE=%ERRORLEVEL%"' in text
    assert 'if "%BUILD_CODE%"=="0"' in text
    assert "BUILD ABGEBROCHEN" in text


def test_installer_does_not_write_model_to_localappdata_as_admin():
    text = (ROOT / "installer" / "ArchivAgent_6_0.iss").read_text(encoding="utf-8")
    assert "{localappdata}" not in text


def test_user_cancel_is_not_reported_as_htr_error():
    text = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    wait_pos = text.index("code=self.proc.wait()")
    cancel_pos = text.index("if self.cancelled:", wait_pos)
    error_pos = text.index("if code:raise RuntimeError", wait_pos)
    assert wait_pos < cancel_pos < error_pos
    assert "[ABBRUCH] Texterkennung wurde vom Benutzer beendet." in text


def test_runtime_uses_selected_installation_directory():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assistant = (ROOT / "src" / "ocr_assistant" / "main.py").read_text(encoding="utf-8")
    backend = (ROOT / "src" / "backend" / "archiv_htr.py").read_text(encoding="utf-8")
    launcher = (ROOT / "src" / "backend" / "archiv_agent.py").read_text(encoding="utf-8")
    assert "Path(sys.executable).resolve().parent" in gui
    assert "Path(sys.executable).resolve().parent.parent" in assistant
    assert "Path(__file__).resolve().parent" in backend
    assert "Path(__file__).resolve().parent" in launcher


def test_update_preserves_ocr_runtime_and_skips_reconfiguration():
    installer = (ROOT / "installer" / "ArchivAgent_6_0.iss").read_text(encoding="utf-8")
    assert "Check: NeedsOcrSetup" in installer
    assert "runtime\\Scripts\\kraken.exe" in installer
    assert 'Name: "{app}\\Projekte"' in installer


def test_htr_reports_page_level_progress():
    backend = (ROOT / "src" / "backend" / "archiv_htr.py").read_text(encoding="utf-8")
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert "[HTR START" in backend
    assert "[HTR FERTIG" in backend
    assert "self.progress.emit(0,len(selected))" in gui
    assert "Texterkennung: Seite {page} wird gelesen" in gui
    assert "Texterkennung: Seite {page} fertig" in gui


def test_animated_archivist_is_local_and_connected_to_htr():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert "class ReadingArchivist" in gui
    assert "QPainter" in gui and "QTimer" in gui
    assert "self.archivist=ReadingArchivist()" in gui
    assert "if text.startswith('Texterkennung'):self.archivist.start()" in gui
    assert "if ok:self.archivist.finish()" in gui
