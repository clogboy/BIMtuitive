import vtk
from PyQt6.QtGui import QCloseEvent, QShowEvent

from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor


class VTKViewer(QVTKRenderWindowInteractor):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.renderer = vtk.vtkRenderer()

        self.render_window = self.GetRenderWindow()
        self.render_window.AddRenderer(self.renderer)

        self.interactor = self.render_window.GetInteractor()
        self._interactor_initialized = False

        self.setup_scene()


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


    def setup_scene(self):

        cube = vtk.vtkCubeSource()

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(cube.GetOutputPort())

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)

        self.renderer.AddActor(actor)

        self.renderer.SetBackground(0.1, 0.1, 0.15)

        self.renderer.ResetCamera()
