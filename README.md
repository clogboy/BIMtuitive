# BIMtuitive

Welcome to BIMtuitive!

This project is in a very early stage. The goal is to build an open source, extensible IFC viewer that runs cross-platform. It is written in Python and built on Qt6, IfcOpenShell, SQL, and OpenGL. The core idea is to export IFC data into a fast, queryable SQL database and support plugins. Performance and ease of use are key priorities.

Why SQL? I believe BIM should rely on accessible tools that can run on any hardware and operating system. In practice, every product that consumes IFC data stores it in its own native format. For that reason, it makes sense to keep versioned project data in a queryable source of truth, while still preserving references to geometric context.

Plugin support is intended to make the viewer useful for workflows such as cost estimation, planning, logistics, and other project-management tasks. The aim is to help teams work from the same version of project data and synchronize it with third-party sources.

Is it finished? Not even close. The main functionality exists, but it still needs testing and optimization. Current roadmap:

- UI development
- Loading IFC data
- Navigating mesh geometry
- Displaying objects in the context of spatial containment relations (treeview)
- Displaying property sets for selected elements
- SQL-native data management
- Model navigation and object selection
- API interfacing
- Documentation

Bonus:
- Additional relational contexts to organise elements
- Multi-model support
- A demo plugin to manage files, issues and data in a Solid pod

Instructions:
Once the program is completed I will create binaries to streamline the installation or run the IFC File Companion as a portable, stand-alone executable/appimage.

If you want to test the project as-is, clone this repository and run it in a virtual environment:
Make sure to have Python 3.x installed on your machine, and added as a PATH variable (happens automatically on Linux, needs admin permission on Windows).
Open a command window in the cloned repository and type "python3 -m venv .venv". This creates a version of the Python environment in the project folder.
The reason for this is to maintain any dependencies contained to the project folder instead of installing them system-wide.

Activate it. On Linux: type "source .venv/bin/activate". On Windows, type ".venv\scripts\activate". Windows users will probably have to enable script execution first.
This can be done in a PowerShell window with admin privileges, by typing "Set-ExecutionPolicy RemoteSigned".

If you see the .venv prefix in your command window, type "pip install -r requirements.txt". This will install all dependencies that are mentioned in requirements.txt.
When this is complete, start the program with "python3 main.py"
