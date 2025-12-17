🚀 PyClicker v1.0 — Cross-Platform Auto Clicker (AppImage)

PyClicker is a modern, safe, and configurable auto-clicker built with Python + Qt (PySide6).

It focuses on usability, safety, and portability, and is distributed as a single AppImage for easy use on Linux without installation. What started as a learning project turned into a fully-featured utility.

✨ Features

⏱ Precise Timing Control

    Minutes / seconds / milliseconds
    Accurate scheduling (not capped at 10 CPS)

🖱 Flexible Clicking

    Left / right / middle mouse button
    Single or double-click
    Optional fixed screen position

🔁 Run Control

    Stop after N clicks (or run indefinitely)
    Optional start delay countdown

⌨ Global Hotkeys

    F8 — toggle start / stop
    F9 — panic stop (immediate)
    Works in the background when supported by the OS

🛟 Safety First

    PyAutoGUI FAILSAFE enabled (move mouse to top-left to stop)
    Panic stop always available
    Clean thread shutdown (no freezes or lockups)

🧩 Clean UI

    Compact window size
    Tab-based layout
    Scrollable sections (no clipped content)
    Rounded, modern Qt styling

📦 Portable

    Distributed as a single AppImage
    No Python or runtime dependencies required
    Works across most Linux distributions

🐧 Linux Notes

Global hotkeys and mouse injection work best on X11.

On Wayland, system security restrictions may limit global hotkeys (the app still works with window-focused hotkeys). This is a platform limitation, not a PyClicker bug.

📥 Installation

    Download the .AppImage from the releases page

    Make it executable:

    chmod +x PyClicker-x86_64.AppImage

Run it:

./PyClicker-x86_64.AppImage

No installation, no root access required.
📜 License

MIT License — free to use, modify, and distribute.

See the LICENSE file for details.
💬 Final Notes

This project explores:

    Qt application design
    Threaded background workers
    Global input hooks
    Safe automation
    Cross-distro Linux packaging

Feedback, issues, and contributions are welcome!
