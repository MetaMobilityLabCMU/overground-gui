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


def rectangle_cells(a: Coord, b: Coord, rows: list[str]) -> list[Coord]:
    """Axis-aligned rectangle (inclusive) spanned by a and b, including edges.

    Degenerates to a line segment when a and b share a row or column.
    """
    r0, c0 = coord_indices(a, rows)
    r1, c1 = coord_indices(b, rows)
    r_lo, r_hi = min(r0, r1), max(r0, r1)
    c_lo, c_hi = min(c0, c1), max(c0, c1)
    return [
        (rows[r], c + 1)
        for r in range(r_lo, r_hi + 1)
        for c in range(c_lo, c_hi + 1)
    ]


def share_row_or_column(a: Coord, b: Coord, rows: list[str]) -> bool:
    """True when a and b are axis-aligned (same row or same column)."""
    r0, c0 = coord_indices(a, rows)
    r1, c1 = coord_indices(b, rows)
    return r0 == r1 or c0 == c1


def cells_between_on_line(current: Coord, target: Coord, rows: list[str]) -> list[Coord]:
    """Strictly in-between cells when current and target share a row or column."""
    r0, c0 = coord_indices(current, rows)
    r1, c1 = coord_indices(target, rows)
    if r0 == r1 and c0 != c1:
        c_lo, c_hi = sorted((c0, c1))
        return [(rows[r0], c + 1) for c in range(c_lo + 1, c_hi)]
    if c0 == c1 and r0 != r1:
        r_lo, r_hi = sorted((r0, r1))
        return [(rows[r], c0 + 1) for r in range(r_lo + 1, r_hi)]
    return []


def waypoint_candidates(current: Coord, target: Coord, rows: list[str]) -> list[Coord]:
    """Valid waypoint cells between current and target.

    A waypoint is never the current or target cell.

    - Same row/column: not a 2D rectangle — use cells strictly between them.
    - Otherwise: cells inside or on the edges of the axis-aligned rectangle,
      excluding the current and target endpoints.
    """
    if current == target:
        return []
    if share_row_or_column(current, target, rows):
        # In-between cells only; endpoints are excluded by construction.
        return cells_between_on_line(current, target, rows)
    return [c for c in rectangle_cells(current, target, rows) if c not in (current, target)]


def can_place_waypoint(current: Coord, target: Coord, rows: list[str]) -> bool:
    """True when there is a distinct waypoint cell (not current/target)."""
    return bool(waypoint_candidates(current, target, rows))


# Destination must be strictly further than this Manhattan distance.
# slow/medium share the normal threshold; fast is stricter.
NORMAL_MIN_MANHATTAN = 2  # require distance >= 3
FAST_MIN_MANHATTAN = 3  # require distance >= 4


def is_fast_distance(current: Coord, other: Coord, rows: list[str]) -> bool:
    """True when Manhattan distance is strictly greater than the fast-mode minimum."""
    return manhattan_distance(current, other, rows) > FAST_MIN_MANHATTAN


def sampling_family(mode: str) -> str:
    """Map UI mode labels to sampling families: 'normal' or 'fast'."""
    if mode == "fast":
        return "fast"
    # slow, medium, and legacy "normal" share the same sampler.
    return "normal"


def min_destination_distance(mode: str) -> int:
    """Exclusive lower bound on Manhattan distance for destinations."""
    return FAST_MIN_MANHATTAN if sampling_family(mode) == "fast" else NORMAL_MIN_MANHATTAN


def is_valid_target(
    current: Coord,
    target: Coord,
    rows: list[str],
    *,
    mode: str = "normal",
) -> bool:
    """Whether target is allowed from current under the sampling mode."""
    if current == target:
        return False
    if not can_place_waypoint(current, target, rows):
        return False
    return manhattan_distance(current, target, rows) > min_destination_distance(mode)


def sample_waypoint(
    current: Coord,
    target: Coord,
    rows: list[str],
    *,
    rng: Optional[random.Random] = None,
    mode: str = "normal",
) -> Optional[Coord]:
    """Sample a waypoint for the path from current to target.

    Same row/column → pick a cell between them on that line.
    Otherwise → pick a cell within/along the rectangle they span.

    Never returns current or target.

    Waypoints may be close; prefer cells that still leave room for a later
    waypoint before the target when any exist. Mode only affects optional
    preference for longer waypoint hops in fast family modes.
    """
    rng = rng or random.Random()
    family = sampling_family(mode)
    candidates = [c for c in waypoint_candidates(current, target, rows) if c not in (current, target)]
    if not candidates:
        return None

    if family == "fast":
        far = [c for c in candidates if is_fast_distance(current, c, rows)]
        if far:
            weights = [manhattan_distance(current, c, rows) for c in far]
            return rng.choices(far, weights=weights, k=1)[0]

    far_from_current = [c for c in candidates if manhattan_distance(current, c, rows) >= 2]
    pool = far_from_current if far_from_current else candidates

    # Prefer cells that still leave room for a later waypoint before the target.
    spaced = [c for c in pool if can_place_waypoint(c, target, rows)]
    if spaced:
        pool = spaced
    return rng.choice(pool)


def _targets_with_waypoint(
    coords: list[Coord],
    last: Coord,
    rows: list[str],
    *,
    mode: str = "normal",
) -> list[Coord]:
    """Candidate targets that are not `last` and satisfy mode constraints."""
    return [c for c in coords if is_valid_target(last, c, rows, mode=mode)]


def _pick_fast_target(
    rng: random.Random,
    coords: list[Coord],
    last: Coord,
    rows: list[str],
) -> Coord:
    """Pick a far target: Manhattan > 3 when possible, weighted toward longer distances."""
    pool = _targets_with_waypoint(coords, last, rows, mode="fast")
    if pool:
        weights = [manhattan_distance(last, c, rows) for c in pool]
        return rng.choices(pool, weights=weights, k=1)[0]

    # Small grids: no cell meets Manhattan > 3 with a waypoint — use farthest viable.
    soft = _targets_with_waypoint(coords, last, rows, mode="normal")
    if not soft:
        others = [c for c in coords if c != last]
        return rng.choice(others) if others else last
    max_d = max(manhattan_distance(last, c, rows) for c in soft)
    farthest = [c for c in soft if manhattan_distance(last, c, rows) == max_d]
    return rng.choice(farthest)


def _pick_normal_target(
    rng: random.Random,
    coords: list[Coord],
    last: Coord,
    rows: list[str],
) -> Coord:
    """Pick a slow/medium target: distance > 2, weighted toward longer hops."""
    pool = _targets_with_waypoint(coords, last, rows, mode="normal")
    if pool:
        weights = [manhattan_distance(last, c, rows) for c in pool]
        return rng.choices(pool, weights=weights, k=1)[0]

    # Tiny grids: fall back to farthest waypoint-capable cell.
    soft = [c for c in coords if c != last and can_place_waypoint(last, c, rows)]
    if not soft:
        others = [c for c in coords if c != last]
        return rng.choice(others) if others else last
    max_d = max(manhattan_distance(last, c, rows) for c in soft)
    farthest = [c for c in soft if manhattan_distance(last, c, rows) == max_d]
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

    mode may be "slow", "medium", "normal", or "fast".
    slow/medium/normal: destination Manhattan > 2, weighted toward longer distances.
    fast: destination Manhattan > 3, weighted toward longer distances.
    """
    family = sampling_family(mode)

    rng = rng or random.Random()
    rows = row_labels(height)
    coords = all_coordinates(height, width)
    if not coords:
        raise ValueError("grid has no cells")
    last = exclude
    while True:
        if last is None:
            nxt = rng.choice(coords)
        elif family == "fast":
            nxt = _pick_fast_target(rng, coords, last, rows)
        else:
            nxt = _pick_normal_target(rng, coords, last, rows)
        last = nxt
        yield nxt
