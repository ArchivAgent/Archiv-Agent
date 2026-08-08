from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
STAGE_ROOT = ROOT / "stage"
STAGE = STAGE_ROOT / "ArchivAgent"
OUT = ROOT / "output"

DEV_PYTHON = Path(r"C:\ArchivAgent\kraken_env\Scripts\python.exe")
LEGACY_SOURCE = Path(r"C:\ArchivAgent")
MODEL_ID = "a0daddf4-4a50-502d-91d7-8f72e8577a33"
MODEL = (
    Path(os.environ["LOCALAPPDATA"])
    / "htrmopo"
    / "htrmopo"
    / MODEL_ID
    / "german_handwriting.mlmodel"
)


class BuildError(RuntimeError):
    pass


def run(*args, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    command = [str(value) for value in args]
    print(">", subprocess.list2cmdline(command), flush=True)
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise BuildError(
            f"Befehl fehlgeschlagen (Code {result.returncode}): "
            f"{subprocess.list2cmdline(command)}"
        )


def clean(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def require(path: Path, label: str) -> None:
    if not path.exists():
        raise BuildError(f"{label} fehlt: {path}")


def has_module(module_name: str) -> bool:
    result = subprocess.run(
        [
            str(DEV_PYTHON),
            "-c",
            (
                "import importlib.util,sys;"
                f"sys.exit(0 if importlib.util.find_spec({module_name!r}) else 1)"
            ),
        ],
        check=False,
    )
    return result.returncode == 0


def ensure_dev_tools() -> None:
    missing = [
        package
        for package, module in (
            ("pytest", "pytest"),
            ("pyinstaller", "PyInstaller"),
            ("certifi", "certifi"),
        )
        if not has_module(module)
    ]
    if missing:
        print("Fehlende Build-Werkzeuge werden installiert:", ", ".join(missing))
        run(
            DEV_PYTHON,
            "-m",
            "pip",
            "install",
            "--upgrade",
            *missing,
        )


def find_iscc() -> Path:
    candidates: list[Path] = []
    for base in (
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
    ):
        if base:
            candidates.extend(
                Path(base) / version / "ISCC.exe"
                for version in ("Inno Setup 7", "Inno Setup 6")
            )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise BuildError("Inno Setup 7 oder 6 wurde nicht gefunden.")


def compile_sources() -> None:
    python_files = sorted(SRC.rglob("*.py"))
    if not python_files:
        raise BuildError("Keine Python-Quelldateien gefunden.")

    for source in python_files:
        result = subprocess.run(
            [
                str(DEV_PYTHON),
                "-m",
                "py_compile",
                str(source),
            ],
            check=False,
        )
        if result.returncode != 0:
            raise BuildError(f"Syntaxprüfung fehlgeschlagen: {source}")
    print(f"Syntaxprüfung erfolgreich: {len(python_files)} Python-Datei(en).")


def preflight() -> None:
    print("[1/8] Voraussetzungen prüfen")
    require(DEV_PYTHON, "Entwicklungs-Python")
    require(MODEL, "Handschriftenmodell")
    require(SRC / "archivagent" / "main.py", "ArchivAgent-GUI")
    require(SRC / "ocr_assistant" / "main.py", "OCR-Assistent")
    require(SRC / "backend" / "archiv_agent.py", "Backend")
    require(SRC / "backend" / "archiv_htr.py", "HTR-Modul")
    require(ROOT / "requirements-ocr.txt", "OCR-Anforderungsliste")
    require(ROOT / "installer" / "ArchivAgent_6_0.iss", "Inno-Setup-Skript")
    require(ROOT / "docs" / "LIZENZHINWEISE.txt", "Lizenzhinweise")
    require(ROOT / "docs" / "VOR_DER_INSTALLATION.txt", "Installationshinweise")
    find_iscc()


def main() -> int:
    preflight()

    print("[2/8] Entwicklungswerkzeuge prüfen")
    ensure_dev_tools()

    print("[3/8] Python-Quellcode prüfen")
    compile_sources()

    backend = SRC / "backend"
    for name in ("archiv_search.py", "archiv_utils.py"):
        source = LEGACY_SOURCE / name
        require(source, name)
        shutil.copy2(source, backend / name)

    print("[4/8] Automatische Tests ausführen")
    run(DEV_PYTHON, "-m", "pytest", "-q", ROOT / "tests")

    for path in (DIST, BUILD, STAGE_ROOT):
        clean(path)
    OUT.mkdir(parents=True, exist_ok=True)

    print("[5/8] ArchivAgent bauen")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(backend), str(SRC)])
    run(
        DEV_PYTHON,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        "ArchivAgent",
        "--distpath",
        DIST,
        "--workpath",
        BUILD / "gui",
        "--specpath",
        BUILD / "gui_spec",
        "--paths",
        backend,
        "--collect-all",
        "PySide6",
        "--collect-data",
        "certifi",
        SRC / "archivagent" / "main.py",
        env=env,
    )

    print("[6/8] OCR-Assistent bauen")
    run(
        DEV_PYTHON,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        "ArchivAgent_OCR_Assistent",
        "--distpath",
        DIST,
        "--workpath",
        BUILD / "ocr_assistant",
        "--specpath",
        BUILD / "ocr_assistant_spec",
        "--collect-all",
        "PySide6",
        SRC / "ocr_assistant" / "main.py",
    )

    print("[7/8] Release vollständig vorbereiten")
    shutil.copytree(DIST / "ArchivAgent", STAGE, dirs_exist_ok=True)
    shutil.copytree(
        DIST / "ArchivAgent_OCR_Assistent",
        STAGE / "OCR_Assistent",
        dirs_exist_ok=True,
    )

    for name in (
        "archiv_agent.py",
        "archiv_htr.py",
        "archiv_search.py",
        "archiv_utils.py",
    ):
        source = backend / name
        require(source, name)
        shutil.copy2(source, STAGE / name)

    shutil.copy2(
        ROOT / "requirements-ocr.txt",
        STAGE / "requirements-ocr.txt",
    )

    model_dir = STAGE / "Models" / MODEL_ID
    model_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MODEL, model_dir / "german_handwriting.mlmodel")

    shutil.copytree(ROOT / "docs", STAGE / "docs", dirs_exist_ok=True)
    shutil.copytree(ROOT / "licenses", STAGE / "licenses", dirs_exist_ok=True)

    checks = (
        STAGE / "ArchivAgent.exe",
        STAGE / "OCR_Assistent" / "ArchivAgent_OCR_Assistent.exe",
        STAGE / "requirements-ocr.txt",
        STAGE / "archiv_agent.py",
        STAGE / "archiv_htr.py",
        STAGE / "archiv_search.py",
        STAGE / "archiv_utils.py",
        model_dir / "german_handwriting.mlmodel",
        STAGE / "docs" / "LIZENZHINWEISE.txt",
    )
    for item in checks:
        require(item, "Release-Bestandteil")
        print("  OK:", item)

    print("[8/8] Windows-Setup erzeugen")
    run(
        find_iscc(),
        ROOT / "installer" / "ArchivAgent_6_0.iss",
        cwd=ROOT,
    )

    setup = OUT / "ArchivAgent_Setup_6.0.0_RC9.exe"
    require(setup, "Setup-Datei")
    if setup.stat().st_size < 1_000_000:
        raise BuildError(
            f"Die Setup-Datei ist unerwartet klein ({setup.stat().st_size} Bytes)."
        )

    digest = hashlib.sha256(setup.read_bytes()).hexdigest().upper()
    checksum = OUT / "ArchivAgent_Setup_6.0.0_RC9_SHA256.txt"
    checksum.write_text(
        f"{digest}  {setup.name}\n",
        encoding="ascii",
    )
    require(checksum, "SHA-256-Datei")

    print()
    print("=" * 68)
    print("BUILD ERFOLGREICH UND VOLLSTÄNDIG GEPRÜFT")
    print("Setup:", setup)
    print("SHA-256:", checksum)
    print("=" * 68)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as exc:
        print()
        print("=" * 68)
        print("BUILD FEHLGESCHLAGEN")
        print(exc)
        print("=" * 68)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print()
        print("BUILD DURCH BENUTZER ABGEBROCHEN.")
        raise SystemExit(2)
    except Exception as exc:
        print()
        print("=" * 68)
        print("UNERWARTETER BUILD-FEHLER")
        print(f"{type(exc).__name__}: {exc}")
        print("=" * 68)
        raise SystemExit(1)
