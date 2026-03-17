# BIMtuitive

Welcome to BIMtuitive!

I'm in the very early stages of development, but when I'm done this will be one of the first open source, extensible IFC viewers. The aim is to make this a cross-platform solution (written in Python and based on QT6, IfcOpenShell, SQL and OpenGL) which exports the IFC data to a fast performing, queriable SQL database and supports plugins. Performance and ease of use are a main focus.

Why SQL? Because I believe that BIM should be based on accessible tools that run on any hardware and operating system. In practice, any product that consumes IFC data will store it in its own native format. So to me it makes sense that versioned data should live as a queriable source of truth. as long as it can still maintain a reference to its geometric context.
The intent to support plugins that interact with the data will make it possible to use this viewer for cost estimation, planning, logistics and other project management operations in a way that should enable everyone to work with the same version of the project data which can be easily updated and synchronised with third party data sources.

Is it finished? No, not by a long shot. My roadmap is as follows:

- UI development
- Loading and testing IFC data
- Displaying objects in the context of spatial containment relations (treeview)
- Displaying property sets for selected elements
- Navigating mesh geometry and selecting objects
- SQL-native data management
- Performance optimisations
- API interfacing
- Documentation

- BONUS:
- Additional relational contexts to organise elements
- Multi-model support
- A demo plugin to manage files, issues and data in a Solid pod

Instructions:
Whomever wants to test this product as-is, is welcome to clone this repo. Once in this cloned project folder it is recommended to test this in a virtual environment with the following commands:
- python3 -m venv .venv
- source .venv/bin/activate(.bat for Windows)
- pip install -r requirements.txt (this will install the PyQt6, IfcOpenShell, vtk and SqLite-utils dependencies)
- python3 main.py
