# fbxExport.py

import bpy
import os

def exportVisibleMeshesAsFbx(filepath=''):
    """
    Export visible mesh objects as FBX with specific settings.
    If no filepath is given, saves next to the open .blend file.
    
    Args:
        filepath (str): Full path where the FBX should be saved
    """
    if not filepath:
        filepath = saveNextToCurrentFile()

    # Export FBX with specific settings
    bpy.ops.export_scene.fbx(
        filepath=filepath,
        use_visible=True,
        global_scale=1.0,
        apply_unit_scale=True,
        apply_scale_options='FBX_SCALE_NONE',
        use_space_transform=True,
        bake_space_transform=False,
        
        # Geometry settings
        use_mesh_modifiers=True,
        use_subsurf=True,
        mesh_smooth_type='OFF',
        
        # Disable animation
        bake_anim=False,
        bake_anim_use_all_bones=False,
        bake_anim_use_nla_strips=False,
        bake_anim_use_all_actions=False,
        bake_anim_force_startend_keying=False,
        
        # Other common settings
        axis_forward='-Z',
        axis_up='Y',
        use_custom_props=False,
        path_mode='AUTO',
        embed_textures=True,
        batch_mode='OFF',
        use_batch_own_dir=False
    )
    
def saveNextToCurrentFile():
    """
    Saves the current file with a new name in the same directory.
    
    Args:
        filepath (str): The path to save the new file to.
        
    Returns:
        str: The path to the new file.
    """
    currentPath = bpy.data.filepath
    currentFilepath, currentFileName = os.path.split(currentPath)
    currentFileName = os.path.splitext(currentFileName)[0]
    newFileName = f"{currentFileName}_sceneExport.fbx"
    exportPath = os.path.join(currentFilepath, newFileName)
    
    return exportPath


    