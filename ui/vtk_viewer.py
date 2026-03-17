import vtk
from PyQt6.QtCore import QTimer

from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor


class VTKViewer(QVTKRenderWindowInteractor):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.renderer = vtk.vtkRenderer()

        self.GetRenderWindow().AddRenderer(self.renderer)

        self.interactor = self.GetRenderWindow().GetInteractor()
        self._interactor_initialized = False

        self.setup_scene()

        # Defer Initialize naar de Qt eventloop om thread/race issues bij widget-creatie te vermijden.
        QTimer.singleShot(0, self._initialize_interactor)


    def _initialize_interactor(self):

        if self._interactor_initialized:
            return

        self.interactor.Initialize()
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
