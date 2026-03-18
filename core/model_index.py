class ElementNode:

    def __init__(self, eid, name, etype):

        self.id = eid
        self.name = name
        self.type = etype


class ModelIndex:

    def __init__(self):

        self.elements = []

    def build(self, model):
        self.elements = [
            ElementNode(
                element.id(),
                element.Name if element.Name else "Unnamed",
                element.is_a(),
            )
            for element in model.by_type("IfcProduct")
        ]
