import sys
import os
from typing import Any
import numpy as np
import ifcopenshell
import ifcopenshell.geom
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTreeView, QSplitter,
                             QFileDialog, QToolBar)
from PyQt6.QtCore import QAbstractItemModel, QModelIndex, Qt, QRunnable, pyqtSignal, QObject, QThreadPool, pyqtSlot
from vispy import scene
from vispy.color import Color
from vispy.scene.visuals import Mesh

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

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent): return QModelIndex()
        parent_item = parent.internalPointer() if parent.isValid() else self.root_item
        return self.createIndex(row, column, parent_item.child(row))

    def parent(self, child):  # type: ignore[override]
        if not child.isValid(): return QModelIndex()
        child_item = child.internalPointer()
        parent_item = child_item.parent_item
        return QModelIndex() if parent_item == self.root_item else self.createIndex(parent_item.row(), 0, parent_item)

    def rowCount(self, parent=QModelIndex()):
        if parent.column() > 0: return 0
        return (parent.internalPointer() if parent.isValid() else self.root_item).child_count()

    def columnCount(self, parent=QModelIndex()): return 1
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role == Qt.ItemDataRole.DisplayRole:
            return index.internalPointer().display_name
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
            geom: Any = getattr(shape, "geometry", shape)
            v_raw = np.asarray(geom.verts, dtype=np.float32).reshape(-1, 3)
            # Lokale centering: corrigeert RD-offset voor enkel element
            v = v_raw - v_raw[0]
            f = np.asarray(geom.faces, dtype=np.uint32).reshape(-1, 3)
            try:
                n = np.asarray(geom.normals, dtype=np.float32).reshape(-1, 3)
            except Exception:
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
            num_threads = max(1, (os.cpu_count() or 2) - 1)
            iterator = ifcopenshell.geom.iterator(self.settings, self.model, num_threads)
            all_verts, all_faces = [], []
            offset = 0
            world_origin = None  # Eénmalige RD-offset, gezet op eerste vertex

            if iterator.initialize():
                while True:
                    shape = iterator.get()
                    geom: Any = getattr(shape, "geometry", shape)
                    v = np.asarray(geom.verts, dtype=np.float32).reshape(-1, 3)
                    f = np.asarray(geom.faces, dtype=np.uint32).reshape(-1, 3)
                    if len(v) and len(f):
                        if world_origin is None:
                            world_origin = v[0].copy()
                        v -= world_origin  # in-place, geen extra kopie
                        all_verts.append(v)
                        all_faces.append(f + offset)
                        offset += len(v)
                    if not iterator.next(): break

            if all_verts:
                v_final = np.concatenate(all_verts)
                f_final = np.concatenate(all_faces)
                self.signals.ready.emit(v_final, f_final, np.zeros((len(v_final), 3), dtype=np.float32))
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
        self.mesh_visual = Mesh(shading='flat', color=Color('royalblue'), parent=self.view.scene)
        splitter.addWidget(self.canvas.native)
        
        self.setCentralWidget(splitter)
        
        # 4. Toolbar
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        load_act = toolbar.addAction("Open IFC Bestand")
        if load_act is not None:
            load_act.triggered.connect(self.open_file)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecteer IFC", "", "IFC Files (*.ifc)")
        if path:
            print(f"Laden: {path}")
            model = ifcopenshell.open(path)
            self.ifc_model = IfcTreeModel(model)
            self.tree_view.setModel(self.ifc_model)
            sel = self.tree_view.selectionModel()
            if sel is not None:
                sel.selectionChanged.connect(self.on_select)

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
        
        # Fit camera direct op de nieuwe mesh bounds
        self.view.camera.set_range(margin=0.1)
        
        self.mesh_visual.update()
        self.canvas.update()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = IFCViewer()
    window.show()
    sys.exit(app.exec())
