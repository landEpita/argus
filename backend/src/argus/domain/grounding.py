"""
Is every figure in a model's text backed by the data it was given?

The check is deliberately simple and strict: each number written in the text
must equal, once rounded to the precision it is written with, some number in
the evidence. Small counts (0-10) and years are allowed, as they are too
common in prose to be claims.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_NUMBER = re.compile(
    r"(?<![\w.])[-+\u2212]?(?:\d{1,3}(?:[ \u202f\u00a0,]\d{3})+(?![\d])|\d+)(?:\.\d+)?"
)


def numbers_in(text: str) -> list[str]:
    """Numbers as written, normalised: thousands separators removed, true minus → '-'."""
    out = []
    for match in _NUMBER.finditer(text):
        raw = match.group().replace("\u2212", "-").replace("+", "")
        raw = re.sub(r"[ \u202f\u00a0,]", "", raw)
        if raw.strip("-"):
            out.append(raw)
    return out


def _decimals(written: str) -> int:
    return len(written.split(".", 1)[1]) if "." in written else 0


def _is_prose(value: float, written: str) -> bool:
    if "." in written:
        return False
    return 0 <= abs(value) <= 10 or 1900 <= value <= 2100


def ungrounded(text: str, evidence: Iterable[str]) -> list[str]:
    """Numbers in `text` that no number in `evidence` supports (signs are ignored)."""
    known: list[float] = []
    for chunk in evidence:
        known.extend(abs(float(n)) for n in numbers_in(chunk))
    missing = []
    for written in numbers_in(text):
        value = abs(float(written))
        if _is_prose(value, written):
            continue
        places = _decimals(written)
        tolerance = 0.5 * 10**-places + 1e-9
        if not any(abs(k - value) <= tolerance for k in known):
            missing.append(written)
    return missing
