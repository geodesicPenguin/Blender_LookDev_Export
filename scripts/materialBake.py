#materialBake.py

import bpy
import os
import shutil


class MaterialBaker:
    def __init__(self, resolution=1024, fileFormat='JPEG', copyTextures=False, exportDir=None):
        """ 
        Args:
            resolution: The resolution of the bake images
            fileFormat: The file format to save the images as
            copyTextures: Whether to copy all image textures to the save location
            exportDir: The directory to save the bake images to. If not specified, it will be in the blend file's directory.
        """
        self.nonTextureInputs = {} # Will store data for bake inputs that are not texture images
        self.textureInputs = {} # Will store data for bake inputs that are texture images
        
        self.resolution = resolution # The resolution of the bake images
        self.fileFormat = fileFormat # The file format to save the images as
        
        self.copyTextures = copyTextures # Whether to copy all image textures to the save location
        
        self.exportDir = exportDir if exportDir else self.dirNextToFile() # The directory to save the bake images to. If not specified, it will be in the blend file's directory.
        
        self.bakeAllMaterials() # Bake all materials
        
    def getAllMaterials(self):
        """
        Retrieves all node-based materials in the current Blender scene.
        
        Returns:
            tuple: A tuple containing all materials that use nodes.
        """
        materials = tuple(mat for mat in bpy.data.materials if self.isValidMaterial(mat))
        
        return materials

    def isValidMaterial(self, material):
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
        isOnMesh = any(obj for obj in bpy.data.objects if obj.type == 'MESH' and material.name in obj.material_slots)
        
        return hasNodes and hasUsers and isNotFake and isOnMesh

    def getMaterialObjectFromName(self, materialName):
        """
        Gets a Blender material object from its name.
        A string of the name is not sufficient, as it cannot be used to perform material functions. We need the actual python object.
        
        Args:
            materialName (str): The name of the material to find
            
        Returns:
            bpy.types.Material: The material object if found, None otherwise
        """
        return bpy.data.materials.get(materialName)

    def getObjectsFromMaterial(self, materialName):
        """
        Retrieves all mesh objects that use the specified material.
        
        Args:
            materialName (str): The name of the material to find

        Returns:
            tuple: A tuple of Blender mesh objects that use this material
        """
        objects = tuple(obj for obj in bpy.context.scene.objects if materialName in obj.material_slots and obj.type == 'MESH')
        
        return objects

    def analyzeShaderConnections(self):
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
        nonTextureInputs = self.nonTextureInputs
        
        materials = self.getAllMaterials()
            
        for material in materials:
            bakeDisplacementData = self.getDisplacementBakeInputs(material)
            bakeChannelData = self.getBSDFBakeInputs(material)
            
            if bakeDisplacementData or bakeChannelData:
                # Initialize the dictionary for this material
                if material.name not in nonTextureInputs:
                    nonTextureInputs[material.name] = {}
                
                # Update with both dictionaries if they exist
                if bakeDisplacementData:
                    nonTextureInputs[material.name].update(bakeDisplacementData)
                if bakeChannelData:
                    nonTextureInputs[material.name].update(bakeChannelData)
                
                # Remove the material if it has no entries
                if not nonTextureInputs[material.name]:
                    del nonTextureInputs[material.name]
                
        return nonTextureInputs

    def getBSDFBakeInputs(self, material):
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
        textureInputs = self.textureInputs
        materialNodes = material.node_tree.nodes
        principledNode = next((node for node in materialNodes if node.type == 'BSDF_PRINCIPLED'), None)
        
        if principledNode:
            channelDict = {}
            
            for inputSocket in principledNode.inputs:
                if inputSocket.links:
                    connectedNode = inputSocket.links[0].from_node
                    outputSocket = inputSocket.links[0].from_socket
                    
                    # Special handling for the Normal channel
                    if inputSocket.name == 'Normal' and connectedNode.type == 'NORMAL_MAP':
                        # Check if Normal Map node has a texture input
                        if not any(link.from_node.type == 'TEX_IMAGE' for link in connectedNode.inputs[1].links):
                            # Check if Normal Map node has any input connections at all
                            if any(input.links for input in connectedNode.inputs):
                                channelDict[inputSocket.name] = (connectedNode.name, outputSocket.name)
                    # For all other inputs
                    if connectedNode.type != 'TEX_IMAGE':
                        channelDict[inputSocket.name] = (connectedNode.name, outputSocket.name)
                    else: # If it does have a texture input, we add it to the texture inputs dictionary
                        if material.name not in textureInputs:
                            textureInputs[material.name] = {}   
                        textureInputs[material.name][inputSocket.name] = (connectedNode.name, outputSocket.name)
            
            return channelDict
        return {}

    def getDisplacementBakeInputs(self, material):
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
        textureInputs = self.textureInputs
        
        materialNodes = material.node_tree.nodes
        outputNode = next((node for node in materialNodes if node.type == 'OUTPUT_MATERIAL'), None)
        
        if outputNode:
            channelDict = {}
            
            # Check displacement input
            dispInput = outputNode.inputs['Displacement']
            if dispInput.links:
                connectedNode = dispInput.links[0].from_node
                outputSocket = dispInput.links[0].from_socket
                
                if connectedNode.type == 'DISPLACEMENT':
                    # Check if Displacement node has a texture input
                    if not any(link.from_node.type == 'TEX_IMAGE' for link in connectedNode.inputs['Height'].links):
                        channelDict['Displacement'] = (connectedNode.name, outputSocket.name)
                    else: # If it does have a texture input, we add it to the texture inputs dictionary
                        textureInputs[material.name]['Displacement'] = (connectedNode.name, outputSocket.name)
                        
            return channelDict
        return {}

    def setBakeRenderOptions(self, useGPU=True):
        """
        Sets the bake options for the current scene.
        """
        bpy.context.scene.render.engine = 'CYCLES'
        bpy.context.scene.cycles.samples = 10
        
        if useGPU:
            bpy.context.scene.cycles.device = 'GPU'
        else:
            bpy.context.scene.cycles.device = 'CPU'
            
    def createBakeImage(self, materialName, channel):
        """
        Creates a new image texture and assigns it to the specified channel name.
        
        Args:
            materialName (str): The name of the material that the bake image belongs to
            channel (str): The name of the channel to bake
            resolution (int): The resolution of the bake image (default is 1024)
            
        Returns:
            bpy.types.Image: The newly created image texture
        """
        resolution = self.resolution
        
        imageName = f"{materialName}_{channel}_baked"
        bakeImage = bpy.data.images.new(
            name=imageName,
            width=resolution,  
            height=resolution
        )
        return bakeImage

    def setSelectedBakeImageNode(self, materialName, bakeImageNode):
        """
        Sets the specified texture node as the active node for baking.
        """
        # Deselect all nodes first
        material = self.getMaterialObjectFromName(materialName)
        for node in material.node_tree.nodes:
            node.select = False
        material = self.getMaterialObjectFromName(materialName)
        material.node_tree.nodes.active = bakeImageNode

    def createBakeImageNode(self, materialName, image):
        """
        Creates a new image texture node and assigns it to the specified image.
        
        Returns:
            bpy.types.ShaderNodeTexImage: The newly created image texture node
        """
        material = self.getMaterialObjectFromName(materialName)
        textureNode = material.node_tree.nodes.new('ShaderNodeTexImage')
        textureNode.image = image
        
        return textureNode

    def bakeChannel(self, channel):
        """
        Bakes a single channel for the active object.
        
        Args:
            channel (str): The name of the channel to bake
        """
        bakeType = self.getBakeType(channel) 
        bpy.ops.object.bake(type=bakeType, 
                            normal_space='TANGENT',
                            margin=16)

    def getBakeType(self, channel):
        """
        Maps material channels to their necessary bake types.
        EMIT is the default, as any map that is not a normal map can be baked with it.
        Normal maps are baked with NORMAL, as they need the normal bake settings to bake correctly.
        
        Args:
            channel (str): The channel name from the Principled BSDF or Material Output if baking displacement
            
        Returns:
            str: The corresponding Blender bake type
        """
        bakeTypes = {
            'Normal': 'NORMAL'
        }
        return bakeTypes.get(channel, 'EMIT')

    def createBakeNetwork(self, materialName, channel, nodeName, outputSocketName):
        """
        Connects a specified node to the Material Output node's Surface input.
        The node connected to the output node will be baked.
        This is temporary, as we will connect the finished texture nodes to the BSDF node later.
        
        Args:
            materialName (str): Name of the material containing the source node
            channel (str): The channel name to bake
            nodeName (str): Name of the node to connect to the Material Output node
            outputSocketName (str): Name of the output socket of the source node going to the material output node
        """
        # Get the material
        material = self.getMaterialObjectFromName(materialName)
        if not material or not material.node_tree:
            return False
            
        # Get the nodes
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        
        materialOutputNode = next((node for node in nodes if node.type == 'OUTPUT_MATERIAL'), None)
        sourceNode = nodes.get(nodeName)
        
        # Clear existing connection to Surface input if any
        for link in materialOutputNode.inputs['Surface'].links:
            links.remove(link)
        
        # For normal maps, connect the BSDF output instead of the specified node
        if channel == "Normal":
            bsdfNode = next((node for node in nodes if node.type == 'BSDF_PRINCIPLED'), None)
            if bsdfNode:
                links.new(bsdfNode.outputs['BSDF'], materialOutputNode.inputs['Surface'])
        else:
            # Make new connection for other channels
            links.new(sourceNode.outputs[outputSocketName], materialOutputNode.inputs['Surface'])

    def saveChannelBake(self, bakeImage, materialName, channel, fileFormat='JPEG', exportDir=None):
        """
        Saves the bake image to the specified path.
        
        Args:
            bakeImageNode: The texture node to save
            materialName: The name of the material that the bake image belongs to
            channel: The name of the channel to save
            fileFormat: The file format to save the image as (default is JPEG)
            exportDir: The directory to save the image to (default is None, which will error if used)
        """
        materialName = materialName.rstrip().replace(' ', '_')
        channel = channel.replace(' ', '_')
        fileName = f"{materialName}_{channel}.{fileFormat}"
        bakeImage.filepath_raw = os.path.join(exportDir, fileName)
        bakeImage.file_format = fileFormat
        self.configureImageSettings(fileFormat)
        bakeImage.save()

    def configureImageSettings(self, fileFormat='PNG'):
        """
        Configures image format settings for baked textures.
        
        Args:
            fileFormat (str): The file format to use ('PNG', 'JPEG', 'TIFF', 'OPEN_EXR')
        """
        bakeSettings = bpy.context.scene.render.bake
        settings = bakeSettings.image_settings
        
        # Set the file format
        settings.file_format = fileFormat
        
        # Configure format-specific settings
        if fileFormat == 'PNG':
            settings.color_mode = 'RGBA'
            settings.color_depth = '8'
            settings.compression = 15
            
        elif fileFormat == 'JPEG':
            settings.color_mode = 'RGB'  
            settings.quality = 100
            
        elif fileFormat == 'TIFF':
            settings.color_mode = 'RGB'
            settings.tiff_codec = 'DEFLATE'
            
    def isFileFormatValid(self, fileFormat):
        """Checks if the file format is valid.
        
        Args:
            fileFormat (str): The file format to check
            
        Returns:
            bool: True if the file format is valid, False otherwise
        """
        return fileFormat in ['JPEG', 'PNG', 'TIFF']

    def selectBakeObjects(self, materialName):
        """Selects the objects to bake from. 
        Deselects all objects before selecting the ones we want to bake.
        Unhides the objects to make sure they are visible in the viewport. (Bake fails if they are hidden)
        The dictionary returned contains the names of the visible and hidden objects. We need this to restore the original state after baking.
        
        Args:
            materialName (str): The name of the material to select objects from
            
        Returns:
            dict: A dictionary where:
                - keys are 'visible' and 'hidden'
                - values are lists of object names
        """
        objects = self.getObjectsFromMaterial(materialName)

        bpy.ops.object.select_all(action='DESELECT')
        
        objectData = {'visible':(), 'hidden':()}
        
        for obj in objects:
            if obj.hide_get() or obj.hide_viewport or obj.hide_render:
                obj.hide_viewport = False
                obj.hide_set(False)
                obj.hide_render = False
                objectData['hidden'] += (obj.name,)
            else:
                objectData['visible'] += (obj.name,)
            obj.select_set(True)
            
        return objectData

    def setupBake(self, materialName, channel, nodeData):
        """Processes a single channel for baking.
        Args:
            materialName (str): The name of the material to bake
            channel (str): The name of the channel to bake
            nodeData (tuple): A tuple containing the node name and output socket name
            
        Returns:
            bool: True if the bake was successful, False otherwise
        """
        resolution = self.resolution
        fileFormat = self.fileFormat
        
        nodeName, outputSocketName = nodeData
        
        # Create and setup nodes
        bakeImage = self.createBakeImage(materialName, channel)
        bakeImageNode = self.createBakeImageNode(materialName, bakeImage) 
        
        # Select the required objects to bake from 
        objectData = self.selectBakeObjects(materialName)
        
        # Setup bake network 
        self.createBakeNetwork(materialName, channel, nodeName, outputSocketName)
        self.setSelectedBakeImageNode(materialName, bakeImageNode)
        
        # Bake the channel
        try:
            isSuccess = True
            self.bakeChannel(channel)
        
            # Save the result
            exportMaterialDir = self.exportMaterialDirectory(materialName)
            self.saveChannelBake(bakeImage, materialName, channel, fileFormat, exportMaterialDir)
            
            # Connect the baked texture to its corresponding input
            self.connectBakedTexture(materialName, bakeImageNode, channel)
        
        # Handle any errors that occur during baking
        except RuntimeError as e:
            isSuccess = False
            print(f"\n Error baking {channel}: {str(e)}\n")
        
        # Restore the original state of the objects
        for objName in objectData['hidden']:
            obj = bpy.data.objects.get(objName)
            obj.hide_viewport = True
            obj.hide_set(True)
            obj.hide_render = True
            
        return isSuccess

    def bakeAllMaterials(self):
        """
        Bakes all materials in the scene.
        """
        if not self.isFileFormatValid(self.fileFormat):
            raise ValueError(f"Invalid file format: {self.fileFormat}")
        
        self.showMessage('Baking materials...', 'INFO')
        
        self.toggleSystemConsole()
        self.saveScene()
        self.saveSceneBackup()
        self.setBakeRenderOptions()
        
        self.analyzeShaderConnections()
        channelsToBake = self.nonTextureInputs
        channelsToCopy = self.textureInputs
        
        multipleUsers = {}
        
        # Process each material
        failedMaterials = []
        for materialName, channelDict in channelsToBake.items():
            # Check if the material is used by multiple objects
            objects = self.getObjectsFromMaterial(materialName)
            if len(objects) > 1:
                multipleUsers[materialName] = [obj.name for obj in objects]
                
            print('\n'*5,materialName, channelDict,'\n'*5, sep=' | ')
            # Process each channel
            for channel, nodeData in channelDict.items():
                isSuccess = self.setupBake(materialName, channel, nodeData)
            if isSuccess:
                # Connect the BSDF node to the Material Output node after all channels are baked. 
                self.connectBSDFToMaterialOutput(materialName)
            else:
                print(f"Error baking {materialName}")
                failedMaterials.append(materialName)
                
        # Copy the textures to the material directory
        if self.copyTextures:
            for materialName, textureData in channelsToCopy.items():
                self.copyTextureToDirectory(materialName, textureData)
             
        if multipleUsers:
            print('\n'*3, 'Materials with multiple users:', *multipleUsers, *multipleUsers.values(), '\n', '\nIf the UVs are not identical, you may get strange results.', '\n'*3, sep='\n')
            self.showMessage('Some materials baked onto multiple objects (Check console)', 'ERROR')
        elif failedMaterials and multipleUsers:
            print('\n'*3, 'Failed materials:', *failedMaterials, '\n'*3, 'Materials with multiple users:', *multipleUsers, *multipleUsers.values(), '\n', '\nIf the UVs are not identical, you may get strange results.','\n'*3, sep=' ')
            self.showMessage('Some materials failed to bake or had issues with multiple users (Check console)', 'ERROR')
        elif failedMaterials:
            print('\n'*3, 'Failed materials:', *failedMaterials, '\n'*3, sep='')
            self.showMessage('Some materials failed to bake (Check console)', 'ERROR')
        else:
            print('\n'*3, 'All materials baked successfully', '\n'*3, sep='')
            self.showMessage('All materials baked successfully', 'INFO')
            
        # Save the new scene after baking
        self.saveScene()
        self.toggleSystemConsole()

    def connectBakedTexture(self, materialName, bakeImageNode, channel):
        """
        Connects a baked texture node to its corresponding input on the material.
        
        Args:
            materialName (str): The name of the material containing the nodes
            bakeImageNode: The image texture node containing the baked result
            channel: The channel name to connect to (e.g., 'Base Color', 'Normal', etc.)
        """
        material = self.getMaterialObjectFromName(materialName)
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

    def connectBSDFToMaterialOutput(self, materialName):
        """
        Connects the BSDF node to the Material Output node's Surface input.
        """
        material = self.getMaterialObjectFromName(materialName)
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        principledNode = next((node for node in nodes if node.type == 'BSDF_PRINCIPLED'), None)
        outputNode = next((node for node in nodes if node.type == 'OUTPUT_MATERIAL'), None)
        links.new(principledNode.outputs['BSDF'], outputNode.inputs['Surface'])

    def toggleSystemConsole(self):
        """
        Toggles the visibility of the Blender System Console.
        Allows the user to see any bake working in the console.
        
        Doesn't seem to work in Blender version 4.2.2 LTS, so as a workaround, we to a try and except to see if it works.
        """
        try:
            bpy.ops.wm.console_toggle()
        except:
            pass

    def saveScene(self):
        """
        Saves the current Blender scene.
        
        Returns:
            bool: True if save was successful, False otherwise
        """
        if not bpy.data.filepath:
            raise RuntimeError("File must be saved before baking")
        else:
            bpy.ops.wm.save_mainfile()
            return True     

    def saveSceneBackup(self):
        """Saves current file to scene_export subfolder.
        
        Returns:
            bool: True if save was successful, False otherwise
        """
        currentPath = bpy.data.filepath
        if not currentPath:
            return False
            
        exportDir = self.exportDir
        
        currentFileName = os.path.splitext(os.path.basename(currentPath))[0]
        newFileName = f"{currentFileName}_BAKED.blend"
        newPath = os.path.join(exportDir, newFileName)
        bpy.ops.wm.save_as_mainfile(filepath=newPath)
        return True

    def dirNextToFile(self):
        """
        Creates a new directory for the export next to the blend file.
        
        Returns:
            str: The path to the export directory
        """
        dirPath = bpy.path.abspath('//')
        sceneExportDir = os.path.join(dirPath, "scene_export")
        os.makedirs(sceneExportDir, exist_ok=True)
        return sceneExportDir

    def exportMaterialDirectory(self, materialName):
        """
        Creates a new directory for the export of a specific material.
        
        Args:
            materialName (str): The name of the material to create a directory for
            
        Returns:
            str: The path to the export directory
        """
        exportDir = self.exportDir
        
        materialName = materialName.rstrip().replace(' ', '_')
        
        materialDir = os.path.join(exportDir, materialName)
        os.makedirs(materialDir, exist_ok=True)
        return materialDir
    
    def copyTextureToDirectory(self, materialName, textureInputs):
        """
        Copies the texture images to the export directory.
        
        Args:
            materialName (str): The name of the material containing the textures
            textureInputs (dict): Dictionary mapping texture names to (node_name, socket_name) tuples
            
        Returns:
            str: The path to the copied texture
        """
        materialDir = self.exportMaterialDirectory(materialName)
        
        for textureName, textureData in textureInputs.items():
            textureNodeName, textureOutputSocketName = textureData
            material = self.getMaterialObjectFromName(materialName)
            textureNode = material.node_tree.nodes.get(textureNodeName)
            
            if textureNode and textureNode.image:
                imagePath = bpy.path.abspath(textureNode.image.filepath)
                if os.path.exists(imagePath):
                    fileName = os.path.basename(imagePath)
                    newPath = os.path.join(materialDir, fileName)
                    shutil.copy2(imagePath, newPath)
        return newPath


    def showMessage(self, message, type='INFO'):
        """
        Shows a message in the Blender interface.
        
        Args:
            message (str): The message to display
            type (str): Message type ('INFO' or 'ERROR')
        """
        def draw(self, context):
            self.layout.label(text=message)
        
        bpy.context.window_manager.popup_menu(draw, title="Message", icon=type)
    
    
