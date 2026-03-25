import os
from dataclasses import dataclass
from typing import Any, cast

import ifcopenshell.geom
import ifcopenshell
import numpy as np
from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot
from vispy.color import Color
from vispy.scene.visuals import Mesh


@dataclass(frozen=True)
class MeshData:
    vertices: np.ndarray
    faces: np.ndarray
    face_colors: np.ndarray | None = None
    bounds_min: np.ndarray | None = None
    bounds_max: np.ndarray | None = None
    origin: np.ndarray | None = None


DEFAULT_RGBA = np.array([0.77, 0.78, 0.81, 1.0], dtype=np.float32)


def _to_float(value, default=0.0):
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


def _material_rgba(material):
    default_rgba = DEFAULT_RGBA
    if material is None:
        return default_rgba

    diffuse = getattr(material, "diffuse", None)
    if diffuse is None:
        return default_rgba

    r = _to_float(getattr(diffuse, "r", None), default_rgba[0])
    g = _to_float(getattr(diffuse, "g", None), default_rgba[1])
    b = _to_float(getattr(diffuse, "b", None), default_rgba[2])
    transparency = _to_float(getattr(material, "transparency", None), 0.0)

    rgba = np.array(
        [
            max(0.0, min(1.0, r)),
            max(0.0, min(1.0, g)),
            max(0.0, min(1.0, b)),
            max(0.05, min(1.0, 1.0 - transparency)),
        ],
        dtype=np.float32,
    )
    return rgba


def _triangle_material_indices(material_ids, triangle_count):
    if triangle_count <= 0:
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


def _face_colors_from_geometry(geometry, triangle_count):
    face_colors = np.tile(DEFAULT_RGBA, (triangle_count, 1))

    materials = list(getattr(geometry, "materials", []) or [])
    material_ids = list(getattr(geometry, "material_ids", []) or [])
    if not materials or not material_ids:
        return face_colors

    palette = [_material_rgba(material) for material in materials]
    tri_material_ids = _triangle_material_indices(material_ids, triangle_count)

    palette_array = np.asarray(palette, dtype=np.float32)
    valid = (tri_material_ids >= 0) & (tri_material_ids < len(palette_array))
    if np.any(valid):
        face_colors[valid] = palette_array[tri_material_ids[valid]]

    return face_colors


def _compute_bounds(vertices):
    return vertices.min(axis=0), vertices.max(axis=0)


class MeshSignals(QObject):
    ready = pyqtSignal(object)
    progress = pyqtSignal(int, int)
    done = pyqtSignal(bool)


class MeshWorker(QRunnable):
    def __init__(self, element, settings, origin=None):
        super().__init__()
        self.element = element
        self.settings = settings
        self.origin = origin
        self.signals = MeshSignals()

    @pyqtSlot()
    def run(self):
        try:
            shape = ifcopenshell.geom.create_shape(self.settings, self.element)
            geometry = cast(Any, getattr(shape, "geometry", shape))
            if not hasattr(geometry, "verts") or not hasattr(geometry, "faces"):
                return

            vertices_raw = np.asarray(geometry.verts, dtype=np.float32).reshape(-1, 3)
            if vertices_raw.size == 0:
                return

            center = self.origin if self.origin is not None else np.mean(vertices_raw, axis=0, dtype=np.float32)
            center = np.asarray(center, dtype=np.float32)
            vertices_raw -= center
            faces = np.asarray(geometry.faces, dtype=np.uint32).reshape(-1, 3)
            if faces.size == 0:
                return

            face_colors = _face_colors_from_geometry(geometry, len(faces))
            bounds_min, bounds_max = _compute_bounds(vertices_raw)

            self.signals.ready.emit(
                MeshData(
                    vertices=vertices_raw,
                    faces=faces,
                    face_colors=face_colors,
                    bounds_min=bounds_min,
                    bounds_max=bounds_max,
                    origin=center,
                )
            )
        except Exception as exc:
            print(f"Geometrie fout voor #{self.element.id()}: {exc}")


class FullModelWorker(QRunnable):
    def __init__(self, model_path, settings, iterator_threads=5, use_iterator=False):
        super().__init__()
        self.model_path = model_path
        self.settings = settings
        self.iterator_threads = max(1, int(iterator_threads))
        self.use_iterator = bool(use_iterator)
        self.signals = MeshSignals()

    @pyqtSlot()
    def run(self):
        try:
            model = ifcopenshell.open(self.model_path)
            products = [
                product
                for product in model.by_type("IfcProduct")
                if bool(getattr(product, "Representation", None))
            ]
            total_products = len(products)

            if total_products <= 0:
                self.signals.progress.emit(0, 0)
                self.signals.done.emit(False)
                return

            self.signals.progress.emit(0, total_products)
            progress_step = max(25, total_products // 100)

            if self.use_iterator:
                vertices_chunks, faces_chunks, color_chunks = self._collect_with_iterator(
                    model,
                    total_products,
                    progress_step,
                )
                if not vertices_chunks:
                    # Fallback keeps robustness when iterator is unstable on specific platforms/files.
                    vertices_chunks, faces_chunks, color_chunks = self._collect_sequential(
                        products,
                        total_products,
                        progress_step,
                    )
            else:
                vertices_chunks, faces_chunks, color_chunks = self._collect_sequential(
                    products,
                    total_products,
                    progress_step,
                )

            if not vertices_chunks:
                self.signals.done.emit(False)
                return

            merged_vertices = np.vstack(vertices_chunks)
            merged_faces = np.vstack(faces_chunks)
            merged_face_colors = np.vstack(color_chunks) if color_chunks else None
            origin = np.asarray(np.mean(merged_vertices, axis=0, dtype=np.float32), dtype=np.float32)
            merged_vertices -= origin
            bounds_min, bounds_max = _compute_bounds(merged_vertices)
            self.signals.ready.emit(
                MeshData(
                    vertices=merged_vertices,
                    faces=merged_faces,
                    face_colors=merged_face_colors,
                    bounds_min=bounds_min,
                    bounds_max=bounds_max,
                    origin=origin,
                )
            )
            self.signals.done.emit(True)
        except Exception as exc:
            print(f"Modelgeometrie fout: {exc}")
            self.signals.done.emit(False)

    def _collect_with_iterator(self, model, total_products, progress_step):
        vertices_chunks = []
        faces_chunks = []
        color_chunks = []
        vertex_offset = 0

        try:
            iterator = ifcopenshell.geom.iterator(self.settings, model, self.iterator_threads)
            if not iterator.initialize():
                return [], [], []

            processed = 0
            while True:
                shape = iterator.get()
                geometry = cast(Any, getattr(shape, "geometry", shape))
                if hasattr(geometry, "verts") and hasattr(geometry, "faces"):
                    vertices = np.asarray(geometry.verts, dtype=np.float32).reshape(-1, 3)
                    faces = np.asarray(geometry.faces, dtype=np.uint32).reshape(-1, 3)
                    if vertices.size and faces.size:
                        vertices_chunks.append(vertices)
                        faces_chunks.append(faces + vertex_offset)
                        color_chunks.append(_face_colors_from_geometry(geometry, len(faces)))
                        vertex_offset += len(vertices)

                processed += 1
                if processed % progress_step == 0 or processed >= total_products:
                    self.signals.progress.emit(min(processed, total_products), total_products)

                if not iterator.next():
                    break
        except Exception as exc:
            print(f"Iterator fallback: {exc}")
            return [], [], []

        return vertices_chunks, faces_chunks, color_chunks

    def _collect_sequential(self, products, total_products, progress_step):
        vertices_chunks = []
        faces_chunks = []
        color_chunks = []
        vertex_offset = 0

        for index, product in enumerate(products, start=1):
            try:
                shape = ifcopenshell.geom.create_shape(self.settings, product)
            except Exception:
                if index % progress_step == 0 or index >= total_products:
                    self.signals.progress.emit(index, total_products)
                continue

            geometry = cast(Any, getattr(shape, "geometry", shape))
            if hasattr(geometry, "verts") and hasattr(geometry, "faces"):
                vertices = np.asarray(geometry.verts, dtype=np.float32).reshape(-1, 3)
                faces = np.asarray(geometry.faces, dtype=np.uint32).reshape(-1, 3)
                if vertices.size and faces.size:
                    vertices_chunks.append(vertices)
                    faces_chunks.append(faces + vertex_offset)
                    color_chunks.append(_face_colors_from_geometry(geometry, len(faces)))
                    vertex_offset += len(vertices)

            if index % progress_step == 0 or index >= total_products:
                self.signals.progress.emit(index, total_products)

        return vertices_chunks, faces_chunks, color_chunks


class IfcGeometryController:
    def __init__(self):
        self._use_world_coords = True
        self._cache_shapes = True
        self._mesh_cache = {}
        self._model_origin = None
        self._uploaded_mesh_per_visual = {}
        self._model_mesh_cache = {}

    def _create_settings(self):
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, self._use_world_coords)
        settings.set("cache-shapes", self._cache_shapes)
        return settings

    def can_render(self, ifc_object):
        return (
            ifc_object is not None
            and ifc_object.is_a("IfcProduct")
            and bool(getattr(ifc_object, "Representation", None))
        )

    def create_mesh_visual(self, parent_scene, color="royalblue"):
        return Mesh(shading="flat", color=Color(color), parent=parent_scene)

    def create_worker(self, ifc_object):
        # Create independent settings per worker to avoid cross-thread native state issues.
        return MeshWorker(ifc_object, self._create_settings(), origin=self._model_origin)

    def create_model_worker(self, model_path):
        # Open IFC in the worker to avoid sharing one native model object across threads.
        # Iterator-based meshing is opt-in because it can be unstable on some systems/files.
        use_iterator = os.environ.get("IFC_ENABLE_ITERATOR", "0") == "1"
        worker = FullModelWorker(
            model_path,
            self._create_settings(),
            iterator_threads=max(1, (os.cpu_count() or 2) - 1),
            use_iterator=use_iterator,
        )
        return worker

    def reset(self):
        self._mesh_cache.clear()
        self._model_origin = None
        self._uploaded_mesh_per_visual.clear()

    def clear_model_cache(self):
        self._model_mesh_cache.clear()

    def _file_signature(self, model_path):
        try:
            stat = os.stat(model_path)
            return (os.path.abspath(model_path), int(stat.st_mtime_ns), int(stat.st_size))
        except OSError:
            return None

    def get_cached_model_mesh(self, model_path):
        signature = self._file_signature(model_path)
        if signature is None:
            return None
        return self._model_mesh_cache.get(signature)

    def cache_model_mesh(self, model_path, mesh_data):
        signature = self._file_signature(model_path)
        if signature is None or mesh_data is None:
            return
        self._model_mesh_cache[signature] = mesh_data

    def set_model_mesh(self, mesh_data):
        self._model_origin = mesh_data.origin
        self._mesh_cache.clear()

    def get_cached_mesh(self, ifc_object):
        if ifc_object is None:
            return None
        return self._mesh_cache.get(ifc_object.id())

    def cache_mesh(self, ifc_object, mesh_data):
        if ifc_object is None or mesh_data is None:
            return
        self._mesh_cache[ifc_object.id()] = mesh_data

    def clear_visual(self, mesh_visual, canvas):
        self._uploaded_mesh_per_visual.pop(id(mesh_visual), None)
        mesh_visual.visible = False
        mesh_visual.update()
        canvas.update()

    def update_visual(self, mesh_visual, view, canvas, mesh_data, focus=True):
        if mesh_data is None:
            return

        if mesh_data.vertices.size == 0 or mesh_data.faces.size == 0:
            return

        mesh_visual.visible = True
        visual_key = id(mesh_visual)
        mesh_key = id(mesh_data)
        needs_upload = self._uploaded_mesh_per_visual.get(visual_key) != mesh_key
        if needs_upload:
            if mesh_data.face_colors is not None and len(mesh_data.face_colors) == len(mesh_data.faces):
                mesh_visual.set_data(
                    vertices=mesh_data.vertices,
                    faces=mesh_data.faces,
                    face_colors=mesh_data.face_colors,
                )
            else:
                mesh_visual.set_data(vertices=mesh_data.vertices, faces=mesh_data.faces)
            self._uploaded_mesh_per_visual[visual_key] = mesh_key

        if focus:
            min_corner = mesh_data.bounds_min if mesh_data.bounds_min is not None else mesh_data.vertices.min(axis=0)
            max_corner = mesh_data.bounds_max if mesh_data.bounds_max is not None else mesh_data.vertices.max(axis=0)
            center = (min_corner + max_corner) * 0.5
            view.camera.center = tuple(center.tolist())
            view.camera.set_range(
                x=(float(min_corner[0]), float(max_corner[0])),
                y=(float(min_corner[1]), float(max_corner[1])),
                z=(float(min_corner[2]), float(max_corner[2])),
                margin=0.1,
            )
        mesh_visual.update()
        canvas.update()