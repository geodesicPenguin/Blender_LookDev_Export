bl_info = {
    "name": "Lookdev Export Tool",
    "author": "Lucas Santos",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Toolbar > Lookdev",
    "description": "Exports lookdev materials and FBXto file",
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