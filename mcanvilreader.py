import os, bpy

from struct import unpack   #, error as StructError
from . import nbtreader, mcregionreader
from .mineregion import OPTIONS, EXCLUDED_BLOCKS, BLOCKDATA, REPORTING, unknownBlockIDs, WORLD_ROOT
##..yuck: they're immutable and don't return properly except for the dict-type ones. Get rid of this in next cleanup.

from math import floor

class AnvilChunkReader(mcregionreader.ChunkReader):

    #readBlock( bX, bZ (by?) ...  ignoring 'region' boundaries and chunk boundaries? We need an ignore-chunk-boundaries level of abstraction

    def getSingleBlock(chunkXZ, blockXYZ):   #returns the value and extradata bits for a single block of given absolute x,y,z block coords within chunk cx,cz. or None if area not generated.
        #y is value from 0..255
        cx, cy = chunkXZ
        bX,bY,bZ = blockXYZ
        rX = floor(cx / 32) # is this the same as >> 8 ??
        rZ = floor(cz / 32)
        rHdrOffset = ((cx % 32) + (cz % 32) * 32) * 4
        rFile = "r.%d.%d.mca" % (rx, rz)
        if not os.path.exists(rFile):
            return None
        with open(rFile, 'rb') as regionfile:
            regionfile.seek(rheaderoffset)
            cheadr = regionfile.read(4)
            dataoffset = unpack(">i", b'\x00'+cheadr[0:3])[0]
            chunksectorcount = cheadr[3]
            if dataoffset == 0 and chunksectorcount == 0:
                return None #Region exists, but the chunk we're after was never created within it.
            else:
                #possibly check for cached chunk data here, under the cx,cz in a list of already-loaded sets.
                chunkdata = AnvilChunkReader._readChunkData(regionfile, dataoffset, chunksectorcount)
                chunkLvl = chunkdata.value['Level'].value
                sections = chunkLvl['Sections'].value
                #each section is a 16x16x16 piece of chunk, with a Y-byte from 0-15, so that the 'y' value is 16*that + in-section-Y-value
                #some sections can be skipped, so we must iterate to find the right one with the 'Y' we expect.
                bSection = bY / 16
                sect = None
                for section in sections:
                    secY = section.value['Y'].value
                    if secY == bSection:
                        sect = section.value
                if sect is None:
                    return None
                blockData = sec['Blocks'].value    #a TAG_Byte_Array value (bytes object). Blocks is 16x16 bytes
                extraData = sec['Data'].value      #BlockLight, Data and SkyLight are 16x16 "4-bit cell" additional data arrays.
                sY = dY % 16
                blockIndex = (sY * 16 + dZ) * 16 + dX
                blockID = blockData[ blockIndex ]
                return blockID    #, extravalue)
                #NB: this can be made massively more efficient by storing 4 'neighbour chunk' data reads for every chunk properly processed.
                #Don't need to do diagonals, even.



    

    def readChunk(self, chunkPosX, chunkPosZ, vertexBuffer):  # aka "readChunkFromRegion" ...
        """Loads chunk located at the X,Z chunk location provided."""

        global REPORTING

        #region containing a given chunk is found thusly: floor of c over 32
        regionX = floor(chunkPosX / 32)
        regionZ = floor(chunkPosZ / 32)

        rheaderoffset = ((chunkPosX % 32) + (chunkPosZ % 32) * 32) * 4

        #print("Reading chunk %d,%d from region %d,%d" %(chunkPosX, chunkPosZ, regionX,regionZ))

        rfileName = "r.%d.%d.mca" % (regionX, regionZ)
        if not os.path.exists(rfileName):
            #Can't load: it doesn't exist!
            print("No such region generated.")
            return

        with open(rfileName, 'rb') as regfile:
            # header for the chunk we want is at...
            #The location in the region file of a chunk at (x, z) (in chunk coordinates) can be found at byte offset 4 * ((x mod 32) + (z mod 32) * 32) in its McRegion file.
            #Its timestamp can be found 4096 bytes later in the file
            regfile.seek(rheaderoffset)
            cheadr = regfile.read(4)
            dataoffset = unpack(">i", b'\x00'+cheadr[0:3])[0]
            chunksectorcount = cheadr[3]
            
            if dataoffset == 0 and chunksectorcount == 0:
                pass
                #print("Region exists, but chunk has never been created within it.")
            else:
                chunkdata = AnvilChunkReader._readChunkData(regfile, dataoffset, chunksectorcount)  #todo: rename that function!
                #Geometry creation! etc... If surface only, can get heights etc from lightarray?

                #top level tag in NBT is an unnamed TAG_Compound, for some reason, containing a named TAG_Compound "Level"
                chunkLvl = chunkdata.value['Level'].value
                #chunkXPos = chunkLvl['xPos'].value
                #chunkZPos = chunkLvl['zPos'].value
                #print("Reading blocks for chunk: (%d, %d)\n" % (chunkXPos, chunkZPos))
                AnvilChunkReader._readBlocks(chunkLvl, vertexBuffer)
                #print("Loaded chunk %d,%d" % (chunkPosX,chunkPosZ))

                REPORTING['totalchunks'] += 1


    def _readChunkData(bstream, chunkOffset, chunkSectorCount): #rename this!
        #get the datastring out of the file...
        import io, zlib

        #cf = open(fname, 'rb')
        initialPos = bstream.tell()

        cstart = chunkOffset * 4096    #4 kiB
        clen = chunkSectorCount * 4096
        bstream.seek(cstart)    #this bstream is the region file

        chunkHeaderAndData = bstream.read(clen)

        #chunk header stuff is:
        # 4 bytes: length (of remaining data)
        # 1 byte : compression type (1 - gzip - unused; 2 - zlib: it should always be this in actual fact)
        # then the rest, is length-1 bytes of compressed (zlib) NBT data.

        chunkDLength = unpack(">i", chunkHeaderAndData[0:4])[0]
        chunkDCompression = chunkHeaderAndData[4]
        if chunkDCompression != 2:
            print("Not a zlib-compressed chunk!?")
            raise StringError()    #MinecraftSomethingError, perhaps.

        chunkZippedBytes = chunkHeaderAndData[5:]

        #could/should check that chunkZippedBytes is same length as chunkDLength-1.

        #put the regionfile byte stream back to where it started:
        bstream.seek(initialPos)

        #Read the compressed chunk data
        zipper = zlib.decompressobj()
        chunkData = zipper.decompress(chunkZippedBytes)
        chunkDataAsFile = io.BytesIO(chunkData)
        chunkNBT = nbtreader.readNBT(chunkDataAsFile)

        return chunkNBT

    def getSectionBlock(blockLoc, sectionDict):
        """Fetches a block from section NBT data."""
        (bX,bY,bZ) = blockLoc
        secY = bY >> 4  #/ 16
        if secY not in sectionDict:
            return None
        sect = sectionDict[secY]
        sY = bY & 0xf   #mod 16
        bIndex = (sY * 16 + bZ) * 16 + bX
        #bitshift, or run risk of int casts
        dat = sect['Blocks'].value
        return dat[bIndex]

    #Hollow volumes optimisation (version1: in-chunk only)
    def _isExposedBlock(blockCoord, chunkXZ, secBlockData, sectionDict, blockID, skyHighLimit, depthLimit):    #another param: neighbourChunkData[] - a 4-list of NBT stuff...
        (dX,dY,dZ) = blockCoord
        #fail-fast. checks if all ortho adjacent neighbours fall inside this chunk.
        #EASY! Because it's 0-15 for both X and Z. For Y, we're iterating upward,
        #so get the previous value (the block below) passed in.

        if blockID == 18:   #leaves   #and glass? and other exemptions?
            return True
        
        if dX == 0 or dX == 15 or dY == 0 or dZ == 0 or dZ == 15:
            #get neighbour directly
            return True	#instead, check neigbouring chunks...
        

        #we can no longer get the block below or above easily as we might be iterating +x, -16x, or +z at any given step.
        if dY == skyHighLimit or dY == depthLimit:
            return True

        ySect = dY / 16     ## all this dividing integers by 16! I ask you! (>> 4)!
        yBoff = dY % 16     ## &= 0x0f
        #if you are on a section boundary, need next section for block above. else

        #GLOBALS (see readBlocks, below)
        CHUNKSIZE_X = 16    #static consts - global?
        CHUNKSIZE_Z = 16
        #new layout goes YZX. improves compression, apparently.
        ##_Y_SHIFT = 7    # 2**7 is 128. use for fast multiply
        ##_YZ_SHIFT = 11    #16 * 128 is 2048, which is 2**11

        #check above (Y+1)
        #either it's in the same section (quick/easy lookup) or it's in another section (still quite easy - next array over)
        #or, it's in another chunk. in which case, check chunkreadcache for the 4 adjacent. Failing this, it's the worse case and
        #we need to read into a whole new chunk data grab.
        if yBoff == 15:
            upBlock = AnvilChunkReader.getSectionBlock((dX,dY+1,dZ), sectionDict)
            if upBlock != blockID:
                return True
        else:
            #get it from current section
            upIndex = ((yBoff+1) * 16 + dZ) * 16 + dX
            upBlock = secBlockData[ upIndex ]
            if upBlock != blockID:
                return True

        #Check below (Y-1):
        if yBoff == 0:
            downBlock = AnvilChunkReader.getSectionBlock((dX,dY-1,dZ), sectionDict)
            if downBlock != blockID:
                return True
        else:
            downIndex = ((yBoff-1) * 16 + dZ) * 16 + dX
            dnBlock = secBlockData[downIndex]
            if dnBlock != blockID:
                return True
        
        #Have checked above and below; now check all sides. Same section, but maybe different chunks...
        #Check X-1 (leftward)
        leftIndex = (yBoff * 16 + dZ) * 16 + (dX-1)
        #ngbIndex = dY + (dZ << _Y_SHIFT) + ((dX-1) << _YZ_SHIFT)    #Check this lookup in readBlocks, below! Can it go o.o.b.?
        try:
            neighbour = secBlockData[leftIndex]
        except IndexError:
            print("Bogus index cockup: %d. Blockdata len is 16x16x16 bytes (4096)." % leftIndex)
            quit()
        if neighbour != blockID:
            return True

        #Check X+1
        rightIndex = (yBoff * 16 + dZ) * 16 + (dX+1)
        #ngbIndex = dY + (dZ << _Y_SHIFT) + ((dX+1) << _YZ_SHIFT)    #Check this lookup in readBlocks, below! Can it go o.o.b.?
        neighbour = secBlockData[rightIndex]
        if neighbour != blockID:
            return True

        #Check Z-1
        ngbIndex = (yBoff * 16 + (dZ-1)) * 16 + dX
        #ngbIndex = dY + ((dZ-1) << _Y_SHIFT) + (dX << _YZ_SHIFT)    #Check this lookup in readBlocks, below! Can it go o.o.b.?
        neighbour = secBlockData[ngbIndex]
        if neighbour != blockID:
            return True

        #Check Z+1
        ngbIndex = (yBoff * 16 + (dZ+1)) * 16 + dX
        #ngbIndex = dY + ((dZ+1) << _Y_SHIFT) + (dX << _YZ_SHIFT)    #Check this lookup in readBlocks, below! Can it go o.o.b.?
        neighbour = secBlockData[ngbIndex]
        if neighbour != blockID:
            return True

        return False


    #nb: 0 is bottom bedrock, 256 (255?) is top of sky. Sea is 64.
    def _readBlocks(chunkLevelData, vertexBuffer):
        """readBlocks(chunkLevelData) -> takes a named TAG_Compound 'Level' containing a chunk's Anvil Y-Sections, each of which 0-15 has blocks, data, heightmap, xpos,zpos, etc.
    Adds the data points into a 'vertexBuffer' which is a per-named-type dictionary of ????'s. That later is made into Blender geometry via from_pydata."""
        #TODO: also TileEntities and Entities. Entities will generally be an empty list.
        #TileEntities are needed for some things to define fully...

        #TODO: Keep an 'adjacent chunk cache' for neighbourhood is-exposed checks.
        
        global unknownBlockIDs, OPTIONS, REPORTING

        #chunkLocation = 'xPos' 'zPos' ...
        chunkX = chunkLevelData['xPos'].value
        chunkZ = chunkLevelData['zPos'].value
        biomes = chunkLevelData['Biomes'].value    #yields a TAG_Byte_Array value (bytes object) of len 256 (16x16)
        #heightmap = chunkLevelData['HeightMap'].value
        #'TileEntities' -- surely need this for piston data and stuff, no?
        
        entities = chunkLevelData['Entities'].value    # load ze sheeps!! # a list of tag-compounds.
        AnvilChunkReader._loadEntities(entities)

        skyHighLimit = OPTIONS['highlimit']
        depthLimit   = OPTIONS['lowlimit']

        CHUNKSIZE_X = 16
        CHUNKSIZE_Z = 16
        SECTNSIZE_Y = 16

        ##_Y_SHIFT = 7    # 2**7 is 128. use for fast multiply
        ##_YZ_SHIFT = 11    #16 * 128 is 2048, which is 2**11
        sections = chunkLevelData['Sections'].value
        
        #each section is a 16x16x16 piece of chunk, with a Y-byte from 0-15, so that the 'y' value is 16*that + in-section-Y-value
        
        #iterate through all block Y values from bedrock to max height (minor step through X,Z.)
        #bearing in mind some can be skipped out.
        
        #sectionDict => a dictionary of sections, indexed by Y.
        sDict = {}
        for section in sections:
            sY = section.value['Y'].value
            sDict[sY] = section.value
        
        for section in sections:
            sec = section.value
            secY = sec['Y'].value * SECTNSIZE_Y
            
            #if (secY + 16) < lowlimit, skip this section. no need to load it.
            if (secY+16 < depthLimit):
                continue
            
            if (secY > skyHighLimit):
                return
            
            #Now actually proceed with adding in the section's block data.
            blockData = sec['Blocks'].value    #yields a TAG_Byte_Array value (bytes object). Blocks is 16x16 bytes
            extraData = sec['Data'].value      #BlockLight, Data and SkyLight are 16x16 "4-bit cell" additional data arrays.

            #get starting Y from heightmap, ignoring excess height iterations...
            #heightByte = heightMap[dX + (dZ << 4)]    # z * 16
            #heightByte = 255    #quickFix: start from tip top, for now
            #if heightByte > skyHighLimit:
            #    heightByte = skyHighLimit

            #go y 0 to 16...
            for sy in range(16):
                dY = secY + sy
                
                if dY < depthLimit:
                    continue
                if dY > skyHighLimit:
                    return

                # dataX will be dX, blender X will be bX.
                for dZ in range(CHUNKSIZE_Z):
                    #print("looping chunk z %d" % dZ)
                    for dX in range(CHUNKSIZE_X):
                        #oneBlockLeft = 0   #data value of the block 1 back to the left (-X) from where we are now. (for neighbour comparisons)
                        #ie microcached 'last item read'. needs tweaked for chunk crossover...

                        ##blockIndex = (dZ << _Y_SHIFT) + (dX << _YZ_SHIFT)  # max number of bytes in a chunk is 32768. this is coming in at 32839 for XYZ: (15,71,8)
                        ##blockIndex = (dZ * 16) + dX
                        #YZX ((y * 16 + z) * 16 + x
                        blockIndex = (sy * 16 + dZ) * 16 + dX
                        blockID = blockData[ blockIndex ]

                        #except IndexError:
                        #    print("X:%d Y:%d Z %d, blockID from before: %d, cx,cz: %d,%d. Blockindex: %d" % (dX,dY,dZ,blockID,chunkX,chunkZ, blockIndex))
                        #    raise IndexError

                        #create this block in the output!
                        if blockID != 0 and blockID not in EXCLUDED_BLOCKS:    # 0 is air
                            REPORTING['blocksread'] += 1

                            #hollowness test:
                            if blockID in BLOCKDATA:
                                if AnvilChunkReader._isExposedBlock((dX,dY,dZ), (chunkX, chunkZ), blockData, sDict, blockID, skyHighLimit, depthLimit):
                                #TODO: Make better version of this check, counting across chunks and regions.
                                    #Load extra data (if applicable to blockID):
                                    #if it has extra data, grab 4 bits from extraData
                                    datOffset = (int(blockIndex /2))    #divided by 2
                                    datHiBits = blockIndex % 2 #odd or even, will be hi or low nibble
                                    extraDatByte = extraData[datOffset] # should be a byte of which we only want part.
                                    hiMask = 0b11110000
                                    loMask = 0b00001111
                                    extraValue = None
                                    if datHiBits:
                                        #get high 4, and shift right 4.
                                        extraValue = loMask & (extraDatByte >> 4)
                                    else:
                                        #mask hi 4 off.
                                        extraValue = extraDatByte & loMask
                                    #create block in corresponding blockmesh
                                    AnvilChunkReader.createBlock(blockID, (chunkX, chunkZ), (dX,dY,dZ), extraValue, vertexBuffer)
                                else:
                                    REPORTING['blocksdropped'] += 1
                            else:
                                #print("Unrecognised Block ID: %d" % blockID)
                                #createUnknownMeshBlock()
                                unknownBlockIDs.add(blockID)

        #TAG_Byte("Y"): 0
        #TAG_Byte_Array("Blocks"): [4096 bytes array]
        #TAG_Byte_Array("BlockLight"): [2048 bytes array]
        #TAG_Byte_Array("Data"): [2048 bytes array]
        #TAG_Byte_Array("SkyLight"): [2048 bytes array]
        ##TAG_Byte_Array("Add"): [2048 bytes array]     ##Only appears if it's needed!

    def _loadEntities(entities):
        global WORLD_ROOT
        for e in entities:
            eData = e.value
            
            etypename = eData['id'].value   #eg 'Sheep'
            ename = "en%sMarker" % etypename
            epos = [p.value for p in eData['Pos'].value]   #list[3] of double
            erot = [r.value for r in eData['Rotation'].value]  #list[2] of float ([0] orientation (angle round Z-axis) and [1] 0.00, probably y-tilt.

            #instantiate and rotate-in a placeholder object for this (and add to controlgroup or parent to something handy.)
            #translate to blend coords, too.
            entMarker = bpy.data.objects.new(ename, None)
            #set its coordinates...
            #convert Minecraft coordinate position of player into Blender coords:
            entMarker.location[0] = -epos[2]
            entMarker.location[1] = -epos[0]
            entMarker.location[2] = epos[1]
            
            #also, set its z-rotation to erot[0]...
            #entMarker.rotation[2] = erot[0]
            
            bpy.context.scene.objects.link(entMarker)
            entMarker.parent = WORLD_ROOT
            
        
        
##NB! Future blocks will require the Add tag to be checked and mixed in!
#Each section also has a "Add" tag, which is a DataLayer byte array just like 
#"Data". The "Add" tag is not included in the converter since the old format 
#never had block ids above 255. This extra tag is created whenever a block 
#requires it, so the getTile() method needs to check if the array exists and 
#then combine it with the default block data. In other words, 
#blockId = (add << 8) + baseId.

        # Blocks, Data, Skylight, ... heightmap
        #Blocks contain the block ids; Data contains the extra info: 4 bits of lighting info + 4 bits of 'extra fields'
        # eg Lamp direction, crop wetness, etc.
        # Heightmap gives us quick access to the top surface of everything - ie optimise out iterating through all sky blocks.
        
        #To access a specific block from either the block or data array from XYZ coordinates, use the following formula:
        # Index = x + (y * Height + z) * Width 

        ##Note that the old format is XZY ((x * 16 + z) * 16 + y) and the new format is YZX ((y * 16 + z) * 16 + x)

        #16x16 (256) ints of heightmap data. Each int records the lowest level
        #in each column where the light from the sky is at full strength. Speeds up
        #computing of the SkyLight. Note: This array's indexes are ordered Z,X 
        #whereas the other array indexes are ordered X,Z,Y.

        #loadedData -> we buffer everything into lists, then batch-create the
        #vertices later. This makes the model build in Blender many, many times faster

        #list of named, distinct material meshes. add vertices to each, only in batches.
        #Optimisation: 'Hollow volumes': only add if there is at least 1 orthogonal non-same-type neighbour.
        #Aggressive optimisation: only load if there is 1 air orthogonal neighbour (or transparent materials).


            


#    def mcToBlendCoord(chunkPos, blockPos):
#        """Converts a minecraft chunk X,Z pair and a minecraft ordered X,Y,Z block location triple into a Blender coordinate vector Vx,Vy,Vz.
#    And remember: in Minecraft, Y points to the sky."""
        
        # Mapping Minecraft coords -> Blender coords
        # In Minecraft, +Z (west) <--- 0 ----> -Z (east), while North is -X and South is +X
        # In Blender, north is +Y, south is-Y, west is -X and east is +X.
        # So negate Z and map it as X, and negate X and map it as Y. It's slightly odd!

#        vx = -(chunkPos[1] << 4) - blockPos[2]
#        vy = -(chunkPos[0] << 4) - blockPos[0]   # -x of chunkpos and -x of blockPos (x,y,z)
#        vz = blockPos[1]    #Minecraft's Y.
        
#        return Vector((vx,vy,vz))


#    def createBlock(blockID, chunkPos, blockPos, extraBlockData, vertBuffer):
#        """adds a vertex to the blockmesh for blockID in the relevant location."""

        #chunkpos is X,Z; blockpos is x,y,z for block.
#        mesh = getMCBlockType(blockID, extraBlockData)  #this could be inefficient. Perhaps create all the types at the start, then STOP MAKING THIS CHECK!
#        if mesh is None:
#            return

#        typeName = mesh.name
#        vertex = mcToBlendCoord(chunkPos, blockPos)

#        if typeName in vertBuffer:
#            vertBuffer[typeName].append(vertex)
#        else:
#            vertBuffer[typeName] = [vertex]
#
#        #xyz is local to the 'stone' mesh for example. but that's from 0 (world).
#        #regionfile can be found from chunkPos.
#        #Chunkpos is an X,Z pair.
#        #Blockpos is an X,Y,Z triple - within chunk.
