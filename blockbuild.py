import bpy
from mathutils import *
import os, sys

#create class for the other functions? BlockBuilder.

#NICEIF: SpaceView3D.grid_subdivisions = 16 (so they're MC pixel-based)

#TODO: tidy this up to one location (double defined here from mineregion)
MCPATH = ''
if sys.platform == 'darwin':
    MCPATH = os.path.join(os.environ['HOME'], 'Library', 'Application Support', 'minecraft')
elif sys.platform == 'linux':
    MCPATH = os.path.join(os.environ['HOME'], '.minecraft')
else:
    MCPATH = os.path.join(os.environ['APPDATA'], '.minecraft')
# This needs to be set by the addon during initial inclusion. Set as a bpy.props.StringProperty within the Scene, then refer to it all over this addon.

def isBMesh():
    majorver = bpy.app.version[0] * 100 + bpy.app.version[1]
    return majorver > 262
    #return int(bpy.app.build_revision) > 43451

#class BlockBuilder:
#    """Defines methods for creating whole-block Minecraft blocks with correct texturing - just needs minecraft path."""

def construct(blockID, basename, diffuseRGB, cubeTexFaces, extraData, constructType="box", shapeParams=None, cycParams=None):
    # find block function/constructor that matches the construct type.
    
    #if it's a simple cube...
    #stairs
    #onehigh
    #torch
    block = None
    if constructType == 'box':
        block = createMCBlock(basename, diffuseRGB, cubeTexFaces, cycParams)	#extra data
    elif constructType == 'onehigh':
        block = createInsetMCBlock(basename, diffuseRGB, cubeTexFaces, [0,15,0], cycParams)
    elif constructType == '00track':
        block = createTrack(basename, diffuseRGB, cubeTexFaces, extraData, cycParams)
    #elif constructType == 'hash':  #or crop? Is it the same? crops, etc.
    elif constructType == 'cross':
        block = createXBlock(basename, diffuseRGB, cubeTexFaces, extraData, cycParams)
    elif constructType == 'stair':
        block = createStairBlock(basename, diffuseRGB, cubeTexFaces, extraData, cycParams)
    elif constructType == 'fence':
        block = createFenceBlock(basename, diffuseRGB, cubeTexFaces, shapeParams, cycParams)    # for this, shape params will be NESW flags.
    elif constructType == 'inset':  #make an inset box (requires shapeParams)
        block = createInsetMCBlock(basename, diffuseRGB, cubeTexFaces, shapeParams, cycParams) #shapeprms must be a 3-list
    else:
        block = createMCBlock(basename, diffuseRGB, cubeTexFaces, cycParams)	#extra data	# soon to be removed as a catch-all!
    return block


def getMCTex():
    tname = 'mcTexBlocks'
    if tname in bpy.data.textures:
        return bpy.data.textures[tname]

    print("creating fresh new minecraft terrain texture")
    texNew = bpy.data.textures.new(tname, 'IMAGE')
    texNew.image = getMCImg()
    # FIXME
    #texNew.image.use_premultiply = True
    texNew.image.alpha_mode = 'PREMUL'
    texNew.use_alpha = True
    texNew.use_preview_alpha = True
    texNew.use_interpolation = False
    texNew.filter_type = 'BOX'    #no AA - nice minecraft pixels!

def getMCImg():
    global MCPATH
    osdir = os.getcwd()	#original os folder before jumping to temp.
    if 'terrain.png' in bpy.data.images:
        return bpy.data.images['terrain.png']
    else:
        img = None
        # FIXME - older save file location/layout?  Current releases use a different file, location, and ordering within the file... should we expect saves upgraded to latest release or provide a multiple choice/user customizable texture mapping?
        #import zipfile
        #mcjar = os.path.sep.join([MCPATH, 'bin', 'minecraft.jar'])
        # zf = open(mcjar, 'rb')
        # zipjar = zipfile.ZipFile(zf)
        # if 'terrain.png' in zipjar.namelist():
        #    os.chdir(bpy.app.tempdir)
        #    zipjar.extract('terrain.png')
        # zipjar.close()
        # zf.close()  #needed?
        #    #
        # temppath = os.path.sep.join([os.getcwd(), 'terrain.png'])
        temppath = os.path.sep.join([MCPATH, 'textures_0.png']) # FIXME - code is expecting terrain.png and a different layout
        
        if os.path.exists(temppath):
            img = bpy.data.images.load(temppath)
        else:
            # generate a placeholder image for the texture if terrain.png doesn't exist (rather than failing)
            print("no terrain texture found... creating empty")
            img = bpy.data.images.new('terrain.png', 1024, 1024, True, False)
            img.source = 'FILE'
        os.chdir(osdir)
        return img


def getCyclesMCImg():
    #Ideally, we want a very large version of terrain.png to hack around
    #cycles' inability to give us control of Alpha in 2.61
    #However, for now it just gives a separate instance of the normal one that
    #will need to be scaled up manually (ie replace this image to fix all transparent noodles)
    #todo: proper interpolation via nodes
    
    if 'hiResTerrain.png' not in bpy.data.images:
        im1 = None
        if 'terrain.png' not in bpy.data.images:
            im1 = getMCImg()
        else:
            im1 = bpy.data.images['terrain.png']

        #Create second version/instance of it.
        im2 = im1.copy()
        im2.name = 'hiResTerrain.png'
        #scale that up / modify... somehow? Add no-interpolation nodes

    return bpy.data.images['hiResTerrain.png']


def createBMeshBlockCubeUVs(blockname, me, matrl, faceIndices):    #assume me is a cube mesh.  RETURNS **NAME** of the uv layer created.
    """Uses faceIndices, a list of per-face MC texture indices, to unwrap
    the cube's faces onto their correct places on terrain.png.
    Face order for faceIndices is [Bottom,Top,Right,Front,Left,Back]"""
    #print("Creating bmesh uvs for: %s" % blockname)
    if faceIndices is None:
        print("Warning: no face texture for %s" % blockname)
        return

    __listtype = type([])
    if type(faceIndices) != __listtype:
        if (type(faceIndices) == type(0)):
            faceIndices = [faceIndices]*6
            print("Applying singular value to all 6 faces")
        else:
            print("setting material and uvs for %s: non-numerical face list" % blockname)
            print(faceIndices)
            raise IndexError("improper face assignment data!")

    if matrl.name not in me.materials:
        me.materials.append(matrl)

    uname = blockname + 'UVs'
    if uname in me.uv_textures:
        blockUVLayer = me.uv_textures[uname]
    else:
        blockUVLayer = me.uv_textures.new(name=uname)

    #blockUVLoop = me.uv_loop_layers[-1]	#works prior to 2.63??
    blockUVLoop = me.uv_layers.active
    uvData = blockUVLoop.data

    #bmesh face indices - a mapping to the new cube order
    #faceIndices face order is [Bottom,Top,Right,Front,Left,Back]
    #BMESH loop  face order is [left,back,right,front,bottom,top] (for default cube)
    bmfi = [faceIndices[4], faceIndices[5], faceIndices[2], faceIndices[3], faceIndices[0], faceIndices[1]]

    #get the loop, and iterate it based on the me.polygons face info. yay!
    #The order is a bit off from what might be expected, though...
    #And the uv order goes uv2 <-- uv1
    #                       |       ^
    #                       v       |
    #                      uv3 --> uv4
    # It's anticlockwise from top right.

    #the 4 always-the-same offsets from the uv tile to get its corners
    #(anticlockwise from top right).
    #TODO: get image dimension to automagically work with hi-res texture packs.
    uvUnit = 1/16.0     #one sixteenth, aka the normalised size of a tx tile within the texture image.
    #16px is 1/16th of the a 256x256 terrain.png. etc.
    #calculation of the tile location will get the top left corner, via "* 16".

    # these are the default face uvs, ie topright, topleft, botleft, botright.
    uvcorners = [(uvUnit, 0.0), (0.0,0.0), (0.0, -uvUnit), (uvUnit,-uvUnit)]
    #uvUnit is subtracted, as Y(v) counts up from image bottom, but I count 0 from top
    #top is rotated from default
    uvcornersTop = [(uvUnit,-uvUnit), (uvUnit, 0.0), (0.0,0.0), (0.0, -uvUnit)] # 4,1,2,3
    #bottom is rotated and flipped from default
    uvcornersBot = [(0.0, -uvUnit), (0.0,0.0), (uvUnit, 0.0), (uvUnit,-uvUnit)] # 3,2,1,4

    #we have to assign each UV in sequence of the 'loop' for the whole mesh: 24 for a cube.
    
    xim = getMCImg()
    meshtexfaces = blockUVLayer.data.values()

    matrl.game_settings.alpha_blend = 'CLIP'
    matrl.game_settings.use_backface_culling = False

    faceNo = 0  #or enumerate me.polygons?
    #face order is: [left,back,right,front,bottom,top]
    for pface in me.polygons:
        face = meshtexfaces[faceNo]
        face.image = xim
        faceTexId = bmfi[faceNo]
        #calculate the face location on the uvmap
        mcTexU = faceTexId % 16
        mcTexV = int(faceTexId / 16)  #int division.
        #DEBUG print("minecraft chunk texture x,y within image: %d,%d" % (mcTexU, mcTexV))
        #multiply by square size to get U1,V1 (topleft):
        u1 = (mcTexU * 16.0) / 256.0    # or >> 4 (div by imagesize to get as fraction)
        v1 = (mcTexV * 16.0) / 256.0    # ..
        v1 = 1.0 - v1 #y goes low to high   #DEBUG print("That means u1,v1 is %f,%f" % (u1,v1))

        loopPolyStart = pface.loop_start  #where its verts start in the loop. Yay!
        #if loop total's not 4, need to work with ngons or tris or do more complex stuff.
        loopPolyCount = pface.loop_total
        loopPolyEnd = loopPolyStart + loopPolyCount

        corners = uvcorners
        if faceNo == 5: #top face
            corners = uvcornersTop
        elif faceNo == 4:   #bottom face
            corners = uvcornersBot
        uvx = 0
        for uvc in range(loopPolyStart, loopPolyEnd):
            offset = corners[uvx] # 0..3
            mcUV = Vector((u1+offset[0], v1+offset[1]))
            #apply the calculated face uv + vert offset to the current loop element

            uvData[uvc].uv = mcUV
            uvx += 1
        faceNo += 1

    me.tessface_uv_textures.data.update()   #a guess. does this actually help? YES! Without it all the world's grey and textureless!

    return "".join([blockname, 'UVs'])


def createBlockCubeUVs(blockname, me, matrl, faceIndices):    #assume me is a cube mesh.  RETURNS **NAME** of the uv layer created.
    #Use faceIndices, a list of per-face MC texture square indices, to unwrap 
    #the cube's faces to correct places on terrain.png
    if faceIndices is None:
        print("Warning: no face texture for %s" % blockname)
        return

    #Face order is [Bottom,Top,Right,Front,Left,Back]
    __listtype = type([])
    if type(faceIndices) != __listtype:
        if (type(faceIndices) == type(0)):
            faceIndices = [faceIndices]*6
            print("Applying singular value to all 6 faces")
        else:
            print("setting material and uvs for %s: non-numerical face list" % blockname)
            print(faceIndices)
            raise IndexError("improper face assignment data!")

    if matrl.name not in me.materials:
        me.materials.append(matrl)
    
    uname = blockname + 'UVs'
    blockUVLayer = me.uv_textures.new(uname)   #assuming it's not so assigned already, ofc.
    xim = getMCImg()
    meshtexfaces = blockUVLayer.data.values()

    #Legacy compatibility feature: before 2.60, the alpha clipping is set not
    #via the 'game_settings' but in the material...
    bver = bpy.app.version[0] + bpy.app.version[1] / 100.0  #eg 2.59
    if bver >= 2.6:
        matrl.game_settings.alpha_blend = 'CLIP'
        matrl.game_settings.use_backface_culling = False

    for fnum, fid in enumerate(faceIndices):
        face = meshtexfaces[fnum]
        face.image = xim
        if bver < 2.6:
            face.blend_type = 'ALPHA'
        #use_image

        #Pick UV square off the 2D texture surface based on its Minecraft texture 'index'
        #eg 160 for lapis, 49 for glass, etc.
    
        mcTexU = fid % 16
        mcTexV = int(fid / 16)  #int division.


        #multiply by square size to get U1,V1:
        u1 = (mcTexU * 16.0) / 256.0    # or >> 4 (div by imagesize to get as fraction)
        v1 = (mcTexV * 16.0) / 256.0    # ..
        v1 = 1.0 - v1 #y goes low to high for some reason.

        #DEBUG print("That means u1,v1 is %f,%f" % (u1,v1))
        #16px will be 1/16th of the image.
        #The image is 256px wide and tall.

        uvUnit = 1/16.0

        mcUV1 = Vector((u1,v1))
        mcUV2 = Vector((u1+uvUnit,v1))
        mcUV3 = Vector((u1+uvUnit,v1-uvUnit))  #subtract uvunit for y  
        mcUV4 = Vector((u1, v1-uvUnit))

        #DEBUG print("Creating UVs for face with values: %f,%f to %f,%f" % (u1,v1,mcUV3[0], mcUV3[1]))

        #We assume the cube faces are always the same order.
        #So, face 0 is the bottom.
        if fnum == 1:    # top
            face.uv1 = mcUV2
            face.uv2 = mcUV1
            face.uv3 = mcUV4
            face.uv4 = mcUV3
        elif fnum == 5:    #back
            face.uv1 = mcUV1
            face.uv2 = mcUV4
            face.uv3 = mcUV3
            face.uv4 = mcUV2
        else:   #bottom (0) and all the other sides..
            face.uv1 = mcUV3
            face.uv2 = mcUV2
            face.uv3 = mcUV1
            face.uv4 = mcUV4

    return "".join([blockname, 'UVs'])

    #References for UV stuff:

#http://www.blender.org/forum/viewtopic.php?t=15989&view=previous&sid=186e965799143f26f332f259edd004f4

    #newUVs = cubeMesh.uv_textures.new('lapisUVs')
    #newUVs.data.values() -> list... readonly?

    #contains one item per face...
    #each item is a bpy_struct MeshTextureFace
    #each has LOADS of options
    
    # .uv1 is a 2D Vector(u,v)
    #they go:
    
    # uv1 --> uv2
    #          |
    #          V
    # uv4 <-- uv3
    #
    # .. I think

## For comments/explanation, see above.
def createInsetUVs(blockname, me, matrl, faceIndices, insets):
    """Returns name of UV layer created."""
    __listtype = type([])
    if type(faceIndices) != __listtype:
        if (type(faceIndices) == type(0)):
            faceIndices = [faceIndices]*6
            print("Applying singular value to all 6 faces")
        else:
            print("setting material and uvs for %s: non-numerical face list" % blockname)
            print(faceIndices)
            raise IndexError("improper face assignment data!")

    #faceindices: array of minecraft material indices into the terrain.png.
    #Face order is [Bottom,Top,Right,Front,Left,Back]
    uname = blockname + 'UVs'
    blockUVLayer = me.uv_textures.new(uname)

    xim = getMCImg()
    #ADD THE MATERIAL! ...but why not earlier than this? uv layer add first?
    if matrl.name not in me.materials:
        me.materials.append(matrl)

    meshtexfaces = blockUVLayer.data.values()
    bver = bpy.app.version[0] + bpy.app.version[1] / 100.0  #eg 2.59
    if bver >= 2.6:
        matrl.game_settings.alpha_blend = 'CLIP'
        matrl.game_settings.use_backface_culling = False

    #Insets are [bottom,top,sides]
    uvUnit = 1/16.0
    uvPixl = uvUnit / 16.0
    iB = insets[0] * uvPixl
    iT = insets[1] * uvPixl
    iS = insets[2] * uvPixl
    for fnum, fid in enumerate(faceIndices):
        face = meshtexfaces[fnum]
        face.image = xim
        
        if bver < 2.6:
            face.blend_type = 'ALPHA'
        
        #Pick UV square off the 2D texture surface based on its Minecraft index
        #eg 160 for lapis, 49 for glass... etc, makes for x,y:
        mcTexU = fid % 16
        mcTexV = int(fid / 16)  #int division.
        #DEBUG print("MC chunk tex x,y in image: %d,%d" % (mcTexU, mcTexV))
        #multiply by square size to get U1,V1:

        u1 = (mcTexU * 16.0) / 256.0    # or >> 4 (div by imagesize to get as fraction)
        v1 = (mcTexV * 16.0) / 256.0
        v1 = 1.0 - v1 #y goes low to high for some reason. (er...)
        #DEBUG print("That means u1,v1 is %f,%f" % (u1,v1))
    
        #16px will be 1/16th of the image.
        #The image is 256px wide and tall.

        mcUV1 = Vector((u1,v1))
        mcUV2 = Vector((u1+uvUnit,v1))
        mcUV3 = Vector((u1+uvUnit,v1-uvUnit))  #subtract uvunit for y  
        mcUV4 = Vector((u1, v1-uvUnit))

        #DEBUG print("Creating UVs for face with values: %f,%f to %f,%f" % (u1,v1,mcUV3[0], mcUV3[1]))

        #can we assume the cube faces are always the same order? It seems so, yes.
        #So, face 0 is the bottom.
        if fnum == 0:   #bottom
            face.uv1 = mcUV3
            face.uv2 = mcUV2
            face.uv3 = mcUV1
            face.uv4 = mcUV4

            face.uv3 = Vector((face.uv3[0]+iS, face.uv3[1]-iS))
            face.uv2 = Vector((face.uv2[0]-iS, face.uv2[1]-iS))
            face.uv1 = Vector((face.uv1[0]-iS, face.uv1[1]+iS))
            face.uv4 = Vector((face.uv4[0]+iS, face.uv4[1]+iS))
        
        elif fnum == 1:    # top
            face.uv1 = mcUV2
            face.uv2 = mcUV1
            face.uv3 = mcUV4
            face.uv4 = mcUV3
            
            #do insets! OMG, they really ARE anticlockwise. ffs.
            #why wasn't it right the very, very first time?!
            ## Nope. This is messed up. The error is endemic and spread
            #through all uv application in this script.
            #vertex ordering isn't the problem, script references have
            #confused the entire issue.
    # uv1(2)-> uv2 (1)
    #          |
    #          V
    # uv4(3) <-- uv3(4)
            face.uv2 = Vector((face.uv2[0]+iS, face.uv2[1]-iS))
            face.uv1 = Vector((face.uv1[0]-iS, face.uv1[1]-iS))
            face.uv4 = Vector((face.uv4[0]-iS, face.uv4[1]+iS))
            face.uv3 = Vector((face.uv3[0]+iS, face.uv3[1]+iS))

        elif fnum == 5:    #back
            face.uv1 = mcUV1
            face.uv2 = mcUV4
            face.uv3 = mcUV3
            face.uv4 = mcUV2

            face.uv1 = Vector((face.uv1[0]+iS, face.uv1[1]-iT))
            face.uv4 = Vector((face.uv4[0]-iS, face.uv4[1]-iT))
            face.uv3 = Vector((face.uv3[0]-iS, face.uv3[1]+iB))
            face.uv2 = Vector((face.uv2[0]+iS, face.uv2[1]+iB))
            
        else:   #all the other sides..
            face.uv1 = mcUV3
            face.uv2 = mcUV2
            face.uv3 = mcUV1
            face.uv4 = mcUV4

            face.uv3 = Vector((face.uv3[0]+iS, face.uv3[1]-iT))
            face.uv2 = Vector((face.uv2[0]-iS, face.uv2[1]-iT))
            face.uv1 = Vector((face.uv1[0]-iS, face.uv1[1]+iB))
            face.uv4 = Vector((face.uv4[0]+iS, face.uv4[1]+iB))
        

    return "".join([blockname, 'UVs'])


def createBMeshInsetUVs(blockname, me, matrl, faceIndices, insets):
    """Uses faceIndices, a list of per-face MC texture indices, to unwrap
    the cube's faces onto their correct places on terrain.png.
    Uses 3 insets ([bottom,top,sides]) to indent UVs per-face.
    Face order for faceIndices is [Bottom,Top,Right,Front,Left,Back]"""
    #print("Creating bmesh uvs for: %s" % blockname)
    if faceIndices is None:
        print("Warning: no face texture for %s" % blockname)
        return

    __listtype = type([])
    if type(faceIndices) != __listtype:
        if (type(faceIndices) == type(0)):
            faceIndices = [faceIndices]*6
            print("Applying singular value to all 6 faces")
        else:
            print("setting material and uvs for %s: non-numerical face list" % blockname)
            print(faceIndices)
            raise IndexError("improper face assignment data!")

    if matrl.name not in me.materials:
        me.materials.append(matrl)

    uname = blockname + 'UVs'
    if uname in me.uv_textures:
        blockUVLayer = me.uv_textures[uname]
    else:
        blockUVLayer = me.uv_textures.new(name=uname)

    #blockUVLoop = me.uv_loop_layers[-1]	#Works prior to 2.63! no it doesn't!!
    blockUVLoop = me.uv_layers.active
    uvData = blockUVLoop.data

    bmfi = [faceIndices[4], faceIndices[5], faceIndices[2], faceIndices[3], faceIndices[0], faceIndices[1]]
    uvUnit = 1/16.0     #one sixteenth, aka the normalised size of a tx tile within the texture image.
    #Insets are [bottom,top,sides]
    uvPixl = uvUnit / 16.0
    iB = insets[0] * uvPixl #insetBottom
    iT = insets[1] * uvPixl #insetTop
    iS = insets[2] * uvPixl #insetSides

    #Sorry. This array set is going to be dense, horrible, and impenetrable.
    #For the simple version of this, see createBMeshUVs, not the insets one     #uvcorners is for sides. Xvalues affected by iS
    uvcorners = [(uvUnit-iS, 0.0-iT), (0.0+iS,0.0-iT), (0.0+iS, -uvUnit+iB), (uvUnit-iS,-uvUnit+iB)]
    uvcornersTop = [(uvUnit-iS,-uvUnit+iS), (uvUnit-iS, 0.0-iS), (0.0+iS,0.0-iS), (0.0+iS, -uvUnit+iS)] # 4,1,2,3
    uvcornersBot = [(0.0+iS, -uvUnit+iS), (0.0+iS,0.0-iS), (uvUnit-iS, 0.0-iS), (uvUnit-iS,-uvUnit+iS)] # 3,2,1,4
    
    xim = getMCImg()
    meshtexfaces = blockUVLayer.data.values()

    matrl.game_settings.alpha_blend = 'CLIP'
    matrl.game_settings.use_backface_culling = False

    faceNo = 0  #or enumerate me.polygons?
    #face order is: [left,back,right,front,bottom,top]
    for pface in me.polygons:
        face = meshtexfaces[faceNo]
        face.image = xim
        faceTexId = bmfi[faceNo]
        #calculate the face location on the uvmap
        mcTexU = faceTexId % 16
        mcTexV = int(faceTexId / 16)  #int division.
        #DEBUG print("minecraft chunk texture x,y within image: %d,%d" % (mcTexU, mcTexV))
        #multiply by square size to get U1,V1 (topleft):
        u1 = (mcTexU * 16.0) / 256.0    # or >> 4 (div by imagesize to get as fraction)
        v1 = (mcTexV * 16.0) / 256.0    # ..
        v1 = 1.0 - v1 #y goes low to high   #DEBUG print("That means u1,v1 is %f,%f" % (u1,v1))

        loopPolyStart = pface.loop_start  #where its verts start in the loop. Yay!
        #if loop total's not 4, need to work with ngons or tris or do more complex stuff.
        loopPolyCount = pface.loop_total
        loopPolyEnd = loopPolyStart + loopPolyCount

        corners = uvcorners
        if faceNo == 5: #top face
            corners = uvcornersTop
        elif faceNo == 4:   #bottom face
            corners = uvcornersBot
        uvx = 0
        for uvc in range(loopPolyStart, loopPolyEnd):
            offset = corners[uvx] # 0..3
            mcUV = Vector((u1+offset[0], v1+offset[1]))
            #apply the calculated face uv + vert offset to the current loop element

            uvData[uvc].uv = mcUV
            uvx += 1
        faceNo += 1

    me.tessface_uv_textures.data.update()   #Without this, all the world is grey and textureless!

    return "".join([blockname, 'UVs'])
    

#CYCLES! Exciting!

#for an emission, we just replace the diffuse node (Diffuse BDSF) with an Emission node (EMISSION)
# You can't just change the type as it's read-only, so will need to create a new node of the right type,
# put it in the old BSDF node's location, then swap the inputs and finally delete the old (disconnected)
#diffuse node.
# For transparency, need to script-in A'n'W's setup.

def createDiffuseCyclesMat(mat):
    """Changes a BI basic textured, diffuse material for use with Cycles.
    Assumes that the material in question already has an associated UV Mapping."""

    #compatibility with Blender 2.5x:
    if not hasattr(bpy.context.scene, 'cycles'):
        print("No cycles support... skipping")
        return
    
    #Switch render engine to Cycles. Yippee ki-yay!
    if bpy.context.scene.render.engine != 'CYCLES':
        bpy.context.scene.render.engine = 'CYCLES'

    mat.use_nodes = True

    #maybe check number of nodes - there should be 2.
    ntree = mat.node_tree
    
    #print("Examining material nodetree for %s!" % mat.name)
    #print("["%s,%s" % (n.name, n.type) for n in mat.node_tree.nodes]")
    
    #get refs to existing nodes:
    diffNode = ntree.nodes['Diffuse BSDF']
    matOutNode = ntree.nodes['Material Output']
    #add the two new ones we need (texture inputs)
    #imgTexNode = ntree.nodes.new(type='TEX_IMAGE')
    imgTexNode = ntree.nodes.new(type='ShaderNodeTexImage')
    #texCoordNode = ntree.nodes.new(type='TEX_COORD')
    texCoordNode = ntree.nodes.new(type='ShaderNodeTexCoord')

    #Plug the UVs from texCoord into the Image texture (and assign the image from existing texture!)
    #img = mat. texture? .image?
    imgTexNode.image = getMCImg() ##bpy.data.images['terrain.png']   #hardwired for MCraft...
    #maybe imgTexNode.color_space = 'LINEAR' needed?! probably yes...
    
    ntree.links.new(input=texCoordNode.outputs['UV'], output=imgTexNode.inputs['Vector'])

    #Plug the image output into the diffuseNode's Color input
    ntree.links.new(input=imgTexNode.outputs['Color'], output=diffNode.inputs['Color'])
    
    #Arrange the nodes in a clean layout:
    texCoordNode.location = Vector((-200, 200))
    imgTexNode.location = Vector((0, 200))
    diffNode.location = Vector((250,200))
    matOutNode.location = Vector((450,200))


def createEmissionCyclesMat(mat, emitAmt):
    """Changes a BI basic textured, diffuse material for use with Cycles.
    Sets up the same as a diffuse cycles material, but with emission instead of Diffuse BDSF.
    Assumes that the material in question already has an associated UV Mapping."""

    createDiffuseCyclesMat(mat)

    ntree = mat.node_tree   #there will now be 4 nodes in there, one of them being the diffuse shader.
    nodes = ntree.nodes
    links = ntree.links

    #get ref to existing nodes:
    diffNode = nodes['Diffuse BSDF']
    #emitNode = nodes.new(type='EMISSION')
    emitNode = nodes.new(type='ShaderNodeEmission')

    #position emission node on same place as diff was:
    #loc = diffNode.location
    #emitNode.location = loc
    emitNode.location = diffNode.location

    #change links: delete the old links and add new ones.

    colorDiffSockIn = diffNode.inputs['Color']
    emitNode.inputs['Strength'].default_value = float(emitAmt) #set this from the EMIT value of data passed in.

    bsdfDiffSockOut = diffNode.outputs['BSDF']
    emitSockOut = emitNode.outputs[0]

    for nl in links:
        if nl.to_socket == colorDiffSockIn:
            links.remove(nl)

        # FIXME - ReferenceError: StructRNA of type NodeLink has been removed
        #if nl.from_socket == bsdfDiffSockOut:
        #    links.remove(nl)

    #now create new linkages to the new emit node:

    matOutNode = nodes['Material Output']
    imgTexNode = nodes['Image Texture']
    links.new(input=imgTexNode.outputs['Color'], output=emitNode.inputs['Color'])
    links.new(input=emitNode.outputs[0], output=matOutNode.inputs['Surface'])

    #and remove the diffuse shader, which is no longer needed.
    nodes.remove(diffNode)


def createPlainTransparentCyclesMat(mat):
    """Creates an 'alpha-transparent' Cycles material with no colour-cast overlay.
    Useful for objects such as Ladders, Doors, Flowers, Tracks, etc. """

    #Ensure Cycles is in use
    if bpy.context.scene.render.engine != 'CYCLES':
        bpy.context.scene.render.engine = 'CYCLES'
    mat.use_nodes = True

    ntree = mat.node_tree
    ntree.nodes.clear()

    #Create all needed nodes:
    #nn = ntree.nodes.new(type="TEX_COORD")
    nn = ntree.nodes.new(type="ShaderNodeTexCoord")
    nn.name = "Texture Coordinate"
    nn.location = Vector((-200.000, 200.000))
    #nn = ntree.nodes.new(type="OUTPUT_MATERIAL")
    nn = ntree.nodes.new(type="ShaderNodeOutputMaterial")
    nn.name = "Material Output"
    nn.location = Vector((850.366, 221.132))
    #nn.inputs['Displacement'].default_value = 0.0
    #nn = ntree.nodes.new(type="TEX_IMAGE")
    nn = ntree.nodes.new(type="ShaderNodeTexImage")
    nn.name = "Image Texture"
    nn.location = Vector((35.307, 172.256))
    #nn.inputs['Vector'].default_value = bpy.data.node_groups['Shader Nodetree'].nodes["Image Texture"].inputs[0].default_value
    nn.image = getCyclesMCImg()
    
    #todo: fix/set the image texture. This needs to be the scaled-up one, here. So make it the normal one, but with a different name.
    #check diffuse for how this gets set to the right value!
    #nn = ntree.nodes.new(type="RGBTOBW")
    nn = ntree.nodes.new(type="ShaderNodeRGBToBW")
    nn.name = "RGB to BW"
    nn.location = Vector((217.001, 274.182))

    #nn = ntree.nodes.new(type="MATH")
    nn = ntree.nodes.new(type="ShaderNodeMath")
    nn.name = "AlphaBlackGT"
    nn.operation = 'GREATER_THAN'
    nn.location = Vector((387.480, 325.267))
    nn.inputs[0].default_value = 0.001
    #nn.inputs[1].default_value = 0.001
    #nn = ntree.nodes.new(type="BSDF_DIFFUSE")
    nn = ntree.nodes.new(type="ShaderNodeBsdfDiffuse")
    nn.name = "Diffuse BSDF"
    nn.location = Vector((357.214, 181.751))
    ###nn.inputs['Color'].default_value = bpy.data.node_groups['Shader Nodetree'].nodes["Diffuse BSDF"].inputs[0].default_value
    nn.inputs['Roughness'].default_value = 0.0
    #nn = ntree.nodes.new(type="BSDF_TRANSPARENT")
    nn = ntree.nodes.new(type="ShaderNodeBsdfTransparent")
    nn.name = "Transparent BSDF"
    nn.location = Vector((356.909, 70.560))
    ###nn.inputs['Color'].default_value = bpy.data.node_groups['Shader Nodetree'].nodes["Transparent BSDF"].inputs[0].default_value
    #nn = ntree.nodes.new(type="MIX_SHADER")
    nn = ntree.nodes.new(type="ShaderNodeMixShader")
    nn.name = "Mix Shader"
    nn.location = Vector((641.670, 223.397))
    nn.inputs['Fac'].default_value = 0.5

    #link creation
    nd = ntree.nodes
    links = ntree.links
    links.new(input=nd['Diffuse BSDF'].outputs['BSDF'], output=nd['Mix Shader'].inputs[1])
    links.new(input=nd['Texture Coordinate'].outputs['UV'], output=nd['Image Texture'].inputs['Vector'])
    links.new(input=nd['Image Texture'].outputs['Color'], output=nd['Diffuse BSDF'].inputs['Color'])
    links.new(input=nd['Image Texture'].outputs['Color'], output=nd['RGB to BW'].inputs['Color'])
    links.new(input=nd['Mix Shader'].outputs['Shader'], output=nd['Material Output'].inputs['Surface'])
    links.new(input=nd['Transparent BSDF'].outputs['BSDF'], output=nd['Mix Shader'].inputs[2])
    links.new(input=nd['AlphaBlackGT'].outputs['Value'], output=nd['Mix Shader'].inputs['Fac'])
    links.new(input=nd['RGB to BW'].outputs['Val'], output=nd['AlphaBlackGT'].inputs[1])    #2nd input. Tres importante.



def setupCyclesMat(material, cyclesParams):
    if 'emit' in cyclesParams:
        emitAmt = cyclesParams['emit']
        if emitAmt > 0.0:
            createEmissionCyclesMat(material, emitAmt)
            return

    if 'transp' in cyclesParams and cyclesParams['transp']: #must be boolean true
        if 'ovr' in cyclesParams:
            #get the overlay colour, and create a transp overlay material.
            return
        #not overlay
        createPlainTransparentCyclesMat(material)
        return
    
    createDiffuseCyclesMat(material)


def getMCMat(blocktype, rgbtriple, cyclesParams=None):  #take cycles params Dictionary - ['type': DIFF/EMIT/TRANSP, 'emitAmt': 0.0]
    """Creates or returns a general-use default Minecraft material."""
    matname = blocktype + 'Mat'

    if matname in bpy.data.materials:
        return bpy.data.materials[matname]

    blockMat = bpy.data.materials.new(matname)
    ## ALL-MATERIAL DEFAULTS
    blockMat.use_transparency = True # surely not for everything!? not stone,dirt,etc!
    blockMat.alpha = 0.0
    blockMat.specular_alpha = 0.0
    blockMat.specular_intensity = 0.0

    ##TODO: blockMat.use_transparent_shadows - on recving objects (solids)
    ##TODO: Cast transparent shadows from translucent things like water.
    if rgbtriple is not None:
        #create the solid shaded-view material colour
        diffusecolour = [n/256.0 for n in rgbtriple]
        blockMat.diffuse_color = diffusecolour
        blockMat.diffuse_shader = 'OREN_NAYAR'
        blockMat.diffuse_intensity = 0.8
        blockMat.roughness = 0.909
    else:
        #create a blank/obvious 'unhelpful' material.
        blockMat.diffuse_color = [214,127,255] #shocking pink
    return blockMat


###############################################################################
#                 Primary Block-Shape Creation Functions                      #
###############################################################################

def createInsetMCBlock(mcname, colourtriple, mcfaceindices, insets=[0,0,0], cyclesParams=None):
    """With no insets (the default), creates a full-size cube.
Else uses [bottom,top,sides] to inset the cube size and UV coords.
Side insets are applied symmetrically around the cube; maximum side inset is 7.
Units are in Minecraft texels - so from 1 to 15. Inset 16 is an error."""
    blockname = mcname + 'Block'
    if blockname in bpy.data.objects:
        return bpy.data.objects[blockname]

    pxlUnit = 1/16.0    #const
    #Base cube
    bpy.ops.object.mode_set(mode='OBJECT')  #just to be sure... needed?
    bpy.ops.mesh.primitive_cube_add()
    blockOb = bpy.context.object    #ref to last created ob.
    bpy.ops.transform.resize(value=(0.5, 0.5, 0.5)) #quarter size (to 1x1x1)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    blockOb.name = blockname
    mesh = blockOb.data
    meshname = blockname + 'Mesh'
    mesh.name = meshname

    #Inset the mesh
    verts = mesh.vertices

    if isBMesh():   #inset the mesh, bmesh-version.
        #loop the verts per face, change their .co by the inset amount.
        #tverts = mesh.tessfaces.data.vertices # unneeded..
        #polygon face order is: [left,back,right,front,bottom,top]
        leface = mesh.polygons[0]
        bkface = mesh.polygons[1]
        rgface = mesh.polygons[2]
        frface = mesh.polygons[3]
        botface= mesh.polygons[4]
        topface= mesh.polygons[5]

    else:
        botface = mesh.faces[0]
        topface = mesh.faces[1]
        rgface  = mesh.faces[2]
        frface  = mesh.faces[3]
        leface  = mesh.faces[4]
        bkface  = mesh.faces[5]

    bi = insets[0] * pxlUnit
    ti = insets[1] * pxlUnit
    si = insets[2] * pxlUnit

    #does this need to be enforced as global rather than local coords?
    #There are ways to inset these along their normal directions,
    #but it's complex to understand, so I'll just inset all sides. :(
    for v in topface.vertices:
        vtx = verts[v]
        vp = vtx.co
        vtx.co = Vector((vp[0], vp[1], vp[2]-ti))
    
    for v in botface.vertices:
        vtx = verts[v]
        vp = vtx.co
        vtx.co = Vector((vp[0], vp[1], vp[2]+bi))
    
    for v in rgface.vertices:
        vtx = verts[v]
        vp = vtx.co
        vtx.co = Vector((vp[0]-si, vp[1], vp[2]))

    for v in frface.vertices:
        vtx = verts[v]
        vp = vtx.co
        vtx.co = Vector((vp[0], vp[1]+si, vp[2]))

    for v in leface.vertices:
        vtx = verts[v]
        vp = vtx.co
        vtx.co = Vector((vp[0]+si, vp[1], vp[2]))

    for v in bkface.vertices:
        vtx = verts[v]
        vp = vtx.co
        vtx.co = Vector((vp[0], vp[1]-si, vp[2]))

    #Fetch/setup the material.
    blockMat = getMCMat(mcname, colourtriple, cyclesParams)

    mcTexture = getMCTex()
    blockMat.texture_slots.add()  #it has 18, but unassignable...
    mTex = blockMat.texture_slots[0]
    mTex.texture = mcTexture
    #set as active texture slot?
    
    mTex.texture_coords = 'UV'
    mTex.use_map_alpha = True	#mibbe not needed?

    mcuvs = None
    if isBMesh():
        mcuvs = createBMeshInsetUVs(mcname, mesh, blockMat, mcfaceindices, insets)
    else:
        mcuvs = createInsetUVs(mcname, mesh, blockMat, mcfaceindices, insets)

    if mcuvs is not None:
        mTex.uv_layer = mcuvs

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.transform.rotate(value=(-1.5708), axis=(0, 0, 1), constraint_axis=(False, False, True), constraint_orientation='GLOBAL')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')

    #last, setup cycles on the material if user asked for it.
    if cyclesParams is not None:
        setupCyclesMat(blockMat, cyclesParams)

    return blockOb


def createMCBlock(mcname, colourtriple, mcfaceindices, cyclesParams=None):
    """Creates a new minecraft WHOLE-block if it doesn't already exist, properly textured.
    Array order for mcfaceindices is: [bottom, top, right, front, left, back]"""

    #Has an instance of this blocktype already been made?
    blockname = mcname + 'Block'
    if blockname in bpy.data.objects:
        return bpy.data.objects[blockname]

    #Create cube
    bpy.ops.mesh.primitive_cube_add()
    blockOb = bpy.context.object    #get ref to last created ob.
    bpy.ops.transform.resize(value=(0.5, 0.5, 0.5))    #quarter size (to 1x1x1: it's currently 2x2x2 bu)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    blockOb.name = blockname
    blockMesh = blockOb.data
    meshname = blockname + 'Mesh'
    blockMesh.name = meshname

    #Fetch/setup the material.
    blockMat = getMCMat(mcname, colourtriple, cyclesParams)

#    #ADD THE MATERIAL! (conditional on it already being applied?)
#    blockMesh.materials.append(blockMat)    # previously is in the uvtex creation function for some reason...

    mcTexture = getMCTex()
    blockMat.texture_slots.add()  #it has 18, but unassignable...
    mTex = blockMat.texture_slots[0]
    mTex.texture = mcTexture
    #set as active texture slot?
    
    mTex.texture_coords = 'UV'
    mTex.use_map_alpha = True	#mibbe not needed?

    mcuvs = None
    if isBMesh():
        mcuvs = createBMeshBlockCubeUVs(mcname, blockMesh, blockMat, mcfaceindices)
    else:
        mcuvs = createBlockCubeUVs(mcname, blockMesh, blockMat, mcfaceindices)
    
    if mcuvs is not None:
        mTex.uv_layer = mcuvs
    #array order is: [bottom, top, right, front, left, back]
    
    #for the cube's faces to align correctly to Minecraft north, based on the UV assignments I've bodged, correct it all by spinning the verts after the fact. :p
    # -90degrees in Z. (clockwise a quarter turn)
    # Or, I could go through a crapload more UV assignment stuff, which is no fun at all.
    #bpy ENSURE MEDIAN rotation point, not 3d cursor pos.
    
    bpy.ops.object.mode_set(mode='EDIT')
    #bpy.ops.objects.editmode_toggle()
    bpy.ops.mesh.select_all(action='SELECT')
    #don't want toggle! Want "ON"!
    bpy.ops.transform.rotate(value=(-1.5708), axis=(0, 0, 1), constraint_axis=(False, False, True), constraint_orientation='GLOBAL')
    #bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')

    #last, setup cycles on the material if user asked for it.
    if cyclesParams is not None:
        setupCyclesMat(blockMat, cyclesParams)
    
    return blockOb

def createFenceBlock(mcname, colourtriple, mcfaceindices, shapeParams, cyclesParams=None):
    #create a central upright fencepost; determine side attachments during load process. ...
    #mcname + "fencePost"
    block = createInsetMCBlock(mcname, colourtriple, mcfaceindices, [0,0,6], cyclesParams)
    print("Fence added. Shape params: %s" % shapeParams.__repr__)
    return block


def createXBlock(basename, diffuseRGB, mcfaceindices, extraData, cycParams):
    """Creates an x-shaped billboard block if it doesn't already exist,
    properly textured. Array order for mcfaceindices is: [\, /].
    A single item facelist will be applied to both faces of the X."""

    #Has one of this blocktype already been made?
    blockname = basename + 'Block'
    if blockname in bpy.data.objects:
        return bpy.data.objects[blockname]

    if not isBMesh():
        return createMCBlock(basename, diffuseRGB, mcfaceindices, cycParams)

    import bmesh
    #BMesh-create X
    m = bmesh.new()
    xverts = [  (-0.45,0.45,0.5),   #v1
                (0.45,-0.45,0.5),
                (0.45,-0.45,-0.5),
                (-0.45,0.45,-0.5),  #v4
                (0.45,0.45,0.5),   #v5
                (-0.45,-0.45,0.5),
                (-0.45,-0.45,-0.5),
                (0.45,0.45,-0.5)  #v8
             ]

    for v in xverts:
        m.verts.new(v)

    #Looks like you can slice bm.verts! Nice!
    f1 = m.faces.new(m.verts[0:4])
    f2 = m.faces.new(m.verts[4:])

    meshname = blockname + 'Mesh'
    crossMesh = bpy.data.meshes.new(meshname)
    m.to_mesh(crossMesh)
    crossOb = bpy.data.objects.new(blockname, crossMesh)
    #link it in! Unlike the primitive cube, it doesn't self-link.
    bpy.context.scene.objects.link(crossOb)

    #Fetch/setup the material.
    crossMat = getMCMat(basename, diffuseRGB, cycParams)
    mcTexture = getMCTex()
    crossMat.texture_slots.add()  #it has 18, but unassignable.
    mTex = crossMat.texture_slots[0]
    mTex.texture = mcTexture
    #set as active texture slot?
    
    mTex.texture_coords = 'UV'
    mTex.use_map_alpha = True

    mcuvs = None
    mcuvs = createBMeshXBlockUVs(basename, crossMesh, crossMat, mcfaceindices)
    if mcuvs is not None:
        mTex.uv_layer = mcuvs

    #last, setup cycles on the material if user asked for it.
    if cycParams is not None:
        setupCyclesMat(crossMat, cycParams)

    return crossOb


def createBMeshXBlockUVs(blockname, me, matrl, faceIndices):    #assume me is an X mesh. Returns name of the uv layer created.
    """Uses faceIndices, a list of per-face MC texture indices, to unwrap
    the X's faces onto their correct places on terrain.png.
    Face order for faceIndices is [\,/]"""

    if faceIndices is None:
        print("Warning: no face texture for %s" % blockname)
        return

    __listtype = type([])
    if type(faceIndices) != __listtype:
        if (type(faceIndices) == type(0)):
            faceIndices = [faceIndices]*6
            print("Applying singular value to all 6 faces")
        else:
            print("setting material and uvs for %s: non-numerical face list" % blockname)
            print(faceIndices)
            raise IndexError("improper face assignment data!")

    if matrl.name not in me.materials:
        me.materials.append(matrl)

    uname = blockname + 'UVs'
    if uname in me.uv_textures:
        blockUVLayer = me.uv_textures[uname]
    else:
        blockUVLayer = me.uv_textures.new(name=uname)

    #blockUVLoop = me.uv_loop_layers[-1]	#works prior to 2.63?!
    blockUVLoop = me.uv_layers.active
    uvData = blockUVLoop.data

    #face indices: our X mesh is put together in the right order, so
    #should be just face 0, face 1 in the loop.

    if len(faceIndices) == 1:
        fOnly = faceIndices[0]
        faceIndices = [fOnly, fOnly]    #probably totally unecessary safety.

    bmfi = [faceIndices[0], faceIndices[1]]
    uvUnit = 1/16.0 #the normalised size of a tx tile within the texture image.
    #offsets from topleft of any uv 'tile' to its vert corners (CCW from TR):
    uvcorners = [(uvUnit, 0.0), (0.0,0.0), (0.0, -uvUnit), (uvUnit,-uvUnit)]
    #we assign each UV in sequence of the 'loop' for the whole mesh: 8 for an X

    xim = getMCImg()
    meshtexfaces = blockUVLayer.data.values()

    matrl.game_settings.alpha_blend = 'CLIP'
    matrl.game_settings.use_backface_culling = False

    #faceNo = 0  #or enumerate me.polygons?
    #face order is: [\,/]
    for faceNo, pface in enumerate(me.polygons):
        face = meshtexfaces[faceNo]
        face.image = xim
        faceTexId = bmfi[faceNo]
        #calculate the face location on the uvmap
        mcTexU = faceTexId % 16
        mcTexV = int(faceTexId / 16)  #int division.
        #multiply by square size to get U1,V1 (topleft):
        u1 = (mcTexU * 16.0) / 256.0    # or >> 4 (div by imagesize to get as fraction)
        v1 = (mcTexV * 16.0) / 256.0    # ..
        v1 = 1.0 - v1 #y goes low to high   #DEBUG print("That means u1,v1 is %f,%f" % (u1,v1))

        loopPolyStart = pface.loop_start  #where its verts start in loop. :D
        #if loop total's not 4, need to work with ngons/tris or do more complex stuff.
        loopPolyCount = pface.loop_total
        loopPolyEnd = loopPolyStart + loopPolyCount

        corners = uvcorners
        for n, loopV in enumerate(range(loopPolyStart, loopPolyEnd)):
            offset = corners[n] # 0..3
            mcUV = Vector((u1+offset[0], v1+offset[1]))
            uvData[loopV].uv = mcUV
        #faceNo += 1

   #a guess. does this actually help? YES! Without it all the world's grey and textureless!
    me.tessface_uv_textures.data.update()
    #but then, sometimes it's grey anyway. :(

    return "".join([blockname, 'UVs'])


def createStairsBlock(basename, diffuseRGB, mcfaceindices, extraData, cycParams):
    """Creates a stairs block if it doesn't already exist,
    properly textured. Will create new stair blocks by material,
    direction and inversion."""
    #DOES THE FACING DETERMINE THE UV UNWRAP? The public needs to know! if so... nuts! must be easier way? Can do cube mapping and rotate tex space??

    #Has one of this already been made?
    #... get direction and bytes unpack verticality 
    
    blockname = basename + 'Block'
    if blockname in bpy.data.objects:
        return bpy.data.objects[blockname]

    if not isBMesh():
        return createMCBlock(basename, diffuseRGB, mcfaceindices, cycParams)

    import bmesh
    #BMesh-create X
    
    stair = bmesh.new()
    #Stair Vertices
    sverts = [ (0.5,0.5,0.5),  #v0
            (0.5,0.5,-0.5), #v1
            (0.5,-0.5,-0.5), #v2
            (0.5,-0.5,0), #v3
            (0.5,0,0), #v4
            (0.5,0,0.5), #v5 -- X+ facing stair profile done.
            (-0.5,0.5,0.5),  #v6
            (-0.5,0.5,-0.5), #v7
            (-0.5,-0.5,-0.5), #v8
            (-0.5,-0.5,0), #v9
            (-0.5,0,0), #v10
            (-0.5,0,0.5), #v11 -- X- facing stair profile done.
            #would it be a good idea or a bad idea to reverse order of these latter 6?
          ]

    for v in sverts:
        stair.verts.new(v)
        svs = stair.verts
        #now the faces. in a specific order we can follow for unwrapping later

        #in a stair mesh, we'll have R1,R2 ; stairfacings(vertical) higher,lower; L1,L2; BACK; Top(tip),Top(midstep); Bottom. Maybe. Rearrange for cube order.
        sf1 = stair.faces.new([svs[0], svs[5], svs[4], svs[1]]) #r1
        sf2 = stair.faces.new([svs[4], svs[3], svs[2], svs[1]]) #r2
        sf3 = stair.faces.new([svs[5], svs[11], svs[10],svs[4]])  #vertical topstair face
        sf4 = stair.faces.new([svs[3], svs[9], svs[8],svs[2]])    #vertical bottomstair face
        sf5 = stair.faces.new([svs[9], svs[10], svs[7],svs[8]])   #lface1 (lower..)
        sf6 = stair.faces.new([svs[11],svs[6],svs[7],svs[10]])  #lface2 (upright higher bit)
        sf7 = stair.faces.new([svs[6], svs[0], svs[1],svs[7]])    #back
        sf8 = stair.faces.new([svs[0], svs[6], svs[11],svs[5]])    #topface, topstep
        sf9 = stair.faces.new([svs[4], svs[10], svs[9],svs[3]])    #topface, midstep
        sf10= stair.faces.new([svs[7], svs[1], svs[2],svs[8]])    #bottom

        #check the extra data for direction and upside-downness.
        
        
        
        sm   = bpy.data.meshes.new("StairMesh")
        stob = bpy.data.objects.new("Stair", sm)
        bpy.context.scene.objects.link(stob)
        stair.to_mesh(sm)

        #f1 = m.faces.new([v1,v2,v3,v4])


        #loop1 = f1.loops[0]

    #me = bpy.data.meshes.new("Foo")
    #ob = bpy.data.objects.new("Bar", me)
    #bpy.context.scene.objects.link(ob)


    pass










# #################################################

#if __name__ == "__main__":
#    #BlockBuilder.create ... might tidy up namespace.
#    #nublock  = createMCBlock("Glass", (1,2,3), [49]*6)
#    #nublock2 = createInsetMCBlock("Torch", (240,150,50), [80]*6, [0,6,7])
    
#    nublock3 = createInsetMCBlock("Chest", (164,114,39), [25,25,26,27,26,26], [0,1,1])
