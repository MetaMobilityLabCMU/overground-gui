#!/usr/bin/env python3
"""Overground navigation cue GUI.

Grid rows are letters (H), columns are numbers (W). Space confirms arrival
at the target (via the shown waypoint) and advances to the next leg.
"""

from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Iterator, Optional, Tuple

from overground_gui.coordinates import (
    Coord,
    can_place_waypoint,
    format_coord,
    is_valid_target,
    random_coordinate_stream,
    rectangle_cells,
    row_labels,
    sample_waypoint,
    speakable_coord,
)
from overground_gui.speaker import Speaker

# Shared highlight hue (teal); alpha differs for current vs target.
COLOR_HIGHLIGHT = (46, 160, 154)  # RGB
COLOR_WAYPOINT = (214, 137, 16)  # amber
COLOR_RECT = (46, 160, 154)
COLOR_GRID_LINE = "#2c3e50"
COLOR_LABEL = "#1a252f"
COLOR_BG = "#e8eef2"
COLOR_CELL = "#f7fafb"
COLOR_ARROW = "#1b4f72"
COLOR_ARROW_WAYPOINT = "#b9770e"


def rgba_hex(rgb: Tuple[int, int, int], alpha: float, bg: Tuple[int, int, int] = (247, 250, 251)) -> str:
    """Blend rgb over bg with alpha in [0, 1] and return #rrggbb."""
    a = max(0.0, min(1.0, alpha))
    r = int(rgb[0] * a + bg[0] * (1 - a))
    g = int(rgb[1] * a + bg[1] * (1 - a))
    b = int(rgb[2] * a + bg[2] * (1 - a))
    return f"#{r:02x}{g:02x}{b:02x}"


class OvergroundGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Overground Coordinate Cue")
        self.root.minsize(780, 560)
        self.root.configure(bg=COLOR_BG)

        self.height = tk.IntVar(value=3)
        self.width = tk.IntVar(value=6)
        self.speaker_mode = tk.BooleanVar(value=False)
        # Trial pace label: slow/medium share sampling; fast is stricter.
        self.pace_mode = tk.StringVar(value="medium")

        self.rows: list[str] = []
        self.cols: list[int] = []
        self.current: Optional[Coord] = None
        self.waypoint: Optional[Coord] = None
        self.target: Optional[Coord] = None
        self._stream: Optional[Iterator[Coord]] = None
        self._session_active = False
        self._rng = random.Random()
        # Trial log rows: dicts with step/role/coordinate.
        self._trial_log: list[dict[str, object]] = []
        self._trial_dirty = False
        self._leg_index = 0

        self.speaker = Speaker()
        self._cell_rects: dict[Coord, int] = {}
        self._arrow_ids: list[int] = []

        self._build_ui()
        self.root.bind("<space>", self._on_space)
        self.root.bind("<Configure>", self._on_resize)
        self._apply_grid(start_session=True)

    def _build_ui(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=COLOR_BG)
        style.configure("TLabel", background=COLOR_BG, foreground=COLOR_LABEL)
        style.configure("TCheckbutton", background=COLOR_BG)
        style.configure("TRadiobutton", background=COLOR_BG)
        style.configure("Header.TLabel", font=("Helvetica", 12, "bold"))
        style.configure("Big.TLabel", font=("Helvetica", 28, "bold"), foreground="#0d3b4c")
        style.configure("Waypoint.TLabel", font=("Helvetica", 28, "bold"), foreground="#9a5b00")
        style.configure("Hint.TLabel", font=("Helvetica", 10), foreground="#5a6a75")

        top = ttk.Frame(self.root, padding=(12, 10))
        top.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(top, text="Grid size", style="Header.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))

        ttk.Label(top, text="H (rows / letters)").grid(row=0, column=1, sticky="e", padx=(8, 4))
        h_spin = ttk.Spinbox(top, from_=1, to=52, textvariable=self.height, width=5)
        h_spin.grid(row=0, column=2, sticky="w")

        ttk.Label(top, text="W (cols / numbers)").grid(row=0, column=3, sticky="e", padx=(12, 4))
        w_spin = ttk.Spinbox(top, from_=1, to=52, textvariable=self.width, width=5)
        w_spin.grid(row=0, column=4, sticky="w")

        apply_btn = ttk.Button(top, text="Apply grid", command=self._on_apply)
        apply_btn.grid(row=0, column=5, padx=(16, 0))

        save_btn = ttk.Button(top, text="Save", command=self._on_save)
        save_btn.grid(row=0, column=6, padx=(8, 0))

        reset_btn = ttk.Button(top, text="Reset", command=self._on_reset)
        reset_btn.grid(row=0, column=7, padx=(8, 0))

        ttk.Label(top, text="Mode").grid(row=0, column=8, sticky="e", padx=(16, 4))
        mode_frame = ttk.Frame(top)
        mode_frame.grid(row=0, column=9, sticky="w")
        mode_radios = []
        for i, (value, label) in enumerate(
            (("slow", "Slow"), ("medium", "Medium"), ("fast", "Fast"))
        ):
            rb = ttk.Radiobutton(
                mode_frame,
                text=label,
                value=value,
                variable=self.pace_mode,
                command=self._on_mode_change,
            )
            rb.pack(side=tk.LEFT, padx=(0, 8))
            mode_radios.append(rb)

        speaker_text = "Speaker mode"
        if not self.speaker.available:
            speaker_text += " (TTS unavailable)"
        speaker_cb = ttk.Checkbutton(
            top,
            text=speaker_text,
            variable=self.speaker_mode,
            command=self._on_speaker_toggle,
            state=tk.NORMAL if self.speaker.available else tk.DISABLED,
        )
        speaker_cb.grid(row=0, column=10, padx=(12, 0))

        status = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        status.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(status, text="Target", style="Header.TLabel").pack(side=tk.LEFT)
        self.target_label = ttk.Label(status, text="—", style="Big.TLabel")
        self.target_label.pack(side=tk.LEFT, padx=(12, 24))

        ttk.Label(status, text="Waypoint", style="Header.TLabel").pack(side=tk.LEFT)
        self.waypoint_label = ttk.Label(status, text="—", style="Waypoint.TLabel")
        self.waypoint_label.pack(side=tk.LEFT, padx=(12, 24))

        ttk.Label(status, text="Current", style="Header.TLabel").pack(side=tk.LEFT)
        self.current_label = ttk.Label(status, text="—", style="Big.TLabel")
        self.current_label.pack(side=tk.LEFT, padx=(12, 24))

        self.steps_label = ttk.Label(status, text="Steps: 0", style="Hint.TLabel")
        self.steps_label.pack(side=tk.LEFT, padx=(0, 16))

        self.hint_label = ttk.Label(
            status,
            text="Space = confirm arrival at target (via waypoint)",
            style="Hint.TLabel",
        )
        self.hint_label.pack(side=tk.RIGHT)

        legend = ttk.Frame(self.root, padding=(12, 0, 12, 6))
        legend.pack(side=tk.TOP, fill=tk.X)
        self._draw_legend_swatches(legend)

        canvas_frame = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        canvas_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_frame, bg=COLOR_BG, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Keep focus for spacebar even after clicking widgets
        focus_widgets = [
            self.root,
            self.canvas,
            h_spin,
            w_spin,
            apply_btn,
            save_btn,
            reset_btn,
            speaker_cb,
            *mode_radios,
        ]
        for w in focus_widgets:
            w.bind("<Button-1>", lambda e: self.root.focus_set(), add="+")

    def _draw_legend_swatches(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Legend:", style="Hint.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        for label, rgb, alpha in (
            ("Current", COLOR_HIGHLIGHT, 0.85),
            ("Waypoint", COLOR_WAYPOINT, 0.70),
            ("Target", COLOR_HIGHLIGHT, 0.40),
        ):
            sw = tk.Canvas(parent, width=18, height=18, highlightthickness=0, bg=COLOR_BG)
            sw.pack(side=tk.LEFT, padx=(0, 4))
            sw.create_rectangle(1, 1, 17, 17, fill=rgba_hex(rgb, alpha), outline=COLOR_GRID_LINE)
            ttk.Label(parent, text=label, style="Hint.TLabel").pack(side=tk.LEFT, padx=(0, 14))
        ttk.Label(parent, text="Path: current → waypoint → target", style="Hint.TLabel").pack(side=tk.LEFT)

    def _on_apply(self) -> None:
        if self._trial_dirty:
            if not messagebox.askyesno(
                "Apply grid",
                "Applying a new grid starts a new trial and discards unsaved coordinates.\n\nContinue?",
            ):
                self.root.focus_set()
                return
        self._apply_grid(start_session=True)

    def _on_reset(self) -> None:
        detail = (
            "Unsaved trial coordinates will be discarded.\n\n"
            if self._trial_dirty
            else ""
        )
        if not messagebox.askyesno(
            "Reset trial",
            f"Reset for the next trial?\n\n{detail}"
            "This clears the current trial sequence and picks new start/target coordinates.",
        ):
            self.root.focus_set()
            return
        self._apply_grid(start_session=True)

    def _on_save(self) -> None:
        if not self._trial_log:
            messagebox.showinfo("Save trial", "Nothing to save yet.")
            self.root.focus_set()
            return

        default_name = datetime.now().strftime("trial_%Y%m%d_%H%M%S.csv")
        path = filedialog.asksaveasfilename(
            title="Save trial contents",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            self.root.focus_set()
            return

        try:
            self._write_trial_csv(Path(path))
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not save trial:\n{exc}")
            self.root.focus_set()
            return

        self._trial_dirty = False
        messagebox.showinfo("Save trial", f"Saved {len(self._trial_log)} rows to:\n{path}")
        self.root.focus_set()

    def _write_trial_csv(self, path: Path) -> None:
        h = len(self.rows)
        w = len(self.cols)
        saved_at = datetime.now(timezone.utc).isoformat()
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["# overground-gui trial"])
            writer.writerow(["# grid_height", h])
            writer.writerow(["# grid_width", w])
            writer.writerow(["# saved_at_utc", saved_at])
            writer.writerow(["step", "role", "coordinate", "mode"])
            for row in self._trial_log:
                writer.writerow([row["step"], row["role"], row["coordinate"], row["mode"]])

    def _log_row(self, step: int, role: str, coordinate: str, *, mode: Optional[str] = None) -> None:
        self._trial_log.append(
            {
                "step": step,
                "role": role,
                "coordinate": coordinate,
                "mode": mode if mode is not None else self._pace_mode(),
            }
        )

    def _pace_mode(self) -> str:
        mode = self.pace_mode.get()
        return mode if mode in ("slow", "medium", "fast") else "medium"

    def _rebuild_stream(self, *, exclude: Optional[Coord] = None) -> None:
        h = len(self.rows)
        w = len(self.cols)
        if h < 1 or w < 1:
            return
        self._stream = random_coordinate_stream(h, w, mode=self._pace_mode(), exclude=exclude)

    def _target_ok(self, candidate: Coord) -> bool:
        assert self.current is not None
        return is_valid_target(
            self.current, candidate, self.rows, mode=self._pace_mode()
        )

    def _next_target_from_stream(self) -> Coord:
        """Draw a target that satisfies the active mode constraints."""
        assert self._stream is not None and self.current is not None
        for _ in range(64):
            candidate = next(self._stream)
            if self._target_ok(candidate):
                return candidate
        return candidate

    def _set_waypoint_for_leg(self) -> None:
        """Sample one waypoint for the current→target leg (guidance only)."""
        assert self.current is not None and self.target is not None
        if can_place_waypoint(self.current, self.target, self.rows):
            self.waypoint = sample_waypoint(
                self.current,
                self.target,
                self.rows,
                rng=self._rng,
                mode=self._pace_mode(),
            )
        else:
            self.waypoint = None

    def _begin_leg(self, target: Optional[Coord] = None, *, log: bool) -> None:
        """Choose a destination and waypoint. Current stays until Space reaches target."""
        assert self.current is not None
        chosen_target: Optional[Coord] = None
        for _ in range(64):
            if target is not None and self._target_ok(target):
                candidate = target
            else:
                candidate = self._next_target_from_stream()
            chosen_target = candidate
            if self._target_ok(candidate):
                break
            target = None

        self.target = chosen_target
        self._set_waypoint_for_leg()
        # If no waypoint fit (should be rare), keep resampling for a valid leg.
        if self.waypoint is None:
            for _ in range(64):
                self.target = self._next_target_from_stream()
                self._set_waypoint_for_leg()
                if self.waypoint is not None:
                    break

        if log:
            self._leg_index += 1
            mode = self._pace_mode()
            if self.waypoint is not None:
                self._log_row(
                    self._leg_index,
                    "waypoint",
                    format_coord(self.waypoint),
                    mode=mode,
                )
            self._log_row(
                self._leg_index,
                "target",
                format_coord(self.target),
                mode=mode,
            )

    def _apply_grid(self, start_session: bool) -> None:
        try:
            h = int(self.height.get())
            w = int(self.width.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Invalid size", "H and W must be integers.")
            return
        if h < 1 or w < 1:
            messagebox.showerror("Invalid size", "H and W must be at least 1.")
            return
        if h > 52 or w > 52:
            messagebox.showerror("Invalid size", "H and W must be at most 52.")
            return

        self.rows = row_labels(h)
        self.cols = list(range(1, w + 1))
        self._rebuild_stream()

        if start_session:
            self.current = next(self._stream)
            self._trial_log = []
            self._log_row(0, "start", format_coord(self.current))
            self._leg_index = 0
            self._begin_leg(log=True)
            self._trial_dirty = False
            self._session_active = True
            self._announce_target()

        self._update_labels()
        self._redraw()
        self.root.focus_set()

    def _on_mode_change(self) -> None:
        # Rebuild sampler for subsequent legs; keep the in-progress leg as-is.
        exclude = self.target if self.target is not None else self.current
        self._rebuild_stream(exclude=exclude)
        self.root.focus_set()

    def _on_speaker_toggle(self) -> None:
        if self.speaker_mode.get() and self.target is not None:
            self._announce_target()
        self.root.focus_set()

    def _announce_target(self) -> None:
        if not self.speaker_mode.get() or self.target is None:
            return
        self.speaker.speak(speakable_coord(self.target))

    def _on_space(self, _event: Optional[tk.Event] = None) -> str:
        # Ignore space while typing in spinboxes
        focus = self.root.focus_get()
        if isinstance(focus, (ttk.Spinbox, tk.Spinbox, ttk.Entry, tk.Entry)):
            return ""
        if not self._session_active or self._stream is None or self.target is None:
            return "break"

        # Current always advances to the final destination, never to the waypoint.
        self.current = self.target
        self._begin_leg(log=True)
        self._trial_dirty = True

        self._update_labels()
        self._redraw()
        self._announce_target()
        return "break"

    def _update_labels(self) -> None:
        self.target_label.configure(text=format_coord(self.target) if self.target else "—")
        self.waypoint_label.configure(
            text=format_coord(self.waypoint) if self.waypoint is not None else "—"
        )
        self.current_label.configure(text=format_coord(self.current) if self.current else "—")
        self.steps_label.configure(text=f"Steps: {self._leg_index}")

    def _on_resize(self, _event: Optional[tk.Event] = None) -> None:
        if getattr(self, "_resize_job", None):
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(80, self._redraw)

    def _cell_center(self, coord: Coord, origin_x: float, origin_y: float, cell_w: float, cell_h: float) -> Tuple[float, float]:
        row, col = coord
        r = self.rows.index(row)
        c = col - 1
        return origin_x + (c + 0.5) * cell_w, origin_y + (r + 0.5) * cell_h

    def _redraw(self) -> None:
        if not hasattr(self, "canvas"):
            return
        c = self.canvas
        c.delete("all")
        self._cell_rects.clear()
        self._arrow_ids.clear()

        if not self.rows or not self.cols:
            return

        cw = c.winfo_width()
        ch = c.winfo_height()
        if cw < 40 or ch < 40:
            return

        label_left = 36
        label_top = 28
        pad_right = 16
        pad_bottom = 16

        grid_w = max(1, cw - label_left - pad_right)
        grid_h = max(1, ch - label_top - pad_bottom)
        n_rows = len(self.rows)
        n_cols = len(self.cols)
        cell_w = grid_w / n_cols
        cell_h = grid_h / n_rows
        ox, oy = label_left, label_top

        rect_set: set[Coord] = set()
        if self.current is not None and self.target is not None and self.waypoint is not None:
            rect_set = set(rectangle_cells(self.current, self.target, self.rows))

        # Column headers (numbers)
        for i, col in enumerate(self.cols):
            x = ox + (i + 0.5) * cell_w
            c.create_text(x, label_top / 2, text=str(col), fill=COLOR_LABEL, font=("Helvetica", 11, "bold"))

        # Row headers (letters) + cells
        for r, row in enumerate(self.rows):
            y = oy + (r + 0.5) * cell_h
            c.create_text(label_left / 2, y, text=row, fill=COLOR_LABEL, font=("Helvetica", 11, "bold"))
            for i, col in enumerate(self.cols):
                x0 = ox + i * cell_w
                y0 = oy + r * cell_h
                x1 = x0 + cell_w
                y1 = y0 + cell_h
                coord: Coord = (row, col)
                fill = COLOR_CELL
                if self.current is not None and coord == self.current:
                    fill = rgba_hex(COLOR_HIGHLIGHT, 0.85)
                elif self.waypoint is not None and coord == self.waypoint:
                    fill = rgba_hex(COLOR_WAYPOINT, 0.70)
                elif self.target is not None and coord == self.target:
                    fill = rgba_hex(COLOR_HIGHLIGHT, 0.40)
                elif coord in rect_set:
                    fill = rgba_hex(COLOR_RECT, 0.12)
                rect = c.create_rectangle(x0, y0, x1, y1, fill=fill, outline=COLOR_GRID_LINE, width=1)
                self._cell_rects[coord] = rect
                # Subtle cell label
                c.create_text(
                    (x0 + x1) / 2,
                    (y0 + y1) / 2,
                    text=format_coord(coord),
                    fill="#7a8a94",
                    font=("Helvetica", max(8, min(12, int(min(cell_w, cell_h) / 4)))),
                )

        # Path arrows: current → waypoint → target, or current → target on final hop.
        if self.current is not None and self.target is not None:
            if self.waypoint is not None and self.current != self.waypoint:
                self._draw_arrow(
                    *self._cell_center(self.current, ox, oy, cell_w, cell_h),
                    *self._cell_center(self.waypoint, ox, oy, cell_w, cell_h),
                    color=COLOR_ARROW_WAYPOINT,
                )
                if self.waypoint != self.target:
                    self._draw_arrow(
                        *self._cell_center(self.waypoint, ox, oy, cell_w, cell_h),
                        *self._cell_center(self.target, ox, oy, cell_w, cell_h),
                        color=COLOR_ARROW,
                    )
            elif self.current != self.target:
                self._draw_arrow(
                    *self._cell_center(self.current, ox, oy, cell_w, cell_h),
                    *self._cell_center(self.target, ox, oy, cell_w, cell_h),
                    color=COLOR_ARROW,
                )

    def _draw_arrow(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        *,
        color: str = COLOR_ARROW,
    ) -> None:
        c = self.canvas
        dx, dy = x1 - x0, y1 - y0
        dist = math.hypot(dx, dy)
        if dist < 1:
            return
        # Shorten so arrowheads sit inside cells, not on borders
        inset = min(28.0, dist * 0.22)
        ux, uy = dx / dist, dy / dist
        sx, sy = x0 + ux * inset, y0 + uy * inset
        ex, ey = x1 - ux * inset, y1 - uy * inset

        line = c.create_line(
            sx,
            sy,
            ex,
            ey,
            fill=color,
            width=3,
            arrow=tk.LAST,
            arrowshape=(14, 18, 6),
            capstyle=tk.ROUND,
        )
        # Soft shadow under arrow for contrast on highlighted cells
        shadow = c.create_line(
            sx + 1,
            sy + 1,
            ex + 1,
            ey + 1,
            fill="#00000033" if self._supports_alpha_color() else "#95a5a6",
            width=3,
            arrow=tk.LAST,
            arrowshape=(14, 18, 6),
        )
        c.tag_lower(shadow, line)
        self._arrow_ids.extend([shadow, line])

    @staticmethod
    def _supports_alpha_color() -> bool:
        # Tk on X11 typically does not accept #rrggbbaa; keep False for portability.
        return False


def main() -> None:
    root = tk.Tk()
    OvergroundGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
