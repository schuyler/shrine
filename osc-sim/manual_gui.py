#!/usr/bin/env python3
"""Qt desktop front-end for the manual OSC sensor simulator.

This is a second view over the same ``ManualState`` that drives the curses tool
in ``manual.py`` — all OSC, smoothing, jitter and mute logic is shared, so the
two stay in lockstep. It presents the four nodes as columns of vertical faders
(one per OSC float) with per-channel mute and per-node touch/release buttons,
matching the firmware contract exactly (``/shrine/node/N`` × 5 floats).

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
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from manual import (
    NODE_CHANNELS,
    NUM_CHANNELS,
    NUM_NODES,
    ManualState,
    build_clients,
)

SLIDER_RANGE = 100  # QSlider is integer; map 0..100 <-> 0.0..1.0


class ChannelStrip(QWidget):
    """A single fader: vertical slider + live value label + mute button.

    The slider position is the *target*; the label shows the *current* (eased,
    optionally jittered) value actually being sent — mirroring the curses tool's
    "bar = current, number = target" convention.
    """

    def __init__(self, state: ManualState, node: int, ch: int):
        super().__init__()
        self.state = state
        self.node = node
        self.ch = ch

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self.value_label = QLabel("0.00")
        self.value_label.setAlignment(Qt.AlignHCenter)

        self.slider = QSlider(Qt.Vertical)
        self.slider.setRange(0, SLIDER_RANGE)
        self.slider.setValue(0)
        self.slider.valueChanged.connect(self._on_slider)

        self.mute_btn = QPushButton("M")
        self.mute_btn.setCheckable(True)
        self.mute_btn.setFixedWidth(34)
        self.mute_btn.clicked.connect(self._on_mute)

        name_label = QLabel(NODE_CHANNELS[ch][0])
        name_label.setAlignment(Qt.AlignHCenter)

        layout.addWidget(self.value_label)
        layout.addWidget(self.slider, 1, Qt.AlignHCenter)
        layout.addWidget(self.mute_btn, 0, Qt.AlignHCenter)
        layout.addWidget(name_label)

    def _on_slider(self, value: int):
        self.state.set(self.node, self.ch, value / SLIDER_RANGE)

    def _on_mute(self):
        # Drive the model from the button, then let refresh() reconcile styling.
        if self.mute_btn.isChecked() != self.state.muted[self.node][self.ch]:
            self.state.toggle_mute(self.node, self.ch)

    def refresh(self):
        """Sync widgets from the model (cheap; called every frame)."""
        muted = self.state.muted[self.node][self.ch]

        # Slider follows the target so programmatic changes (zero/fill) show up,
        # without fighting the user during a drag (target == slider then).
        want = round(self.state.target[self.node][self.ch] * SLIDER_RANGE)
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
            self.value_label.setText(f"{self.state.current[self.node][self.ch]:.2f}")


class NodeColumn(QWidget):
    """One node's five channel strips plus a touch/release button."""

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
        self.touch_btn.clicked.connect(lambda: self.state.toggle_touch(self.node))
        layout.addWidget(self.touch_btn)

        strips_row = QHBoxLayout()
        strips_row.setSpacing(2)
        self.strips = [ChannelStrip(state, node, c) for c in range(NUM_CHANNELS)]
        for strip in self.strips:
            strips_row.addWidget(strip)
        layout.addLayout(strips_row, 1)

    def refresh(self):
        released = self.state.node_released(self.node)
        self.touch_btn.setText("Touch" if released else "Release")
        for strip in self.strips:
            strip.refresh()


class MixerWindow(QMainWindow):
    def __init__(self, clients: list, rate: float, smoothing: bool, jitter: bool):
        super().__init__()
        self.setWindowTitle("Shrine Manual Sensor Simulator")
        self.state = ManualState(smoothing=smoothing, jitter=jitter)
        self.clients = clients
        self.start = time.monotonic()

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # Node columns.
        cols = QHBoxLayout()
        self.columns = [NodeColumn(self.state, n) for n in range(NUM_NODES)]
        for i, col in enumerate(self.columns):
            cols.addWidget(col)
            if i < NUM_NODES - 1:
                divider = QFrame()
                divider.setFrameShape(QFrame.VLine)
                cols.addWidget(divider)
        root.addLayout(cols, 1)

        # Global control bar.
        controls = QHBoxLayout()

        targets = ", ".join(f"{c._address}:{c._port}" for c in clients)
        controls.addWidget(QLabel(f"OSC → {targets}  @ {rate:g} Hz"))
        controls.addStretch(1)

        self.smooth_chk = QCheckBox("smoothing")
        self.smooth_chk.setChecked(smoothing)
        self.smooth_chk.toggled.connect(
            lambda v: setattr(self.state, "smoothing", v)
        )
        controls.addWidget(self.smooth_chk)

        self.jitter_chk = QCheckBox("jitter")
        self.jitter_chk.setChecked(jitter)
        self.jitter_chk.toggled.connect(
            lambda v: setattr(self.state, "jitter", v)
        )
        controls.addWidget(self.jitter_chk)

        zero_btn = QPushButton("Zero all")
        zero_btn.clicked.connect(self.state.zero_all)
        controls.addWidget(zero_btn)

        fill_btn = QPushButton("Fill all")
        fill_btn.clicked.connect(self.state.fill_all)
        controls.addWidget(fill_btn)

        root.addLayout(controls)

        # Drive OSC + UI refresh off one timer.
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(max(1, round(1000.0 / rate)))

    def _tick(self):
        t = time.monotonic() - self.start
        self.state.update()
        self.state.send(self.clients, t)
        for col in self.columns:
            col.refresh()


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
    window.resize(720, 520)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
