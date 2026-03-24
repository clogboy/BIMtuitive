import os
import sys

if sys.platform.startswith("linux") and not os.environ.get("QT_QPA_PLATFORM"):
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if os.environ.get("WAYLAND_DISPLAY") or session_type == "wayland":
        os.environ["QT_QPA_PLATFORM"] = "xcb"

import ifcopenshell
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTreeView, QSplitter, 
                             QFileDialog, QToolBar, QStatusBar, QProgressBar)
from PyQt6.QtCore import QAbstractItemModel, QModelIndex, Qt, QThreadPool
from vispy import app, scene

from ifc_geometry import IfcGeometryController

app.use_app("pyqt6")

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

# --- 3. Hoofdscherm ---
class IFCViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BIMtuitive Minimal IFC Viewer")
        self.resize(1280, 720)
        self.thread_pool = QThreadPool()
        self._selection_model = None
        self._active_ifc_object = None
        self._model_loading = False
        self._current_model_path = None
        self.geometry_controller = IfcGeometryController()
        self._model_loading_total = 0
        
        # 2. UI Layout
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        splitter.addWidget(self.tree_view)
        
        # 3. VisPy Canvas Setup
        self.canvas = scene.SceneCanvas(keys='interactive', show=False, bgcolor='white')
        self.view = self.canvas.central_widget.add_view()
        self.view.bgcolor = '#f0f0f0' # Iets grijzere viewport voor contrast
        self.view.camera = scene.cameras.TurntableCamera(fov=45, up='z', azimuth=45, elevation=20)
        
        # Toon het volledige model als basislaag en selectie als overlay.
        self.model_mesh_visual = self.geometry_controller.create_mesh_visual(self.view.scene, color='#c4c8cf')
        self.selection_mesh_visual = self.geometry_controller.create_mesh_visual(self.view.scene, color='royalblue')
        splitter.addWidget(self.canvas.native)
        
        self.setCentralWidget(splitter)

        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Klaar")

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimumWidth(220)
        self.status_bar.addPermanentWidget(self.progress_bar)
        
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
            self._current_model_path = path
            model = ifcopenshell.open(path)
            self.geometry_controller.clear_model_cache()
            self.geometry_controller.reset()
            self.geometry_controller.clear_visual(self.model_mesh_visual, self.canvas)
            self.geometry_controller.clear_visual(self.selection_mesh_visual, self.canvas)
            self._active_ifc_object = None
            self.ifc_model = IfcTreeModel(model)
            self.tree_view.setModel(self.ifc_model)
            selection_model = self.tree_view.selectionModel()
            if self._selection_model is not None:
                try:
                    self._selection_model.selectionChanged.disconnect(self.on_select)
                except TypeError:
                    pass
            if selection_model is not None:
                selection_model.selectionChanged.connect(self.on_select)
                self._selection_model = selection_model

            cached_model_mesh = self.geometry_controller.get_cached_model_mesh(path)
            if cached_model_mesh is not None:
                self._model_loading = False
                self.progress_bar.setVisible(False)
                self.status_bar.showMessage("Volledig model geladen (cache)")
                self.update_model_view(cached_model_mesh)
                self.canvas.update()
                return

            model_worker = self.geometry_controller.create_model_worker(path)
            model_worker.signals.ready.connect(self.update_model_view)
            model_worker.signals.progress.connect(self.update_model_progress)
            model_worker.signals.done.connect(self.finish_model_progress)
            self._model_loading = True
            self.thread_pool.start(model_worker)
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setVisible(True)
            self.status_bar.showMessage("Volledig model wordt opgebouwd...")
            self.canvas.update()

    def on_select(self, selected, _):
        if not selected.indexes(): return
        if self._model_loading:
            return

        item = selected.indexes()[0].internalPointer()
        
        if self.geometry_controller.can_render(item.ifc_object):
            self._active_ifc_object = item.ifc_object

            cached_mesh = self.geometry_controller.get_cached_mesh(item.ifc_object)
            if cached_mesh is not None:
                self.update_selection_view(cached_mesh)
                return

            worker = self.geometry_controller.create_worker(item.ifc_object)
            worker.signals.ready.connect(self.update_selection_view)
            self.thread_pool.start(worker)

    def update_model_view(self, mesh_data):
        if self._current_model_path:
            self.geometry_controller.cache_model_mesh(self._current_model_path, mesh_data)
        self.geometry_controller.set_model_mesh(mesh_data)
        print(f"Rendering volledig model met {len(mesh_data.vertices)} vertices...")
        self.geometry_controller.update_visual(self.model_mesh_visual, self.view, self.canvas, mesh_data, focus=True)

    def update_model_progress(self, processed, total):
        self._model_loading_total = total
        if total <= 0:
            self.progress_bar.setRange(0, 0)
            self.status_bar.showMessage("Volledig model wordt opgebouwd...")
            return

        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(processed)
        self.status_bar.showMessage(f"Model laden: {processed}/{total} producten")

    def finish_model_progress(self, success):
        self._model_loading = False
        if success:
            self.status_bar.showMessage("Volledig model geladen")
        else:
            self.status_bar.showMessage("Model laden voltooid zonder renderbare geometrie")
        self.progress_bar.setVisible(False)

    def update_selection_view(self, mesh_data):
        if self._active_ifc_object is not None:
            self.geometry_controller.cache_mesh(self._active_ifc_object, mesh_data)

        print(f"Rendering element met {len(mesh_data.vertices)} vertices...")
        self.geometry_controller.update_visual(self.selection_mesh_visual, self.view, self.canvas, mesh_data, focus=True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = IFCViewer()
    window.show()
    sys.exit(app.exec())
