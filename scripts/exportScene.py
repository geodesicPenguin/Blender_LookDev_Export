# exportScene.py

import bpy
import os

def saveBlendFile():
    """
    Saves a copy of the current .blend file in a 'scene_export' subdirectory.
    Creates the directory if it doesn't exist.
    """
    # Ask user for confirmation before saving
    if not bpy.app.background:  # Only show popup if running in UI mode
        result = bpy.context.window_manager.invoke_props_dialog(None, width=400)
        if not result:
            return None
            
        def draw(self, context):
            self.layout.label(text="This operation will save a copy of your file.")
            self.layout.label(text="Do you want to continue?")
            
        bpy.context.window_manager.popup_menu(draw, title="Save Confirmation", icon='QUESTION')
    
    # Get current .blend filepath
    current_filepath = bpy.data.filepath
    
    if not current_filepath:
        raise Exception("Please save the .blend file first")
        
    # Get directory of current file
    current_dir = os.path.dirname(current_filepath)
    
    # Create scene_export subdirectory if it doesn't exist
    export_dir = os.path.join(current_dir, "scene_export")
    os.makedirs(export_dir, exist_ok=True)
    
    # Get filename without path
    filename = os.path.basename(current_filepath)
    
    # Create new filepath in scene_export directory
    new_filepath = os.path.join(export_dir, filename)
    
    # Save copy of .blend file
    bpy.ops.wm.save_as_mainfile(filepath=new_filepath, copy=True)
    
    return new_filepath
