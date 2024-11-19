#materialBake.py

import bpy
import os


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
            - values are sets containing names of input channels (str) that have 
              non-texture connections
    
    Example:
        {
            'Material.001': {'Base Color', 'Roughness'},
            'Material.002': {'Metallic', 'Normal'}
        }
    """
    nonTextureInputs = {}
    materials = getAllMaterials()
        
    for material in materials:
        bakeChannels = getBSDFBakeInputs(material)
        bakeDisplacementChannel = getDisplacementBakeInputs(material)
        
        if bakeChannels or bakeDisplacementChannel:
            # Initialize the set for this material
            if material.name not in nonTextureInputs:
                nonTextureInputs[material.name] = set()
            
            # Update with both sets if they exist
            if bakeChannels:
                nonTextureInputs[material.name].update(bakeChannels)
            if bakeDisplacementChannel:
                nonTextureInputs[material.name].update(bakeDisplacementChannel)
                
            # Remove the material from the dictionary if there are no bake channels or a displacement channel input
            if not bakeChannels and not bakeDisplacementChannel:
                del nonTextureInputs[material.name]
            
    return nonTextureInputs


def getBSDFBakeInputs(material):
    """
    Analyzes a single material to find image texture inputs connected to its
    Principled BSDF node. If not found, we add the channel to the data set for baking.
    
    Args:
        material: A Blender material object
        
    Returns:
        set: Set of input channel names that have non-texture connections
    """
    nodes = material.node_tree.nodes
    principledNode = next((node for node in nodes if node.type == 'BSDF_PRINCIPLED'), None) # Finds the Principled BSDF node, stops after the first one (should only be one per material slot)
    
    if principledNode:
        channelSet = set()
        
        for input in principledNode.inputs:
            if input.links:
                connectedNode = input.links[0].from_node
                
                # Special handling for the Normal channel
                if input.name == 'Normal' and connectedNode.type == 'NORMAL_MAP':
                    # Check if Normal Map node has a texture input
                    if not any(link.from_node.type == 'TEX_IMAGE' for link in connectedNode.inputs[1].links):
                        channelSet.add(input.name)
                # For all other inputs
                elif connectedNode.type != 'TEX_IMAGE':
                    channelSet.add(input.name)
        
        return channelSet
    return set() # Returns an empty set if no Principled BSDF node is found


def getDisplacementBakeInputs(material):
    """
    Analyzes a single material to find if its Material Output node contains
    an image texture displacement input connected. If not, we add it to the data set for baking.
    Args:
        material: A Blender material object
        
    Returns:
        set: Set containing 'Displacement' if it has non-texture connection, empty set otherwise
    """
    nodes = material.node_tree.nodes
    outputNode = next((node for node in nodes if node.type == 'OUTPUT_MATERIAL'), None) # Finds the Material Output node, stops after the first one (should only be one per material slot)
    
    if outputNode:
        channelSet = set()
        
        # Check displacement input
        dispInput = outputNode.inputs['Displacement']
        if dispInput.links:
            connectedNode = dispInput.links[0].from_node
            
            if connectedNode.type == 'DISPLACEMENT':
                # Check if Displacement node has a texture input
                if not any(link.from_node.type == 'TEX_IMAGE' for link in connectedNode.inputs['Height'].links):
                    channelSet.add('Displacement')
                    
        return channelSet
    return set() # Returns an empty set if no Material Output node is found


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


def createBakeImageNode(material, image):
    """
    Creates a new image texture node and assigns it to the specified image.
    
    Returns:
        bpy.types.ShaderNodeTexImage: The newly created image texture node
    """
    textureNode = material.node_tree.nodes.new('ShaderNodeTexImage')
    textureNode.image = image
    
    return textureNode


def setBakeTextureNodeActive(material, bakeImageNode):
    """
    Sets the specified texture node as the active node for baking.
    """
    material.node_tree.nodes.active = bakeImageNode

     
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
    Emit is the default, as any map that is not a normal map can be baked with it.
    
    Args:
        channel (str): The channel name from the Principled BSDF or Material Output if baking displacement
        
    Returns:
        str: The corresponding Blender bake type
    """
    bake_types = {
        'Normal': 'NORMAL',
    }
    return bake_types.get(channel, 'EMIT')  # Default to EMIT if channel not found

def setBakeNetwork():
    """_summary_
    """


def saveChannelBake(bakeImage, material, channel, fileFormat='JPEG'):
    """
    Saves the bake image to the specified path.
    
    Args:
        bakeImageNode: The texture node to save
        material: The material that the bake image belongs to
        fileFormat: The file format to save the image as (default is JPEG)
    """
    bakeImage.filepath_raw = f"C:/Users/Lucas/Desktop/dummy/{material.name}_{channel}.{fileFormat}"
    bakeImage.file_format = fileFormat
    bakeImage.save()


def bakeAllMaterials(resolution=1024, fileFormat='JPEG'):
    """
    Bakes all materials in the scene.
    
    Args:
        resolution: The resolution of the bake images (default is 1024)
        fileFormat: The file format to save the images as (default is JPEG)
    """
    setBakeOptions()
    channelsToBake = analyzeShaderConnections()
    multipleUsers = {}
    
    for materialName, channels in channelsToBake.items():
        material = getMaterialObjectFromName(materialName)
        objects = getObjectsFromMaterial(material)
        # If the material is assigned to multiple objects, add it to a data set to notify the user at the end
        if len(objects) > 1:
            multipleUsers[materialName] = objects
            
        setSelectedObjects(objects)
            
        for channel in channels:
                bakeImage = createBakeImage(materialName, channel, resolution)
                bakeImageNode = createBakeImageNode(material, bakeImage)
                setBakeTextureNodeActive(material, bakeImageNode)
                bakeChannel(channel)
                saveChannelBake(bakeImage, material, channel, fileFormat)
                
    # Notify the user if any materials were assigned to multiple objects
    if multipleUsers:
        print('#'*10, 'Materials assigned to multiple objects:', '#'*10, sep='\n')
        for material, objects in multipleUsers.items():
            print(f'{material}: {objects}')
        
bakeAllMaterials()