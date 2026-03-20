import vtk
from PyQt6.QtGui import QCloseEvent, QShowEvent

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

        for actor in self._model_actors:
            self.renderer.RemoveActor(actor)

        self._model_actors = []

        self.renderer.ResetCamera()
        if self._interactor_initialized:
            self.render_window.Render()


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

        self.renderer.ResetCamera()

        if self._interactor_initialized:
            self.render_window.Render()

        return count
