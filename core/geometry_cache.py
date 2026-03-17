class GeometryCache:

    def __init__(self):

        self.meshes = {}

    def store(self, element_id, mesh):

        self.meshes[element_id] = mesh
