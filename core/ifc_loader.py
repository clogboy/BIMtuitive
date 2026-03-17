import ifcopenshell


class IfcLoader:

    def load(self, path):

        print(f"Loading IFC: {path}")

        model = ifcopenshell.open(path)

        return model
