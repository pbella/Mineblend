# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# Contributors:
# Originally authored by Acro
# Modified by Phil B

import bpy
from mathutils import *
import os, sys
from . import sysutil

DEBUG_BBUV = False
DEBUG_SHADER = False

#create class for the other functions? BlockBuilder.

#NICEIF: SpaceView3D.grid_subdivisions = 16 (so they're MC pixel-based)

TERRAIN_TEXTURE_ATLAS_NAME = 'textures_0.png' # based on the filename used by Minecraft (was terrain.png)
TEXTURE_ATLAS_UNITS = 32 # Number of textures x & y in the texture atlas (was 16)
TEXTURE_ATLAS_PIXELS_PER_UNIT = 16
TEXTURE_ATLAS_PIXELS = 512 # Pixel w & h of the texture atlas (TEXTURE_ATLAS_UNITS*TEXTURE_ATLAS_PIXELS_PER_UNIT) (was 256)

def getTextureAtlasU(faceTexId):
    return faceTexId % TEXTURE_ATLAS_UNITS

def getTextureAtlasV(faceTexId):
    return  int(faceTexId / TEXTURE_ATLAS_UNITS)  #int division.

def getUVUnit():
    #The normalised size of a tx tile within the texture image.
    return 1/TEXTURE_ATLAS_UNITS

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
    MCPATH = sysutil.getMCPath()
    osdir = os.getcwd()	#original os folder before jumping to temp.
    if TERRAIN_TEXTURE_ATLAS_NAME in bpy.data.images:
        return bpy.data.images[TERRAIN_TEXTURE_ATLAS_NAME]
    else:
        img = None
        temppath = os.path.sep.join([MCPATH, TERRAIN_TEXTURE_ATLAS_NAME])
        print("Mineblend loading terrain: "+temppath)
        
        if os.path.exists(temppath):
            img = bpy.data.images.load(temppath)
        else:
            # generate a placeholder image for the texture if terrain.png doesn't exist (rather than failing)
            print("no terrain texture found... creating empty")
            img = bpy.data.images.new(TERRAIN_TEXTURE_ATLAS_NAME, 1024, 1024, True, False)
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
        if TERRAIN_TEXTURE_ATLAS_NAME not in bpy.data.images:
            im1 = getMCImg()
        else:
            im1 = bpy.data.images[TERRAIN_TEXTURE_ATLAS_NAME]

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
    if DEBUG_BBUV:
        print("createBMeshBlockCubeUVs "+blockname+" attempting to get faces: "+str(faceIndices))
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
    uvUnit = getUVUnit()
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
        # FIXME - old 16x16 (256x256px) texture map
        ##calculate the face location on the uvmap
        #mcTexU = faceTexId % 16
        #mcTexV = int(faceTexId / 16)  #int division.
        ##multiply by square size to get U1,V1 (topleft):
        #u1 = (mcTexU * 16.0) / 256.0    # or >> 4 (div by imagesize to get as fraction)
        #v1 = (mcTexV * 16.0) / 256.0    # ..

        # New 25x19 (512x512px) texture map
        mcTexU = getTextureAtlasU(faceTexId)
        mcTexV = getTextureAtlasV(faceTexId)

        u1 = (mcTexU * TEXTURE_ATLAS_PIXELS_PER_UNIT) / TEXTURE_ATLAS_PIXELS
        v1 = (mcTexV * TEXTURE_ATLAS_PIXELS_PER_UNIT) / TEXTURE_ATLAS_PIXELS

        v1 = 1.0 - v1 #y goes low to high   #DEBUG print("That means u1,v1 is %f,%f" % (u1,v1))
        ##DEBUG
        if DEBUG_BBUV:
            print("mcTexU,mcTexV "+str(mcTexU)+", "+str(mcTexV)+" - u1, v1 %d,%d" % (u1,v1))
            #print("minecraft chunk texture x,y within image: %d,%d" % (mcTexU, mcTexV))
        #if DEBUG_BBUV:
        #    print("createBMeshBlockCubeUVs "+blockname+" u1, v1: %d,%d" % (u1, v1))

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

            if DEBUG_BBUV:
                print("offset "+str(offset)+", mvUV "+str(mcUV))
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
    
        mcTexU = getTextureAtlasU(fid)
        mcTexV = getTextureAtlasV(fid)


        #multiply by square size to get U1,V1:
        u1 = (mcTexU * TEXTURE_ATLAS_PIXELS_PER_UNIT) / TEXTURE_ATLAS_PIXELS    # or >> 4 (div by imagesize to get as fraction)
        v1 = (mcTexV * TEXTURE_ATLAS_PIXELS_PER_UNIT) / TEXTURE_ATLAS_PIXELS    # ..
        v1 = 1.0 - v1 #y goes low to high for some reason.

        #DEBUG print("That means u1,v1 is %f,%f" % (u1,v1))
        #16px will be 1/16th of the image.
        #The image is 256px wide and tall.

        uvUnit = getUVUnit()

        mcUV1 = Vector((u1,v1))
        mcUV2 = Vector((u1+uvUnit,v1))
        mcUV3 = Vector((u1+uvUnit,v1-uvUnit))  #subtract uvunit for y  
        mcUV4 = Vector((u1, v1-uvUnit))

        #DEBUG
        if DEBUG_BBUV:
            print("createBlockCubeUVs Creating UVs for face with values: %f,%f to %f,%f" % (u1,v1,mcUV3[0], mcUV3[1]))

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
    uvUnit = getUVUnit()
    uvPixl = uvUnit / TEXTURE_ATLAS_UNITS
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
        mcTexU = getTextureAtlasU(fid)
        mcTexV = getTextureAtlasV(fid)
        #DEBUG print("MC chunk tex x,y in image: %d,%d" % (mcTexU, mcTexV))
        #multiply by square size to get U1,V1:

        u1 = (mcTexU * TEXTURE_ATLAS_PIXELS_PER_UNIT) / TEXTURE_ATLAS_PIXELS    # or >> 4 (div by imagesize to get as fraction)
        v1 = (mcTexV * TEXTURE_ATLAS_PIXELS_PER_UNIT) / TEXTURE_ATLAS_PIXELS
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
    uvUnit = getUVUnit()
    #Insets are [bottom,top,sides]
    uvPixl = uvUnit / TEXTURE_ATLAS_UNITS
    iB = insets[0] * uvPixl #insetBottom
    iT = insets[1] * uvPixl #insetTop
    iS = insets[2] * uvPixl #insetSides

    #Sorry. This array set is going to be dense, horrible, and impenetrable.
    #For the simple version of this, see createBMeshUVs, not the insets one
    #uvcorners is for sides. Xvalues affected by iS
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
        mcTexU = getTextureAtlasU(faceTexId)
        mcTexV = getTextureAtlasV(faceTexId)
        #DEBUG
        if DEBUG_BBUV:
            print("createBMeshInsetUVs minecraft chunk texture x,y within image: %d,%d" % (mcTexU, mcTexV))

        #multiply by square size to get U1,V1 (topleft):
        u1 = (mcTexU * TEXTURE_ATLAS_PIXELS_PER_UNIT) / TEXTURE_ATLAS_PIXELS    # or >> 4 (div by imagesize to get as fraction)
        v1 = (mcTexV * TEXTURE_ATLAS_PIXELS_PER_UNIT) / TEXTURE_ATLAS_PIXELS    # ..
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
    

# Cycles materials.  createNGmc* are for Node Groups and create*CyclesMat are the for the materials that use them.
#
# Aside from simplifying the individual material layouts, the reason for using Node Groups extensively is to allow for users to easily customize the overall look of their scene (i.e. rather than having to modify dozens of materials, some changes can have global effect by modifying a single Node Group, depending on the change desired)

MC_SHADER_TEX="mcShaderTex"
MC_SHADER_DIFFUSE="mcShaderDiffuse"
MC_SHADER_STENCIL="mcShaderStencil"
MC_SHADER_STENCIL_COLORED="mcShaderStencilColored"
MC_GROUP_TEX_OUTPUT="Color"
MC_GROUP_DIFFUSE_OUTPUT="BSDF"
MC_GROUP_STENCIL_OUTPUT="Shader"
MC_GROUP_STENCIL_COLORED_OUTPUT="Shader"
TYPE_NODE_GROUP_INPUT="NodeGroupInput"
TYPE_NODE_GROUP_OUTPUT="NodeGroupOutput"
TYPE_NODE_GROUP="ShaderNodeGroup"
BSDF_OUTPUT="BSDF"
FACTOR_INPUT="Fac"

def createNGmcTexture():
    """Node Group for texture.  This is a simple texture atlas mapping"""
    if DEBUG_SHADER:
        print("createNGmcTexture")
    ng = bpy.data.node_groups.new(MC_SHADER_TEX,"ShaderNodeTree")
    ngo = ng.nodes.new(type=TYPE_NODE_GROUP_OUTPUT)
    texCoord = ng.nodes.new(type="ShaderNodeTexCoord")
    imageTex = ng.nodes.new(type="ShaderNodeTexImage")
    imageTex.image = getMCImg()
    imageTex.interpolation = "Closest"

    ng.links.new(imageTex.inputs[0],texCoord.outputs[2]) # link the texCoord uv to the imageTex vector
    ng.links.new(ngo.inputs[0],imageTex.outputs[0])
    ng.links.new(ngo.inputs[1],imageTex.outputs[1])

    texCoord.location = Vector((-200, 200))
    imageTex.location = Vector((0, 200))
    ngo.location = Vector((200, 200))

def setNodeGroup(node,ngName):
    if DEBUG_SHADER:
        print("setNodeGroup: "+ngName)
    # FIXME - is there a better way to use a node group from within a node group?
    node.name=ngName
    node.label=ngName
    node.node_tree=bpy.data.node_groups[ngName]

def createNGmcDiffuse():
    """Node Group for diffuse materials"""
    if DEBUG_SHADER:
        print("createNGmcDiffuse")
    ng = bpy.data.node_groups.new(MC_SHADER_DIFFUSE,"ShaderNodeTree")
    ngo = ng.nodes.new(type=TYPE_NODE_GROUP_OUTPUT)
    tex = ng.nodes.new(type=TYPE_NODE_GROUP)
    setNodeGroup(tex,MC_SHADER_TEX)
    diffuse = ng.nodes.new(type="ShaderNodeBsdfDiffuse")

    ng.links.new(diffuse.inputs[0],tex.outputs[0]) # link the texCoord uv to the imageTex vector
    ng.links.new(ngo.inputs[0],diffuse.outputs[0])
    ng.links.new(ngo.inputs[1],tex.outputs[1]) # For stained glass etc

    tex.location = Vector((0, 0))
    diffuse.location = Vector((200, 200))
    ngo.location = Vector((400, 0))

#def createNGmcStencil(): # FIXME - how to handle alternate node data flows? (i.e. loopback / inner node group issue)
#    ng = bpy.data.node_groups.new(MC_SHADER_STENCIL,"ShaderNodeTree")
#    ngo = ng.nodes.new(type="NodeGroupOutput")
#    ngi = ng.nodes.new(type="NodeGroupInput")
#    diffNode = ng.nodes.new(type="ShaderNodeGroup")
#    setNodeGroup(diffNode,MC_SHADER_DIFFUSE)
#
#    links = ng.links
#
#    rgbtobwNode = ng.nodes.new(type="ShaderNodeRGBToBW")
#    gtNode = ng.nodes.new(type="ShaderNodeMath")
#    gtNode.name = "AlphaBlackGT"
#    gtNode.operation = 'GREATER_THAN'
#    gtNode.inputs[0].default_value = 0.001
#
#    transpNode = ng.nodes.new(type="ShaderNodeBsdfTransparent")
#    mixNode = ng.nodes.new(type="ShaderNodeMixShader")
#
#    ngi.location = Vector((-200,0))
#    diffNode.location = Vector((0,0))
#    rgbtobwNode.location = Vector((200,200))
#    gtNode.location = Vector((400,200))
#    transpNode.location = Vector((400,-200))
#    mixNode.location = Vector((600,0))
#    ngo.location = Vector((800,0))
#
#    links.new(input=diffNode.outputs[MC_GROUP_DIFFUSE_OUTPUT], output=rgbtobwNode.inputs['Color'])
#    links.new(input=rgbtobwNode.outputs['Val'], output=gtNode.inputs[1])
#    links.new(input=gtNode.outputs['Value'], output=mixNode.inputs['Fac'])
#
#    #links.new(input=diffNode.outputs[MC_GROUP_DIFFUSE_OUTPUT], output=diff2Node.inputs['Color'])
#    #links.new(input=diff2Node.outputs['BSDF'], output=mixNode.inputs[1])
#
#    # leave the options open
#    #links.new(input=diffNode.outputs['BSDF'], output=mixNode.inputs[1])
#
#    links.new(input=transpNode.outputs['BSDF'], output=mixNode.inputs[2])
#
#    links.new(input=ngi.outputs[0], output=mixNode.inputs[1])
#
#    #links.new(input=mixNode.outputs['Shader'], output=ngo.inputs['Surface'])
#    links.new(input=mixNode.outputs['Shader'], output=ngo.inputs[0])
#    links.new(input=diffNode.outputs['BSDF'], output=ngo.inputs[1])

def createNGmcStencil():
    """Node Group for stencil materials (i.e. colored textures with alpha)"""
    if DEBUG_SHADER:
        print("createNGmcStencil")
    ng = bpy.data.node_groups.new(MC_SHADER_STENCIL,"ShaderNodeTree")
    ngo = ng.nodes.new(type=TYPE_NODE_GROUP_OUTPUT)
    ngi = ng.nodes.new(type=TYPE_NODE_GROUP_INPUT)
    inNode = ng.nodes.new(type=TYPE_NODE_GROUP)
    setNodeGroup(inNode,MC_SHADER_TEX)

    links = ng.links

    diffNode = ng.nodes.new(type="ShaderNodeBsdfDiffuse")
    rgbtobwNode = ng.nodes.new(type="ShaderNodeRGBToBW")
    gtNode = ng.nodes.new(type="ShaderNodeMath")
    gtNode.name = "AlphaBlackGT"
    gtNode.operation = 'GREATER_THAN'
    gtNode.inputs[0].default_value = 0.001

    transpNode = ng.nodes.new(type="ShaderNodeBsdfTransparent")
    mixNode = ng.nodes.new(type="ShaderNodeMixShader")

    ngi.location = Vector((-200,0))
    inNode.location = Vector((0,0))
    rgbtobwNode.location = Vector((200,200))
    diffNode.location = Vector((200,0))
    gtNode.location = Vector((400,200))
    transpNode.location = Vector((400,-200))
    mixNode.location = Vector((600,0))
    ngo.location = Vector((800,0))

    links.new(input=inNode.outputs[MC_GROUP_TEX_OUTPUT], output=rgbtobwNode.inputs['Color'])
    links.new(input=rgbtobwNode.outputs['Val'], output=gtNode.inputs[1])
    links.new(input=gtNode.outputs['Value'], output=mixNode.inputs[FACTOR_INPUT])

    # leave the options open
    links.new(input=inNode.outputs[MC_GROUP_TEX_OUTPUT], output=diffNode.inputs['Color'])
    links.new(input=diffNode.outputs[BSDF_OUTPUT], output=mixNode.inputs[1])

    links.new(input=transpNode.outputs[BSDF_OUTPUT], output=mixNode.inputs[2])

    links.new(input=mixNode.outputs['Shader'], output=ngo.inputs[0])

def createNGmcStencilColored():
    """Node Group for colored stencil materials (i.e. grey scale texture with alpha that needs to be colored)"""
    if DEBUG_SHADER:
        print("createNGmcStencilColored")
    ng = bpy.data.node_groups.new(MC_SHADER_STENCIL_COLORED,"ShaderNodeTree")
    ngo = ng.nodes.new(type=TYPE_NODE_GROUP_OUTPUT)
    ngi = ng.nodes.new(type=TYPE_NODE_GROUP_INPUT)
    texNode = ng.nodes.new(type=TYPE_NODE_GROUP)
    setNodeGroup(texNode,MC_SHADER_TEX)

    links = ng.links

    rgbtobwNode = ng.nodes.new(type="ShaderNodeRGBToBW")
    gtNode = ng.nodes.new(type="ShaderNodeMath")
    gtNode.name = "AlphaBlackGT"
    gtNode.operation = 'GREATER_THAN'
    gtNode.inputs[0].default_value = 0.001

    transpNode = ng.nodes.new(type="ShaderNodeBsdfTransparent")
    alphaMixNode = ng.nodes.new(type="ShaderNodeMixShader")

    ngi.location = Vector((-200,0))
    texNode.location = Vector((0,0))
    rgbtobwNode.location = Vector((200,200))
    gtNode.location = Vector((400,200))
    transpNode.location = Vector((400,-200))
    alphaMixNode.location = Vector((600,0))
    ngo.location = Vector((800,0))

    links.new(input=texNode.outputs[MC_GROUP_TEX_OUTPUT], output=rgbtobwNode.inputs['Color'])
    links.new(input=rgbtobwNode.outputs['Val'], output=gtNode.inputs[1])
    links.new(input=gtNode.outputs['Value'], output=alphaMixNode.inputs[FACTOR_INPUT])

    links.new(input=transpNode.outputs[BSDF_OUTPUT], output=alphaMixNode.inputs[2])

    links.new(input=alphaMixNode.outputs['Shader'], output=ngo.inputs[0])

    ## 'colored' specific portion of material
    colorMixNode = ng.nodes.new(type="ShaderNodeMixRGB")
    #colorMixNode.inputs[1].name="Dark color"
    #colorMixNode.inputs[2].name="Light color"
    colorDiffNode = ng.nodes.new(type="ShaderNodeBsdfDiffuse")

    colorMixNode.location = Vector((0,400))
    colorDiffNode.location = Vector((200,400))

    links.new(input=rgbtobwNode.outputs['Val'], output=colorMixNode.inputs[FACTOR_INPUT])
    # FIXME - material will not render correctly when names are set (i.e. even though the viewport looks fine, the rgb color mix needs to be re-added and links re-established for successful (i.e. non-black) render.)
    #colorMixNode.inputs[1].name="Dark color"
    #colorMixNode.inputs[2].name="Light color"
    #links.new(input=ngi.outputs[0], output=colorMixNode.inputs["Dark color"])
    #links.new(input=ngi.outputs[1], output=colorMixNode.inputs["Light color"])
    links.new(input=ngi.outputs[0], output=colorMixNode.inputs[1])
    links.new(input=ngi.outputs[1], output=colorMixNode.inputs[2])

    links.new(input=colorMixNode.outputs["Color"], output=colorDiffNode.inputs["Color"])
    links.new(input=colorDiffNode.outputs[BSDF_OUTPUT], output=alphaMixNode.inputs[1])
    ngi.outputs[1].name="Dark color"
    ngi.outputs[2].name="Light color"

def createNodeGroups():
    """Create node groups if they don't already exist"""
    if DEBUG_SHADER:
        print("createNodeGroups")
    existsNode = bpy.data.node_groups.get(MC_SHADER_DIFFUSE)
    if existsNode==None:
        createNGmcTexture()
        createNGmcDiffuse()
        createNGmcStencil()
        createNGmcStencilColored()

def removeExistingDiffuseNode(ntree):
    olddif = ntree.nodes['Diffuse BSDF']
    ntree.nodes.remove(olddif)

def createDiffuseCyclesMat(mat):
    """Create a basic textured, diffuse material that uses existing UV mapping into texture atlas"""
    if DEBUG_SHADER:
        print("createDiffuseCyclesMat")
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
    mcdif = ntree.nodes.new(type=TYPE_NODE_GROUP)
    setNodeGroup(mcdif,MC_SHADER_DIFFUSE)
    removeExistingDiffuseNode(ntree)
    matOutNode = ntree.nodes['Material Output']
    ntree.links.new(input=mcdif.outputs[MC_GROUP_DIFFUSE_OUTPUT], output=matOutNode.inputs['Surface'])
    mcdif.location = Vector((0,0))
    matOutNode.location = Vector((200,0))

def createEmissionCyclesMat(mat, emitAmt):
    """Emissive materials such as lava, glowstone, etc"""
    if DEBUG_SHADER:
        print("createEmissionCyclesMat")
    if bpy.context.scene.render.engine != 'CYCLES':
        bpy.context.scene.render.engine = 'CYCLES'

    mat.use_nodes = True

    ntree = mat.node_tree   #there will now be 4 nodes in there, one of them being the diffuse shader.
    removeExistingDiffuseNode(ntree)
    diffNode = ntree.nodes.new(type=TYPE_NODE_GROUP)
    setNodeGroup(diffNode,MC_SHADER_TEX)
    matNode = ntree.nodes['Material Output']
    emitNode = ntree.nodes.new(type='ShaderNodeEmission')
    nodes = ntree.nodes
    links = ntree.links

    diffNode.location = Vector((0,0))
    emitNode.location = Vector((200,0))
    matNode.location = Vector((400,0))

    #change links: delete the old links and add new ones.

    emitNode.inputs['Strength'].default_value = float(emitAmt) #set this from the EMIT value of data passed in.

    bsdfDiffSockOut = diffNode.outputs[MC_GROUP_TEX_OUTPUT]
    emitSockOut = emitNode.outputs[0]

    for nl in links:
        print("link "+str(nl))
        if nl.to_socket == matNode:
            links.remove(nl)

    links.new(input=diffNode.outputs[0], output=emitNode.inputs[0])
    links.new(input=emitNode.outputs[0], output=matNode.inputs['Surface'])


def createStencilCyclesMat(mat):
    """Stencil materials such as flowers"""
    if DEBUG_SHADER:
        print("createStencilCyclesMat")
    #Ensure Cycles is in use
    if bpy.context.scene.render.engine != 'CYCLES':
        bpy.context.scene.render.engine = 'CYCLES'
    mat.use_nodes = True

    ntree = mat.node_tree
    nodes = ntree.nodes
    links = ntree.links
    inNode =  ntree.nodes.new(type=TYPE_NODE_GROUP)
    setNodeGroup(inNode,MC_SHADER_TEX)
    diffNode = nodes["Diffuse BSDF"] # reuse the one that already exists
    matNode = nodes['Material Output']

    rgbtobwNode = ntree.nodes.new(type="ShaderNodeRGBToBW")
    gtNode = ntree.nodes.new(type="ShaderNodeMath")
    gtNode.name = "AlphaBlackGT"
    gtNode.operation = 'GREATER_THAN'
    gtNode.inputs[0].default_value = 0.001

    transpNode = ntree.nodes.new(type="ShaderNodeBsdfTransparent")
    mixNode = ntree.nodes.new(type="ShaderNodeMixShader")

    inNode.location = Vector((0,0))
    diffNode.location = Vector((200,0))
    rgbtobwNode.location = Vector((200,200))
    gtNode.location = Vector((400,200))
    transpNode.location = Vector((400,-200))
    mixNode.location = Vector((600,0))
    matNode.location = Vector((800,0))

    for nl in links:
        if nl.to_socket == matNode:
            links.remove(nl)

    links.new(input=inNode.outputs[MC_GROUP_TEX_OUTPUT], output=rgbtobwNode.inputs['Color'])
    links.new(input=rgbtobwNode.outputs['Val'], output=gtNode.inputs[1])
    links.new(input=gtNode.outputs['Value'], output=mixNode.inputs[FACTOR_INPUT])

    links.new(input=inNode.outputs[MC_GROUP_TEX_OUTPUT], output=diffNode.inputs["Color"])
    links.new(input=diffNode.outputs[BSDF_OUTPUT], output=mixNode.inputs[1])

    links.new(input=transpNode.outputs[BSDF_OUTPUT], output=mixNode.inputs[2])

    links.new(input=mixNode.outputs['Shader'], output=matNode.inputs['Surface'])


def createLeafCyclesMat(mat):
    """Colored stencil materials such as leaves"""
    if DEBUG_SHADER:
        print("createLeafCyclesMat")
    """Very similar to the transparent (glass) material but different enough to need its own"""
    #Ensure Cycles is in use
    if bpy.context.scene.render.engine != 'CYCLES':
        bpy.context.scene.render.engine = 'CYCLES'
    mat.use_nodes = True

    ntree = mat.node_tree   #there will now be 4 nodes in there, one of them being the diffuse shader.
    removeExistingDiffuseNode(ntree)
    nodes = ntree.nodes
    links = ntree.links
    stencilNode = ntree.nodes.new(type=TYPE_NODE_GROUP)
    setNodeGroup(stencilNode,MC_SHADER_STENCIL_COLORED)
    matNode = nodes['Material Output']
    darkColorNode = ntree.nodes.new(type="ShaderNodeRGB")
    darkColorNode.outputs[0].default_value = (0.01, 0.0185002, 0.0137021, 1)
    lightColorNode = ntree.nodes.new(type="ShaderNodeRGB")
    lightColorNode.outputs[0].default_value = (0.098, 0.238398, 0.135633, 1)

    darkColorNode.location = Vector((0, 200))
    lightColorNode.location = Vector((0, 0))
    stencilNode.location = Vector((400,0))
    matNode.location = Vector((600,0))

    links.new(input=darkColorNode.outputs['Color'], output=stencilNode.inputs[0])
    links.new(input=lightColorNode.outputs['Color'], output=stencilNode.inputs[1])
    links.new(input=stencilNode.outputs['Shader'], output=matNode.inputs['Surface'])

def createLeafCyclesMatOld(mat):
    """Very similar to the transparent (glass) material but different enough to need its own"""
    if DEBUG_SHADER:
        print("createLeafCyclesMat")
    #Ensure Cycles is in use
    if bpy.context.scene.render.engine != 'CYCLES':
        bpy.context.scene.render.engine = 'CYCLES'
    mat.use_nodes = True

    ntree = mat.node_tree   #there will now be 4 nodes in there, one of them being the diffuse shader.
    nodes = ntree.nodes
    links = ntree.links
    removeExistingDiffuseNode(ntree)
    diffNode = ntree.nodes.new(type=TYPE_NODE_GROUP)
    setNodeGroup(diffNode,MC_SHADER_TEX)
    matNode = nodes['Material Output']

    rgbtobwNode = ntree.nodes.new(type="ShaderNodeRGBToBW")
    gtNode = ntree.nodes.new(type="ShaderNodeMath")
    gtNode.name = "AlphaBlackGT"
    gtNode.operation = 'GREATER_THAN'
    gtNode.inputs[0].default_value = 0.001

    transpNode = ntree.nodes.new(type="ShaderNodeBsdfTransparent")
    mixNode = ntree.nodes.new(type="ShaderNodeMixShader")

    diffNode.location = Vector((0,0))
    rgbtobwNode.location = Vector((200,200))
    gtNode.location = Vector((400,200))
    transpNode.location = Vector((400,-200))
    mixNode.location = Vector((600,0))
    matNode.location = Vector((800,0))

    for nl in links:
        if nl.to_socket == matNode:
            links.remove(nl)

    links.new(input=diffNode.outputs[MC_GROUP_TEX_OUTPUT], output=rgbtobwNode.inputs['Color'])
    links.new(input=rgbtobwNode.outputs['Val'], output=gtNode.inputs[1])
    links.new(input=gtNode.outputs['Value'], output=mixNode.inputs[FACTOR_INPUT])

    # Leaf difference: feed the matl color into transparent... not needed? FIXME
    links.new(input=transpNode.outputs[BSDF_OUTPUT], output=mixNode.inputs[2])

    links.new(input=mixNode.outputs['Shader'], output=matNode.inputs['Surface'])

    # Leaf specific portion of material
    lcrampNode = ntree.nodes.new(type="ShaderNodeValToRGB")
    lcrampNode.color_ramp.elements[1].color = (0.098, 0.238398, 0.135633, 1)
    lcrampNode.color_ramp.elements[0].color = (0.01, 0.0185002, 0.0137021, 1)
    ldiffNode = ntree.nodes.new(type="ShaderNodeBsdfDiffuse")

    lcrampNode.location = Vector((400,500))
    ldiffNode.location = Vector((700,500))

    links.new(input=rgbtobwNode.outputs['Val'], output=lcrampNode.inputs[FACTOR_INPUT])
    links.new(input=lcrampNode.outputs['Color'], output=ldiffNode.inputs['Color'])
    links.new(input=ldiffNode.outputs[BSDF_OUTPUT], output=mixNode.inputs[1])

def createPlainAlphaCyclesMat(mat):
    """Partially transparent materials such as stained glass"""
    if DEBUG_SHADER:
        print("createPlainAlphaCyclesMat")
    #Ensure Cycles is in use
    if bpy.context.scene.render.engine != 'CYCLES':
        bpy.context.scene.render.engine = 'CYCLES'
    mat.use_nodes = True

    ntree = mat.node_tree
    nodes = ntree.nodes

    createDiffuseCyclesMat(mat)
    diffNode = nodes[MC_SHADER_DIFFUSE]
    matNode = nodes['Material Output']    

    transpNode = ntree.nodes.new(type="ShaderNodeBsdfTransparent")
    mixNode = ntree.nodes.new(type="ShaderNodeMixShader")

    diffNode.location = Vector((0,0))
    transpNode.location = Vector((200,-200))
    mixNode.location = Vector((400,0))
    matNode.location = Vector((600,0))

    links = ntree.links
    # FIXME - does reversing order of inputs give the right effect for stained glass?
    links.new(input=diffNode.outputs[BSDF_OUTPUT], output=mixNode.inputs[2])
    links.new(input=diffNode.outputs['Alpha'], output=mixNode.inputs[FACTOR_INPUT])
    links.new(input=transpNode.outputs[BSDF_OUTPUT], output=mixNode.inputs[1])
    links.new(input=mixNode.outputs['Shader'], output=matNode.inputs['Surface'])


def setupCyclesMat(material, cyclesParams):
    if DEBUG_SHADER:
        print("setupCyclesMat")
    createNodeGroups()
    if 'emit' in cyclesParams:
        emitAmt = cyclesParams['emit']
        if emitAmt > 0.0:
            createEmissionCyclesMat(material, emitAmt)
            return

    if 'stencil' in cyclesParams and cyclesParams['stencil']: #must be boolean true
        if 'ovr' in cyclesParams:
            #get the overlay colour, and create a transp overlay material.
            return
        #not overlay
        createStencilCyclesMat(material)
        return
    
    if 'alpha' in cyclesParams and cyclesParams['alpha']:
        createPlainAlphaCyclesMat(material)
        return

    if 'leaf' in cyclesParams and cyclesParams['leaf']:
        createLeafCyclesMat(material)
        return

    createDiffuseCyclesMat(material)


def getMCMat(blocktype, rgbtriple, cyclesParams=None):  #take cycles params Dictionary - ['type': DIFF/EMIT/TRANSP, 'emitAmt': 0.0]
    """Creates or returns a general-use default Minecraft material."""
    matname = 'mc' + blocktype + 'Mat'

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

def createCubeMesh():
    bpy.context.scene.cursor_location = (0.0, 0.0, 0.0)
    bpy.ops.mesh.primitive_cube_add()
    blockOb = bpy.context.object
    bpy.ops.transform.resize(value=(0.5, 0.5, 0.5))
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return blockOb


def createInsetMCBlock(mcname, colourtriple, mcfaceindices, insets=[0,0,0], cyclesParams=None):
    """With no insets (the default), creates a full-size cube.
Else uses [bottom,top,sides] to inset the cube size and UV coords.
Side insets are applied symmetrically around the cube; maximum side inset is 7.
Units are in Minecraft texels - so from 1 to 15. Inset 16 is an error."""
    blockname = mcname + 'Block'
    if blockname in bpy.data.objects:
        return bpy.data.objects[blockname]

    pxlUnit = getUVUnit()
    bpy.ops.object.mode_set(mode='OBJECT')  #just to be sure... needed?
    blockOb = createCubeMesh()
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

    blockOb = createCubeMesh()
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
    uvUnit = getUVUnit()
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
        mcTexU = getTextureAtlasU(faceTexId)
        mcTexV = getTextureAtlasV(faceTexId)
        #multiply by square size to get U1,V1 (topleft):
        u1 = (mcTexU * TEXTURE_ATLAS_PIXELS_PER_UNIT) / TEXTURE_ATLAS_PIXELS    # or >> 4 (div by imagesize to get as fraction)
        v1 = (mcTexV * TEXTURE_ATLAS_PIXELS_PER_UNIT) / TEXTURE_ATLAS_PIXELS    # ..
        v1 = 1.0 - v1 #y goes low to high   #DEBUG print("That means u1,v1 is %f,%f" % (u1,v1))

        #DEBUG
        if DEBUG_BBUV:
            print("createBMeshXBlockUVs %s u1,v1 %f,%f" % (blockname,u1,v1))
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
