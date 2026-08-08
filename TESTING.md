# ArchivAgent 6.0 RC9 testen

Vielen Dank für den Test von ArchivAgent. Die Testversion soll vor allem zeigen,
ob Installation, Seitenabruf, Handschriftenerkennung und Trefferprüfung auf
unterschiedlichen Windows-Rechnern zuverlässig funktionieren.

## Empfohlener Test

1. Setup installieren.
2. OCR-Assistent öffnen und Kraken einrichten bzw. testen.
3. Ein neues Testprojekt anlegen.
4. Zwei bis drei Seiten eines Kirchenbuchs herunterladen.
5. Einen oder mehrere Familiennamen eingeben.
6. Die automatische Verarbeitung starten.
7. Fortschrittsanzeige und animierten Archivarius beobachten.
8. Erkannte Texte und Treffer prüfen.
9. Einen zweiten Lauf starten und einmal kontrolliert abbrechen.

## Bitte im Fehlerbericht angeben

- Windows 10 oder 11 und Versionsnummer
- Installationsordner
- Python-Version
- verwendeter Link bzw. Archiv-Viewer
- ausgewählter Seitenbereich
- vollständiger Wortlaut der Fehlermeldung
- letzte relevante Zeilen aus dem ArchivAgent-Protokoll

Bitte keine personenbezogenen Zugangsdaten oder privaten Dokumente veröffentlichen.

## Bekannte Einschränkungen

- Die Erkennungsqualität hängt stark von Schrift, Scanqualität und verwendetem Modell ab.
- Kraken liefert innerhalb einer einzelnen Seite keinen exakten Prozentwert.
- Die erste Kraken-Installation kann wegen PyTorch mehrere Minuten dauern.
- Der Windows-Installer ist noch nicht kommerziell codesigniert.
