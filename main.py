import sys

from PyQt6.QtWidgets import QApplication

from core.ifc_loader import IfcLoader
from core.model_index import ModelIndex
from core.sql_store import SQLStore

from ui.main_window import MainWindow

def main():

    if len(sys.argv) < 2:
        print("Usage: python main.py model.ifc")
        return

    path = sys.argv[1]

    loader = IfcLoader()
    model = loader.load(path)

    index = ModelIndex()
    index.build(model)

    db = SQLStore("model.db")
    db.store(index)

    app = QApplication(sys.argv)

    window = MainWindow(index)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
