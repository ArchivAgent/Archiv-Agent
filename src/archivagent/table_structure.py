from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import textwrap
import html
from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageEnhance, ImageOps


@dataclass
class TableStructure:
    image_width: int
    image_height: int
    vertical_lines: list[int]
    horizontal_lines: list[int]
    cells: list[dict[str, int]]
    horizontal_extents: dict[str, list[int]] | None = None
    vertical_extents: dict[str, list[int]] | None = None


def _group_positions(positions: Iterable[int], gap: int = 5) -> list[int]:
    groups: list[list[int]] = []
    for position in positions:
        if not groups or position - groups[-1][-1] > gap:
            groups.append([position])
        else:
            groups[-1].append(position)
    return [round(sum(group) / len(group)) for group in groups]


def _remove_near_duplicates(lines: list[int], minimum_distance: int) -> list[int]:
    result: list[int] = []
    for line in sorted(lines):
        if not result or line - result[-1] >= minimum_distance:
            result.append(line)
    return result


def detect_table_structure(image_path: str | Path) -> TableStructure:
    """Erkennt lange waagerechte/senkrechte Registerlinien ohne OpenCV."""
    with Image.open(image_path) as opened:
        gray = ImageOps.grayscale(ImageOps.exif_transpose(opened))
        # Große Seiten werden nur für die Projektion verkleinert. Die gefundenen
        # Koordinaten werden anschließend auf das Original zurückgerechnet.
        original_width, original_height = gray.size
        scale = min(1.0, 1800 / max(original_width, original_height))
        if scale < 1.0:
            gray = gray.resize(
                (max(1, round(original_width * scale)), max(1, round(original_height * scale))),
                Image.Resampling.LANCZOS,
            )
        gray = ImageEnhance.Contrast(gray).enhance(1.7)
        width, height = gray.size
        pixels = gray.load()
        threshold = 145

        # Linien müssen über einen erheblichen Teil der Seite dunkel sein.
        horizontal_scores = [sum(1 for x in range(width) if pixels[x, y] < threshold) / width for y in range(height)]
        vertical_scores = [sum(1 for y in range(height) if pixels[x, y] < threshold) / height for x in range(width)]
        horizontal = _group_positions((i for i, score in enumerate(horizontal_scores) if score >= 0.34), gap=max(2, round(height * 0.0025)))
        vertical = _group_positions((i for i, score in enumerate(vertical_scores) if score >= 0.28), gap=max(2, round(width * 0.0025)))

        # Bei alten, unterbrochenen Linien zusätzlich lokale Kontinuität prüfen.
        if len(horizontal) < 2:
            horizontal = _group_positions((i for i, score in enumerate(horizontal_scores) if score >= 0.22), gap=max(2, round(height * 0.0025)))
        if len(vertical) < 2:
            vertical = _group_positions((i for i, score in enumerate(vertical_scores) if score >= 0.18), gap=max(2, round(width * 0.0025)))

        horizontal = [round(value / scale) for value in horizontal]
        vertical = [round(value / scale) for value in vertical]
        horizontal = _remove_near_duplicates(horizontal, max(12, round(original_height * 0.008)))
        vertical = _remove_near_duplicates(vertical, max(12, round(original_width * 0.008)))

    cells: list[dict[str, int]] = []
    if len(horizontal) >= 2 and len(vertical) >= 2:
        for row in range(len(horizontal) - 1):
            top, bottom = horizontal[row], horizontal[row + 1]
            if bottom - top < 15:
                continue
            for column in range(len(vertical) - 1):
                left, right = vertical[column], vertical[column + 1]
                if right - left < 15:
                    continue
                cells.append({
                    "row": row + 1, "column": column + 1,
                    "x": left, "y": top, "width": right - left, "height": bottom - top,
                })
    return TableStructure(original_width, original_height, vertical, horizontal, cells)


def save_structure(structure: TableStructure, path: str | Path) -> Path:
    path = Path(path);path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(structure), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_structure(path: str | Path) -> TableStructure:
    """Lädt ein zuvor manuell angepasstes Seitenraster."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    structure = TableStructure(
        image_width=int(data["image_width"]),
        image_height=int(data["image_height"]),
        vertical_lines=[int(value) for value in data.get("vertical_lines", [])],
        horizontal_lines=[int(value) for value in data.get("horizontal_lines", [])],
        cells=list(data.get("cells", [])),
        horizontal_extents={str(k):[int(x) for x in v] for k,v in data.get("horizontal_extents",{}).items()},
        vertical_extents={str(k):[int(x) for x in v] for k,v in data.get("vertical_extents",{}).items()},
    )
    return rebuild_cells(structure)


def scale_structure(structure: TableStructure, image_width: int, image_height: int) -> TableStructure:
    """Überträgt ein gespeichertes Buchraster proportional auf eine andere Seite."""
    sx = image_width / max(1, structure.image_width)
    sy = image_height / max(1, structure.image_height)
    vertical = [round(value * sx) for value in structure.vertical_lines]
    horizontal = [round(value * sy) for value in structure.horizontal_lines]
    horizontal_extents = {}
    for old, new in zip(structure.horizontal_lines, horizontal):
        start, end = (structure.horizontal_extents or {}).get(str(old), [0, structure.image_width])
        horizontal_extents[str(new)] = [round(start * sx), round(end * sx)]
    vertical_extents = {}
    for old, new in zip(structure.vertical_lines, vertical):
        start, end = (structure.vertical_extents or {}).get(str(old), [0, structure.image_height])
        vertical_extents[str(new)] = [round(start * sy), round(end * sy)]
    return rebuild_cells(TableStructure(
        image_width, image_height, vertical, horizontal, [],
        horizontal_extents, vertical_extents,
    ))


def _alto_number(element: ET.Element, name: str, default: float = 0.0) -> float:
    try:
        return float(element.attrib.get(name, default))
    except (TypeError, ValueError):
        return default


def _alto_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def transcription_from_grid(alto_path: str | Path, structure: TableStructure) -> str:
    """Ordnet ALTO-Zeilen den gespeicherten Tabellenzellen zu.

    Innerhalb einer Zelle bleiben getrennt erkannte Textzeilen getrennt. Mehrere
    Zellen derselben Tabellenzeile werden nebeneinander ausgegeben.
    """
    root = ET.parse(alto_path).getroot()
    page = next((item for item in root.iter() if _alto_name(item.tag) == "Page"), None)
    alto_width = max(1.0, _alto_number(page, "WIDTH", structure.image_width) if page is not None else structure.image_width)
    alto_height = max(1.0, _alto_number(page, "HEIGHT", structure.image_height) if page is not None else structure.image_height)
    scale_x = structure.image_width / alto_width
    scale_y = structure.image_height / alto_height
    lines: list[tuple[float, float, str]] = []
    for element in root.iter():
        if _alto_name(element.tag) != "TextLine":
            continue
        words = [
            child.attrib.get("CONTENT", "").strip()
            for child in element.iter()
            if _alto_name(child.tag) in {"String", "Glyph"} and child.attrib.get("CONTENT", "").strip()
        ]
        text = " ".join(words).strip() or (element.attrib.get("CONTENT") or "").strip()
        if text:
            x = (_alto_number(element, "HPOS") + _alto_number(element, "WIDTH") / 2) * scale_x
            y = (_alto_number(element, "VPOS") + _alto_number(element, "HEIGHT", 1.0) / 2) * scale_y
            lines.append((x, y, text))

    vertical = structure.vertical_lines
    horizontal = structure.horizontal_lines
    if len(vertical) < 2 or len(horizontal) < 2:
        return "\n".join(text for _x, _y, text in sorted(lines, key=lambda item: (item[1], item[0]))) + ("\n" if lines else "")
    cells: dict[tuple[int, int], list[tuple[float, str]]] = {}
    for x, y, text in lines:
        column = next((i for i, (left, right) in enumerate(zip(vertical, vertical[1:])) if left <= x < right), None)
        row = next((i for i, (top, bottom) in enumerate(zip(horizontal, horizontal[1:])) if top <= y < bottom), None)
        if row is not None and column is not None:
            cells.setdefault((row, column), []).append((y, text))

    widths = [max(8, min(45, round((right - left) / max(1, structure.image_width) * 150))) for left, right in zip(vertical, vertical[1:])]
    output: list[str] = []
    for row in range(len(horizontal) - 1):
        column_lines = []
        for column,width in enumerate(widths):
            wrapped=[]
            for _y,text in sorted(cells.get((row,column),[])):
                # Niemals OCR-Text am Spaltenende abschneiden. Lange Inhalte
                # werden vollständig innerhalb derselben Zelle umgebrochen.
                wrapped.extend(textwrap.wrap(text,width=max(1,width),break_long_words=True,
                                             break_on_hyphens=False,replace_whitespace=False) or [''])
            column_lines.append(wrapped)
        height = max((len(items) for items in column_lines), default=0)
        if not height:
            output.append("")
            continue
        for line_index in range(height):
            parts = []
            for column, width in enumerate(widths):
                value = column_lines[column][line_index] if line_index < len(column_lines[column]) else ""
                parts.append(value.ljust(width))
            output.append(" | ".join(parts).rstrip())
        if row < len(horizontal) - 2:
            output.append("")
    return "\n".join(output).rstrip() + "\n"


def grid_cells_from_alto(alto_path: str | Path, structure: TableStructure) -> list[list[str]]:
    """Ordnet jedes einzelne ALTO-Wort genau einer Rasterzelle zu.

    Anders als die alte TextLine-Zuordnung gehen dadurch weder Wörter außerhalb
    des inneren Rasters verloren noch wird eine ganze Zeile nur einer Spalte
    zugeschlagen.
    """
    root=ET.parse(alto_path).getroot()
    page=next((item for item in root.iter() if _alto_name(item.tag)=='Page'),None)
    aw=max(1.0,_alto_number(page,'WIDTH',structure.image_width) if page is not None else structure.image_width)
    ah=max(1.0,_alto_number(page,'HEIGHT',structure.image_height) if page is not None else structure.image_height)
    sx=structure.image_width/aw;sy=structure.image_height/ah
    vertical=structure.vertical_lines;horizontal=structure.horizontal_lines
    rows=max(0,len(horizontal)-1);columns=max(0,len(vertical)-1)
    if not rows or not columns:return []
    tokens=[]
    for line in (element for element in root.iter() if _alto_name(element.tag)=='TextLine'):
        children=[element for element in line.iter() if _alto_name(element.tag) in {'String','Glyph'} and (element.attrib.get('CONTENT') or '').strip()]
        if children:
            for element in children:
                value=(element.attrib.get('CONTENT') or '').strip()
                x=(_alto_number(element,'HPOS')+_alto_number(element,'WIDTH')/2)*sx
                y=(_alto_number(element,'VPOS')+_alto_number(element,'HEIGHT',1)/2)*sy
                tokens.append((x,y,value))
        else:
            value=(line.attrib.get('CONTENT') or '').strip()
            if value:
                x=(_alto_number(line,'HPOS')+_alto_number(line,'WIDTH')/2)*sx
                y=(_alto_number(line,'VPOS')+_alto_number(line,'HEIGHT',1)/2)*sy
                tokens.append((x,y,value))
    cells={(row,column):[] for row in range(rows) for column in range(columns)}
    def interval(value,lines):
        found=next((i for i,(a,b) in enumerate(zip(lines,lines[1:])) if a<=value<b),None)
        if found is not None:return found
        return min(range(len(lines)-1),key=lambda i:abs(value-(lines[i]+lines[i+1])/2))
    for x,y,value in tokens:
        cells[(interval(y,horizontal),interval(x,vertical))].append((y,x,value))
    result=[]
    for row in range(rows):
        current=[]
        for column in range(columns):
            items=sorted(cells[(row,column)])
            lines=[];last_y=None
            for y,_x,value in items:
                if last_y is not None and abs(y-last_y)>max(12,structure.image_height*.004):lines.append('\n')
                elif lines:lines.append(' ')
                lines.append(value);last_y=y
            current.append(''.join(lines))
        result.append(current)
    return result


def transcription_html_from_grid(alto_path: str | Path, structure: TableStructure) -> str:
    """Erzeugt eine echte editierbare Tabelle mit Original-Spaltenproportionen."""
    rows=grid_cells_from_alto(alto_path,structure)
    widths=[max(0.1,(right-left)/max(1,structure.image_width)*100) for left,right in zip(structure.vertical_lines,structure.vertical_lines[1:])]
    parts=['<html><head><style>table{border-collapse:collapse;width:100%;table-layout:fixed}td{border:2px solid #2674d9;vertical-align:top;padding:3px;white-space:pre-wrap;overflow-wrap:anywhere}tr{border-top:2px solid #e53935}</style></head><body><table>','<colgroup>']
    parts.extend(f'<col style="width:{width:.5f}%">' for width in widths);parts.append('</colgroup>')
    for row in rows:
        parts.append('<tr>');parts.extend(f'<td>{html.escape(value).replace(chr(10),"<br>")}</td>' for value in row);parts.append('</tr>')
    parts.append('</table></body></html>');return ''.join(parts)


def rebuild_cells(structure: TableStructure) -> TableStructure:
    """Berechnet die Zellen nach einer manuellen Änderung der Trennlinien neu."""
    structure.vertical_lines = sorted({max(0, min(structure.image_width, round(value))) for value in structure.vertical_lines})
    structure.horizontal_lines = sorted({max(0, min(structure.image_height, round(value))) for value in structure.horizontal_lines})
    cells: list[dict[str, int]] = []
    for row, (top, bottom) in enumerate(zip(structure.horizontal_lines, structure.horizontal_lines[1:]), 1):
        if bottom - top < 4:
            continue
        for column, (left, right) in enumerate(zip(structure.vertical_lines, structure.vertical_lines[1:]), 1):
            if right - left < 4:
                continue
            cells.append({"row": row, "column": column, "x": left, "y": top,
                          "width": right - left, "height": bottom - top})
    structure.cells = cells
    if structure.horizontal_extents is None:structure.horizontal_extents={}
    if structure.vertical_extents is None:structure.vertical_extents={}
    return structure


def draw_structure_overlay(image_path: str | Path, structure: TableStructure, output_path: str | Path) -> Path:
    with Image.open(image_path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    line_width = max(3, round(max(image.size) / 700))
    for x in structure.vertical_lines:
        start,end=(structure.vertical_extents or {}).get(str(x),[0,structure.image_height])
        draw.line((x,start,x,end),fill=(20,110,230,220),width=line_width)
    for y in structure.horizontal_lines:
        start,end=(structure.horizontal_extents or {}).get(str(y),[0,structure.image_width])
        draw.line((start,y,end,y),fill=(230,45,45,220),width=line_width)
    for cell in structure.cells:
        draw.rectangle(
            (cell["x"], cell["y"], cell["x"] + cell["width"], cell["y"] + cell["height"]),
            outline=(255, 200, 0, 105), width=max(1, line_width // 2),
        )
    output_path = Path(output_path);output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")
    return output_path
