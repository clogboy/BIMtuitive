import sys
import numpy as np
import ifcopenshell
import ifcopenshell.geom
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTreeView, QSplitter, 
                             QFileDialog, QToolBar, QVBoxLayout, QWidget)
from PyQt6.QtCore import QAbstractItemModel, QModelIndex, Qt, QRunnable, pyqtSignal, QObject, QThreadPool, pyqtSlot
from vispy import scene

# --- 1. IFC Boomstructuur Logica ---
class IfcTreeItem:
    def __init__(self, ifc_object, parent=None):
        self.ifc_object = ifc_object
        self.parent_item = parent
        self.child_items = []
        if ifc_object:
            name = getattr(ifc_object, "Name", "") or "Unnamed"
            self.display_name = f"[{ifc_object.is_a()}] {name} (#{ifc_object.id()})"
        else:
            self.display_name = "Project Root"

    def append_child(self, child): self.child_items.append(child)
    def child(self, row): return self.child_items[row]
    def child_count(self): return len(self.child_items)
    def row(self): return self.parent_item.child_items.index(self) if self.parent_item else 0

class IfcTreeModel(QAbstractItemModel):
    def __init__(self, ifc_file=None, parent=None):
        super().__init__(parent)
        self.root_item = IfcTreeItem(None)
        if ifc_file: self._load_structure(ifc_file)

    def _load_structure(self, model):
        for proj in model.by_type("IfcProject"):
            proj_item = IfcTreeItem(proj, self.root_item)
            self.root_item.append_child(proj_item)
            self._recursive_add(proj, proj_item)
        self.layoutChanged.emit()

    def _recursive_add(self, ifc_obj, parent_item):
        # Aggregatie (Decompositie)
        for rel in getattr(ifc_obj, "IsDecomposedBy", []):
            for sub in rel.RelatedObjects:
                child = IfcTreeItem(sub, parent_item)
                parent_item.append_child(child)
                self._recursive_add(sub, child)
        # Inhoud (Spatiale structuur)
        for rel in getattr(ifc_obj, "ContainsElements", []):
            for el in rel.RelatedElements:
                parent_item.append_child(IfcTreeItem(el, parent_item))

    def index(self, r, c, p):
        if not self.hasIndex(r, c, p): return QModelIndex()
        parent = p.internalPointer() if p.isValid() else self.root_item
        return self.createIndex(r, c, parent.child(r))

    def parent(self, idx):
        if not idx.isValid(): return QModelIndex()
        child = idx.internalPointer()
        parent = child.parent_item
        return QModelIndex() if parent == self.root_item else self.createIndex(parent.row(), 0, parent)

    def rowCount(self, p):
        if p.column() > 0: return 0
        return (p.internalPointer() if p.isValid() else self.root_item).child_count()

    def columnCount(self, p): return 1
    def data(self, idx, role):
        if idx.isValid() and role == Qt.ItemDataRole.DisplayRole:
            return idx.internalPointer().display_name
        return None

# --- 2. Geometrie Worker (Threading) ---
class MeshSignals(QObject):
    ready = pyqtSignal(np.ndarray, np.ndarray, np.ndarray)

class MeshWorker(QRunnable):
    def __init__(self, element, settings):
        super().__init__()
        self.element, self.settings, self.signals = element, settings, MeshSignals()

    @pyqtSlot()
    def run(self):
        try:
            shape = ifcopenshell.geom.create_shape(self.settings, self.element)
            v_raw = np.array(shape.geometry.verts, dtype=np.float32).reshape(-1, 3)
            center = np.mean(v_raw, axis=0)
            v = v_raw - center
            f = np.array(shape.geometry.faces, dtype=np.uint32).reshape(-1, 3)
            n = np.array(shape.geometry.normals, dtype=np.float32).reshape(-1, 3)
            self.signals.ready.emit(v, f, n)
        except: pass

# --- 3. Hoofdscherm ---
class IFCViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyQt6 IFC + VisPy Viewer")
        self.resize(1200, 800)
        self.thread_pool = QThreadPool()
        self.geom_settings = ifcopenshell.geom.settings()
        self.geom_settings.set(self.geom_settings.USE_WORLD_COORDS, True)
        # IFC-instellingen voor mesh
        self.geom_settings = ifcopenshell.geom.settings()
        self.geom_settings.set(self.geom_settings.USE_WORLD_COORDS, True)

        # Als GENERATE_NORMALS niet direct werkt, gebruik de 'valse' boolean setter 
        # of controleer of je versie 'INCLUDE_CURVES' etc. ondersteunt.
        # Voor de meeste moderne versies is dit de juiste manier:
        try:
            # Probeer de directe boolean setter
            self.geom_settings.set(13, True)
        except:
            # Fallback: sommige versies gebruiken een integer constante
            # 1 is meestal de index voor 'generate normals' in de C++ core
            pass 

        # UI Layout
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree_view = QTreeView()
        splitter.addWidget(self.tree_view)
        
        # VisPy Canvas
        self.canvas = scene.SceneCanvas(keys='interactive', show=True, bgcolor='lightblue')
        self.view = self.canvas.central_widget.add_view()
        self.view.bgcolor = 'lightblue'
        self.view.camera = 'turntable'
        self.mesh_visual = scene.visuals.Mesh(shading='flat', parent=self.view.scene)
        splitter.addWidget(self.canvas.native)
        
        self.setCentralWidget(splitter)
        
        # Toolbar
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        load_act = toolbar.addAction("Open IFC")
        load_act.triggered.connect(self.open_file)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open IFC", "", "IFC Files (*.ifc)")
        if path:
            model = ifcopenshell.open(path)
            self.ifc_model = IfcTreeModel(model)
            self.tree_view.setModel(self.ifc_model)
            self.tree_view.selectionModel().selectionChanged.connect(self.on_select)

    def on_select(self, selected, _):
        if not selected.indexes(): return
        item = selected.indexes()[0].internalPointer()
        if item.ifc_object and item.ifc_object.is_a("IfcElement"):
            worker = MeshWorker(item.ifc_object, self.geom_settings)
            worker.signals.ready.connect(self.update_view)
            self.thread_pool.start(worker)

    def update_view(self, v, f, n):
        if v is None or len(v) == 0:
            print("Geen geometrie data gevonden voor dit element.")
            return
        
        try:
            # VisPy gebruikt vaak 'normals' in plaats van 'vertex_normals'
            # Shading='smooth' moet aanstaan in de constructor van de Mesh (zie hieronder)
            self.mesh_visual.set_data(vertices=v, faces=f)
        except Exception as e:
            print(f"Vispy error: {e}")
        
        # Forceer de camera om het object te centreren
        self.mesh_visual.set_data(vertices=v, faces=f)
        self.view.camera.center = (0, 0, 0)
        self.view.camera.set_range()
        self.canvas.update()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = IFCViewer()
    window.show()
    sys.exit(app.exec())
