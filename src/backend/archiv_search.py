from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, asdict
from pathlib import Path

from archiv_utils import normalize_word, write_csv

DEFAULT_NAMES = [
    "Bernbeck", "Pernbeck", "Pernpeck", "Perneck",
    "Bernpeck", "Pernpöck", "Pirnbeck", "Pirnbach",
]

TOKEN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿĀ-ſẞ]{3,}")

# Typische echte bzw. OCR-verformte Endungen der Bernbeck/Pernbeck-Gruppe.
# Wichtig: Bernhärd/Bernhard besitzt keine davon und wird deshalb verworfen.
BECK_ENDINGS = (
    "beck", "peck",
    "bek", "pek",
    "bec", "pec",
    "bck", "pck",
)

@dataclass
class NameHit:
    buchtitel: str
    seite: int
    bilddatei: str
    textdatei: str
    suchname: str
    erkannt: str
    aehnlichkeit: float
    methode: str
    zeile: int
    kontext: str

def ngrams(value: str, size: int = 3) -> set[str]:
    value = normalize_word(value)
    if len(value) < size:
        return {value} if value else set()
    return {value[i:i + size] for i in range(len(value) - size + 1)}

def ngram_score(a: str, b: str) -> float:
    x, y = ngrams(a), ngrams(b)
    if not x or not y:
        return 0.0
    return len(x & y) / len(x | y)

def is_beck_family(target: str) -> bool:
    value = normalize_word(target)
    return value.endswith(("beck", "peck", "bek", "pek"))

def has_beck_ending(candidate: str) -> bool:
    value = normalize_word(candidate)
    if not value:
        return False

    # Die Endung muss am Wortende oder höchstens ein Zeichen davor liegen.
    # So bleiben kleine OCR-Anhängsel tolerierbar.
    for ending in BECK_ENDINGS:
        if value.endswith(ending):
            return True
        if len(value) > len(ending) and value[:-1].endswith(ending):
            return True
    return False

def family_gate(candidate: str, target: str) -> bool:
    """
    Vorfilter für Familiennamen.

    Für Bernbeck/Pernbeck-artige Suchnamen wird nur ein Kandidat zugelassen,
    wenn er eine plausible -beck/-peck-Endung besitzt. Dadurch wird z. B.
    'Bernhärd' nicht mehr als Bernbeck-Treffer bewertet.
    """
    if is_beck_family(target):
        return has_beck_ending(candidate)
    return True

def suffix_score(a: str, b: str) -> float:
    a, b = normalize_word(a), normalize_word(b)
    if not a or not b:
        return 0.0

    for length, score in ((7, 0.99), (6, 0.97), (5, 0.94), (4, 0.88), (3, 0.80)):
        if len(a) >= length and len(b) >= length and a[-length:] == b[-length:]:
            return score

    common = 0
    for ca, cb in zip(reversed(a), reversed(b)):
        if ca != cb:
            break
        common += 1
    return min(0.68 + common * 0.045, 0.90) if common >= 3 else 0.0

def prefix_score(a: str, b: str) -> float:
    a, b = normalize_word(a), normalize_word(b)
    common = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        common += 1
    return min(0.60 + common * 0.035, 0.82) if common >= 4 else 0.0

def score_candidate(token: str, target: str) -> tuple[float, str]:
    if not family_gate(token, target):
        return 0.0, "familienfilter"

    a, b = normalize_word(token), normalize_word(target)
    if not a or not b:
        return 0.0, "keine"

    sequence = difflib.SequenceMatcher(None, a, b).ratio()
    ng = ngram_score(a, b)
    suffix = suffix_score(a, b)
    prefix = prefix_score(a, b)

    scores = {
        "zeichenfolge": sequence,
        "n-gramm": min(ng + 0.18, 1.0) if ng >= 0.45 else ng,
        "suffix": suffix,
        "praefix": prefix,
    }

    # Endung ist bei Familiennamen wichtiger als ein ähnlicher Wortanfang.
    if is_beck_family(target) and has_beck_ending(token):
        scores["familienendung"] = max(suffix, min(sequence + 0.08, 0.99))

    if sequence >= 0.68 and ng >= 0.40 and suffix >= 0.75:
        scores["kombiniert"] = min(
            sequence * 0.45 + ng * 0.20 + suffix * 0.35 + 0.07,
            1.0,
        )

    method = max(scores, key=scores.get)
    return scores[method], method

def find_name_hits(
    text: str,
    names: list[str],
    threshold: float,
    book_title: str,
    page_no: int,
    image_name: str,
    text_name: str,
) -> list[NameHit]:
    candidates: list[NameHit] = []

    for line_no, line in enumerate(text.splitlines(), 1):
        tokens = TOKEN_RE.findall(line)

        # Einzelwörter sind für Familiennamen am zuverlässigsten.
        # Zweiwort-Kandidaten bleiben für getrennte OCR-Wörter erhalten.
        phrases = list(tokens)
        phrases.extend(f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1))

        for phrase in phrases:
            if len(normalize_word(phrase)) < 4:
                continue

            for name in names:
                score, method = score_candidate(phrase, name)
                if score >= threshold:
                    candidates.append(NameHit(
                        buchtitel=book_title,
                        seite=page_no,
                        bilddatei=image_name,
                        textdatei=text_name,
                        suchname=name,
                        erkannt=phrase,
                        aehnlichkeit=round(score, 3),
                        methode=method,
                        zeile=line_no,
                        kontext=line.strip(),
                    ))

    unique: dict[tuple, NameHit] = {}
    for hit in candidates:
        key = (
            hit.buchtitel, hit.seite, hit.suchname,
            hit.erkannt.casefold(), hit.zeile,
        )
        old = unique.get(key)
        if old is None or hit.aehnlichkeit > old.aehnlichkeit:
            unique[key] = hit

    return sorted(
        unique.values(),
        key=lambda h: (-h.aehnlichkeit, h.seite, h.zeile),
    )

def export_hits(path: Path, hits: list[NameHit]) -> None:
    fields = [
        "buchtitel", "seite", "suchname", "erkannt", "aehnlichkeit",
        "methode", "zeile", "kontext", "bilddatei", "textdatei",
    ]
    write_csv(path, fields, (asdict(hit) for hit in hits))
