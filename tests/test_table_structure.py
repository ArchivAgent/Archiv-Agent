from pathlib import Path
import json
import sys

from PIL import Image, ImageDraw


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from archivagent.table_structure import TableStructure, detect_table_structure, draw_structure_overlay, load_structure, rebuild_cells, save_structure, scale_structure, transcription_from_grid


def test_detects_clean_register_grid(tmp_path):
    source = tmp_path / "register.png"
    image = Image.new("RGB", (800, 600), "white")
    draw = ImageDraw.Draw(image)
    vertical = [50, 250, 500, 750]
    horizontal = [50, 200, 400, 550]
    for x in vertical:
        draw.line((x, 20, x, 580), fill="black", width=5)
    for y in horizontal:
        draw.line((20, y, 780, y), fill="black", width=5)
    image.save(source)

    structure = detect_table_structure(source)

    assert len(structure.vertical_lines) == 4
    assert len(structure.horizontal_lines) == 4
    assert len(structure.cells) == 9
    for expected, actual in zip(vertical, structure.vertical_lines):
        assert abs(expected - actual) <= 3
    for expected, actual in zip(horizontal, structure.horizontal_lines):
        assert abs(expected - actual) <= 3

    json_path = save_structure(structure, tmp_path / "structure.json")
    overlay_path = draw_structure_overlay(source, structure, tmp_path / "overlay.png")
    assert json.loads(json_path.read_text(encoding="utf-8"))["cells"]
    assert overlay_path.exists()


def test_rebuilds_cells_after_manual_line_edit():
    structure = TableStructure(800, 600, [50, 400, 750], [50, 300, 550], [])
    rebuild_cells(structure)
    assert len(structure.cells) == 4
    structure.horizontal_lines.append(425)
    rebuild_cells(structure)
    assert structure.horizontal_lines == [50, 300, 425, 550]
    assert len(structure.cells) == 6


def test_book_template_is_scaled_to_target_page():
    source = rebuild_cells(TableStructure(1000, 2000, [100, 500, 900], [200, 1000, 1800], []))
    scaled = scale_structure(source, 2000, 1000)
    assert scaled.vertical_lines == [200, 1000, 1800]
    assert scaled.horizontal_lines == [100, 500, 900]
    assert len(scaled.cells) == 4


def test_saved_manual_grid_is_loaded_again(tmp_path):
    path = tmp_path / "page.json"
    saved = TableStructure(800, 600, [12, 333, 790], [25, 287, 575], [])
    save_structure(rebuild_cells(saved), path)

    loaded = load_structure(path)

    assert loaded.vertical_lines == [12, 333, 790]
    assert loaded.horizontal_lines == [25, 287, 575]
    assert len(loaded.cells) == 4


def test_grid_transcription_preserves_cell_line_breaks(tmp_path):
    alto = tmp_path / "page.xml"
    alto.write_text('''<alto><Layout><Page WIDTH="800" HEIGHT="600"><TextBlock>
      <TextLine HPOS="60" VPOS="70" WIDTH="250" HEIGHT="20"><String CONTENT="links eins"/></TextLine>
      <TextLine HPOS="60" VPOS="105" WIDTH="250" HEIGHT="20"><String CONTENT="links zwei"/></TextLine>
      <TextLine HPOS="440" VPOS="72" WIDTH="250" HEIGHT="20"><String CONTENT="rechts eins"/></TextLine>
      <TextLine HPOS="60" VPOS="350" WIDTH="250" HEIGHT="20"><String CONTENT="zweite Zeile"/></TextLine>
    </TextBlock></Page></Layout></alto>''', encoding="utf-8")
    structure = rebuild_cells(TableStructure(800, 600, [0, 400, 800], [0, 300, 600], []))
    rows = transcription_from_grid(alto, structure).splitlines()
    assert "links eins" in rows[0] and "rechts eins" in rows[0]
    assert "links zwei" in rows[1]
    assert rows[2] == ""
    assert "zweite Zeile" in rows[3]
