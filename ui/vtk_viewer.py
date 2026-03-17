import vtk

from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor


class VTKViewer(QVTKRenderWindowInteractor):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.renderer = vtk.vtkRenderer()

        self.GetRenderWindow().AddRenderer(self.renderer)

        self.interactor = self.GetRenderWindow().GetInteractor()

        self.setup_scene()

        self.interactor.Initialize()


    def setup_scene(self):

        cube = vtk.vtkCubeSource()

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(cube.GetOutputPort())

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)

        self.renderer.AddActor(actor)

        self.renderer.SetBackground(0.1, 0.1, 0.15)

        self.renderer.ResetCamera()
