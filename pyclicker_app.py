"""
PyClicker Tabs (PySide6)
- Compact window + tabs (no giant vertical form)
- Global hotkeys: F8 toggle, F9 PANIC (via pynput if available)
- Safety:
  - F9 PANIC stop
  - PyAutoGUI FAILSAFE (move mouse to top-left corner)
- Features:
  - interval: minutes/seconds/ms
  - click button + double-click
  - stop after N clicks
  - start delay
  - fixed-position clicking + pick current mouse position
  - target CPS display
"""

from __future__ import annotations

import sys
import time
import threading
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QFormLayout,
    QTabWidget,
    QGroupBox,
    QScrollArea,
    QFrame,
    QLabel,
    QSpinBox,
    QPushButton,
    QComboBox,
    QCheckBox,
    QMessageBox,
)

import pyautogui

# -------- Optional global hotkeys --------
try:
    from pynput import keyboard  # type: ignore
    PYNPUT_OK = True
except Exception:
    keyboard = None
    PYNPUT_OK = False

# -------- PyAutoGUI speed + safety --------
pyautogui.PAUSE = 0.0
pyautogui.FAILSAFE = True
try:
    pyautogui.MINIMUM_DURATION = 0.0
    pyautogui.MINIMUM_SLEEP = 0.0
except Exception:
    pass


APP_QSS = """
* { font-size: 13px; }

QMainWindow { background: palette(window); }

QFrame#HeaderCard {
    border: 1px solid palette(mid);
    border-radius: 14px;
    background: palette(base);
    padding: 10px;
}

QLabel#Pill {
    border: 1px solid palette(mid);
    border-radius: 12px;
    padding: 8px 10px;
    font-weight: 700;
}

QTabWidget::pane {
    border: 1px solid palette(mid);
    border-radius: 14px;
    background: palette(base);
    padding: 8px;
}

QTabBar::tab {
    border: 1px solid palette(mid);
    border-bottom: none;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
    padding: 8px 12px;
    margin-right: 6px;
    background: palette(window);
    font-weight: 600;
}

QTabBar::tab:selected {
    background: palette(base);
}

QGroupBox {
    border: 1px solid palette(mid);
    border-radius: 12px;
    margin-top: 12px;
    padding: 10px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 8px;
    font-weight: 700;
}

QSpinBox, QComboBox {
    border: 1px solid palette(mid);
    border-radius: 10px;
    padding: 6px 8px;
    min-height: 30px;
}

QPushButton {
    border: 1px solid palette(mid);
    border-radius: 12px;
    padding: 10px 12px;
    min-height: 38px;
    font-weight: 800;
}

QPushButton:disabled { opacity: 0.55; }

QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; }
"""


@dataclass(frozen=True)
class ClickConfig:
    interval_sec: float
    button: str
    double_click: bool
    max_clicks: int
    start_delay_sec: int
    fixed_pos_enabled: bool
    fixed_x: int
    fixed_y: int


class ClickWorker(QObject):
    started = Signal()
    stopped = Signal()
    tick = Signal(int)
    status = Signal(str)
    error = Signal(str)

    def __init__(self, cfg: ClickConfig):
        super().__init__()
        self.cfg = cfg
        self._stop = threading.Event()
        self._count = 0

    @Slot()
    def stop(self) -> None:
        self._stop.set()

    def _do_click(self) -> int:
        if self.cfg.fixed_pos_enabled:
            pyautogui.moveTo(self.cfg.fixed_x, self.cfg.fixed_y)

        if self.cfg.double_click:
            pyautogui.click(button=self.cfg.button, clicks=2, interval=0.0)
            return 2

        pyautogui.click(button=self.cfg.button)
        return 1

    @Slot()
    def run(self) -> None:
        try:
            self._stop.clear()
            self._count = 0

            # Start delay countdown
            for t in range(self.cfg.start_delay_sec, 0, -1):
                if self._stop.is_set():
                    self.stopped.emit()
                    return
                self.status.emit(f"Starting in {t}s... (F9 PANIC / top-left FAILSAFE)")
                time.sleep(1)

            self.status.emit("Running (F8 toggle / F9 panic / top-left failsafe)")
            self.started.emit()

            interval = max(0.001, float(self.cfg.interval_sec))
            next_t = time.perf_counter()

            # Prevent “infinite catch-up” if the system lags
            max_catchup = 20

            while not self._stop.is_set():
                now = time.perf_counter()
                if now >= next_t:
                    catch = 0
                    while now >= next_t and catch < max_catchup and not self._stop.is_set():
                        try:
                            added = self._do_click()
                        except pyautogui.FailSafeException:
                            self.status.emit("FAILSAFE triggered (top-left). Stopped.")
                            self._stop.set()
                            break

                        self._count += added
                        self.tick.emit(self._count)

                        if self.cfg.max_clicks > 0 and self._count >= self.cfg.max_clicks:
                            self.status.emit("Click limit reached. Stopped.")
                            self._stop.set()
                            break

                        next_t += interval
                        catch += 1
                        now = time.perf_counter()
                else:
                    time.sleep(min(0.002, next_t - now))

        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.stopped.emit()


class GlobalHotkeys(QObject):
    toggle = Signal()
    panic = Signal()

    def __init__(self):
        super().__init__()
        self._gh = None

    def available(self) -> bool:
        return PYNPUT_OK

    def start(self) -> None:
        if not PYNPUT_OK or self._gh is not None:
            return
        self._gh = keyboard.GlobalHotKeys({
            "<f8>": lambda: self.toggle.emit(),
            "<f9>": lambda: self.panic.emit(),
        })
        self._gh.start()

    def stop(self) -> None:
        if self._gh is None:
            return
        try:
            self._gh.stop()
        except Exception:
            pass
        self._gh = None


def wrap_scroll(widget: QWidget) -> QScrollArea:
    """Wrap a widget in a scroll area so the window can stay small but never cuts off content."""
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setFrameShape(QFrame.NoFrame)
    sc.setWidget(widget)
    return sc


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyClicker (Tabs) - F8 Toggle / F9 Panic")

        self._running = False
        self._thread: QThread | None = None
        self._worker: ClickWorker | None = None

        self.hk = GlobalHotkeys()
        self.hk.toggle.connect(self.toggle_start_stop)
        self.hk.panic.connect(self.panic_stop)

        self._build_ui()
        self._wire_ui()

        # Fallback: shortcuts work when window focused
        self._qt_f8 = QShortcut(QKeySequence("F8"), self)
        self._qt_f8.activated.connect(self.toggle_start_stop)
        self._qt_f9 = QShortcut(QKeySequence("F9"), self)
        self._qt_f9.activated.connect(self.panic_stop)

        # Default enable global hotkeys if possible
        if self.hk.available():
            self.chk_global.setChecked(True)
            self.hk.start()
        else:
            self.chk_global.setChecked(False)
            self.chk_global.setEnabled(False)
            self.chk_global.setText("Global hotkeys unavailable (install pynput)")

        self._update_cps()
        self._update_target_enabled()
        self._refresh_summary()

        # Compact sizing (and scroll areas handle overflow)
        self.setMinimumSize(440, 480)
        self.resize(470, 560)

    # ---------- UI BUILD ----------
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        # Header card (always visible)
        header = QFrame()
        header.setObjectName("HeaderCard")
        h = QHBoxLayout(header)
        h.setContentsMargins(10, 10, 10, 10)
        h.setSpacing(10)

        self.lbl_status = QLabel("Status: stopped")
        self.lbl_status.setObjectName("Pill")
        self.lbl_cps = QLabel("CPS: -")
        self.lbl_cps.setObjectName("Pill")
        self.lbl_clicks = QLabel("Clicks: 0")
        self.lbl_clicks.setObjectName("Pill")

        h.addWidget(self.lbl_status, 2)
        h.addWidget(self.lbl_cps, 0)
        h.addWidget(self.lbl_clicks, 0)

        outer.addWidget(header)

        # Tabs
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs)

        # --- Tab 1: Timing ---
        tab_timing = QWidget()
        timing_layout = QVBoxLayout(tab_timing)
        timing_layout.setContentsMargins(6, 6, 6, 6)
        timing_layout.setSpacing(10)

        box_interval = QGroupBox("Interval")
        gi = QGridLayout(box_interval)
        gi.setHorizontalSpacing(10)
        gi.setVerticalSpacing(8)

        self.spin_min = QSpinBox(); self.spin_min.setRange(0, 9999); self.spin_min.setValue(0)
        self.spin_sec = QSpinBox(); self.spin_sec.setRange(0, 59); self.spin_sec.setValue(0)
        self.spin_ms  = QSpinBox(); self.spin_ms.setRange(0, 999); self.spin_ms.setValue(10)

        gi.addWidget(QLabel("Minutes"), 0, 0); gi.addWidget(self.spin_min, 0, 1)
        gi.addWidget(QLabel("Seconds"), 0, 2); gi.addWidget(self.spin_sec, 0, 3)
        gi.addWidget(QLabel("Milliseconds"), 1, 0); gi.addWidget(self.spin_ms, 1, 1)

        self.spin_delay = QSpinBox(); self.spin_delay.setRange(0, 60); self.spin_delay.setValue(0)
        self.spin_limit = QSpinBox(); self.spin_limit.setRange(0, 10_000_000); self.spin_limit.setValue(0)

        gi.addWidget(QLabel("Start delay (s)"), 1, 2); gi.addWidget(self.spin_delay, 1, 3)
        gi.addWidget(QLabel("Stop after clicks (0=infinite)"), 2, 0, 1, 2); gi.addWidget(self.spin_limit, 2, 2, 1, 2)

        timing_layout.addWidget(box_interval)

        box_summary = QGroupBox("Summary")
        fs = QFormLayout(box_summary)
        fs.setHorizontalSpacing(12)
        fs.setVerticalSpacing(8)
        self.lbl_summary = QLabel("-")
        self.lbl_summary.setWordWrap(True)
        fs.addRow("Current config", self.lbl_summary)
        timing_layout.addWidget(box_summary)

        timing_layout.addStretch(1)

        # --- Tab 2: Click ---
        tab_click = QWidget()
        click_layout = QVBoxLayout(tab_click)
        click_layout.setContentsMargins(6, 6, 6, 6)
        click_layout.setSpacing(10)

        box_click = QGroupBox("Click Options")
        fc = QFormLayout(box_click)
        fc.setHorizontalSpacing(12)
        fc.setVerticalSpacing(10)

        self.cmb_button = QComboBox()
        self.cmb_button.addItems(["left", "right", "middle"])

        self.chk_double = QCheckBox("Double-click (2 clicks per interval)")

        fc.addRow("Mouse button", self.cmb_button)
        fc.addRow("", self.chk_double)

        click_layout.addWidget(box_click)
        click_layout.addStretch(1)

        # --- Tab 3: Target ---
        tab_target = QWidget()
        target_layout = QVBoxLayout(tab_target)
        target_layout.setContentsMargins(6, 6, 6, 6)
        target_layout.setSpacing(10)

        box_target = QGroupBox("Target / Position")
        gt = QGridLayout(box_target)
        gt.setHorizontalSpacing(10)
        gt.setVerticalSpacing(8)

        self.chk_fixed = QCheckBox("Click at fixed position")
        self.spin_x = QSpinBox(); self.spin_x.setRange(-1_000_000, 1_000_000); self.spin_x.setValue(0)
        self.spin_y = QSpinBox(); self.spin_y.setRange(-1_000_000, 1_000_000); self.spin_y.setValue(0)
        self.btn_pick = QPushButton("Pick current mouse")

        gt.addWidget(self.chk_fixed, 0, 0, 1, 4)
        gt.addWidget(QLabel("X"), 1, 0); gt.addWidget(self.spin_x, 1, 1)
        gt.addWidget(QLabel("Y"), 1, 2); gt.addWidget(self.spin_y, 1, 3)
        gt.addWidget(self.btn_pick, 2, 0, 1, 4)

        target_layout.addWidget(box_target)
        target_layout.addStretch(1)

        # --- Tab 4: Hotkeys ---
        tab_hotkeys = QWidget()
        hot_layout = QVBoxLayout(tab_hotkeys)
        hot_layout.setContentsMargins(6, 6, 6, 6)
        hot_layout.setSpacing(10)

        box_hot = QGroupBox("Hotkeys & Safety")
        fh = QFormLayout(box_hot)
        fh.setHorizontalSpacing(12)
        fh.setVerticalSpacing(10)

        self.chk_global = QCheckBox("Enable GLOBAL hotkeys (F8 toggle / F9 panic)")
        self.lbl_hot_info = QLabel(
            "Hotkeys:\n"
            "• F8 = toggle start/stop\n"
            "• F9 = PANIC stop\n\n"
            "Failsafe:\n"
            "• Move mouse to TOP-LEFT corner to stop immediately."
        )
        self.lbl_hot_info.setWordWrap(True)

        fh.addRow(self.chk_global)
        fh.addRow(self.lbl_hot_info)

        hot_layout.addWidget(box_hot)
        hot_layout.addStretch(1)

        # --- Tab 5: Run ---
        tab_run = QWidget()
        run_layout = QVBoxLayout(tab_run)
        run_layout.setContentsMargins(6, 6, 6, 6)
        run_layout.setSpacing(10)

        box_run = QGroupBox("Controls")
        rr = QVBoxLayout(box_run)
        rr.setSpacing(10)

        self.btn_start = QPushButton("Start (F8)")
        self.btn_stop = QPushButton("Stop (F8)")
        self.btn_panic = QPushButton("PANIC STOP (F9)")
        self.btn_stop.setEnabled(False)

        rr.addWidget(self.btn_start)
        rr.addWidget(self.btn_stop)
        rr.addWidget(self.btn_panic)

        run_layout.addWidget(box_run)

        box_notes = QGroupBox("Notes")
        rn = QVBoxLayout(box_notes)
        self.lbl_notes = QLabel(
            "If global hotkeys don't work on Linux, you may be on Wayland.\n"
            "Try an X11 session for better global key hooking."
        )
        self.lbl_notes.setWordWrap(True)
        rn.addWidget(self.lbl_notes)
        run_layout.addWidget(box_notes)
        run_layout.addStretch(1)

        # Add tabs with scroll wrappers (small window-friendly)
        self.tabs.addTab(wrap_scroll(tab_timing), "Timing")
        self.tabs.addTab(wrap_scroll(tab_click), "Click")
        self.tabs.addTab(wrap_scroll(tab_target), "Target")
        self.tabs.addTab(wrap_scroll(tab_hotkeys), "Hotkeys")
        self.tabs.addTab(wrap_scroll(tab_run), "Run")

    # ---------- UI WIRING ----------
    def _wire_ui(self) -> None:
        # Any settings change updates summary + CPS
        for w in (self.spin_min, self.spin_sec, self.spin_ms, self.spin_delay, self.spin_limit):
            w.valueChanged.connect(self._on_settings_changed)
        self.cmb_button.currentTextChanged.connect(self._on_settings_changed)
        self.chk_double.toggled.connect(self._on_settings_changed)
        self.chk_fixed.toggled.connect(self._on_settings_changed)
        self.spin_x.valueChanged.connect(self._on_settings_changed)
        self.spin_y.valueChanged.connect(self._on_settings_changed)

        # Target enable
        self.chk_fixed.toggled.connect(self._update_target_enabled)

        # Buttons
        self.btn_pick.clicked.connect(self.pick_mouse_pos)
        self.btn_start.clicked.connect(self.start_clicking)
        self.btn_stop.clicked.connect(self.stop_clicking)
        self.btn_panic.clicked.connect(self.panic_stop)

        # Global hotkeys toggle
        self.chk_global.toggled.connect(self._on_global_hotkeys_toggled)

    @Slot()
    def _on_settings_changed(self) -> None:
        self._update_cps()
        self._refresh_summary()

    @Slot(bool)
    def _on_global_hotkeys_toggled(self, enabled: bool) -> None:
        if not self.hk.available():
            return
        if enabled:
            self.hk.start()
        else:
            self.hk.stop()

    @Slot()
    def _update_target_enabled(self) -> None:
        enabled = self.chk_fixed.isChecked()
        self.spin_x.setEnabled(enabled)
        self.spin_y.setEnabled(enabled)
        self.btn_pick.setEnabled(enabled)

    # ---------- MODEL HELPERS ----------
    def interval_seconds(self) -> float:
        total_ms = (
            int(self.spin_min.value()) * 60_000
            + int(self.spin_sec.value()) * 1_000
            + int(self.spin_ms.value())
        )
        return total_ms / 1000.0

    def make_config(self) -> ClickConfig:
        interval = self.interval_seconds()
        if interval <= 0:
            raise ValueError("Interval must be > 0ms (set at least 1ms).")

        return ClickConfig(
            interval_sec=interval,
            button=self.cmb_button.currentText(),
            double_click=self.chk_double.isChecked(),
            max_clicks=int(self.spin_limit.value()),
            start_delay_sec=int(self.spin_delay.value()),
            fixed_pos_enabled=self.chk_fixed.isChecked(),
            fixed_x=int(self.spin_x.value()),
            fixed_y=int(self.spin_y.value()),
        )

    def _refresh_summary(self) -> None:
        try:
            cfg = self.make_config()
            cps = (2 if cfg.double_click else 1) / cfg.interval_sec
            target = "cursor" if not cfg.fixed_pos_enabled else f"({cfg.fixed_x}, {cfg.fixed_y})"
            lim = "infinite" if cfg.max_clicks == 0 else str(cfg.max_clicks)
            self.lbl_summary.setText(
                f"{cfg.button} | {'double' if cfg.double_click else 'single'} | "
                f"interval={cfg.interval_sec*1000:.1f}ms (~{cps:.1f} CPS) | "
                f"limit={lim} | delay={cfg.start_delay_sec}s | target={target}"
            )
        except Exception as e:
            self.lbl_summary.setText(str(e))

    def _update_cps(self) -> None:
        interval = self.interval_seconds()
        if interval <= 0:
            self.lbl_cps.setText("CPS: -")
            return
        mult = 2 if self.chk_double.isChecked() else 1
        cps = mult / interval
        self.lbl_cps.setText(f"CPS: ~{cps:.1f}")

    # ---------- ACTIONS ----------
    @Slot()
    def pick_mouse_pos(self) -> None:
        x, y = pyautogui.position()
        self.spin_x.setValue(int(x))
        self.spin_y.setValue(int(y))

    @Slot()
    def start_clicking(self) -> None:
        if self._running:
            return

        try:
            cfg = self.make_config()
        except Exception as e:
            QMessageBox.warning(self, "Invalid settings", str(e))
            return

        # Fresh thread per run = clean lifecycle
        self._thread = QThread(self)
        self._worker = ClickWorker(cfg)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.started.connect(self._on_started)
        self._worker.stopped.connect(self._on_stopped)
        self._worker.tick.connect(self._on_tick)
        self._worker.status.connect(self._on_status)
        self._worker.error.connect(self._on_error)

        self.lbl_clicks.setText("Clicks: 0")
        self.lbl_status.setText("Status: starting...")
        self._thread.start()

    @Slot()
    def stop_clicking(self) -> None:
        if self._worker is not None:
            self._worker.stop()

    @Slot()
    def toggle_start_stop(self) -> None:
        if self._running:
            self.stop_clicking()
        else:
            self.start_clicking()

    @Slot()
    def panic_stop(self) -> None:
        # Instant stop request
        self.lbl_status.setText("Status: PANIC STOP!")
        self.stop_clicking()

    # ---------- WORKER SIGNALS ----------
    @Slot()
    def _on_started(self) -> None:
        self._running = True
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.lbl_status.setText("Status: running")

    @Slot()
    def _on_stopped(self) -> None:
        self._running = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)

        self.lbl_status.setText("Status: stopped")

    @Slot(int)
    def _on_tick(self, count: int) -> None:
        self.lbl_clicks.setText(f"Clicks: {count}")

    @Slot(str)
    def _on_status(self, text: str) -> None:
        self.lbl_status.setText(f"Status: {text}")

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        QMessageBox.critical(self, "Error", msg)

    def closeEvent(self, event) -> None:
        try:
            self.hk.stop()
            self.stop_clicking()
            if self._thread is not None and self._thread.isRunning():
                self._thread.quit()
                self._thread.wait(2000)
        finally:
            super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_QSS)

    w = MainWindow()
    w.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
