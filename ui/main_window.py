from PyQt6.QtWidgets import QMainWindow, QSplitter, QTreeWidget, QTreeWidgetItem
from PyQt6.QtCore import Qt

from ui.vtk_viewer import VTKViewer


class MainWindow(QMainWindow):

    def __init__(self, index):

        super().__init__()

        self.index = index

        self.setWindowTitle("IFC File Companion")
        self.resize(1400, 900)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Element", "Type"])

        for element in self.index.elements:

            item = QTreeWidgetItem([
                element.name,
                element.type
            ])

            item.setData(0, Qt.ItemDataRole.UserRole, element.id)

            self.tree.addTopLevelItem(item)

        self.viewer = VTKViewer()

        splitter.addWidget(self.tree)
        splitter.addWidget(self.viewer)

        splitter.setSizes([350, 1050])

        self.setCentralWidget(splitter)
