"""Grid coordinate helpers and random target stream."""

from __future__ import annotations

import random
import string
from typing import Iterator, Optional, Tuple

Coord = Tuple[str, int]  # (row letter, column number), e.g. ("A", 4)


def row_labels(height: int) -> list[str]:
    """Return row labels for height H (A, B, ... then AA, AB, ...)."""
    if height < 1:
        raise ValueError("height must be >= 1")
    labels: list[str] = []
    alphabet = string.ascii_uppercase
    n = 0
    while len(labels) < height:
        if n < 26:
            labels.append(alphabet[n])
        else:
            # AA, AB, ... after Z
            first = (n // 26) - 1
            second = n % 26
            labels.append(alphabet[first] + alphabet[second])
        n += 1
    return labels


def all_coordinates(height: int, width: int) -> list[Coord]:
    if width < 1:
        raise ValueError("width must be >= 1")
    return [(row, col) for row in row_labels(height) for col in range(1, width + 1)]


def format_coord(coord: Coord) -> str:
    row, col = coord
    return f"{row}{col}"


def parse_coord(text: str) -> Coord:
    text = text.strip().upper()
    i = 0
    while i < len(text) and text[i].isalpha():
        i += 1
    if i == 0 or i == len(text):
        raise ValueError(f"Invalid coordinate: {text}")
    row, col_s = text[:i], text[i:]
    if not col_s.isdigit():
        raise ValueError(f"Invalid coordinate: {text}")
    return row, int(col_s)


def speakable_coord(coord: Coord) -> str:
    """Phrase suited for TTS, e.g. 'A 4'."""
    row, col = coord
    letters = " ".join(list(row))
    return f"{letters} {col}"


def random_coordinate_stream(
    height: int,
    width: int,
    *,
    rng: Optional[random.Random] = None,
    exclude: Optional[Coord] = None,
) -> Iterator[Coord]:
    """Endless stream of random grid coordinates, never repeating the last one."""
    rng = rng or random.Random()
    coords = all_coordinates(height, width)
    if not coords:
        raise ValueError("grid has no cells")
    last = exclude
    while True:
        choices = [c for c in coords if c != last] if len(coords) > 1 else coords
        nxt = rng.choice(choices)
        last = nxt
        yield nxt
