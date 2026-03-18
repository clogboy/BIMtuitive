import sys
import os


def _configure_qt_platform():
    # VTK's Qt interactor is more stable on Linux via XCB than native Wayland.
    if not sys.platform.startswith("linux"):
        return

    if os.environ.get("QT_QPA_PLATFORM"):
        return

    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        os.environ["QT_QPA_PLATFORM"] = "xcb"


_configure_qt_platform()

from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow


def _log_runtime_platform():
    if os.environ.get("IFC_LOG_PLATFORM", "1") != "1":
        return

    platform_name = QGuiApplication.platformName()
    qt_qpa_platform = os.environ.get("QT_QPA_PLATFORM", "<auto>")
    session_type = os.environ.get("XDG_SESSION_TYPE", "<unset>")
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "<unset>")

    print(
        "[IFC] Qt backend="
        f"{platform_name} "
        f"(QT_QPA_PLATFORM={qt_qpa_platform}, "
        f"XDG_SESSION_TYPE={session_type}, "
        f"WAYLAND_DISPLAY={wayland_display})"
    )

def main():

    path = ""

    if not len(sys.argv) < 2:
        path = sys.argv[1]

    app = QApplication(sys.argv)
    _log_runtime_platform()

    window = MainWindow(path)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
