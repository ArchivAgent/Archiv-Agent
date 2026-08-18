# ArchivAgent

ArchivAgent ist ein Windows-Programm zur unterstützten Recherche in digitalisierten
Kirchenbüchern, Urkunden, Amtsbüchern und weiteren historischen Archivalien. Es lädt
ausgewählte Seiten aus kompatiblen METS-/DFG-Viewern, erkennt Handschrift mit Kraken
OCR und durchsucht die Ergebnisse nach Familiennamen.

> **Testversion:** ArchivAgent 7.1 RC19 ist eine öffentliche Vorabversion. Bitte
> zunächst mit kleinen Seitenbereichen und Kopien wichtiger Forschungsdaten testen.

## Funktionen

- Buchseiten über einen METS-/DFG-Viewer-Link herunterladen
- eigene Scans, Fotos und gespeicherte Dokumentseiten importieren
- beim Import automatisch den Buchordner `Originalseiten` erstellen und Seiten nummerieren
- frei wählbare Seitenbereiche verarbeiten
- historische Handschrift lokal mit Kraken OCR erkennen
- mehrere Familiennamen mit einstellbarer Suchgenauigkeit suchen
- Fundstellen mit Originalseite und erkanntem Text prüfen
- ganze Trefferseiten in einem gemeinsamen Lesefenster öffnen
- eigene Dokumente ohne Namenssuche vollständig transkribieren
- Original oben und bearbeitbare Transkription mit Zeilen und Spalten nach dem Original unten anzeigen
- Tabellen- und Registerlinien ohne KI erkennen und als farbiges Raster prüfen
- erste echte Tabellenseite ausdrücklich auswählen; Umschlag und Vorsatz bleiben ohne Raster
- das Raster der ersten Tabellenseite proportional auf alle folgenden Buchseiten übertragen
- ein ganzes importiertes Buch mit Vor-/Zurück-Schaltflächen, Originalraster und tabellarischer Transkription durchblättern
- Trefferseiten mit Raster im Original und derselben Tabellenstruktur im erkannten Text anzeigen
- Zeilen und Spalten per Rechtsklick hinzufügen oder entfernen; Linien verschieben und an ihren Enden direkt verlängern oder verkürzen
- leere Rasterdateien aus früheren Erkennungsversuchen automatisch verwerfen und die gewählte Tabellenseite neu erkennen
- korrigierte Transkriptionen getrennt vom OCR-Rohtext speichern
- Projekte, Trefferlisten und Ergebnisse lokal speichern
- laufende Texterkennung mit Seitenfortschritt und animiertem Archivarius anzeigen
- laufende Vorgänge kontrolliert abbrechen

## Digitalisierte Archivalie aus einem DFG-Viewer übernehmen

1. Das gewünschte Dokument oder den gewünschten Band im Online-Archiv aufrufen.
2. Über **Augensymbol**, **Digitalisat**, **Viewer** oder **DFG-Viewer** die
   Bildansicht öffnen.
3. Sobald die digitalisierten Seiten sichtbar sind, mit `Strg + L` die vollständige
   Adresse aus der Browserzeile markieren und mit `Strg + C` kopieren.
4. Nicht die Bildadresse einer einzelnen Scan-Datei verwenden.
5. In ArchivAgent ein Projekt und einen aussagekräftigen Titel für die Archivalie
   eingeben.
6. **Link aus Zwischenablage** anklicken.
7. Familiennamen beziehungsweise Suchbegriffe und den gewünschten Seitenbereich
   angeben.
8. **Alles automatisch starten** wählen.

ArchivAgent liest die METS-Struktur des Viewers, lädt die ausgewählten Seiten, führt
die Handschriftenerkennung lokal aus und durchsucht den erkannten Text. Falls das
Archiv einen Link mit der Bezeichnung **METS**, **METS-XML** oder **DFG-Viewer**
anbietet, kann dieser direkt verwendet werden.

## Systemvoraussetzungen

- Windows 10 oder Windows 11, 64 Bit
- Python 3.13
- Microsoft Visual C++ Redistributable (x64)
- Internetverbindung für Installation und Seitenabruf
- ausreichend freier Speicherplatz; Kraken und PyTorch benötigen mehrere Gigabyte

Die eigentliche Erkennung und Namenssuche erfolgt lokal auf dem Rechner. ArchivAgent
lädt OCR-Komponenten erst nach ausdrücklicher Zustimmung im OCR-Assistenten.

## Installation der Testversion

1. Unter **Releases** die Datei `ArchivAgent_Setup_7.1.0_RC19.exe` herunterladen.
2. Optional die SHA-256-Prüfsumme mit
   `ArchivAgent_Setup_7.1.0_RC19_SHA256.txt` vergleichen.
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

## Eigene Scans und Bilddateien untersuchen

ArchivAgent kann neben unterstützten Online-Archiven auch eigene Scans,
fotografierte Dokumente und bereits gespeicherte Archivseiten untersuchen. Über
**Eigene Scans/Bilder hinzufügen** können mehrere PNG-, JPG-, TIFF-, JP2- oder
WebP-Dateien ausgewählt werden. ArchivAgent legt den benötigten Ordner
`Originalseiten` automatisch an und nummeriert die importierten Seiten fortlaufend.

Danach Familiennamen eintragen und **Alles automatisch starten** oder
**Vorhandenes Buch durchsuchen** wählen. Ohne Viewer-Link erkennt ArchivAgent
automatisch, dass die bereits importierten eigenen Bilder verarbeitet werden sollen.

Für eine vollständige Transkription ohne Namenssuche **Dokument vollständig lesen**
wählen. Im Lesefenster steht das zoombare Original über dem vollständigen erkannten
Text. Der Text kann bearbeitet, kopiert und als separate Korrekturfassung gespeichert
werden; der ursprüngliche OCR-Text bleibt dabei unverändert.

Nach dem Import einer einzelnen Seite verwendet **Dokument vollständig lesen** genau
diese bereits importierte Seite; sie muss nicht erneut ausgewählt oder hochgeladen
werden. Kleine oder sehr breite Bildausschnitte erhalten für die Erkennung automatisch
mehr Rand und eine geeignete Auflösung.

Für den Lesemodus speichert ArchivAgent zusätzlich Krakens ALTO-Koordinaten. Dadurch
lassen sich erkannte Zeilen und Spalten annähernd an ihrer Position im Original
anordnen. Bei Tabellen, Doppelseiten oder schwer erkannten Trennlinien kann die
Anordnung wegen der automatischen Segmentierung vom Original abweichen.

## Tabellenstruktur prüfen (erster Testmodus)

Nach dem Import einer Register- oder Tabellenseite kann **Tabellenstruktur erkennen**
gewählt werden. ArchivAgent sucht dabei ohne KI nach langen waagerechten und
senkrechten Linien. Im Prüffenster sind waagerechte Linien rot, senkrechte Linien
blau und erkannte Zellen gelb markiert. Das Ergebnis wird im Buchordner unter
`HTR\Struktur` als Bild und JSON-Datei gespeichert.

Dieser erste Modus transkribiert die einzelnen Tabellenfelder noch nicht. Er dient
dazu, mit echten historischen Seiten zu testen, ob Zeilen und Spalten zuverlässig
voneinander getrennt werden. Blasse, stark unterbrochene oder handgezeichnete Linien
können noch fehlen oder zusätzlich erkannt werden.

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

Aktuelle Testversion: **ArchivAgent 7.1 RC19**

**Idee, Konzeption und Projektleitung: Frank Bernbeck**

Entwickelt mit KI-gestützter Entwicklungsunterstützung.
