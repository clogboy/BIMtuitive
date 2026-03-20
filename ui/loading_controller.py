from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from ui.load_model_worker import LoadModelWorker


class LoadingController(QObject):

    progress = pyqtSignal(str)
    loaded = pyqtSignal(object, object)
    failed = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._worker = None

    def is_busy(self):
        return self._thread is not None

    def start(self, path):

        if self._thread is not None:
            return False

        self.busy_changed.emit(True)

        self._thread = QThread(self)
        self._worker = LoadModelWorker(path)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress)
        self._worker.finished.connect(self.loaded)
        self._worker.failed.connect(self.failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)

        self._thread.start()
        return True

    @pyqtSlot()
    def _cleanup(self):

        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()

        self._worker = None
        self._thread = None
        self.busy_changed.emit(False)
