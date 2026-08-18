# ArchivAgent 7.1 RC19 testen

## Tabellenbuch testen

1. Ein Buch mit Umschlagseiten und einer später beginnenden Tabelle importieren.
2. **Tabellenstruktur zuweisen / bearbeiten** wählen und ausdrücklich die erste echte Tabellenseite auswählen.
3. Raster prüfen, korrigieren und speichern; die Übertragung auf alle folgenden Seiten bestätigen.
4. **Ganzes Buch anzeigen** öffnen und vorwärts sowie rückwärts blättern. Vor der Startseite darf kein Raster erscheinen, ab der Startseite müssen Original und Transkription tabellarisch dargestellt werden.
5. Einen Treffer ab der Tabellenstartseite öffnen. Im Original und im erkannten Text muss dieselbe Tabellenstruktur erscheinen.
6. Im Raster mit der rechten Maustaste Zeilen und Spalten hinzufügen beziehungsweise entfernen.
7. Eine Linie in der Mitte mit links verschieben; anschließend ein Linienende mit links ziehen und dadurch die Länge ändern.

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

## Eigene Bilder testen

1. Projekt und Buch anlegen oder in die Felder eintragen.
2. **Eigene Scans/Bilder hinzufügen** wählen.
3. Mehrere PNG-, JPG- oder TIFF-Dateien auswählen.
4. Prüfen, ob ArchivAgent den Ordner `Originalseiten` automatisch erstellt und die
   Bilder als `Seite_0001`, `Seite_0002` usw. einordnet.
5. Familiennamen eintragen und **Alles automatisch starten** wählen. ArchivAgent
   muss ohne Viewer-Link direkt die importierten Bilder verarbeiten.

## Vollständigen Lesemodus testen

1. Projekt und Buch anlegen oder auswählen.
2. **Dokument vollständig lesen** wählen und einen einzelnen Scan öffnen.
3. Prüfen, ob die Erkennung ohne eingetragenen Familiennamen startet.
4. Im Lesefenster Original oben und vollständige Transkription unten prüfen.
5. Text korrigieren, kopieren und über **Korrektur speichern** sichern.
6. Einen vorhandenen Treffer auswählen und **Ganze Trefferseite lesen** testen.
7. Prüfen, ob der gefundene Name in der Transkription markiert wird.

## Tabellenstruktur testen

1. Eine vollständige Register- oder Tabellenseite über **Eigene Scans/Bilder hinzufügen** importieren.
2. **Tabellenstruktur erkennen** anklicken.
3. Prüfen, ob rote Linien den Zeilen und blaue Linien den Spalten des Originals folgen.
4. Prüfen, ob die gelben Rechtecke sinnvolle Tabellenfelder bilden.
5. Einen Screenshot des Prüffensters senden und dabei fehlende oder falsche Linien beschreiben.

Die Zellinhalte werden in diesem ersten Test noch nicht einzeln transkribiert.

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
