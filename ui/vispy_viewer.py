import math
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from vispy import app, scene
from vispy.color import Color
from vispy.geometry import MeshData
from vispy.scene.visuals import Mesh

from core.ifc_vispy_mesh_helper import IfcVispyMeshHelper

app.use_app("pyqt6")


class VispyViewer(QWidget):

    context_menu_requested = pyqtSignal(object)

    def __init__(self, parent=None):

        super().__init__(parent)

        self._z_up = (0.0, 0.0, 1.0)
        self._mesh_helper = IfcVispyMeshHelper()
        self._model_visuals = []
        self._isolated_visuals = []
        self._visual_vertices = {}
        self._model_visible = True

        self.canvas = scene.SceneCanvas(keys=None, bgcolor="#9ec8eb")
        self.view = self.canvas.central_widget.add_view()
        self.view.camera = scene.cameras.TurntableCamera(fov=45, up="z", azimuth=45, elevation=20)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas.native)

        self.canvas.native.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.canvas.native.customContextMenuRequested.connect(self._forward_context_menu)


    def _forward_context_menu(self, pos):
        self.context_menu_requested.emit(self.canvas.native.mapToGlobal(pos))


    def _remove_visuals(self, visuals):
        for visual in visuals:
            self._visual_vertices.pop(id(visual), None)
            if visual.parent is not None:
                visual.parent = None
        visuals.clear()

    def _create_mesh_visual(self, mesh):
        color = mesh["style"]
        rgba = Color((float(color[0]), float(color[1]), float(color[2]), float(color[3])))
        mesh_data = MeshData(vertices=mesh["vertices"], faces=mesh["faces"])
        visual = Mesh(
            meshdata=mesh_data,
            color=rgba,
            shading="flat",
            parent=self.view.scene,
        )

        self._visual_vertices[id(visual)] = mesh["vertices"]
        return visual

    def clear_model(self):

        self.clear_isolation(render=False)
        self._remove_visuals(self._model_visuals)
        self._model_visible = True
        self.canvas.update()


    def clear_isolation(self, render=True):

        self._remove_visuals(self._isolated_visuals)

        if render:
            self.canvas.update()


    def _hide_model(self):

        if not self._model_visible:
            return

        for visual in self._model_visuals:
            visual.visible = False

        self._model_visible = False


    def show_all_model(self, reset_camera=True):

        self.clear_isolation(render=False)

        if not self._model_visible:
            for visual in self._model_visuals:
                visual.visible = True
            self._model_visible = True

        if reset_camera:
            self._zoom_to_bounds(self._combined_bounds(self._model_visuals))

        self.canvas.update()


    def can_show_all(self):

        return bool(self._model_visuals) and (not self._model_visible)


    def _zoom_to_bounds(self, bounds):

        if not bounds:
            return

        cx = (bounds[0] + bounds[1]) * 0.5
        cy = (bounds[2] + bounds[3]) * 0.5
        cz = (bounds[4] + bounds[5]) * 0.5

        dx = bounds[1] - bounds[0]
        dy = bounds[3] - bounds[2]
        dz = bounds[5] - bounds[4]
        diagonal = max(1e-3, math.sqrt(dx * dx + dy * dy + dz * dz))

        self.view.camera.center = (cx, cy, cz)
        self.view.camera.scale_factor = diagonal * 1.2
        self.canvas.update()


    def _combined_bounds(self, visuals):

        if not visuals:
            return None

        bounds = None
        for visual in visuals:
            vertices = self._visual_vertices.get(id(visual))
            if vertices is None or len(vertices) == 0:
                continue

            mins = vertices.min(axis=0)
            maxs = vertices.max(axis=0)
            ab = (mins[0], maxs[0], mins[1], maxs[1], mins[2], maxs[2])

            if bounds is None:
                bounds = [ab[0], ab[1], ab[2], ab[3], ab[4], ab[5]]
            else:
                bounds[0] = min(bounds[0], ab[0])
                bounds[1] = max(bounds[1], ab[1])
                bounds[2] = min(bounds[2], ab[2])
                bounds[3] = max(bounds[3], ab[3])
                bounds[4] = min(bounds[4], ab[4])
                bounds[5] = max(bounds[5], ab[5])

        return tuple(bounds) if bounds is not None else None


    def isolate_element(self, element, zoom=False):

        return self.isolate_elements([element], zoom=zoom)


    def isolate_elements(self, elements, zoom=False):

        self.clear_isolation(render=False)

        meshes = []
        for element in elements:
            meshes.extend(self._mesh_helper.build_element_actors(element))

        if not meshes:
            self.canvas.update()
            return False

        self._hide_model()

        self._isolated_visuals = [self._create_mesh_visual(mesh) for mesh in meshes]

        if zoom:
            self._zoom_to_bounds(self._combined_bounds(self._isolated_visuals))

        self.canvas.update()

        return True


    def load_ifc_model(self, model):

        self.clear_model()

        meshes, count = self._mesh_helper.build_actors(model)
        if count == 0 or not meshes:
            return 0

        self._model_visuals = [self._create_mesh_visual(mesh) for mesh in meshes]

        self._model_visible = True
        self._zoom_to_bounds(self._combined_bounds(self._model_visuals))
        self.canvas.update()

        return count
