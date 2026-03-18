from ifcopenshell import geom
import vtk


class IfcVtkMeshHelper:

    def __init__(self):

        self.geom = geom
        if self.geom is None:
            self.settings = None
            return

        self.settings = self.geom.settings()
        self.settings.set(self.settings.USE_WORLD_COORDS, True)


    def build_actors(self, model):

        if self.geom is None or self.settings is None:
            return [], 0

        grouped_poly_data = {}
        included = 0

        for element in model.by_type("IfcProduct"):

            if not getattr(element, "Representation", None):
                continue

            try:
                shape = self.geom.create_shape(self.settings, element)
            except Exception:
                continue

            geometry = self._extract_geometry(shape)
            if geometry is None:
                continue

            material_groups = self._to_poly_data_by_material(geometry)
            if not material_groups:
                continue

            for signature, poly_data in material_groups.items():
                grouped_poly_data.setdefault(signature, []).append(poly_data)

            included += 1

        if included == 0:
            return [], 0

        actors = []
        for signature, poly_data_parts in grouped_poly_data.items():
            actor = self._build_actor_from_parts(signature, poly_data_parts)
            if actor is not None:
                actors.append(actor)

        return actors, included


    def build_actor(self, model):
        # Backward-compatible wrapper for older call sites.
        actors, included = self.build_actors(model)
        if not actors:
            return None, 0

        if len(actors) == 1:
            return actors[0], included

        assembly = vtk.vtkAssembly()
        for actor in actors:
            assembly.AddPart(actor)

        return assembly, included


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
        normals.SetFeatureAngle(55.0)
        normals.Update()

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(normals.GetOutputPort())
        mapper.ScalarVisibilityOff()

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)

        style = self._style_from_signature(signature)
        prop = actor.GetProperty()
        prop.SetColor(style["diffuse"])
        prop.SetOpacity(style["opacity"])
        prop.SetAmbient(0.2)
        prop.SetDiffuse(0.8)
        prop.SetSpecular(style["specular_strength"])
        prop.SetSpecularPower(style["specular_power"])
        prop.SetInterpolationToPhong()
        prop.BackfaceCullingOff()

        return actor


    def _style_from_signature(self, signature):

        r, g, b, opacity, specular = signature
        return {
            "diffuse": (r / 255.0, g / 255.0, b / 255.0),
            "opacity": max(0.02, min(1.0, opacity)),
            "specular_strength": max(0.0, min(1.0, specular)),
            "specular_power": 70.0,
        }


    def _extract_geometry(self, shape):

        # Depending on IfcOpenShell build/settings, create_shape may return
        # an object with .geometry or the geometry-like object directly.
        geometry = getattr(shape, "geometry", shape)

        if not hasattr(geometry, "verts") or not hasattr(geometry, "faces"):
            return None

        return geometry


    def _to_poly_data_by_material(self, geometry):

        vertices = getattr(geometry, "verts", None)
        faces = getattr(geometry, "faces", None)
        if not vertices or not faces:
            return {}

        material_ids = list(getattr(geometry, "material_ids", []) or [])
        materials = list(getattr(geometry, "materials", []) or [])
        palette = self._build_material_palette(materials)

        groups = {}

        def ensure_group(signature):
            if signature in groups:
                return groups[signature]
            points = vtk.vtkPoints()
            triangles = vtk.vtkCellArray()
            index_map = {}
            groups[signature] = {
                "points": points,
                "triangles": triangles,
                "index_map": index_map,
            }
            return groups[signature]

        def remap_point(group, source_index):
            idx = group["index_map"].get(source_index)
            if idx is not None:
                return idx

            base = source_index * 3
            new_idx = group["points"].InsertNextPoint(
                vertices[base], vertices[base + 1], vertices[base + 2]
            )
            group["index_map"][source_index] = new_idx
            return new_idx

        triangle_count = len(faces) // 3
        for i in range(0, len(faces), 3):
            tri_idx = i // 3
            material_index = self._resolve_material_index(material_ids, triangle_count, tri_idx, i)
            signature = self._style_signature_from_palette(palette, material_index)

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
            diffuse = self._rgb255_from_colour(getattr(material, "diffuse", None))
            transparency = self._number_value(getattr(material, "transparency", None), default=0.0)
            specular = self._specular_strength(getattr(material, "specular", None))
            opacity = max(0.0, min(1.0, 1.0 - transparency))

            palette.append((diffuse[0], diffuse[1], diffuse[2], opacity, specular))

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

        return (
            max(0, min(255, int(r * 255))),
            max(0, min(255, int(g * 255))),
            max(0, min(255, int(b * 255))),
        )


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

        value = self._number_value(specular, default=0.15)
        return max(0.0, min(1.0, value))


    def _number_value(self, value, default=0.0):

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


    def _component_value(self, colour, name):

        value = getattr(colour, name, None)
        if value is None:
            return None

        if callable(value):
            try:
                value = value()
            except Exception:
                return None

        try:
            return float(str(value))
        except (TypeError, ValueError):
            return None


    def _resolve_material_index(self, material_ids, triangle_count, triangle_index, face_index):

        if not material_ids:
            return None

        if len(material_ids) == triangle_count:
            return material_ids[triangle_index]

        # Some builds expose material ids per face index list entry.
        if len(material_ids) == triangle_count * 3 and face_index < len(material_ids):
            return material_ids[face_index]

        if triangle_index < len(material_ids):
            return material_ids[triangle_index]

        return None


    def _style_signature_from_palette(self, palette, material_index):

        if material_index is None:
            return 180, 180, 185, 1.0, 0.15

        if 0 <= material_index < len(palette):
            return palette[material_index]

        return 180, 180, 185, 1.0, 0.15