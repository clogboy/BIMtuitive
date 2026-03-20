from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from core.ifc_loader import IfcLoader
from core.model_index import ModelIndex
from core.sql_store import SQLStore


class LoadModelWorker(QObject):

    progress = pyqtSignal(str)
    finished = pyqtSignal(object, object)
    failed = pyqtSignal(str)

    def __init__(self, path):
        super().__init__()
        self.path = path

    @pyqtSlot()
    def run(self):
        try:
            self.progress.emit("Loading IFC...")
            loader = IfcLoader()
            model = loader.load(self.path)

            self.progress.emit("Building index...")
            index = ModelIndex()
            node = index.build(model)

            self.progress.emit("Storing SQL data...")
            db = SQLStore("model.db")
            db.store(index)

            self.finished.emit(model, node)
        except Exception as exc:
            self.failed.emit(str(exc))
