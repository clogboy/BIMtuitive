import sys

from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow

def main():

    path = ""

    if not len(sys.argv) < 2:
        path = sys.argv[1]

    app = QApplication(sys.argv)

    window = MainWindow(path)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
