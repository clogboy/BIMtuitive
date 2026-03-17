class ElementNode:

    def __init__(self, eid, name, etype):

        self.id = eid
        self.name = name
        self.type = etype


class ModelIndex:

    def __init__(self):

        self.elements = []

    def build(self, model):

        for element in model.by_type("IfcProduct"):

            name = element.Name if element.Name else "Unnamed"

            node = ElementNode(
                element.id(),
                name,
                element.is_a()
            )

            self.elements.append(node)
