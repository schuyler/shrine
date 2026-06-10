#!/usr/bin/env python3
"""Qt desktop front-end for the manual OSC sensor simulator.

This is a second view over the same ``ManualState`` that drives the curses tool
in ``manual.py`` — all OSC, smoothing, jitter, mute and pair-symmetry logic is
shared. Each node is a column with its presence faders (``stdev``, ``carrier``)
and a touch/release button; the six GSR couplings sit in a row below, one fader
per node pair (so setting a coupling moves both nodes' reports together).

Install the GUI dependency, then run:

    uv sync --group gui
    uv run --group gui python osc-sim/manual_gui.py --host localhost

Flags mirror manual.py: --host/--port, --targets, --rate, --no-smoothing,
--jitter.
"""

import argparse
import sys
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from manual import (
    FINE_STEP,
    NODE_PAIRS,
    NUM_NODES,
    NUM_PRESENCE,
    PRESENCE_LABELS,
    STEP,
    ManualState,
    build_clients,
)

SLIDER_RANGE = 100  # QSlider is integer; map 0..100 <-> 0.0..1.0


class ChannelStrip(QFrame):
    """A single fader for one channel key: slider + live value + mute button.

    The slider position is the *target*; the label shows the *current* (eased,
    optionally jittered) value actually being sent.
    """

    def __init__(self, state: ManualState, ch, title: str):
        super().__init__()
        self.state = state
        self.ch = ch
        self._selected = False
        self.setObjectName("ChannelStrip")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self.value_label = QLabel("0.00")
        self.value_label.setAlignment(Qt.AlignHCenter)

        self.slider = QSlider(Qt.Vertical)
        self.slider.setRange(0, SLIDER_RANGE)
        self.slider.setValue(0)
        self.slider.setFocusPolicy(Qt.NoFocus)
        self.slider.valueChanged.connect(self._on_slider)

        self.mute_btn = QPushButton("M")
        self.mute_btn.setCheckable(True)
        self.mute_btn.setFixedWidth(34)
        self.mute_btn.setFocusPolicy(Qt.NoFocus)
        self.mute_btn.clicked.connect(self._on_mute)

        name_label = QLabel(title)
        name_label.setAlignment(Qt.AlignHCenter)

        layout.addWidget(self.value_label)
        layout.addWidget(self.slider, 1, Qt.AlignHCenter)
        layout.addWidget(self.mute_btn, 0, Qt.AlignHCenter)
        layout.addWidget(name_label)

    def _on_slider(self, value: int):
        self.state.set(self.ch, value / SLIDER_RANGE)

    def _on_mute(self):
        if self.mute_btn.isChecked() != self.state.muted(self.ch):
            self.state.toggle_mute(self.ch)

    def set_selected(self, selected: bool):
        if selected == self._selected:
            return
        self._selected = selected
        self.setStyleSheet(
            "QFrame#ChannelStrip { background-color: #2d4a6b; border-radius: 3px; }"
            if selected
            else ""
        )

    def refresh(self, dimmed: bool):
        muted = self.state.muted(self.ch)

        want = round(self.state.target(self.ch) * SLIDER_RANGE)
        if self.slider.value() != want:
            self.slider.blockSignals(True)
            self.slider.setValue(want)
            self.slider.blockSignals(False)

        if self.mute_btn.isChecked() != muted:
            self.mute_btn.blockSignals(True)
            self.mute_btn.setChecked(muted)
            self.mute_btn.blockSignals(False)

        if muted:
            self.value_label.setText("mute")
        else:
            self.value_label.setText(f"{self.state.current(self.ch):.2f}")
        # Grey the label when the value is suppressed (muted or node released).
        self.value_label.setStyleSheet("color: gray;" if dimmed else "")


class NodeColumn(QWidget):
    """One node's presence faders plus a touch/release button."""

    def __init__(self, state: ManualState, node: int):
        super().__init__()
        self.state = state
        self.node = node

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        header = QLabel(f"node {node}")
        header.setAlignment(Qt.AlignHCenter)
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        self.touch_btn = QPushButton("Release")
        self.touch_btn.setFocusPolicy(Qt.NoFocus)
        self.touch_btn.clicked.connect(lambda: self.state.toggle_touch(self.node))
        layout.addWidget(self.touch_btn)

        strips_row = QHBoxLayout()
        strips_row.setSpacing(2)
        self.strips = [
            ChannelStrip(state, ("pres", node, i), PRESENCE_LABELS[i])
            for i in range(NUM_PRESENCE)
        ]
        for strip in self.strips:
            strips_row.addWidget(strip)
        layout.addLayout(strips_row, 1)

    def refresh(self):
        released = self.state.node_released(self.node)
        self.touch_btn.setText("Touch" if released else "Release")
        for strip in self.strips:
            strip.refresh(dimmed=released or strip.state.muted(strip.ch))


class MixerWindow(QMainWindow):
    def __init__(self, clients: list, rate: float, smoothing: bool, jitter: bool):
        super().__init__()
        self.setWindowTitle("Shrine Manual Sensor Simulator")
        self.state = ManualState(smoothing=smoothing, jitter=jitter)
        self.clients = clients
        self.start = time.monotonic()
        self.dt = 1.0 / rate
        self.channels = self.state.channels()
        self.sel = 0

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # --- Presence: node columns ---
        cols = QHBoxLayout()
        self.columns = [NodeColumn(self.state, n) for n in range(NUM_NODES)]
        for i, col in enumerate(self.columns):
            cols.addWidget(col)
            if i < NUM_NODES - 1:
                divider = QFrame()
                divider.setFrameShape(QFrame.VLine)
                cols.addWidget(divider)
        root.addLayout(cols, 1)

        # --- Couplings: one fader per node pair ---
        pair_box = QVBoxLayout()
        pair_box.addWidget(QLabel("GSR couplings (node pairs)"))
        pair_row = QHBoxLayout()
        self.pair_strips = []
        for p, (a, b) in enumerate(NODE_PAIRS):
            strip = ChannelStrip(self.state, ("pair", p), f"{a}–{b}")
            self.pair_strips.append(strip)
            pair_row.addWidget(strip)
        pair_row.addStretch(1)
        pair_box.addLayout(pair_row)
        root.addLayout(pair_box, 1)

        # Map each channel key to its strip widget for selection highlighting.
        self._strip_for = {}
        for col in self.columns:
            for strip in col.strips:
                self._strip_for[strip.ch] = strip
        for strip in self.pair_strips:
            self._strip_for[strip.ch] = strip

        # --- Global control bar ---
        controls = QHBoxLayout()
        targets = ", ".join(f"{c._address}:{c._port}" for c in clients)
        controls.addWidget(QLabel(f"OSC → {targets}  @ {rate:g} Hz"))
        controls.addStretch(1)

        self.smooth_chk = QCheckBox("smoothing")
        self.smooth_chk.setChecked(smoothing)
        self.smooth_chk.setFocusPolicy(Qt.NoFocus)
        self.smooth_chk.toggled.connect(lambda v: setattr(self.state, "smoothing", v))
        controls.addWidget(self.smooth_chk)

        self.jitter_chk = QCheckBox("jitter")
        self.jitter_chk.setChecked(jitter)
        self.jitter_chk.setFocusPolicy(Qt.NoFocus)
        self.jitter_chk.toggled.connect(lambda v: setattr(self.state, "jitter", v))
        controls.addWidget(self.jitter_chk)

        zero_btn = QPushButton("Zero all")
        zero_btn.setFocusPolicy(Qt.NoFocus)
        zero_btn.clicked.connect(self.state.zero_all)
        controls.addWidget(zero_btn)

        fill_btn = QPushButton("Fill all")
        fill_btn.setFocusPolicy(Qt.NoFocus)
        fill_btn.clicked.connect(self.state.fill_all)
        controls.addWidget(fill_btn)
        root.addLayout(controls)

        # --- Keyboard status + hint ---
        self.status_label = QLabel()
        root.addWidget(self.status_label)
        hint = QLabel(
            "keys:  arrows/hjkl move   +/- adjust   ]/[ fine   0-9 set   space=1.0   "
            "x mute   t touch/release node   n/m zero/max node   z/f zero/fill   "
            "s smooth   J jitter   q quit"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        root.addWidget(hint)

        self.setFocusPolicy(Qt.StrongFocus)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(max(1, round(1000.0 / rate)))

    def _tick(self):
        t = time.monotonic() - self.start
        self.state.update(self.dt)
        self.state.send(self.clients, t)
        self._sync_widgets()

    def _sync_widgets(self):
        for col in self.columns:
            col.refresh()
        for p, (a, b) in enumerate(NODE_PAIRS):
            dimmed = self.state.pair_muted[p] or self.state.released[a] or self.state.released[b]
            self.pair_strips[p].refresh(dimmed=dimmed)

        sel_ch = self.channels[self.sel]
        for ch, strip in self._strip_for.items():
            strip.set_selected(ch == sel_ch)

        val = "muted" if self.state.muted(sel_ch) else f"{self.state.target(sel_ch):.2f}"
        self.status_label.setText(f"selected:  {self.state.label(sel_ch)} = {val}")

    def keyPressEvent(self, event):
        key = event.key()
        text = event.text()
        sel_ch = self.channels[self.sel]
        n_ch = len(self.channels)

        if key == Qt.Key_Q or key == Qt.Key_Escape:
            self.close()
            return
        elif key in (Qt.Key_Left, Qt.Key_Up) or text in ("h", "k"):
            self.sel = (self.sel - 1) % n_ch
        elif key in (Qt.Key_Right, Qt.Key_Down) or text in ("l", "j"):
            self.sel = (self.sel + 1) % n_ch
        elif text in ("+", "="):
            self.state.adjust(sel_ch, STEP)
        elif text in ("-", "_"):
            self.state.adjust(sel_ch, -STEP)
        elif text == "]":
            self.state.adjust(sel_ch, FINE_STEP)
        elif text == "[":
            self.state.adjust(sel_ch, -FINE_STEP)
        elif text == " ":
            self.state.set(sel_ch, 1.0)
        elif text.isdigit():
            self.state.set(sel_ch, int(text) / 10.0)
        elif text == "x":
            self.state.toggle_mute(sel_ch)
        elif text == "t":
            if sel_ch[0] == "pres":
                self.state.toggle_touch(sel_ch[1])
        elif text == "n":
            if sel_ch[0] == "pres":
                self.state.set_node(sel_ch[1], 0.0)
        elif text == "m":
            if sel_ch[0] == "pres":
                self.state.set_node(sel_ch[1], 1.0)
        elif text == "z":
            self.state.zero_all()
        elif text == "f":
            self.state.fill_all()
        elif text == "s":
            self.smooth_chk.toggle()
        elif text == "J":
            self.jitter_chk.toggle()
        else:
            super().keyPressEvent(event)
            return

        self._sync_widgets()


def main():
    parser = argparse.ArgumentParser(
        description="Qt desktop front-end for the manual OSC sensor simulator."
    )
    parser.add_argument("--host", default="127.0.0.1", help="OSC target host")
    parser.add_argument("--port", type=int, default=57120, help="OSC target port")
    parser.add_argument("--rate", type=float, default=30.0, help="Message send rate in Hz")
    parser.add_argument(
        "--no-smoothing",
        action="store_true",
        help="Start with smoothing off (faders snap to set values instantly)",
    )
    parser.add_argument(
        "--jitter",
        action="store_true",
        help="Start with organic jitter on (subtle noise layered on held values)",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        metavar="HOST:PORT",
        help="Send to multiple targets via broadcast UDP. Overrides --host/--port.",
    )
    args = parser.parse_args()

    clients = build_clients(args)

    app = QApplication(sys.argv)
    window = MixerWindow(clients, args.rate, not args.no_smoothing, args.jitter)
    window.resize(760, 620)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
