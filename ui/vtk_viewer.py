import vtk
import math
from PyQt6.QtGui import QCloseEvent, QShowEvent
from PyQt6.QtCore import Qt

from core.ifc_vtk_mesh_helper import IfcVtkMeshHelper
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor


class VTKViewer(QVTKRenderWindowInteractor):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.renderer = vtk.vtkRenderer()

        self.render_window = self.GetRenderWindow()
        self.render_window.AddRenderer(self.renderer)

        self.interactor = self.render_window.GetInteractor()

        self._z_up = (0.0, 0.0, 1.0)
        self._up_blend = 0.22

        style = vtk.vtkInteractorStyleTerrain()
        self.interactor.SetInteractorStyle(style)

        camera = self.renderer.GetActiveCamera()
        camera.SetViewUp(*self._z_up)

        self.interactor.AddObserver(vtk.vtkCommand.InteractionEvent, self._stabilize_z_up)
        self.interactor.AddObserver(vtk.vtkCommand.EndInteractionEvent, self._enforce_z_up)

        self._interactor_initialized = False
        self._mesh_helper = IfcVtkMeshHelper()
        self._model_actors = []
        self._isolated_actors = []
        self._model_visible = True

        self._setup_scene()


    def _enforce_z_up(self, _obj=None, _event=None):
        camera = self.renderer.GetActiveCamera()
        camera.SetViewUp(*self._z_up)
        camera.OrthogonalizeViewUp()


    def _stabilize_z_up(self, _obj=None, _event=None):
        camera = self.renderer.GetActiveCamera()
        current = camera.GetViewUp()

        bx = current[0] * (1.0 - self._up_blend) + self._z_up[0] * self._up_blend
        by = current[1] * (1.0 - self._up_blend) + self._z_up[1] * self._up_blend
        bz = current[2] * (1.0 - self._up_blend) + self._z_up[2] * self._up_blend

        mag = (bx * bx + by * by + bz * bz) ** 0.5
        if mag == 0.0:
            return

        camera.SetViewUp(bx / mag, by / mag, bz / mag)


    def showEvent(self, event: QShowEvent):

        super().showEvent(event)
        self._initialize_interactor()


    def closeEvent(self, event: QCloseEvent):

        if self._interactor_initialized:
            self.interactor.Disable()
            self.render_window.Finalize()
            self._interactor_initialized = False
        super().closeEvent(event)


    def mousePressEvent(self, event):

        if event.button() == Qt.MouseButton.RightButton:
            event.accept()
            return

        super().mousePressEvent(event)


    def mouseReleaseEvent(self, event):

        if event.button() == Qt.MouseButton.RightButton:
            event.accept()
            return

        super().mouseReleaseEvent(event)


    def wheelEvent(self, event):

        if not self._interactor_initialized:
            super().wheelEvent(event)
            return

        dy = event.angleDelta().y()
        if dy == 0:
            dy = event.pixelDelta().y()

        if dy == 0:
            event.ignore()
            return

        camera = self.renderer.GetActiveCamera()
        factor = 1.14 if dy > 0 else 1 / 1.14
        camera.Dolly(factor)
        self.renderer.ResetCameraClippingRange()
        self.render_window.Render()

        event.accept()


    def _initialize_interactor(self):

        if self._interactor_initialized:
            return

        self.interactor.Initialize()
        self.render_window.Render()

        self._interactor_initialized = True

    def _setup_scene(self):

        self.renderer.SetBackground(0.62, 0.78, 0.92)
        self.renderer.SetUseDepthPeeling(False)
        self.render_window.SetAlphaBitPlanes(0)
        self.render_window.SetMultiSamples(0)

        light = vtk.vtkLight()
        light.SetLightTypeToSceneLight()
        light.SetPosition(0.0, 0.0, 5000.0)
        light.SetFocalPoint(0.0, 0.0, 0.0)
        light.SetColor(0.85, 0.88, 0.92)
        light.SetIntensity(1.2)
        self.renderer.AddLight(light)

        self.renderer.ResetCamera()

    def clear_model(self):

        self.clear_isolation(render=False)

        for actor in self._model_actors:
            self.renderer.RemoveActor(actor)

        self._model_actors = []
        self._model_visible = True

        self.renderer.ResetCamera()
        if self._interactor_initialized:
            self.render_window.Render()


    def clear_isolation(self, render=True):

        if not self._isolated_actors:
            return

        for actor in self._isolated_actors:
            self.renderer.RemoveActor(actor)

        self._isolated_actors = []

        if render and self._interactor_initialized:
            self.render_window.Render()


    def _hide_model(self):

        if not self._model_visible:
            return

        for actor in self._model_actors:
            self.renderer.RemoveActor(actor)

        self._model_visible = False


    def show_all_model(self, reset_camera=True):

        self.clear_isolation(render=False)

        if not self._model_visible:
            for actor in self._model_actors:
                self.renderer.AddActor(actor)
            self._model_visible = True

        if reset_camera:
            self.renderer.ResetCamera()

        if self._interactor_initialized:
            self.render_window.Render()


    def can_show_all(self):

        return bool(self._model_actors) and (not self._model_visible)


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

        camera = self.renderer.GetActiveCamera()
        pos = camera.GetPosition()
        fp = camera.GetFocalPoint()

        vx = pos[0] - fp[0]
        vy = pos[1] - fp[1]
        vz = pos[2] - fp[2]
        vm = math.sqrt(vx * vx + vy * vy + vz * vz)
        if vm < 1e-6:
            vx, vy, vz = (1.0, 1.0, 1.0)
            vm = math.sqrt(3.0)

        ux, uy, uz = vx / vm, vy / vm, vz / vm
        distance = max(diagonal * 1.8, 2.0)

        camera.SetFocalPoint(cx, cy, cz)
        camera.SetPosition(cx + ux * distance, cy + uy * distance, cz + uz * distance)
        camera.SetViewUp(*self._z_up)
        camera.OrthogonalizeViewUp()

        self.renderer.ResetCameraClippingRange(bounds)


    def _combined_bounds(self, actors):

        if not actors:
            return None

        bounds = None
        for actor in actors:
            ab = actor.GetBounds()
            if not ab:
                continue

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

        actors = []
        for element in elements:
            actors.extend(self._mesh_helper.build_element_actors(element))

        if not actors:
            if self._interactor_initialized:
                self.render_window.Render()
            return False

        self._hide_model()

        self._isolated_actors = actors
        for actor in self._isolated_actors:
            self.renderer.AddActor(actor)

        if zoom:
            self._zoom_to_bounds(self._combined_bounds(self._isolated_actors))

        if self._interactor_initialized:
            self.render_window.Render()

        return True


    def load_ifc_model(self, model):

        self.clear_model()

        actors, count = self._mesh_helper.build_actors(model)
        if count == 0 or not actors:
            return 0

        opaque = []
        translucent = []
        for actor in actors:
            prop = actor.GetProperty()
            if prop is not None and prop.GetOpacity() < 0.999:
                translucent.append(actor)
            else:
                opaque.append(actor)

        self._model_actors = opaque + translucent
        for actor in self._model_actors:
            self.renderer.AddActor(actor)

        self._model_visible = True

        self.renderer.ResetCamera()

        if self._interactor_initialized:
            self.render_window.Render()

        return count
