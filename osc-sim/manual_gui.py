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
    FINE_STEP,
    NODE_CHANNELS,
    NUM_CHANNELS,
    NUM_NODES,
    STEP,
    ManualState,
    build_clients,
)

SLIDER_RANGE = 100  # QSlider is integer; map 0..100 <-> 0.0..1.0


class ChannelStrip(QFrame):
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
        # Keyboard is driven from the window, not individual sliders, so the
        # selection cursor and arrow-key navigation stay consistent.
        self.slider.setFocusPolicy(Qt.NoFocus)
        self.slider.valueChanged.connect(self._on_slider)

        self.mute_btn = QPushButton("M")
        self.mute_btn.setCheckable(True)
        self.mute_btn.setFixedWidth(34)
        self.mute_btn.setFocusPolicy(Qt.NoFocus)
        self.mute_btn.clicked.connect(self._on_mute)

        name_label = QLabel(NODE_CHANNELS[ch][0])
        name_label.setAlignment(Qt.AlignHCenter)

        layout.addWidget(self.value_label)
        layout.addWidget(self.slider, 1, Qt.AlignHCenter)
        layout.addWidget(self.mute_btn, 0, Qt.AlignHCenter)
        layout.addWidget(name_label)

    def set_selected(self, selected: bool):
        if selected == self._selected:
            return
        self._selected = selected
        self.setStyleSheet(
            "QFrame#ChannelStrip { background-color: #2d4a6b; border-radius: 3px; }"
            if selected
            else ""
        )

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
        self.touch_btn.setFocusPolicy(Qt.NoFocus)
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
        self.sel_node = 0
        self.sel_ch = 0

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
        self.smooth_chk.setFocusPolicy(Qt.NoFocus)
        self.smooth_chk.toggled.connect(
            lambda v: setattr(self.state, "smoothing", v)
        )
        controls.addWidget(self.smooth_chk)

        self.jitter_chk = QCheckBox("jitter")
        self.jitter_chk.setChecked(jitter)
        self.jitter_chk.setFocusPolicy(Qt.NoFocus)
        self.jitter_chk.toggled.connect(
            lambda v: setattr(self.state, "jitter", v)
        )
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

        # Keyboard status + shortcut hint.
        self.status_label = QLabel()
        root.addWidget(self.status_label)
        hint = QLabel(
            "keys:  arrows/hjkl move   +/- adjust   ]/[ fine   0-9 set   space=1.0   "
            "x mute   t touch/release   n/m zero/max node   z/f zero/fill   s smooth   J jitter   q quit"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        root.addWidget(hint)

        # The window owns all keystrokes; child widgets are NoFocus.
        self.setFocusPolicy(Qt.StrongFocus)

        # Drive OSC + UI refresh off one timer.
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(max(1, round(1000.0 / rate)))

    def _tick(self):
        t = time.monotonic() - self.start
        self.state.update()
        self.state.send(self.clients, t)
        self._sync_widgets()

    def _sync_widgets(self):
        for col in self.columns:
            col.refresh()
        for n, col in enumerate(self.columns):
            for c, strip in enumerate(col.strips):
                strip.set_selected(n == self.sel_node and c == self.sel_ch)
        ch_name = NODE_CHANNELS[self.sel_ch][0]
        muted = self.state.muted[self.sel_node][self.sel_ch]
        val = "muted" if muted else f"{self.state.target[self.sel_node][self.sel_ch]:.2f}"
        self.status_label.setText(
            f"selected:  node {self.sel_node} / {ch_name} = {val}"
        )

    def keyPressEvent(self, event):
        key = event.key()
        text = event.text()
        n, c = self.sel_node, self.sel_ch

        if key == Qt.Key_Q or key == Qt.Key_Escape:
            self.close()
            return
        elif key == Qt.Key_Left or text == "h":
            self.sel_node = (n - 1) % NUM_NODES
        elif key == Qt.Key_Right or text == "l":
            self.sel_node = (n + 1) % NUM_NODES
        elif key == Qt.Key_Up or text == "k":
            self.sel_ch = (c - 1) % NUM_CHANNELS
        elif key == Qt.Key_Down or text == "j":
            self.sel_ch = (c + 1) % NUM_CHANNELS
        elif text in ("+", "="):
            self.state.adjust(n, c, STEP)
        elif text in ("-", "_"):
            self.state.adjust(n, c, -STEP)
        elif text == "]":
            self.state.adjust(n, c, FINE_STEP)
        elif text == "[":
            self.state.adjust(n, c, -FINE_STEP)
        elif text == " ":
            self.state.set(n, c, 1.0)
        elif text.isdigit():
            self.state.set(n, c, int(text) / 10.0)
        elif text == "x":
            self.state.toggle_mute(n, c)
        elif text == "t":
            self.state.toggle_touch(n)
        elif text == "n":
            self.state.set_node(n, 0.0)
        elif text == "m":
            self.state.set_node(n, 1.0)
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

        # Reflect the change immediately rather than waiting for the next tick.
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
    window.resize(720, 520)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
