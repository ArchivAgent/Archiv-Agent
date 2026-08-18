from pathlib import Path
import sys


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src" / "backend"))

from archiv_layout import spatial_text_from_alto


def test_full_page_reader_has_vertical_original_and_editable_transcription():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert "class FullPageReader(QDialog)" in gui
    assert "QSplitter(Qt.Orientation.Vertical)" in gui
    assert "Original" in gui
    assert "Transkription — Zeilen und Spalten nach dem Original angeordnet" in gui
    assert "QTextEdit.LineWrapMode.WidgetWidth" in gui
    assert "self.transcription.setAcceptRichText(True)" in gui
    assert "transcription_html_from_grid" in gui
    assert "Korrektur speichern" in gui
    assert "Verdächtige Zeichen markieren" in gui
    assert "def highlight_suspicious" in gui
    assert "Die korrigierte Tabelle wurde dauerhaft gespeichert" in gui
    assert "Kraken-Ground-Truth wurde für das Modelltraining angelegt" in gui


def test_reader_is_available_for_hits_and_own_documents():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert "Dokument vollständig lesen" in gui
    assert "Ganze Trefferseite lesen" in gui
    assert "def read_own_document" in gui
    assert "def read_current_hit_page" in gui
    assert "self.open_page_reader" in gui
    assert "self.image_view.show_image(self.image_path,bbox)" in gui
    assert "saved or self.estimated_line_bbox(hit,img)[0]" in gui


def test_read_only_mode_does_not_replace_existing_hit_lists():
    launcher = (ROOT / "src" / "backend" / "archiv_agent.py").read_text(encoding="utf-8")
    htr = (ROOT / "src" / "backend" / "archiv_htr.py").read_text(encoding="utf-8")
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert '"--read-only"' in launcher
    assert "args.names = []" in launcher
    assert "if args.read_only:" in launcher
    assert "if names:" in htr
    assert "self.action in ('htr','all','read')" in gui
    assert "cmd.append('--read-only')" in gui


def test_alto_coordinates_preserve_rows_and_columns(tmp_path):
    alto = tmp_path / "page.xml"
    alto.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#">
  <Layout><Page WIDTH="1000" HEIGHT="800"><PrintSpace>
    <TextBlock>
      <TextLine HPOS="50" VPOS="100" WIDTH="250" HEIGHT="30"><String CONTENT="Links eins"/></TextLine>
      <TextLine HPOS="550" VPOS="102" WIDTH="250" HEIGHT="30"><String CONTENT="Rechts eins"/></TextLine>
      <TextLine HPOS="50" VPOS="200" WIDTH="250" HEIGHT="30"><String CONTENT="Links zwei"/></TextLine>
      <TextLine HPOS="550" VPOS="202" WIDTH="250" HEIGHT="30"><String CONTENT="Rechts zwei"/></TextLine>
    </TextBlock>
  </PrintSpace></Page></Layout>
</alto>""", encoding="utf-8")
    result = spatial_text_from_alto(alto, columns=80).splitlines()
    content_rows = [line for line in result if line.strip()]
    assert len(content_rows) == 2
    assert content_rows[0].index("Links eins") < content_rows[0].index("Rechts eins")
    assert content_rows[1].index("Links zwei") < content_rows[1].index("Rechts zwei")


def test_backend_requests_alto_for_spatial_transcription():
    htr = (ROOT / "src" / "backend" / "archiv_htr.py").read_text(encoding="utf-8")
    builder = (ROOT / "build_release.py").read_text(encoding="utf-8")
    # Kraken erhält entweder das Original oder die für kleine/breite Ausschnitte
    # vorbereitete Eingabedatei. Entscheidend sind ALTO-Ausgabe und Parameter.
    assert '"-a", "-i", str(ocr_input), str(alto_output)' in htr
    assert "spatial_text_from_alto" in htr
    assert '"archiv_layout.py"' in builder


def test_small_crops_are_prepared_and_empty_ocr_is_reported():
    htr = (ROOT / "src" / "backend" / "archiv_htr.py").read_text(encoding="utf-8")
    assert "def prepare_cropped_image" in htr
    assert "kleiner oder breiter Ausschnitt wurde vergrößert" in htr
    assert "Kraken hat auf dieser Seite keine Textzeilen erkannt" in htr


def test_imported_scan_is_reused_without_second_upload_dialog():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert "self.last_imported_image=imported[0] if len(imported)==1 else None" in gui
    assert "Bereits importierte Seite auswählen" in gui
    assert "Bitte eine bereits über „Eigene Scans/Bilder hinzufügen“ importierte Seite auswählen" in gui
    assert "for index,button in enumerate((a,i,h,c))" in gui
    assert "Vorhandenes Buch/Scan durchsuchen" in gui
    assert "QPushButton('Nur Seiten herunterladen')" not in gui


def test_table_structure_mode_is_available_for_imported_scans():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert "Tabellenstruktur erkennen" in gui
    assert "def detect_current_table" in gui


def test_table_page_is_selected_explicitly_instead_of_using_cover():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert "def select_table_page" in gui
    assert "Auf welcher Seite beginnt die Tabelle?" in gui
    assert "Umschlag- und Vorsatzseiten bleiben ohne Raster." in gui
    assert "image=self.select_table_page()" in gui


def test_table_template_is_used_for_book_and_hit_views():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert "Ganzes Buch anzeigen" in gui
    assert "def show_whole_book" in gui
    assert "def apply_table_template" in gui
    assert "Buchvorlage.json" in gui
    assert "Erkannter Text — als Tabelle nach dem Original" in gui
    assert "self.scan_view.show_structure(load_structure(structure_path))" in gui


def test_raster_context_menu_and_direct_length_drag_are_available():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert "def contextMenuEvent" in gui
    assert "Zeile hinzufügen" in gui
    assert "Zeile entfernen" in gui
    assert "Spalte hinzufügen" in gui
    assert "Spalte entfernen" in gui
    assert "self.dragging_endpoint" in gui
    assert "Linienende mit links ziehen" in gui


def test_empty_saved_grid_is_detected_again_and_can_be_refreshed():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert "structure is None or len(structure.horizontal_lines)<2 or len(structure.vertical_lines)<2" in gui
    assert "Raster neu erkennen" in gui
    assert "def redetect" in gui
    assert "self.view.reload_lines()" in gui


def test_table_lines_can_be_moved_added_deleted_and_saved():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert "class DraggableSeparator" in gui
    assert "Neue Zeilengrenze" in gui
    assert "Ausgewählte Linie löschen" in gui
    assert "Raster speichern" in gui


def test_saved_table_grid_is_visible_in_transcription():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert "class StructuredTextEdit" in gui
    assert "self.structure.horizontal_lines" in gui
    assert "self.structure.vertical_lines" in gui
    assert "resolve_page_structurefile" in gui
    assert "class TableStructureDialog" in gui
    assert "HTR'/'Struktur" in gui
    assert "self.image_view.show_structure(self.structure)" in gui
    assert "transcription_html_from_grid(self.alto_path,self.structure)" in gui
    assert "resolve_page_altofile" in gui


def test_clicking_original_cell_selects_matching_transcription():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert "self.image_view.scene_click_callback=self.select_original_cell" in gui
    assert "def select_original_cell" in gui
    assert "self.transcription.ensureCursorVisible()" in gui


def test_vertical_separators_are_easy_to_select_and_delete():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert "stroker.setWidth(18)" in gui
    assert "7 if self.isSelected() else 4" in gui
    assert "Qt.Key.Key_Delete" in gui
    assert "tolerance=12.0/scale" in gui
    assert "self.scene.clearSelection();chosen.setSelected(True)" in gui
    assert "self.dragging_separator=chosen" in gui
    assert "def mouseMoveEvent(self,event):" in gui


def test_clicking_hit_opens_complete_page_immediately():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert "self.table.cellClicked.connect(self.open_selected_hit_page)" in gui
    assert "def open_selected_hit_page" in gui
    assert "self.read_current_hit_page()" in gui


def test_grid_transcription_never_truncates_words():
    source = (ROOT / "src" / "archivagent" / "table_structure.py").read_text(encoding="utf-8")
    assert "textwrap.wrap" in source
    assert "parts.append(value[:width]" not in source
    assert "parts.append(value.ljust(width))" in source
    assert "OCR-Rohtext neu laden (Korrektur verwerfen)" not in (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert "def grid_cells_from_alto" in source
    assert "def transcription_html_from_grid" in source
    assert "table-layout:fixed" in source
    assert "overflow-wrap:anywhere" in source


def test_old_split_hit_preview_is_removed():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    hits_page = gui[gui.index("    def hits_page(self):"):gui.index("    def open_selected_hit_page")]
    assert "self.scan_view" not in hits_page
    assert "self.ocr_panel" not in hits_page
    assert "Ganze Trefferseite lesen" not in hits_page
    assert "self.nav.currentRowChanged.connect(self.navigation_changed)" in gui


def test_navigation_is_simplified_and_has_info():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    nav = "self.nav.addItems(['Buch durchsuchen','Bücher','Treffer prüfen','Einstellungen','Info'])"
    assert nav in gui
    assert "def info_page" in gui
    assert "Programmierer: Frank Bernbeck" in gui
    assert "self.document_tools.setVisible(has_document)" in gui


def test_table_corrections_keep_format_and_selected_text_size():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    assert "self.transcription.toHtml()" in gui
    assert "self.transcription.setHtml(corrected_html.read_text" in gui
    assert "QTextCursor.SelectionType.WordUnderCursor" in gui
    assert "cursor.mergeCharFormat(fmt)" in gui
    assert "status':'gesammelt_nicht_trainiert'" in gui
    assert "def rebuild_transcription_preserving_corrections" in gui
    assert "self.save_correction(silent=True)" in gui


def test_real_kraken_training_and_scrollable_start_page():
    gui = (ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    backend = (ROOT / "src" / "backend" / "archiv_htr.py").read_text(encoding="utf-8")
    assert "Persönliches Kraken-Modell trainieren" in gui
    assert "def save_training_alto" in gui
    assert "def train_personal_model" in gui
    assert "'--load',str(base_model)" in gui
    assert "'--weights-format','safetensors'" in gui
    assert "models.extend(folder.rglob(\"*.safetensors\"))" in backend
    assert "scroll=QScrollArea()" in gui
    assert "w.setMinimumHeight(820)" in gui


def test_html_table_click_targets_actual_cell_and_raster_lengths_are_editable():
    gui=(ROOT / "src" / "archivagent" / "main.py").read_text(encoding="utf-8")
    structure=(ROOT / "src" / "archivagent" / "table_structure.py").read_text(encoding="utf-8")
    assert "table.cellAt(row,column)" in gui
    assert "def select_hit_cell" in gui
    assert "Rasterlinien bearbeiten/löschen" in gui
    assert "Ausgewählte Linie löschen" in gui
    assert "Anfang im Bild setzen" in gui
    assert "Ende im Bild setzen" in gui
    assert "horizontal_extents" in structure
    assert "vertical_extents" in structure
