import bpy
import materialBake
import fbxExport

bl_info = {
    "name": "Lookdev Export Tool",
    "author": "Lucas Santos",
    "version": (1, 0),
    "blender": (4, 20, 0),
    "location": "View3D > Toolbar > Lookdev",
    "description": "Exports lookdev materials to a JSON file",
    "warning": "",
    "wiki_url": "",
    "category": "Lookdev Export",
}

class LookdevPanel(bpy.types.Panel):
    """Creates a Panel in the 3D View"""
    bl_label = 'Lookdev Export'
    bl_idname = 'VIEW3D_PT_lookdev_export'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Lookdev'
    
    def draw(self, context):
        layout = self.layout
        
        row = layout.row()
        row.label(text='Export Scene Lookdev', icon = 'IMAGE')
        row = layout.row()
        row.operator('lookdev.bake_materials',icon='CUBE', text='Bake Scene Materials and Save FBX')

        
class LookDevBakeMaterials(bpy.types.Operator):
    """Bake materials to a external file"""
    bl_idname = 'lookdev.bake_materials'
    bl_label = 'Bake Materials'
    bl_options = {'REGISTER', 'UNDO'}
    
    fileFormat : bpy.props.StringProperty(name='File Format', default='JPEG')
    textureResolution : bpy.props.IntProperty(name='Texture Resolution', default=4096)
    
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "textureResolution")
        layout.prop(self, "fileFormat")
        layout.label(text="WARNING: ")
        layout.label(text="Pressing OK saves this file,then opens a new file.")
    
    
    def execute(self, context):
        materialBake.bakeAllMaterials(self.textureResolution, self.fileFormat)
        fbxExport.exportVisibleMeshesAsFbx()
        print('Baking materials...') # This does not work. Seems like nothing in this function prints.
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
        
    


        
        
def register():
    print("Register function called")  # Debug print
    bpy.utils.register_class(LookdevPanel)
    bpy.utils.register_class(LookDevBakeMaterials)
def unregister():
    bpy.utils.unregister_class(LookdevPanel)
    bpy.utils.unregister_class(LookDevBakeMaterials)

if __name__ == '__main__':
    register()
    