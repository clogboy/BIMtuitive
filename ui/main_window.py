from PyQt6.QtWidgets import QMainWindow, QSplitter, QTreeWidget, QTreeWidgetItem, QToolBar, QFileDialog, QStyle
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QAction

from core.ifc_loader import IfcLoader
from core.model_index import ModelIndex
from core.sql_store import SQLStore

from ui.vtk_viewer import VTKViewer


class MainWindow(QMainWindow):

    def __init__(self, path):

        super().__init__()

        self.path = path

        if not path == "":
            initModel(path)

        self.setWindowTitle("IFC File Companion")
        self.resize(1400, 900)

        toolbar = QToolBar()
        button_openfile = QAction("Open Folder...", self)
        button_openfile.setStatusTip("Open a project folder")
        button_openfile.triggered.connect(self.openfile_button_clicked)
        toolbar.addAction(button_openfile)

        self.addToolBar(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Element", "Type"])

        self.viewer = VTKViewer()

        splitter.addWidget(self.tree)
        splitter.addWidget(self.viewer)

        splitter.setSizes([350, 1050])

        self.setCentralWidget(splitter)
    
    def openfile_button_clicked(self):
        self.path = QFileDialog.getExistingDirectory(self, "Select IFC file")
        if not self.path:
            return

        self.initModel(path)

    def initModel(path):
        loader = IfcLoader()
        model = loader.load(path)

        index = ModelIndex()
        index.build(model)

        db = SQLStore("model.db")
        db.store(index)

        for element in self.index.elements:

            item = QTreeWidgetItem([
                element.name,
                element.type
            ])

            item.setData(0, Qt.ItemDataRole.UserRole, element.id)

            self.tree.addTopLevelItem(item)
