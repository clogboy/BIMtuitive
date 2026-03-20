from PyQt6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QProgressBar,
    QStatusBar,
    QSplitter,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
)
from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction

from core.ifc_loader import IfcLoader
from core.model_index import ModelIndex
from core.sql_store import SQLStore

from ui.vtk_viewer import VTKViewer


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


class MainWindow(QMainWindow):

    NODE_ROLE = Qt.ItemDataRole.UserRole
    NODE_LOADED_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(self, _path: str = ""):

        super().__init__()
        self.setWindowTitle("IFC File Companion")
        self.resize(1400, 900)

        self.path = ""
        self._load_thread = None
        self._load_worker = None
        self._init_status_bar()
        self._build_ui()

        if _path:
            self._init_model(_path)


    def _build_ui(self):

        self._add_toolbar()

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Element"])
        self.tree.setUniformRowHeights(True)
        self.tree.itemExpanded.connect(self._on_tree_item_expanded)

        self.viewer = VTKViewer()

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

        self._init_model(self.path)


    def _init_model(self, path):
        if self._load_thread is not None:
            return

        self._set_loading(True, "Loading IFC...")
        self.open_action.setEnabled(False)

        self._load_thread = QThread(self)
        self._load_worker = LoadModelWorker(path)
        self._load_worker.moveToThread(self._load_thread)

        self._load_thread.started.connect(self._load_worker.run)
        self._load_worker.progress.connect(self._step_loading)
        self._load_worker.finished.connect(self._on_model_loaded)
        self._load_worker.failed.connect(self._on_model_load_failed)
        self._load_worker.finished.connect(self._load_thread.quit)
        self._load_worker.failed.connect(self._load_thread.quit)
        self._load_thread.finished.connect(self._cleanup_loader_thread)

        self._load_thread.start()


    def _set_loading(self, active, message):

        self.progress.setVisible(active)
        self._status_bar.showMessage(message)


    def _step_loading(self, message):

        self._status_bar.showMessage(message)


    @pyqtSlot(object, object)
    def _on_model_loaded(self, model, node):

        self._step_loading("Building tree...")
        self._populate_tree(node)

        self._step_loading("Building geometry...")
        self.viewer.load_ifc_model(model)

        self._set_loading(False, "Ready")


    @pyqtSlot(str)
    def _on_model_load_failed(self, message):

        self._set_loading(False, f"Load failed: {message}")


    @pyqtSlot()
    def _cleanup_loader_thread(self):

        if self._load_worker is not None:
            self._load_worker.deleteLater()
        if self._load_thread is not None:
            self._load_thread.deleteLater()

        self._load_worker = None
        self._load_thread = None
        self.open_action.setEnabled(True)


    def _populate_tree(self, node):

        self.tree.clear()
        self.tree.setUpdatesEnabled(False)
        self.tree.blockSignals(True)
        self.tree.setSortingEnabled(True)        

        try:
            root_item = self._create_node_item(node)
            self.tree.addTopLevelItem(root_item)
        finally:
            self.tree.blockSignals(False)
            self.tree.setUpdatesEnabled(True)


    def _create_node_item(self, node):

        item = QTreeWidgetItem([node["name"]])
        item.setData(0, self.NODE_ROLE, node)
        item.setData(0, self.NODE_LOADED_ROLE, False)

        if node.get("children"):
            item.addChild(QTreeWidgetItem(["..."]))

        return item


    def _on_tree_item_expanded(self, item):

        node = item.data(0, self.NODE_ROLE)
        if not node:
            return

        if item.data(0, self.NODE_LOADED_ROLE):
            return

        item.takeChildren()

        if node["type"] == "IfcBuildingStorey":
            grouped = {}
            for child in node.get("children", []):
                grouped.setdefault(child["type"], []).append(child)

            for element_type in sorted(grouped):
                group_item = QTreeWidgetItem([f"{element_type} ({len(grouped[element_type])})"])
                item.addChild(group_item)
                for child in grouped[element_type]:
                    group_item.addChild(self._create_node_item(child))
        else:
            for child in node.get("children", []):
                item.addChild(self._create_node_item(child))

        item.setData(0, self.NODE_LOADED_ROLE, True)