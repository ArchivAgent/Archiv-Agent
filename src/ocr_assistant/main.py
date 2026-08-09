from __future__ import annotations

import os
import subprocess
import sys
import winreg
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

def installed_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        # Die EXE liegt in <Installationsordner>\OCR_Assistent.
        return Path(sys.executable).resolve().parent.parent
    return Path(os.environ.get("ARCHIVAGENT_HOME", r"C:\ArchivAgent"))


APP_DIR = installed_app_dir()
RUNTIME_DIR = APP_DIR / "runtime"
REQUIREMENTS = APP_DIR / "requirements-ocr.txt"
PYTHON_DOWNLOAD = "https://www.python.org/downloads/windows/"
VC_REDIST_DOWNLOAD = "https://aka.ms/vc14/vc_redist.x64.exe"


class OcrAssistant(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ArchivAgent 7.0 RC2 – OCR-Assistent")
        self.resize(780, 680)
        self.process: QProcess | None = None
        self.python_exe: Path | None = None
        self.vc_runtime_ok = False
        self.elapsed_seconds = 0
        self.install_timer = QTimer(self)
        self.install_timer.timeout.connect(self.update_elapsed_hint)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        title = QLabel("OCR-Komponente einrichten")
        title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        layout.addWidget(title)

        intro = QLabel(
            "Für die Handschriftenerkennung benötigt ArchivAgent zusätzliche "
            "kostenlose Komponenten. Es wird nichts ohne Ihre Zustimmung "
            "heruntergeladen oder installiert."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.sandbox_mode = self.detect_sandbox_or_vm()
        hint = (
            "Windows Sandbox oder virtuelle Maschine erkannt. Die OCR-Einrichtung "
            "kann hier 20 bis 40 Minuten dauern."
            if self.sandbox_mode else
            "Hinweis: In Windows Sandbox oder virtuellen Maschinen kann die "
            "OCR-Einrichtung 20 bis 40 Minuten dauern."
        )
        self.sandbox_hint = QLabel(hint)
        self.sandbox_hint.setWordWrap(True)
        self.sandbox_hint.setStyleSheet(
            "QLabel { background:#fff4cc; border:1px solid #d6b656; padding:10px; }"
        )
        layout.addWidget(self.sandbox_hint)

        info = QGroupBox("Was wird benötigt?")
        info_layout = QVBoxLayout(info)
        for text in (
            "Microsoft Visual C++ Runtime – Systembibliotheken von Microsoft",
            "Python 3.13 – technische Laufzeit von python.org",
            "Kraken OCR – freie Handschriftenerkennung von PyPI",
            "Handschriftenmodell von Stefan Weil – CC BY-SA 4.0, Zenodo",
        ):
            label = QLabel("✓ " + text)
            label.setWordWrap(True)
            info_layout.addWidget(label)
        layout.addWidget(info)

        why = QPushButton("Warum wird Python benötigt?")
        why.clicked.connect(self.show_python_explanation)
        layout.addWidget(why)

        self.vc_status = QLabel("Visual C++ Runtime wurde noch nicht geprüft.")
        self.vc_status.setWordWrap(True)
        self.vc_status.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(self.vc_status)

        vc_buttons = QHBoxLayout()
        self.vc_check_button = QPushButton("Visual C++ prüfen")
        self.vc_check_button.clicked.connect(self.check_vc_runtime)
        self.vc_download_button = QPushButton("Offiziellen Microsoft-Installer öffnen")
        self.vc_download_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(VC_REDIST_DOWNLOAD))
        )
        vc_buttons.addWidget(self.vc_check_button)
        vc_buttons.addWidget(self.vc_download_button)
        layout.addLayout(vc_buttons)

        self.status = QLabel("Python-Prüfung noch nicht durchgeführt.")
        self.status.setWordWrap(True)
        self.status.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(self.status)

        python_buttons = QHBoxLayout()
        check = QPushButton("Python prüfen")
        check.clicked.connect(self.check_python)
        self.check_button = check

        download = QPushButton("Offizielle Python-Seite öffnen")
        download.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(PYTHON_DOWNLOAD))
        )
        self.download_button = download

        python_buttons.addWidget(check)
        python_buttons.addWidget(download)
        layout.addLayout(python_buttons)

        consent_text = QLabel(
            "Kraken und seine Abhängigkeiten werden nach Ihrer Zustimmung "
            "aus dem offiziellen Python-Paketindex PyPI installiert."
        )
        consent_text.setWordWrap(True)
        layout.addWidget(consent_text)

        self.confirm = QCheckBox("Ich stimme dieser Installation zu.")
        self.confirm.stateChanged.connect(self.update_buttons)
        layout.addWidget(self.confirm)

        self.install_button = QPushButton("Kraken sichtbar installieren")
        self.install_button.setEnabled(False)
        self.install_button.clicked.connect(self.install_kraken)
        layout.addWidget(self.install_button)

        self.step_status = QLabel("Bereit.")
        self.step_status.setWordWrap(True)
        layout.addWidget(self.step_status)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        layout.addWidget(QLabel("Installationsprotokoll"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)

        bottom = QHBoxLayout()
        self.test_button = QPushButton("OCR-Installation testen")
        self.test_button.setEnabled(False)
        self.test_button.clicked.connect(self.test_runtime)
        close = QPushButton("Schließen")
        close.clicked.connect(self.close)
        bottom.addWidget(self.test_button)
        bottom.addStretch()
        bottom.addWidget(close)
        layout.addLayout(bottom)

        self.check_vc_runtime()
        self.check_python()

    def append(self, text: str):
        self.log.appendPlainText(text.rstrip())

    def show_python_explanation(self):
        QMessageBox.information(
            self,
            "Warum wird Python benötigt?",
            "Python ist eine freie Programmiersprache.\n\n"
            "ArchivAgent verwendet Python ausschließlich als technische "
            "Laufzeit für die Handschriftenerkennung. Sie müssen Python "
            "weder bedienen noch programmieren.\n\n"
            "Die Installation erfolgt über den sichtbaren offiziellen "
            "Python-Installer. ArchivAgent lädt nichts heimlich herunter.",
        )

    def detect_sandbox_or_vm(self) -> bool:
        return (
            os.environ.get("USERNAME", "").casefold() == "wdagutilityaccount"
            or "sandbox" in os.environ.get("COMPUTERNAME", "").casefold()
        )

    def update_elapsed_hint(self):
        self.elapsed_seconds += 1
        minutes = self.elapsed_seconds // 60
        if minutes >= 5 and self.sandbox_mode:
            self.step_status.setText(
                f"Die Einrichtung läuft seit {minutes} Minuten. "
                "In einer Windows Sandbox sind 20 bis 40 Minuten normal."
            )
        else:
            self.step_status.setText(
                f"OCR-Komponenten werden eingerichtet – seit {minutes} Minute(n)."
            )

    def locate_vc_runtime(self) -> bool:
        paths = (
            r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
            r"SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
        )
        for path in paths:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
                    installed, _ = winreg.QueryValueEx(key, "Installed")
                    if int(installed) == 1:
                        return True
            except (FileNotFoundError, OSError, ValueError):
                pass
        return False

    def check_vc_runtime(self):
        self.vc_runtime_ok = self.locate_vc_runtime()
        if self.vc_runtime_ok:
            self.vc_status.setText("✓ Microsoft Visual C++ Runtime wurde gefunden.")
            self.append("[OK] Microsoft Visual C++ Runtime gefunden.")
        else:
            self.vc_status.setText(
                "Microsoft Visual C++ Runtime wurde nicht gefunden.\n"
                "Installieren Sie sie über den offiziellen Microsoft-Installer "
                "und klicken Sie danach erneut auf „Visual C++ prüfen“."
            )
            self.append("[HINWEIS] Microsoft Visual C++ Runtime fehlt.")
        self.update_buttons()

    def locate_python(self) -> Path | None:
        commands = (
            ["py", "-3.13", "-c", "import sys; print(sys.executable)"],
            ["python", "-c", "import sys; print(sys.executable)"],
        )
        for command in commands:
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=20,
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                    ),
                )
                if result.returncode == 0 and result.stdout.strip():
                    candidate = Path(result.stdout.strip())
                    if candidate.exists():
                        return candidate
            except Exception:
                pass

        expected = (
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Programs"
            / "Python"
            / "Python313"
            / "python.exe"
        )
        return expected if expected.exists() else None

    def check_python(self):
        self.python_exe = self.locate_python()
        if self.python_exe:
            self.status.setText(f"✓ Python wurde gefunden:\n{self.python_exe}")
            self.append(f"[OK] Python gefunden: {self.python_exe}")
        else:
            self.status.setText(
                "Python 3.13 wurde nicht gefunden.\n"
                "Öffnen Sie die offizielle Python-Seite, installieren Sie "
                "Python sichtbar und klicken Sie danach erneut auf "
                "„Python prüfen“."
            )
            self.append("[HINWEIS] Python 3.13 wurde nicht gefunden.")
        self.update_buttons()

    def update_buttons(self):
        ready = bool(self.python_exe and self.vc_runtime_ok and self.confirm.isChecked())
        self.install_button.setEnabled(ready and self.process is None)
        self.test_button.setEnabled(
            (RUNTIME_DIR / "Scripts" / "python.exe").exists()
            and self.process is None
        )

    def install_kraken(self):
        if not self.vc_runtime_ok:
            QMessageBox.warning(self, "Visual C++ fehlt", "Bitte zuerst die Microsoft Visual C++ Runtime installieren und erneut prüfen.")
            return
        if not self.python_exe:
            QMessageBox.warning(
                self, "Python fehlt", "Bitte zuerst Python installieren."
            )
            return
        if not REQUIREMENTS.exists():
            QMessageBox.critical(
                self, "Datei fehlt", f"Nicht gefunden:\n{REQUIREMENTS}"
            )
            return

        self.log.clear()
        self.append("=== ArchivAgent OCR-Einrichtung ===")
        self.elapsed_seconds = 0
        self.install_timer.start(1000)
        self.step_status.setText("OCR-Komponenten werden eingerichtet.")
        self.append(f"Python: {self.python_exe}")
        self.append(
            "Die Einrichtung läuft sichtbar. Bitte dieses Fenster geöffnet lassen."
        )

        script = APP_DIR / "Logs" / "install_ocr_visible.cmd"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(
            "@echo off\r\n"
            "chcp 65001 >nul\r\n"
            f'echo Verwende Python: "{self.python_exe}"\r\n'
            f'if exist "{RUNTIME_DIR}" rmdir /s /q "{RUNTIME_DIR}"\r\n'
            f'"{self.python_exe}" -m venv "{RUNTIME_DIR}"\r\n'
            "if errorlevel 1 exit /b 11\r\n"
            f'"{RUNTIME_DIR}\\Scripts\\python.exe" -m pip install '
            "--upgrade pip wheel setuptools\r\n"
            "if errorlevel 1 exit /b 12\r\n"
            f'"{RUNTIME_DIR}\\Scripts\\python.exe" -m pip install '
            f'-r "{REQUIREMENTS}"\r\n'
            "if errorlevel 1 exit /b 13\r\n"
            f'if not exist "{RUNTIME_DIR}\\Scripts\\kraken.exe" exit /b 14\r\n'
            f'"{RUNTIME_DIR}\\Scripts\\kraken.exe" --version\r\n'
            "if errorlevel 1 exit /b 15\r\n"
            "exit /b 0\r\n",
            encoding="utf-8",
        )

        self.process = QProcess(self)
        self.process.setProgram("cmd.exe")
        self.process.setArguments(["/c", str(script)])
        self.process.setWorkingDirectory(str(APP_DIR))
        self.process.setProcessChannelMode(
            QProcess.ProcessChannelMode.MergedChannels
        )
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.install_finished)
        self.progress.setRange(0, 0)
        self.install_button.setEnabled(False)
        self.vc_check_button.setEnabled(False)
        self.vc_download_button.setEnabled(False)
        self.check_button.setEnabled(False)
        self.download_button.setEnabled(False)
        self.process.start()

    def read_output(self):
        if self.process:
            data = bytes(self.process.readAllStandardOutput()).decode(
                "utf-8", errors="replace"
            )
            if data:
                self.append(data)

    def install_finished(self, code: int, _status):
        self.read_output()
        self.install_timer.stop()
        self.progress.setRange(0, 1)
        self.progress.setValue(1 if code == 0 else 0)
        self.process = None
        self.vc_check_button.setEnabled(True)
        self.vc_download_button.setEnabled(True)
        self.check_button.setEnabled(True)
        self.download_button.setEnabled(True)

        if code == 0:
            self.status.setText(
                "✓ Die OCR-Komponente wurde erfolgreich eingerichtet."
            )
            QMessageBox.information(
                self,
                "Einrichtung abgeschlossen",
                "Python, Kraken und die OCR-Abhängigkeiten wurden "
                "erfolgreich eingerichtet.",
            )
        else:
            details = {
                11: "Die separate Python-Laufzeit konnte nicht erstellt werden.",
                12: "Die Python-Installationswerkzeuge konnten nicht aktualisiert werden.",
                13: "Kraken oder eine seiner Abhängigkeiten konnte nicht installiert werden.",
                14: (
                    "Die Installation wurde beendet, aber die Programmdatei "
                    f"kraken.exe fehlt im Ordner {RUNTIME_DIR / 'Scripts'}."
                ),
                15: (
                    "kraken.exe ist vorhanden, konnte aber nicht gestartet werden. "
                    "Die wirkliche Fehlermeldung steht im Installationsprotokoll; "
                    "häufig handelt es sich um eine fehlende DLL oder PyTorch-Abhängigkeit."
                ),
            }.get(code, f"Unbekannter Installationsfehler (Fehlercode {code}).")
            self.status.setText(details)
            QMessageBox.critical(
                self,
                "Einrichtung fehlgeschlagen",
                details,
            )
        self.update_buttons()

    def test_runtime(self):
        runtime_python = RUNTIME_DIR / "Scripts" / "python.exe"
        kraken_exe = RUNTIME_DIR / "Scripts" / "kraken.exe"
        self.append("=== Ausführlicher OCR-Test ===")
        self.append(f"Python erwartet: {runtime_python}")
        self.append(f"Kraken erwartet: {kraken_exe}")

        if not runtime_python.exists():
            message = (
                "Die OCR-Laufzeit fehlt vollständig:\n"
                f"{runtime_python}\n\n"
                "Bitte Kraken erneut installieren."
            )
            self.append("[FEHLT] " + str(runtime_python))
            QMessageBox.critical(self, "OCR-Laufzeit fehlt", message)
            return

        if not kraken_exe.exists():
            scripts_dir = RUNTIME_DIR / "Scripts"
            nearby = sorted(p.name for p in scripts_dir.glob("*kraken*"))
            module_test = subprocess.run(
                [
                    str(runtime_python), "-c",
                    "import importlib.util; print(importlib.util.find_spec('kraken'))",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            module_output = (module_test.stdout or module_test.stderr).strip()
            message = (
                "Kraken wurde nicht als startbares Windows-Programm angelegt.\n\n"
                f"Fehlende Datei:\n{kraken_exe}\n\n"
                f"Kraken-Dateien im Scripts-Ordner: {', '.join(nearby) or 'keine'}\n"
                f"Python-Modultest: {module_output or 'keine Ausgabe'}"
            )
            self.append("[DATEI FEHLT] " + str(kraken_exe))
            self.append("[MODULTEST] " + (module_output or "keine Ausgabe"))
            QMessageBox.critical(self, "kraken.exe fehlt", message)
            return

        try:
            result = subprocess.run(
                [str(kraken_exe), "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            output = (result.stdout or result.stderr).strip()
            self.append(f"[TEST] {output}")
            if result.returncode == 0:
                QMessageBox.information(
                    self,
                    "OCR-Test erfolgreich",
                    output or "Kraken funktioniert.",
                )
            else:
                message = (
                    f"kraken.exe wurde gefunden, startete aber mit Fehlercode "
                    f"{result.returncode}.\n\n{output or 'Keine Fehlermeldung ausgegeben.'}"
                )
                QMessageBox.critical(
                    self,
                    "Kraken startet nicht",
                    message,
                )
        except FileNotFoundError:
            QMessageBox.critical(
                self, "kraken.exe fehlt", f"Nicht gefunden:\n{kraken_exe}"
            )
        except OSError as exc:
            message = (
                "kraken.exe ist vorhanden, Windows konnte sie jedoch nicht starten.\n\n"
                f"{type(exc).__name__}: {exc}\n\n"
                "Das deutet meist auf eine fehlende DLL oder eine nicht ladbare "
                "PyTorch-Abhängigkeit hin."
            )
            self.append("[STARTFEHLER] " + message.replace("\n", " | "))
            QMessageBox.critical(self, "Kraken-Startfehler", message)
        except Exception as exc:
            QMessageBox.critical(
                self, "OCR-Test fehlgeschlagen", str(exc)
            )


def main() -> int:
    app = QApplication(sys.argv)
    window = OcrAssistant()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
