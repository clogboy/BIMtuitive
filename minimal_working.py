import sys
import numpy as np
import ifcopenshell
import ifcopenshell.geom
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTreeView, QSplitter, 
                             QFileDialog, QToolBar)
from PyQt6.QtCore import QAbstractItemModel, QModelIndex, Qt, QRunnable, pyqtSignal, QObject, QThreadPool, pyqtSlot
from vispy import scene

# --- 1. IFC Boomstructuur Logica ---
class IfcTreeItem:
    def __init__(self, ifc_object, parent=None):
        self.ifc_object = ifc_object
        self.parent_item = parent
        self.child_items = []
        if ifc_object:
            name = getattr(ifc_object, "Name", "") or "Naamloos"
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
        for rel in getattr(ifc_obj, "IsDecomposedBy", []):
            for sub in rel.RelatedObjects:
                child = IfcTreeItem(sub, parent_item)
                parent_item.append_child(child)
                self._recursive_add(sub, child)
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
            # Voorkom jitter door te centreren op lokaal nulpunt
            center = np.mean(v_raw, axis=0)
            v = v_raw - center
            f = np.array(shape.geometry.faces, dtype=np.uint32).reshape(-1, 3)
            # Gebruik dummy normalen als generator faalt
            try:
                n = np.array(shape.geometry.normals, dtype=np.float32).reshape(-1, 3)
            except:
                n = np.zeros_like(v)
            self.signals.ready.emit(v, f, n)
        except Exception as e:
            print(f"Geometrie fout voor #{self.element.id()}: {e}")

class FullModelWorker(QRunnable):
    def __init__(self, model, settings):
        super().__init__()
        self.model, self.settings, self.signals = model, settings, MeshSignals()

    @pyqtSlot()
    def run(self):
        try:
            # Gebruik de iterator voor snelheid en multiprocessing
            iterator = ifcopenshell.geom.iterator(self.settings, self.model, multiprocessing=True)
            all_verts, all_faces = [], []
            offset = 0

            if iterator.initialize():
                while True:
                    shape = iterator.get()
                    v = np.array(shape.geometry.verts, dtype=np.float32).reshape(-1, 3)
                    f = np.array(shape.geometry.faces, dtype=np.uint32).reshape(-1, 3)
                    
                    all_verts.append(v)
                    all_faces.append(f + offset) # Verschuif indices voor de gecombineerde buffer
                    offset += len(v)
                    
                    if not iterator.next(): break

            if all_verts:
                v_final = np.concatenate(all_verts)
                f_final = np.concatenate(all_faces)
                # Centreer het HELE model rond 0,0,0
                center = np.mean(v_final, axis=0)
                self.signals.ready.emit(v_final - center, f_final, np.zeros_like(v_final))
        except Exception as e:
            print(f"Fout bij laden model: {e}")

# --- 3. Hoofdscherm ---
class IFCViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BIMtuitive Minimal IFC Viewer")
        self.resize(1280, 720)
        self.thread_pool = QThreadPool()
        
        # 1. IFC Settings (één keer correct instellen)
        self.geom_settings = ifcopenshell.geom.settings()
        self.geom_settings.set(self.geom_settings.USE_WORLD_COORDS, True)
        try:
            self.geom_settings.set(13, True) # GENERATE_NORMALS index
        except: pass

        # 2. UI Layout
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        splitter.addWidget(self.tree_view)
        
        # 3. VisPy Canvas Setup
        self.canvas = scene.SceneCanvas(keys='interactive', show=True, bgcolor='white')
        self.view = self.canvas.central_widget.add_view()
        self.view.bgcolor = '#f0f0f0' # Iets grijzere viewport voor contrast
        self.view.camera = 'turntable'
        
        # Initialiseer Mesh met een opvallende kleur
        self.mesh_visual = scene.visuals.Mesh(shading='flat', color='royalblue', parent=self.view.scene)
        splitter.addWidget(self.canvas.native)
        
        self.setCentralWidget(splitter)
        
        # 4. Toolbar
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        load_act = toolbar.addAction("Open IFC Bestand")
        load_act.triggered.connect(self.open_file)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecteer IFC", "", "IFC Files (*.ifc)")
        if path:
            print(f"Laden: {path}")
            model = ifcopenshell.open(path)
            self.ifc_model = IfcTreeModel(model)
            self.tree_view.setModel(self.ifc_model)
            self.tree_view.selectionModel().selectionChanged.connect(self.on_select)

            worker = FullModelWorker(model, self.geom_settings)
            worker.signals.ready.connect(self.update_view)
            self.thread_pool.start(worker)

    def on_select(self, selected, _):
        if not selected.indexes(): return
        item = selected.indexes()[0].internalPointer()
        
        # Alleen geometrie berekenen voor elementen, niet voor containers
        if item.ifc_object and item.ifc_object.is_a("IfcElement"):
            worker = MeshWorker(item.ifc_object, self.geom_settings)
            worker.signals.ready.connect(self.update_view)
            self.thread_pool.start(worker)

    def update_view(self, v, f, n):
        if v.size == 0: return
        
        print(f"Rendering element met {len(v)} vertices...")
        
        # Update mesh data
        self.mesh_visual.set_data(vertices=v, faces=f)
        
        # Reset camera naar het object
        self.view.camera.center = (0, 0, 0)
        self.view.camera.set_range(margin=0.1)
        
        self.mesh_visual.update()
        self.canvas.update()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = IFCViewer()
    window.show()
    sys.exit(app.exec())
