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


def setBakeRenderOptions(useGPU=True):
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


def setSelectedBakeImageNode(materialName, bakeImageNode):
    """
    Sets the specified texture node as the active node for baking.
    """
    material = getMaterialObjectFromName(materialName)
    material.node_tree.nodes.active = bakeImageNode
    

def createBakeImageNode(materialName, image):
    """
    Creates a new image texture node and assigns it to the specified image.
    
    Returns:
        bpy.types.ShaderNodeTexImage: The newly created image texture node
    """
    material = getMaterialObjectFromName(materialName)
    textureNode = material.node_tree.nodes.new('ShaderNodeTexImage')
    textureNode.image = image
    
    return textureNode

        
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
    material = getMaterialObjectFromName(materialName)
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


def saveChannelBake(bakeImage, materialName, channel, fileFormat='JPEG', exportDir=None):
    """
    Saves the bake image to the specified path.
    
    Args:
        bakeImageNode: The texture node to save
        materialName: The name of the material that the bake image belongs to
        channel: The name of the channel to save
        fileFormat: The file format to save the image as (default is JPEG)
        exportDir: The directory to save the image to (default is None, which will error if used)
    """
    bakeImage.filepath_raw = os.path.join(exportDir, f"{materialName}_{channel}.{fileFormat}")
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


def selectBakeObjects(materialName):
    """Selects the objects to bake from.
    
    Args:
        materialName (str): The name of the material to select objects from
    """
    material = getMaterialObjectFromName(materialName)
    objects = getObjectsFromMaterial(material)
    for obj in objects:
        obj.select_set(True)
        

def isFileFormatValid(fileFormat):
    """Checks if the file format is valid.
    
    Args:
        fileFormat (str): The file format to check
        
    Returns:
        bool: True if the file format is valid, False otherwise
    """
    return fileFormat in ['JPEG', 'PNG', 'TIFF', 'Targa']


def setupBake(materialName, channel, nodeData, resolution, fileFormat):
    """Processes a single channel for baking."""
    nodeName, outputSocketName = nodeData
    
    # Create and setup nodes
    bakeImage = createBakeImage(materialName, channel, resolution)
    bakeImageNode = createBakeImageNode(materialName, bakeImage) 
    
    # Select the required objects to bake from
    selectBakeObjects(materialName)
    
    # Setup bake network and execute bake
    createBakeNetwork(materialName, nodeName, outputSocketName)
    setSelectedBakeImageNode(materialName, bakeImageNode)
    bakeChannel(channel)
    
    # Save the result
    exportMaterialDir = exportMaterialDirectory(materialName)
    saveChannelBake(bakeImage, materialName, channel, fileFormat, exportMaterialDir)
    
    # Connect the baked texture to its corresponding input
    connectBakedTexture(materialName, bakeImageNode, channel)
    connectBSDFToMaterialOutput(materialName)
    

def bakeAllMaterials(resolution=1024, fileFormat='JPEG'):
    """
    Bakes all materials in the scene.
    
    Args:
        resolution: The resolution of the bake images (default is 1024)
        fileFormat: The file format to save the images as (default is JPEG)
    """
    if not isFileFormatValid(fileFormat):
        raise ValueError(f"Invalid file format: {fileFormat}")
    
    saveScene()
    setBakeRenderOptions()
    channelsToBake = analyzeShaderConnections()
    multipleUsers = {}
    
    # Process each material
    for materialName, channelDict in channelsToBake.items():
        # Process each channel
        for channel, nodeData in channelDict.items():
            setupBake(materialName, channel, nodeData, 
                             resolution, fileFormat)
            
    saveSceneBackup()
            
    
      
            
def exportDirectory():
    """
    Creates a new directory for the export.
    
    Returns:
        str: The path to the export directory
    """
    currentPath = bpy.data.filepath
    dirPath = os.path.dirname(currentPath)
    exportDir = os.path.join(dirPath, "scene_export")
    os.makedirs(exportDir, exist_ok=True)
    return exportDir


def exportMaterialDirectory(materialName):
    """
    Creates a new directory for the export of a specific material.
    
    Returns:
        str: The path to the export directory
    """
    exportDir = exportDirectory()
    materialDir = os.path.join(exportDir, materialName)
    os.makedirs(materialDir, exist_ok=True)
    return materialDir


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
    """Saves current file to scene_export subfolder.
    
    Returns:
        bool: True if save was successful, False otherwise
    """
    currentPath = bpy.data.filepath
    if not currentPath:
        return False
        
    exportDir = exportDirectory()
    
    currentFileName = os.path.splitext(os.path.basename(currentPath))[0]
    newFileName = f"{currentFileName}_BAKED.blend"
    newPath = os.path.join(exportDir, newFileName)
    bpy.ops.wm.save_as_mainfile(filepath=newPath)
    return True




def connectBakedTexture(materialName, bakeImageNode, channel):
    """
    Connects a baked texture node to its corresponding input on the material.
    
    Args:
        materialName (str): The name of the material containing the nodes
        bakeImageNode: The image texture node containing the baked result
        channel: The channel name to connect to (e.g., 'Base Color', 'Normal', etc.)
    """
    material = getMaterialObjectFromName(materialName)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    
    # Get the main shader nodes
    principledNode = next((node for node in nodes if node.type == 'BSDF_PRINCIPLED'), None)
    outputNode = next((node for node in nodes if node.type == 'OUTPUT_MATERIAL'), None)
    
    # Handle special cases for normal and displacement maps
    if channel == 'Normal':
        normalMapNode = nodes.new('ShaderNodeNormalMap')
        normalMapNode.location = (bakeImageNode.location.x + 300, bakeImageNode.location.y)
        links.new(bakeImageNode.outputs['Color'], normalMapNode.inputs['Color'])
        links.new(normalMapNode.outputs['Normal'], principledNode.inputs['Normal'])
        
    elif channel == 'Displacement':
        dispNode = nodes.new('ShaderNodeDisplacement')
        dispNode.location = (bakeImageNode.location.x + 300, bakeImageNode.location.y)
        links.new(bakeImageNode.outputs['Color'], dispNode.inputs['Height'])
        links.new(dispNode.outputs['Displacement'], outputNode.inputs['Displacement'])
        
    # All other channels connect directly to BSDF
    elif channel in principledNode.inputs:
        links.new(bakeImageNode.outputs['Color'], principledNode.inputs[channel])
     

def connectBSDFToMaterialOutput(materialName):
    """
    Connects the BSDF node to the Material Output node's Surface input.
    """
    material = getMaterialObjectFromName(materialName)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principledNode = next((node for node in nodes if node.type == 'BSDF_PRINCIPLED'), None)
    outputNode = next((node for node in nodes if node.type == 'OUTPUT_MATERIAL'), None)
    links.new(principledNode.outputs['BSDF'], outputNode.inputs['Surface'])

#make function to delete all OLD nodes from shader networks?

