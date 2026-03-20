class ElementNode:

    def __init__(self, eid, name, etype):

        self.id = eid
        self.name = name
        self.type = etype


class ModelIndex:

    def __init__(self):

        self.elements = []

    def build(self, model):
        self.model = model

        # lookup tables
        self.aggregates = {}
        self.contained = {}
        self.parent_of = {}

        # cache IFC objects
        self.objects = {}

        self._index_objects()
        self._index_relationships()

        project = self.model.by_type("IfcProject")[0]
        return self._build_node(project.GlobalId)
    
    def _index_objects(self):
        for obj in self.model.by_type("IfcObjectDefinition"):
            self.objects[obj.GlobalId] = obj

    def _index_relationships(self):

        # Aggregates (Project → Site → Building → Storey)
        for rel in self.model.by_type("IfcRelAggregates"):
            parent = rel.RelatingObject.GlobalId
            children = [o.GlobalId for o in rel.RelatedObjects]

            self.aggregates.setdefault(parent, []).extend(children)

            for c in children:
                self.parent_of[c] = parent

        # Contained (Storey → Elements)
        for rel in self.model.by_type("IfcRelContainedInSpatialStructure"):
            parent = rel.RelatingStructure.GlobalId
            children = [o.GlobalId for o in rel.RelatedElements]

            self.contained.setdefault(parent, []).extend(children)

            for c in children:
                self.parent_of[c] = parent

    # -------------------------
    # Tree builder
    # -------------------------

    def _build_node(self, guid):

        obj = self.objects.get(guid)

        if not obj:
            return None

        node = {
            "id": guid,
            "name": obj.Name if obj.Name else "Unnamed",
            "type": obj.is_a(),
            "children": []
        }

        # eerst spatial structuur (aggregates)
        for child_id in self.aggregates.get(guid, []):
            child_node = self._build_node(child_id)
            if child_node:
                node["children"].append(child_node)

        # dan elementen (contained)
        for child_id in self.contained.get(guid, []):
            child_obj = self.objects.get(child_id)

            if not child_obj:
                continue

            node["children"].append({
                "id": child_id,
                "name": child_obj.Name if child_obj.Name else "Unnamed",
                "type": child_obj.is_a(),
                "children": []
            })

        return node