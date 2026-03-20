from ifcopenshell import geom
import numpy as np


class IfcVispyMeshHelper:

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

            for signature, mesh in groups.items():
                grouped.setdefault(signature, []).append(mesh)

            count += 1

        if count == 0:
            return [], 0

        meshes = []
        for signature, parts in grouped.items():
            merged = self._merge_mesh_parts(parts)
            if merged is not None:
                vertices, faces = merged
                faces = self._fix_winding(vertices, faces)
                meshes.append({"vertices": vertices, "faces": faces, "style": signature})

        return meshes, count


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

        meshes = []
        for signature, mesh in groups.items():
            vertices, faces = mesh
            faces = self._fix_winding(vertices, faces)
            meshes.append({"vertices": vertices, "faces": faces, "style": signature})

        return meshes


    def _merge_mesh_parts(self, parts):

        if not parts:
            return None

        if len(parts) == 1:
            return parts[0]

        vertices_chunks = []
        faces_chunks = []
        offset = 0
        for vertices, faces in parts:
            vertices_chunks.append(vertices)
            faces_chunks.append(faces + offset)
            offset += len(vertices)

        return np.vstack(vertices_chunks), np.vstack(faces_chunks)


    def _fix_winding(self, vertices, faces):

        if len(vertices) == 0 or len(faces) == 0:
            return faces

        v0 = vertices[faces[:, 0]]
        v1 = vertices[faces[:, 1]]
        v2 = vertices[faces[:, 2]]
        signed_volume = np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0

        if signed_volume < 0.0:
            return faces[:, [0, 2, 1]]

        return faces


    def _extract_geometry(self, shape):
        geometry = getattr(shape, "geometry", shape)
        return geometry if hasattr(geometry, "verts") and hasattr(geometry, "faces") else None


    def _to_poly_data_by_material(self, geometry):

        vertices = getattr(geometry, "verts", None)
        faces = getattr(geometry, "faces", None)
        if not vertices or not faces:
            return {}

        verts = np.asarray(vertices, dtype=np.float32).reshape(-1, 3)
        tris = np.asarray(faces, dtype=np.uint32).reshape(-1, 3)
        if len(tris) == 0:
            return {}

        styles = self._build_material_palette(getattr(geometry, "materials", []) or [])
        material_ids = list(getattr(geometry, "material_ids", []) or [])
        tri_materials = self._triangle_material_indices(material_ids, len(tris))

        mesh_by_material = {}
        for material_index in np.unique(tri_materials):
            signature = self._style_signature_from_palette(styles, None if material_index < 0 else int(material_index))

            selected = tri_materials == material_index
            group_faces = tris[selected]
            if len(group_faces) == 0:
                continue

            unique_indices, inverse = np.unique(group_faces.reshape(-1), return_inverse=True)
            group_vertices = verts[unique_indices]
            remapped_faces = inverse.reshape(-1, 3).astype(np.uint32)

            mesh_by_material[signature] = (group_vertices, remapped_faces)

        return mesh_by_material


    def _triangle_material_indices(self, material_ids, triangle_count):

        if triangle_count == 0:
            return np.empty((0,), dtype=np.int32)

        if not material_ids:
            return np.full((triangle_count,), -1, dtype=np.int32)

        arr = np.asarray(material_ids, dtype=np.int32)
        if len(arr) == triangle_count:
            return arr
        if len(arr) == triangle_count * 3:
            return arr[::3]

        out = np.full((triangle_count,), -1, dtype=np.int32)
        count = min(triangle_count, len(arr))
        out[:count] = arr[:count]
        return out


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