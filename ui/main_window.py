from PyQt6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QProgressBar,
    QStatusBar,
    QSplitter,
    QToolBar,
    QTreeWidget,
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QAction

from ui.loading_controller import LoadingController
from ui.selection_controller import SelectionController
from ui.tree_controller import TreeController
from ui.vispy_viewer import VispyViewer


class MainWindow(QMainWindow):

    def __init__(self, _path: str = ""):

        super().__init__()
        self.setWindowTitle("IFC File Companion")
        self.resize(1400, 900)

        self.path = ""
        self.model = None
        self._init_status_bar()
        self._build_ui()
        self._init_loading_controller()

        if _path:
            self._start_model_load(_path)


    def _build_ui(self):

        self._add_toolbar()

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.tree = QTreeWidget()
        self.tree_controller = TreeController(self.tree)

        self.viewer = VispyViewer()
        self.selection_controller = SelectionController(
            self.tree_controller,
            self.viewer,
            self._status_bar.showMessage,
            self,
        )

        splitter.addWidget(self.tree)
        splitter.addWidget(self.viewer)
        splitter.setSizes([350, 1050])

        self.setCentralWidget(splitter)

    def _init_status_bar(self):

        self._status_bar = QStatusBar(self)
        self.setStatusBar(self._status_bar)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setFixedWidth(180)

        self._status_bar.addPermanentWidget(self.progress)
        self._status_bar.showMessage("Ready")


    def _add_toolbar(self):

        toolbar = QToolBar()
        self.open_action = QAction("Load IFC", self)
        self.open_action.setStatusTip("Open an IFC file")
        self.open_action.triggered.connect(self._open_file_button_clicked)
        toolbar.addAction(self.open_action)

        self.addToolBar(toolbar)
    

    def _open_file_button_clicked(self):
        self.path, _ = QFileDialog.getOpenFileName(self, "Select IFC file", "", "IFC Files (*.ifc)")
        if not self.path:
            return

        self._start_model_load(self.path)

    def _init_loading_controller(self):

        self.loading_controller = LoadingController(self)
        self.loading_controller.progress.connect(self._step_loading)
        self.loading_controller.loaded.connect(self._on_model_loaded)
        self.loading_controller.failed.connect(self._on_model_load_failed)
        self.loading_controller.busy_changed.connect(self._on_loading_busy_changed)

    def _start_model_load(self, path):

        if self.loading_controller.is_busy():
            return

        self._set_loading(True, "Loading IFC...")
        self.loading_controller.start(path)


    def _set_loading(self, active, message):

        self.progress.setVisible(active)
        self.setCursor(Qt.CursorShape.WaitCursor if active else Qt.CursorShape.ArrowCursor)
        self._status_bar.showMessage(message)


    def _step_loading(self, message):

        self._status_bar.showMessage(message)


    @pyqtSlot(object, object)
    def _on_model_loaded(self, model, node):

        self.model = model
        self.selection_controller.set_model(model)

        self._step_loading("Building tree...")
        self.tree_controller.populate(node)

        self._step_loading("Building geometry...")
        self.viewer.load_ifc_model(model)

        self._set_loading(False, "Ready")


    @pyqtSlot(str)
    def _on_model_load_failed(self, message):

        self._set_loading(False, f"Load failed: {message}")

    @pyqtSlot(bool)
    def _on_loading_busy_changed(self, busy):

        self.open_action.setEnabled(not busy)

