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


def coord_indices(coord: Coord, rows: list[str]) -> Tuple[int, int]:
    """Return 0-based (row_index, col_index) for a coordinate."""
    row, col = coord
    return rows.index(row), col - 1


def are_adjacent(a: Coord, b: Coord, rows: list[str]) -> bool:
    """True if a and b are 8-neighbors (Chebyshev distance == 1)."""
    if a == b:
        return False
    r0, c0 = coord_indices(a, rows)
    r1, c1 = coord_indices(b, rows)
    return max(abs(r0 - r1), abs(c0 - c1)) == 1


def manhattan_distance(a: Coord, b: Coord, rows: list[str]) -> int:
    """Taxi-geometry (Manhattan) distance between two coordinates."""
    r0, c0 = coord_indices(a, rows)
    r1, c1 = coord_indices(b, rows)
    return abs(r0 - r1) + abs(c0 - c1)


# Fast mode: only steps strictly further than this Manhattan distance.
FAST_MIN_MANHATTAN = 3


def _pick_fast_target(
    rng: random.Random,
    coords: list[Coord],
    last: Coord,
    rows: list[str],
) -> Coord:
    """Pick a far target: Manhattan > 3, weighted toward longer distances."""
    others = [c for c in coords if c != last]
    if not others:
        return last

    far = [c for c in others if manhattan_distance(last, c, rows) > FAST_MIN_MANHATTAN]
    if far:
        weights = [manhattan_distance(last, c, rows) for c in far]
        return rng.choices(far, weights=weights, k=1)[0]

    # Small grids: no cell beyond the threshold — fall back to farthest cells.
    max_d = max(manhattan_distance(last, c, rows) for c in others)
    farthest = [c for c in others if manhattan_distance(last, c, rows) == max_d]
    return rng.choice(farthest)


def random_coordinate_stream(
    height: int,
    width: int,
    *,
    rng: Optional[random.Random] = None,
    exclude: Optional[Coord] = None,
    mode: str = "normal",
) -> Iterator[Coord]:
    """Endless stream of random grid coordinates, never repeating the last one.

    mode="normal":
        Adjacent (too-close) picks are counted; every other adjacent candidate is
        resampled from non-adjacent cells when any exist.

    mode="fast":
        Next step must have Manhattan distance > 3 from the previous coordinate
        when possible, with selection weighted by distance (longer favored).
    """
    if mode not in ("normal", "fast"):
        raise ValueError(f"unknown mode: {mode}")

    rng = rng or random.Random()
    rows = row_labels(height)
    coords = all_coordinates(height, width)
    if not coords:
        raise ValueError("grid has no cells")
    last = exclude
    adjacent_count = 0
    while True:
        if last is None:
            nxt = rng.choice(coords)
        elif mode == "fast":
            nxt = _pick_fast_target(rng, coords, last, rows)
        else:
            choices = [c for c in coords if c != last] if len(coords) > 1 else list(coords)
            nxt = rng.choice(choices)
            if len(choices) > 1 and are_adjacent(last, nxt, rows):
                adjacent_count += 1
                # Every other adjacent choice: resample from non-adjacent cells.
                if adjacent_count % 2 == 0:
                    non_adjacent = [c for c in choices if not are_adjacent(last, c, rows)]
                    if non_adjacent:
                        nxt = rng.choice(non_adjacent)
        last = nxt
        yield nxt
