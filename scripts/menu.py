import bpy
from . import materialBake
from . import fbxExport


class LookdevPanel(bpy.types.Panel):
    """Creates a Panel in the 3D View"""
    bl_label = 'Lookdev Export'
    bl_idname = 'VIEW3D_PT_lookdev_export'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Lookdev' # This will be the tab name in the sidebar
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.ui_properties
        
        layout.scale_y = 1.2
        
        layout.label(text='Bake and Export Materials')
        box = layout.box()
        
        box.prop(props, "textureResolution")
        box.prop(props, "fileFormat")
        box.prop(props, "isCopyingTextures")
        box.prop(props, "isExportingFBX")
        box.prop(props, "isDefaultExportLocation")

        
        # Only enable filePath if not using default location
        row = box.row()
        row.enabled = not props.isDefaultExportLocation
        row.prop(props, "filePath")
        
        row.operator("lookdev.browse_for_folder",text='',icon="FILE_FOLDER")
        
        box.operator("lookdev.export_materials",text='Bake and Export')


class UiProperties(bpy.types.PropertyGroup):
    """All UI Properties"""
    textureResolution: bpy.props.IntProperty(name="Texture Resolution", description="Resolution of the texture", default=4096)
    fileFormat: bpy.props.EnumProperty(name="File Format", description="File format of the texture", items=[("PNG", "PNG", "Portable Network Graphics"), ("JPEG", "JPEG", "Joint Photographic Experts Group"), ("TIFF", "TIFF", "Tagged Image File Format")], default="PNG")
    isCopyingTextures: bpy.props.BoolProperty(name='Save all textures to save location', description='Copies all image textures to save location (Keeps textures organized, since all the new baked textures will be next to the default image textures)', default=True)
    isExportingFBX: bpy.props.BoolProperty(name="Export with FBX", description="Export the scene geometry and lights as an FBX file with all the baked textures auto-applied", default=True)
    isDefaultExportLocation: bpy.props.BoolProperty(name="Save Next To File", description="Save the files next to the current Blender file", default=True)
    filePath: bpy.props.StringProperty(name="Filepath", description="Directory to save files to. Default will create a subfolder called 'scene_export' in the current Blender file location.", default='')


class BrowseForFolderOperator(bpy.types.Operator):
    """Browse for a folder"""
    bl_idname = "lookdev.browse_for_folder"
    bl_label = "Browse for Folder"
    
    directory: bpy.props.StringProperty(
        name="Export Directory",
        description="Choose a directory",
        subtype='DIR_PATH'
    )
    
    def execute(self, context):
        # Update the filePath property with the selected directory
        context.scene.ui_properties.filePath = self.directory
        return {'FINISHED'}
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    

class ExportMaterialsOperator(bpy.types.Operator):
    """Export Materials"""
    bl_idname = "lookdev.export_materials"
    bl_label = "Save and Export?"
    
    def draw(self, context):
        layout = self.layout
        layout.scale_y = 1.2
        layout.label(text='The file will save before exporting.')
        layout.label(text='A new file will be made with the baked textures applied.')
    
    def execute(self, context):
        props = context.scene.ui_properties
        
        print("Exporting materials...")
        
        resolution = props.textureResolution
        fileFormat = props.fileFormat
        isCopyingTextures = props.isCopyingTextures
        filePath = props.filePath
        
        materialBake.MaterialBaker(resolution, fileFormat, isCopyingTextures, filePath)
        
        if props.isExportingFBX:
            fbxExport.exportMeshesAndLightsAsFbx(filePath)
            
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


def register():
    bpy.utils.register_class(UiProperties)
    bpy.types.Scene.ui_properties = bpy.props.PointerProperty(type=UiProperties)
    
    bpy.utils.register_class(BrowseForFolderOperator)
    bpy.utils.register_class(ExportMaterialsOperator)
    bpy.utils.register_class(LookdevPanel)

def unregister():
    bpy.utils.unregister_class(UiProperties)
    bpy.utils.unregister_class(BrowseForFolderOperator)
    bpy.utils.unregister_class(ExportMaterialsOperator)
    bpy.utils.unregister_class(LookdevPanel)

