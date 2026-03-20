from ifcopenshell import geom
import vtk


class IfcVtkMeshHelper:

    DEFAULT_STYLE = (180, 180, 185, 1.0, 0.15)

    def __init__(self):

        if geom is None:
            self.settings = None
            return

        self.settings = geom.settings()
        self.settings.set(self.settings.USE_WORLD_COORDS, True)


    def build_actors(self, model):

        if self.settings is None:
            return [], 0

        grouped = {}
        count = 0

        for element in model.by_type("IfcProduct"):
            if not getattr(element, "Representation", None):
                continue

            try:
                shape = geom.create_shape(self.settings, element)
            except Exception:
                continue

            geometry = self._extract_geometry(shape)
            if geometry is None:
                continue

            groups = self._to_poly_data_by_material(geometry)
            if not groups:
                continue

            for signature, poly_data in groups.items():
                grouped.setdefault(signature, []).append(poly_data)

            count += 1

        if count == 0:
            return [], 0

        actors = []
        for signature, parts in grouped.items():
            actor = self._build_actor_from_parts(signature, parts)
            if actor is not None:
                actors.append(actor)

        return actors, count


    def build_element_actors(self, element):

        if self.settings is None or element is None:
            return []

        if not getattr(element, "Representation", None):
            return []

        try:
            shape = geom.create_shape(self.settings, element)
        except Exception:
            return []

        geometry = self._extract_geometry(shape)
        if geometry is None:
            return []

        groups = self._to_poly_data_by_material(geometry)
        if not groups:
            return []

        actors = []
        for signature, poly_data in groups.items():
            actor = self._build_actor_from_parts(signature, [poly_data])
            if actor is not None:
                actors.append(actor)

        return actors


    def _build_actor_from_parts(self, signature, poly_data_parts):

        append_filter = vtk.vtkAppendPolyData()
        for part in poly_data_parts:
            append_filter.AddInputData(part)

        if append_filter.GetNumberOfInputConnections(0) == 0:
            return None

        append_filter.Update()

        clean = vtk.vtkCleanPolyData()
        clean.SetInputConnection(append_filter.GetOutputPort())
        clean.ConvertLinesToPointsOff()
        clean.ConvertPolysToLinesOff()
        clean.ConvertStripsToPolysOn()
        clean.Update()

        normals = vtk.vtkPolyDataNormals()
        normals.SetInputConnection(clean.GetOutputPort())
        normals.ComputePointNormalsOn()
        normals.ComputeCellNormalsOff()
        normals.ConsistencyOn()
        normals.NonManifoldTraversalOn()
        normals.AutoOrientNormalsOn()
        normals.SplittingOn()
        normals.SetFeatureAngle(50.0)
        normals.Update()

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(normals.GetOutputPort())
        mapper.ScalarVisibilityOff()

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)

        prop = actor.GetProperty()
        prop.SetColor(signature[0], signature[1], signature[2])
        prop.SetOpacity(signature[3])
        prop.SetInterpolationToPhong()
        prop.SetAmbient(0.15)
        prop.SetDiffuse(0.85)
        prop.SetSpecular(min(0.2, signature[4]))
        prop.SetSpecularPower(20.0)
        prop.BackfaceCullingOff()

        return actor


    def _extract_geometry(self, shape):
        geometry = getattr(shape, "geometry", shape)
        return geometry if hasattr(geometry, "verts") and hasattr(geometry, "faces") else None


    def _to_poly_data_by_material(self, geometry):

        vertices = getattr(geometry, "verts", None)
        faces = getattr(geometry, "faces", None)
        if not vertices or not faces:
            return {}

        styles = self._build_material_palette(getattr(geometry, "materials", []) or [])
        material_ids = list(getattr(geometry, "material_ids", []) or [])

        groups = {}

        def ensure_group(signature):
            if signature not in groups:
                groups[signature] = {
                    "points": vtk.vtkPoints(),
                    "triangles": vtk.vtkCellArray(),
                    "index_map": {},
                }
            return groups[signature]

        def remap_point(group, source_index):
            idx = group["index_map"].get(source_index)
            if idx is not None:
                return idx

            base = source_index * 3
            new_idx = group["points"].InsertNextPoint(vertices[base], vertices[base + 1], vertices[base + 2])
            group["index_map"][source_index] = new_idx
            return new_idx

        triangle_count = len(faces) // 3
        for i in range(0, len(faces), 3):
            tri_idx = i // 3
            material_index = self._resolve_material_index(material_ids, triangle_count, tri_idx, i)
            signature = self._style_signature_from_palette(styles, material_index)

            group = ensure_group(signature)

            triangle = vtk.vtkTriangle()
            triangle.GetPointIds().SetId(0, remap_point(group, faces[i]))
            triangle.GetPointIds().SetId(1, remap_point(group, faces[i + 1]))
            triangle.GetPointIds().SetId(2, remap_point(group, faces[i + 2]))
            group["triangles"].InsertNextCell(triangle)

        poly_data_by_material = {}
        for signature, group in groups.items():
            if group["points"].GetNumberOfPoints() == 0:
                continue

            poly_data = vtk.vtkPolyData()
            poly_data.SetPoints(group["points"])
            poly_data.SetPolys(group["triangles"])
            poly_data_by_material[signature] = poly_data

        return poly_data_by_material


    def _build_material_palette(self, materials):

        palette = []
        for material in materials:
            r, g, b = self._rgb255_from_colour(getattr(material, "diffuse", None))
            t = self._to_float(getattr(material, "transparency", None), 0.0) or 0.0
            s = self._specular_strength(getattr(material, "specular", None))
            palette.append((r / 255.0, g / 255.0, b / 255.0, max(0.02, min(1.0, 1.0 - t)), s))

        return palette


    def _rgb255_from_colour(self, colour):

        default = (180, 180, 185)
        if colour is None:
            return default

        r = self._component_value(colour, "r")
        g = self._component_value(colour, "g")
        b = self._component_value(colour, "b")

        if r is None or g is None or b is None:
            return default

        return max(0, min(255, int(r * 255))), max(0, min(255, int(g * 255))), max(0, min(255, int(b * 255)))


    def _specular_strength(self, specular):

        if specular is None:
            return 0.15

        if hasattr(specular, "r") and hasattr(specular, "g") and hasattr(specular, "b"):
            r = self._component_value(specular, "r")
            g = self._component_value(specular, "g")
            b = self._component_value(specular, "b")
            if r is None or g is None or b is None:
                return 0.15
            return max(0.0, min(1.0, (r + g + b) / 3.0))

        return max(0.0, min(1.0, self._to_float(specular, 0.15) or 0.15))


    def _component_value(self, colour, name):

        value = getattr(colour, name, None)
        if value is None:
            return None

        if callable(value):
            try:
                value = value()
            except Exception:
                return None

        return self._to_float(value)


    def _resolve_material_index(self, material_ids, triangle_count, triangle_index, face_index):

        if not material_ids:
            return None

        if len(material_ids) == triangle_count:
            return material_ids[triangle_index]
        if len(material_ids) == triangle_count * 3 and face_index < len(material_ids):
            return material_ids[face_index]
        return material_ids[triangle_index] if triangle_index < len(material_ids) else None


    def _style_signature_from_palette(self, palette, material_index):

        if material_index is not None and 0 <= material_index < len(palette):
            return palette[material_index]

        return self.DEFAULT_STYLE


    def _to_float(self, value, default=None):

        if value is None:
            return default

        if callable(value):
            try:
                value = value()
            except Exception:
                return default

        try:
            return float(str(value))
        except (TypeError, ValueError):
            return default