from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem


class TreeController:

    NODE_ROLE = Qt.ItemDataRole.UserRole
    NODE_LOADED_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(self, tree: QTreeWidget):
        self.tree = tree
        self.tree.setHeaderLabels(["Element"])
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.itemExpanded.connect(self.on_item_expanded)

    def populate(self, node):

        self.tree.clear()
        self.tree.setUpdatesEnabled(False)
        self.tree.blockSignals(True)
        self.tree.setSortingEnabled(True)

        try:
            self.tree.addTopLevelItem(self._create_node_item(node))
        finally:
            self.tree.blockSignals(False)
            self.tree.setUpdatesEnabled(True)

        self.tree.sortItems(0, Qt.SortOrder.AscendingOrder)

    def selected_nodes(self):

        selected = []
        for item in self.tree.selectedItems():
            node = item.data(0, self.NODE_ROLE)
            if node:
                selected.append(node)

        return selected

    def node_from_item(self, item):

        return item.data(0, self.NODE_ROLE)

    def clear_selection(self):

        self.tree.clearSelection()
        self.tree.setCurrentItem(None)

    def _create_node_item(self, node):

        item = QTreeWidgetItem([node["name"]])
        item.setData(0, self.NODE_ROLE, node)
        item.setData(0, self.NODE_LOADED_ROLE, False)

        if node.get("children"):
            item.addChild(QTreeWidgetItem(["..."]))

        return item

    def on_item_expanded(self, item):

        node = item.data(0, self.NODE_ROLE)
        if not node:
            return

        if item.data(0, self.NODE_LOADED_ROLE):
            return

        item.takeChildren()

        if node["type"] == "IfcBuildingStorey":
            grouped = {}
            for child in node.get("children", []):
                grouped.setdefault(child["type"], []).append(child)

            for element_type in sorted(grouped):
                group_item = QTreeWidgetItem([f"{element_type} ({len(grouped[element_type])})"])
                item.addChild(group_item)
                for child in grouped[element_type]:
                    group_item.addChild(self._create_node_item(child))
        else:
            for child in node.get("children", []):
                item.addChild(self._create_node_item(child))

        item.setData(0, self.NODE_LOADED_ROLE, True)
