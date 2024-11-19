#materialBake.py

import bpy
import os
#notes:
# make another func thatll connect the finished bake node to the BSDF node
# choose either to use the bpy objects or the names (if we use names, we will have to cast to the actual node object later)

def getAllMaterials():
    """
    Retrieves all node-based materials in the current Blender scene.
    
    Returns:
        tuple: A tuple containing all materials that use nodes.
    """
    materials = tuple(mat for mat in bpy.data.materials if isValidMaterial(mat))
    
    return materials


def isValidMaterial(material):
    """
    Checks if a material is valid for baking.
    
    Args:
        material: A Blender material object
        
    Returns:
        bool: True if the material meets the criteria, False otherwise
    """
    hasNodes = material.use_nodes
    hasUsers = material.users > 0
    isNotFake = not material.use_fake_user
    isOnMesh = any(obj for obj in bpy.data.objects if obj.type == 'MESH' and material.name in obj.material_slots) # may want to use obj.data.materials instead of obj.material_slots
    
    return hasNodes and hasUsers and isNotFake and isOnMesh


def getMaterialObjectFromName(materialName):
    """
    Gets a Blender material object from its name.
    A string of the name is not sufficient, as it cannot be used to perform material functions. We need the actual python object.
    
    Args:
        materialName (str): The name of the material to find
        
    Returns:
        bpy.types.Material: The material object if found, None otherwise
    """
    return bpy.data.materials.get(materialName)


def getNodeObjectFromName(nodeName, material):
    """
    Gets a Blender node object from its name.
    """
    return material.node_tree.nodes.get(nodeName)


def getObjectsFromMaterial(material):
    """
    Retrieves all mesh objects that use the specified material.
    
    Args:
        material: A Blender material object
        
    Returns:
        tuple: A tuple of Blender mesh objects that use this material
    """
    objects = tuple(obj for obj in bpy.context.scene.objects if material.name in obj.material_slots and obj.type == 'MESH')
    
    return objects


def analyzeShaderConnections():
    """
    Analyzes all materials in the scene to find non-texture inputs connected to 
    Principled BSDF nodes and displacement inputs connected to the Material Output node.
    
    This function examines each material's node tree, specifically looking at 
    Principled BSDF nodes and Material Output nodes. It identifies input channels 
    that have connections from nodes other than image texture nodes, or normal 
    and displacement nodes connected to texture nodes.
    
    
    Returns:
        dict: A dictionary where:
            - keys are material names (str)
            - values are dictionaries where:
                - keys are input channel names (str)
                - values are tuples of (node_name, output_socket_name)
    
    Example:
        {
            'Material.001': {
                'Base Color': ('RGB Curves.001', 'output_socket_name'),
                'Roughness': ('Mix RGB.003', 'output_socket_name')
            },
            'Material.002': {
                'Metallic': ('Value', 'output_socket_name'),
                'Normal': ('Normal Map.001', 'output_socket_name')
            }
        }
    """
    nonTextureInputs = {}
    materials = getAllMaterials()
        
    for material in materials:
        bakeChannelData = getBSDFBakeInputs(material)
        bakeDisplacementData = getDisplacementBakeInputs(material)
        
        if bakeChannelData or bakeDisplacementData:
            # Initialize the dictionary for this material
            if material.name not in nonTextureInputs:
                nonTextureInputs[material.name] = {}
            
            # Update with both dictionaries if they exist
            if bakeChannelData:
                nonTextureInputs[material.name].update(bakeChannelData)
            if bakeDisplacementData:
                nonTextureInputs[material.name].update(bakeDisplacementData)
            
            # Remove the material if it has no entries
            if not nonTextureInputs[material.name]:
                del nonTextureInputs[material.name]
            
    return nonTextureInputs


def getBSDFBakeInputs(material):
    """
    Analyzes a single material to find image texture inputs connected to its
    Principled BSDF node. If not found, we add the channel to the data set for baking.
    
    Args:
        material: A Blender material object
        
    Returns:
        dict: A dictionary where:
            - keys are input channel names (str)
            - values are tuples of (node_name, output_socket_name)
    """
    materialNodes = material.node_tree.nodes
    principledNode = next((node for node in materialNodes if node.type == 'BSDF_PRINCIPLED'), None)
    
    if principledNode:
        channelDict = {}
        
        for inputSocket in principledNode.inputs:
            if inputSocket.links:
                connectedNode = inputSocket.links[0].from_node
                outputSocket = inputSocket.links[0].from_socket  # Get the output socket of the node going to the input
                
                # Special handling for the Normal channel
                if inputSocket.name == 'Normal' and connectedNode.type == 'NORMAL_MAP':
                    # Check if Normal Map node has a texture input
                    if not any(link.from_node.type == 'TEX_IMAGE' for link in connectedNode.inputs[1].links):
                        channelDict[inputSocket.name] = (connectedNode.name, outputSocket.name)
                # For all other inputs
                elif connectedNode.type != 'TEX_IMAGE':
                    channelDict[inputSocket.name] = (connectedNode.name, outputSocket.name)
        
        return channelDict
    return {}  # Returns an empty dict if no Principled BSDF node is found


def getDisplacementBakeInputs(material):
    """
    Analyzes a single material to find if its Material Output node contains
    an image texture displacement input connected. If not, we add it to the data set for baking.
    Args:
        material: A Blender material object
        
    Returns:
        dict: A dictionary where:
            - keys are input channel names (str)
            - values are tuples of (node_name, output_socket_name)
    """
    materialNodes = material.node_tree.nodes
    outputNode = next((node for node in materialNodes if node.type == 'OUTPUT_MATERIAL'), None) # Finds the Material Output node, stops after the first one (should only be one per material slot)
    
    if outputNode:
        channelDict = {}
        
        # Check displacement input
        dispInput = outputNode.inputs['Displacement']
        if dispInput.links:
            connectedNode = dispInput.links[0].from_node
            outputSocket = dispInput.links[0].from_socket  # Get the output socket of the node going to the input
            
            if connectedNode.type == 'DISPLACEMENT':
                # Check if Displacement node has a texture input
                if not any(link.from_node.type == 'TEX_IMAGE' for link in connectedNode.inputs['Height'].links):
                    channelDict['Displacement'] = (connectedNode.name, outputSocket.name)
                    
        return channelDict
    return {}  # Returns an empty dict if no Material Output node is found


def setBakeOptions(useGPU=True):
    """
    Sets the bake options for the current scene.
    """
    bpy.context.scene.render.engine = 'CYCLES'
    bpy.context.scene.cycles.samples = 10 # Smaller sample size for faster baking. Negligible quality difference.
    
    if useGPU:
        bpy.context.scene.cycles.device = 'GPU'
    else:
        bpy.context.scene.cycles.device = 'CPU'
        
        
def createBakeImage(materialName, channel, resolution=1024):
    """
    Creates a new image texture and assigns it to the specified channel name.
    
    Args:
        materialName (str): The name of the material that the bake image belongs to
        channel (str): The name of the channel to bake
        resolution (int): The resolution of the bake image (default is 1024)
        
    Returns:
        bpy.types.Image: The newly created image texture
    """
    imageName = f"{materialName}_{channel}_baked"
    bakeImage = bpy.data.images.new(
        name=imageName,
        width=resolution,  
        height=resolution
    )
    return bakeImage

def setSelectedBakeImageNode(material, bakeImageNode):
    """
    Sets the specified texture node as the active node for baking.
    """
    material.node_tree.nodes.active = bakeImageNode

def createBakeImageNode(material, image):
    """
    Creates a new image texture node and assigns it to the specified image.
    
    Returns:
        bpy.types.ShaderNodeTexImage: The newly created image texture node
    """
    textureNode = material.node_tree.nodes.new('ShaderNodeTexImage')
    textureNode.image = image
    
    return textureNode

     
def setSelectedObjects(objects): 
    """
    Selects all given objects in the current scene.
    """
    for obj in objects:
        obj.select_set(True)
        
        
def bakeChannel(channel):
    """
    Bakes a single channel for the active object.
    
    Args:
        channel (str): The name of the channel to bake
    """
    bakeType = getBakeType(channel) 
    bpy.ops.object.bake(type=bakeType, 
                        normal_space='TANGENT', # For normal maps, ignored otherwise
                        margin=16)
                        # use_split_materials if multiple materials on 1 mesh?


def getBakeType(channel):
    """
    Maps material channels to their necessary bake types.
    EMIT is the default, as any map that is not a normal map can be baked with it.
    Normal maps are baked with NORMAL, as they need the normal bake settings to bake correctly.
    
    Args:
        channel (str): The channel name from the Principled BSDF or Material Output if baking displacement
        
    Returns:
        str: The corresponding Blender bake type
    """
    bake_types = {
        'Normal': 'NORMAL'
    }
    return bake_types.get(channel, 'EMIT')  # Default to EMIT if channel not found


def createBakeNetwork(materialName, nodeName, outputSocketName):
    """
    Connects a specified node to the Material Output node's Surface input.
    The node connected to the output node will be baked.
    This is temporary, as we will connect the finished texture nodes to the BSDF node later.
    
    Args:
        materialName (str): Name of the material containing the source node
        nodeName (str): Name of the node to connect to the Material Output node
        outputSocketName (str): Name of the output socket of the source node going to the material output node
    """
    # Get the material
    material = bpy.data.materials.get(materialName)
    if not material or not material.node_tree:
        return False
        
    # Get the nodes
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    
    materialOutputNode = next((node for node in nodes if node.type == 'OUTPUT_MATERIAL'), None) # Finds the Material Output node, stops after the first one (should only be one per material slot)
    sourceNode = nodes.get(nodeName)
    
    # Clear existing connection to Surface input if any
    for link in materialOutputNode.inputs['Surface'].links:
        links.remove(link)
    
    # Make new connection
    links.new(sourceNode.outputs[outputSocketName], materialOutputNode.inputs['Surface'])


def saveChannelBake(bakeImage, material, channel, fileFormat='JPEG', exportDir=None):
    """
    Saves the bake image to the specified path.
    
    Args:
        bakeImageNode: The texture node to save
        material: The material that the bake image belongs to
        fileFormat: The file format to save the image as (default is JPEG)
        exportDir: The directory to save the image to (default is None, which will error if used)
    """
    bakeImage.filepath_raw = os.path.join(exportDir, f"{material.name}_{channel}.{fileFormat}")
    bakeImage.file_format = fileFormat
    bakeImage.save()


# def handleMultipleUsers(material_name, objects, multiple_users_dict):
#     """Tracks materials that are used by multiple objects."""
#     if len(objects) > 1:
#         multiple_users_dict[material_name] = objects

# def printMultipleUserWarnings(multiple_users):
#     """Prints warnings for materials used by multiple objects."""
#     if multiple_users:
#         print('#'*10, 'Materials assigned to multiple objects:', '#'*10, sep='\n')
#         for material, objects in multiple_users.items():
#             print(f'{material}: {objects}')


def setupBakeEnvironment(material_name):
    """Prepares the scene for baking a specific material."""
    material = getMaterialObjectFromName(material_name)
    objects = getObjectsFromMaterial(material)
    setSelectedObjects(objects)
    return material #change this later, i dislike that we have to return the material here


def processBakeChannel(material, material_name, channel, node_data, resolution, fileFormat):
    """Processes a single channel for baking."""
    node_name, output_socket_name = node_data
    
    # Create and setup nodes
    bake_image = createBakeImage(material_name, channel, resolution)
    bake_image_node = createBakeImageNode(material, bake_image)
    
    # Setup bake network and execute bake
    createBakeNetwork(material_name, node_name, output_socket_name)
    setSelectedBakeImageNode(material, bake_image_node)
    bakeChannel(channel)
    
    # Save the result
    exportMaterialDir = exportMaterialDirectory(material_name)
    saveChannelBake(bake_image, material, channel, fileFormat, exportMaterialDir)


def bakeAllMaterials(resolution=1024, file_format='JPEG'):
    """
    Bakes all materials in the scene.
    
    Args:
        resolution: The resolution of the bake images (default is 1024)
        file_format: The file format to save the images as (default is JPEG)
    """
    saveScene()
    setBakeOptions()
    channels_to_bake = analyzeShaderConnections()
    multiple_users = {}
    
    # Process each material
    for material_name, channel_dict in channels_to_bake.items():
        # Setup environment
        material = setupBakeEnvironment(material_name)
        
        # Process each channel
        for channel, node_data in channel_dict.items():
            processBakeChannel(material, material_name, channel, node_data, 
                             resolution, file_format)
            
    saveSceneBackup()
            
            
def exportDirectory():
    """
    Creates a new directory for the export.
    """
    current_path = bpy.data.filepath
    dir_path = os.path.dirname(current_path)
    export_dir = os.path.join(dir_path, "scene_export")
    os.makedirs(export_dir, exist_ok=True)
    return export_dir


def exportMaterialDirectory(material_name):
    """
    Creates a new directory for the export of a specific material.
    """
    export_dir = exportDirectory()
    material_dir = os.path.join(export_dir, material_name)
    os.makedirs(material_dir, exist_ok=True)
    return material_dir


# def exportMaterialFilepath(material_name, channel, file_format, exportDir):
#     """
#     Creates a filepath for the export.
#     """
#     export_path = os.path.join(exportDir, f"{material_name}_{channel}.{file_format}")
#     return export_path
            

def saveScene():
    """
    Saves the current Blender scene.
    
    Returns:
        bool: True if save was successful, False otherwise
    """
    # Check if file has been saved before
    if not bpy.data.filepath:
        bpy.ops.wm.save_as_mainfile('INVOKE_DEFAULT')
        # Return True since the save dialog is handled by Blender
        return True
        
    try:
        bpy.ops.wm.save_mainfile()
        return True
    except Exception as e:
        print(f"Error saving file: {str(e)}")
        return False
    

def saveSceneBackup():
    """Saves current file to scene_export subfolder."""
    current_path = bpy.data.filepath
    if not current_path:
        return False
        
    exportDir = exportDirectory()
    
    current_file_name = os.path.splitext(os.path.basename(current_path))[0]
    new_file_name = f"{current_file_name}_BAKED.blend"
    new_path = os.path.join(exportDir, new_file_name)
    bpy.ops.wm.save_as_mainfile(filepath=new_path)
    return True





# NOTE: This will automatically save the scene as a backup before baking with no warning. (can be changed later)
bakeAllMaterials()

