# ArchivAgent

ArchivAgent ist ein Windows-Programm zur unterstützten Recherche in digitalisierten
Kirchenbüchern und historischen Archivalien. Es lädt ausgewählte Buchseiten aus
METS/DFG-Viewern, erkennt Handschrift mit Kraken OCR und durchsucht die Ergebnisse
nach Familiennamen.

> **Testversion:** ArchivAgent 6.0 RC9 ist eine öffentliche Vorabversion. Bitte
> zunächst mit kleinen Seitenbereichen und Kopien wichtiger Forschungsdaten testen.

## Funktionen

- Buchseiten über einen METS-/DFG-Viewer-Link herunterladen
- frei wählbare Seitenbereiche verarbeiten
- historische Handschrift lokal mit Kraken OCR erkennen
- mehrere Familiennamen mit einstellbarer Suchgenauigkeit suchen
- Fundstellen mit Originalseite und erkanntem Text prüfen
- Projekte, Trefferlisten und Ergebnisse lokal speichern
- laufende Texterkennung mit Seitenfortschritt und animiertem Archivarius anzeigen
- laufende Vorgänge kontrolliert abbrechen

## Systemvoraussetzungen

- Windows 10 oder Windows 11, 64 Bit
- Python 3.13
- Microsoft Visual C++ Redistributable (x64)
- Internetverbindung für Installation und Seitenabruf
- ausreichend freier Speicherplatz; Kraken und PyTorch benötigen mehrere Gigabyte

Die eigentliche Erkennung und Namenssuche erfolgt lokal auf dem Rechner. ArchivAgent
lädt OCR-Komponenten erst nach ausdrücklicher Zustimmung im OCR-Assistenten.

## Installation der Testversion

1. Unter **Releases** die Datei `ArchivAgent_Setup_6.0.0_RC9.exe` herunterladen.
2. Optional die SHA-256-Prüfsumme mit
   `ArchivAgent_Setup_6.0.0_RC9_SHA256.txt` vergleichen.
3. Setup starten und den Installationshinweisen folgen.
4. Im OCR-Assistenten Python und Microsoft Visual C++ prüfen.
5. Der Installation von Kraken zustimmen. Die erste Einrichtung kann einige Zeit dauern.

Der Installer ist derzeit nicht kommerziell codesigniert. Windows SmartScreen kann
deshalb eine Warnung anzeigen. Prüfen Sie Dateiname und SHA-256-Prüfsumme und laden
Sie die Datei ausschließlich aus diesem Repository herunter.

## Aktualisierung

Eine neue Version kann über die vorhandene Installation installiert werden. Projekte,
Modelle und die eingerichtete Kraken-Laufzeit bleiben erhalten, wenn derselbe
Installationsordner verwendet wird.

## Kurzer Testablauf

1. Ein neues Testprojekt und Buch anlegen.
2. Einen gültigen METS-/DFG-Viewer-Link einfügen.
3. Zunächst nur zwei oder drei Seiten auswählen.
4. **Alles automatisch starten** anklicken.
5. Download, Texterkennung, Trefferliste und Abbruchfunktion prüfen.

Ausführlichere Hinweise stehen in [TESTING.md](TESTING.md).

## Datenschutz

Projekte, heruntergeladene Seiten, erkannte Texte und Treffer werden lokal im
gewählten ArchivAgent-Ordner gespeichert. Es werden keine Forschungsdaten an einen
ArchivAgent-Server übertragen.

## Rückmeldungen und Fehlerberichte

Bitte unter **Issues** einen Fehlerbericht eröffnen. Hilfreich sind:

- Windows-Version
- ArchivAgent-Version
- verwendeter Viewer bzw. Archivtyp
- genaue Fehlermeldung
- relevante Protokollzeilen ohne private oder sensible Daten

## Lizenz und Danksagung

Der Programmcode steht unter der [GNU General Public License v3.0](LICENSE).

ArchivAgent verwendet Kraken OCR und ein Handschriftenmodell von **Stefan Weil**.
Das Modell wird unter **CC BY-SA 4.0** verwendet. Weitere Hinweise befinden sich in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) und im Ordner `licenses`.

## Status

Aktuelle Testversion: **ArchivAgent 6.0 RC9**

**Idee, Konzeption und Projektleitung: Frank Bernbeck**

Entwickelt mit KI-gestützter Entwicklungsunterstützung.
