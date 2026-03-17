class TreeModel:

    def build(self, index):

        tree = {}

        for element in index.elements:

            tree[element.id] = element

        return tree
