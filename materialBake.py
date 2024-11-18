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
    objects = getObjectsFromMaterial(materials)
        
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
    bpy.context.scene.render.samples = 10 # Smaller sample size for faster baking. Negligible quality difference.
    bpy.context.scene.render.bake.margin = 16
    
    if useGPU:
        bpy.context.scene.cycles.device = 'GPU'
    else:
        bpy.context.scene.cycles.device = 'CPU'
        
        
def createBakeImage(channel, resolution=1024):
    """
    Creates a new image texture node and assigns it to the specified channel name.
    
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


def createBakeImageNode(image):
    """
    Creates a new image texture node and assigns it to the specified image.
    
    Returns:
        bpy.types.ShaderNodeTexImage: The newly created image texture node
    """
    nodes = bpy.context.scene.node_tree.nodes
    textureNode = nodes.new('ShaderNodeTexImage')
    textureNode.image = image
    return textureNode

        
def setActiveObject(obj): # find way to set active object and not have to select the object first as well as the active image texture node
    """
    Sets the active object for the current scene.
    """
    bpy.context.view_layer.objects.active = obj
        
        
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

def saveChannelBake(image, fileFormat='JPEG'):
    """
    Saves the bake image to the specified path.
    
    Args:
        image: The image texture to save
        fileFormat: The file format to save the image as (default is JPEG)
    """
    image.filepathRaw = f"//{image.name}.png"
    image.fileFormat = fileFormat
    image.save()


def bakeAllMaterials():
    """
    Bakes all materials in the scene.
    """
    setBakeOptions()
    channelsToBake = analyzeShaderConnections()
    
    for material, channels in channelsToBake.items():
        for channel in channels:
            bakeChannel(channel)
            

        
