from PyQt6.QtWidgets import QMainWindow, QSplitter, QTreeWidget, QTreeWidgetItem, QToolBar, QFileDialog
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction

from core.ifc_loader import IfcLoader
from core.model_index import ModelIndex
from core.sql_store import SQLStore

from ui.vtk_viewer import VTKViewer


class MainWindow(QMainWindow):

    def __init__(self, _path: str = ""):

        super().__init__()
        self.setWindowTitle("IFC File Companion")
        self.resize(1400, 900)

        self.path = ""
        self._build_ui()

        if _path:
            self._init_model(_path)


    def _build_ui(self):

        self._add_toolbar()

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Element", "Type"])

        self.viewer = VTKViewer()

        splitter.addWidget(self.tree)
        splitter.addWidget(self.viewer)
        splitter.setSizes([350, 1050])

        self.setCentralWidget(splitter)


    def _add_toolbar(self):

        toolbar = QToolBar()
        open_action = QAction("Load IFC", self)
        open_action.setStatusTip("Open an IFC file")
        open_action.triggered.connect(self._open_file_button_clicked)
        toolbar.addAction(open_action)

        self.addToolBar(toolbar)
    

    def _open_file_button_clicked(self):
        self.path, _ = QFileDialog.getOpenFileName(self, "Select IFC file", "", "IFC Files (*.ifc)")
        if not self.path:
            return

        self._init_model(self.path)


    def _init_model(self, path):
        loader = IfcLoader()
        model = loader.load(path)

        index = ModelIndex()
        index.build(model)

        db = SQLStore("model.db")
        db.store(index)

        self._populate_tree(index)
        self.viewer.load_ifc_model(model)


    def _populate_tree(self, index):
        self.tree.clear()

        for element in index.elements:

            item = QTreeWidgetItem([element.name, element.type])

            item.setData(0, Qt.ItemDataRole.UserRole, element.id)

            self.tree.addTopLevelItem(item)
