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

        style = vtk.vtkInteractorStyleTerrain()
        self.interactor.SetInteractorStyle(style)

        camera = self.renderer.GetActiveCamera()
        camera.SetViewUp(*self._z_up)

        self.interactor.AddObserver(vtk.vtkCommand.EndInteractionEvent, self._enforce_z_up)

        self._interactor_initialized = False
        self._mesh_helper = IfcVtkMeshHelper()
        self._model_actors = []

        self._setup_scene()


    def _enforce_z_up(self, _obj=None, _event=None):
        camera = self.renderer.GetActiveCamera()
        camera.SetViewUp(*self._z_up)
        camera.OrthogonalizeViewUp()

    def showEvent(self, event: QShowEvent):

        super().showEvent(event)
        self._initialize_interactor()


    def closeEvent(self, event: QCloseEvent):

        # Ensure VTK/X11 resources are released before Qt thread teardown.
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

        self.renderer.SetBackground(0.1, 0.1, 0.15)
        self.renderer.SetUseDepthPeeling(False)
        self.renderer.SetMaximumNumberOfPeels(4)
        self.renderer.SetOcclusionRatio(0.2)

        self.render_window.SetAlphaBitPlanes(0)
        self.render_window.SetMultiSamples(0)

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

        self._model_actors = actors
        for actor in self._model_actors:
            self.renderer.AddActor(actor)

        self.renderer.ResetCamera()

        if self._interactor_initialized:
            self.render_window.Render()

        return count
