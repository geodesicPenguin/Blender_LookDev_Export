bl_info = {
    "name": "Lookdev Export Tool",
    "author": "Lucas Santos",
    "version": (1, 0),
    "blender": (4, 20, 0),
    "location": "View3D > Toolbar > Lookdev",
    "description": "Exports lookdev materials to file",
    "warning": "",
    "wiki_url": "",
    "category": "Lookdev Export",
}
from . import menu

def register():
    menu.register()

def unregister():
    menu.unregister()

if __name__ == "__main__":
    register() 