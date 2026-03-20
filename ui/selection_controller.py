from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu

import ifcopenshell.util.element


class SelectionController:

    def __init__(self, tree_controller, viewer, status_callback, menu_parent):
        self.tree_controller = tree_controller
        self.viewer = viewer
        self.status = status_callback
        self.menu_parent = menu_parent
        self.model = None

        self.tree_controller.tree.itemDoubleClicked.connect(self.on_tree_item_double_clicked)
        self.viewer.context_menu_requested.connect(self._on_viewer_context_menu)

    def set_model(self, model):
        self.model = model

    def on_tree_item_double_clicked(self, item, _column):

        if self.model is None:
            return

        node = self.tree_controller.node_from_item(item)
        if not node:
            return

        node_id = node.get("id")
        if not node_id:
            return

        element = self.model.by_guid(node_id)
        if element is None:
            return

        psets = ifcopenshell.util.element.get_psets(element)
        isolated = self.viewer.isolate_elements([element], zoom=True)
        print(f"{node.get('type')} {node.get('name')} ({node_id})")
        print(psets)

        if isolated:
            self.status(f"Loaded {len(psets)} property sets and isolated {node.get('name')}")
        else:
            self.status(f"Loaded {len(psets)} property sets for {node.get('name')}")

    def on_viewer_context_menu(self, parent, global_pos):

        menu = QMenu(parent)

        selected_elements = self._selected_elements_from_tree()
        can_show_selected = len(selected_elements) > 0
        can_show_all = self.viewer.can_show_all()

        show_selected_action = QAction("Show Selected", parent)
        show_selected_action.setEnabled(can_show_selected)
        menu.addAction(show_selected_action)

        show_all_action = QAction("Show All", parent)
        show_all_action.setEnabled(can_show_all)
        menu.addAction(show_all_action)

        action = menu.exec(global_pos)
        if action == show_selected_action:
            isolated = self.viewer.isolate_elements(selected_elements, zoom=True)
            if isolated:
                self.status(f"Isolated {len(selected_elements)} selected element(s)")
            else:
                self.status("Could not isolate selected elements")
        elif action == show_all_action:
            self.viewer.show_all_model(reset_camera=True)
            self.tree_controller.clear_selection()
            self.status("Full model restored")

    def _on_viewer_context_menu(self, global_pos):

        self.on_viewer_context_menu(self.menu_parent, global_pos)

    def _selected_elements_from_tree(self):

        if self.model is None:
            return []

        elements = []
        for node in self.tree_controller.selected_nodes():
            element = self.model.by_guid(node.get("id"))
            if element is not None:
                elements.append(element)

        return elements
