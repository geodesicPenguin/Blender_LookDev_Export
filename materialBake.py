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
    
    return hasNodes and hasUsers and isNotFake


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
    Retrieves all objects that use the specified material.
    
    Args:
        material: A Blender material object
        
    Returns:
        tuple: A tuple of Blender object objects that use this material
    """
    objects = tuple(obj for obj in bpy.context.scene.objects if material in obj.data.materials)
    
    return objects


def analyzeShaderConnections():
    """
    Analyzes materials and their associated objects to find non-texture inputs that need baking.
    
    Returns:
        dict: A dictionary where:
            - keys are material names (str)
            - values are dictionaries containing:
                - 'Objects': list of object names using this material
                - 'Channels': list of input channels that need baking
    
    Example:
        {
            'Material.001': {
                'Objects': ['Cube', 'Sphere'],
                'Channels': ['Base Color', 'Roughness']
            }
        }
    """
    bakingData = {}
    materials = getAllMaterials()
    
    for material in materials:
        bakeChannels = getBSDFBakeInputs(material)
        bakeDisplacementChannel = getDisplacementBakeInputs(material)
        
        # Combine both channel sets (displacement has to be done separately, since it's plugged directly into the material output node)
        bakeChannels = set()
        if bakeChannels:
            bakeChannels.update(bakeChannels)
        if bakeDisplacementChannel:
            bakeChannels.update(bakeDisplacementChannel)
            
        # Only add to result if there are channels to bake
        if bakeChannels:
            # Get objects using this material
            material_objects = getObjectsFromMaterial(material)
            object_names = [obj.name for obj in material_objects]
            
            bakingData[material.name] = {
                'Objects': object_names,
                'Channels': list(bakeChannels)
            }
    
    return bakingData


def getBSDFBakeInputs(material):
    """
    Analyzes a single material to find non-texture inputs connected to its
    Principled BSDF node.
    
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
                if input.name.lower() == 'normal' and connectedNode.type == 'NORMAL_MAP':
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
    Analyzes a single material to find if its Material Output node has
    a non-texture displacement input connected.
    
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
    bpy.context.scene.render.bake.margin = 16
    
    if useGPU:
        bpy.context.scene.cycles.device = 'GPU'
    else:
        bpy.context.scene.cycles.device = 'CPU'
        
        
def createBakeImage(channel, resolution=1024):
    """
    Creates a new image texture and assigns it to the specified channel name.
    
    Returns:
        bpy.types.Image: The newly created image texture
    """
    imageName = f"{channel}_baked"
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
    """
    bpy.ops.object.bake(type=channel, 
                        pass_filter={'COLOR'},
                        margin=16)
                        # use_split_materials if multiple materials on 1 mesh
                        # normal map settings in bake?
    #bpy.context.scene.render.bake.normal_space = 'OBJECT'

def saveChannelBake(bakeImage, material, fileFormat='JPEG'):
    """
    Saves the bake image to the specified path.
    
    Args:
        bakeImageNode: The texture node to save
        material: The material that the bake image belongs to
        fileFormat: The file format to save the image as (default is JPEG)
    """
    bakeImage.filepathRaw = f"C:/Users/Lucas/Desktop/dummy/{material.name}.{fileFormat}"
    bakeImage.fileFormat = fileFormat
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
    
    for materialName, data in channelsToBake.items():
        material = getMaterialObjectFromName(materialName)
        
        for obj in data['Objects']:
            # If the material is assigned to multiple objects, add it to a data set to notify the user at the end
            if len(data['Objects']) > 1:
                multipleUsers[material] = []
                multipleUsers[material].append(obj)
            
            setSelectedObjects(data['Objects'])
            
            for channel in data['Channels']:
                bakeImage = createBakeImage(channel, resolution)
                bakeImageNode = createBakeImageNode(material, bakeImage)
                setBakeTextureNodeActive(material, bakeImageNode)
                bakeChannel(channel)
                saveChannelBake(bakeImage, material, fileFormat)
                
    # Notify the user if any materials were assigned to multiple objects
    if multipleUsers:
        print('#'*10, 'Materials assigned to multiple objects:', '#'*10, sep='\n')
        for material, objects in multipleUsers.items():
            print(f'{material}: {objects}')
        
bakeAllMaterials()