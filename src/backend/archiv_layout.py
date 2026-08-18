from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import statistics
import xml.etree.ElementTree as ET


@dataclass
class LayoutLine:
    x: float
    y: float
    width: float
    height: float
    text: str


def _number(element: ET.Element, name: str, default: float = 0.0) -> float:
    try:
        return float(element.attrib.get(name, default))
    except (TypeError, ValueError):
        return default


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def read_alto_lines(path: str | Path) -> tuple[float, float, list[LayoutLine]]:
    root = ET.parse(path).getroot()
    page = next((item for item in root.iter() if _local_name(item.tag) == "Page"), None)
    page_width = _number(page, "WIDTH") if page is not None else 0.0
    page_height = _number(page, "HEIGHT") if page is not None else 0.0
    lines: list[LayoutLine] = []
    for element in root.iter():
        if _local_name(element.tag) != "TextLine":
            continue
        words = [
            child.attrib.get("CONTENT", "").strip()
            for child in element.iter()
            if _local_name(child.tag) in {"String", "Glyph"} and child.attrib.get("CONTENT", "").strip()
        ]
        text = " ".join(words).strip()
        if not text:
            text = (element.attrib.get("CONTENT") or "").strip()
        if not text:
            text = " ".join(
                (child.text or "").strip() for child in element.iter()
                if _local_name(child.tag) in {"Unicode", "PlainText"} and (child.text or "").strip()
            ).strip()
        if not text:
            continue
        x = _number(element, "HPOS");y = _number(element, "VPOS")
        width = _number(element, "WIDTH");height = max(1.0, _number(element, "HEIGHT", 1.0))
        lines.append(LayoutLine(x, y, width, height, text))
        page_width = max(page_width, x + width)
        page_height = max(page_height, y + height)
    # Manche Serializer liefern String-Elemente ohne umschließende TextLine.
    if not lines:
        for element in root.iter():
            if _local_name(element.tag) != "String":
                continue
            text = (element.attrib.get("CONTENT") or "").strip()
            if not text:
                continue
            x = _number(element, "HPOS");y = _number(element, "VPOS")
            width = _number(element, "WIDTH");height = max(1.0, _number(element, "HEIGHT", 1.0))
            lines.append(LayoutLine(x, y, width, height, text))
            page_width = max(page_width, x + width);page_height = max(page_height, y + height)
    return max(page_width, 1.0), max(page_height, 1.0), lines


def spatial_text_from_alto(path: str | Path, columns: int = 150) -> str:
    """Erzeugt eine editierbare Textansicht mit annähernd originalen Spalten."""
    page_width, page_height, lines = read_alto_lines(path)
    if not lines:
        return ""
    heights = [line.height for line in lines]
    median_height = statistics.median(heights) if heights else 20.0
    tolerance = max(4.0, median_height * 0.65)
    rows: list[dict] = []
    for line in sorted(lines, key=lambda item: (item.y + item.height / 2, item.x)):
        center = line.y + line.height / 2
        row = next((candidate for candidate in reversed(rows[-4:]) if abs(candidate["center"] - center) <= tolerance), None)
        if row is None:
            rows.append({"center": center, "items": [line]})
        else:
            row["items"].append(line)
            count = len(row["items"]);row["center"] = (row["center"] * (count - 1) + center) / count

    output: list[str] = []
    previous_center = None
    line_step = max(median_height * 1.45, 1.0)
    for row in rows:
        if previous_center is not None:
            missing = min(2, max(0, round((row["center"] - previous_center) / line_step) - 1))
            output.extend("" for _ in range(missing))
        canvas: list[str] = []
        for line in sorted(row["items"], key=lambda item: item.x):
            position = max(0, min(columns - 1, round(line.x / page_width * (columns - 1))))
            if len(canvas) < position:
                canvas.extend(" " for _ in range(position - len(canvas)))
            elif canvas and not canvas[-1].isspace():
                canvas.append(" ")
            canvas.extend(line.text)
        output.append("".join(canvas).rstrip())
        previous_center = row["center"]
    return "\n".join(output).rstrip() + "\n"
