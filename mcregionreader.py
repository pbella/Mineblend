import os

from struct import unpack   #, error as StructError
from . import nbtreader
from .mineregion import OPTIONS, EXCLUDED_BLOCKS, BLOCKDATA, REPORTING, unknownBlockIDs, getMCBlockType, mcToBlendCoord #yuck!
##..yuck: they're immutable and don't return properly except for the dict-type ones. Get rid of this in next cleanup.

class ChunkReader:

    #readBlock( cX,cZ,(sY?), (bX,bY,bZ) ... )  ignoring 'region' boundaries and chunk boundaries? We need an ignore-chunk-boundaries level of abstraction

    def readChunk(self, chunkPosX, chunkPosZ, vertexBuffer):  # aka "readChunkFromRegion" ...
        """Loads chunk located at the X,Z chunk location provided."""
        from math import floor
        global REPORTING

        #region containing a given chunk is found thusly: floor of c over 32
        regionX = floor(chunkPosX / 32)
        regionZ = floor(chunkPosZ / 32)

        rheaderoffset = ((chunkPosX % 32) + (chunkPosZ % 32) * 32) * 4

        #print("Reading chunk %d,%d from region %d,%d" %(chunkPosX, chunkPosZ, regionX,regionZ))

        rfileName = "r.%d.%d.mcr" % (regionX, regionZ)
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
                chunkdata = self._readChunkData(regfile, dataoffset, chunksectorcount)  #todo: rename that function!
                #Geometry creation! etc... If surface only, can get heights etc from lightarray?

                #top level tag in NBT is an unnamed TAG_Compound, for some reason, containing a named TAG_Compound "Level"
                chunkLvl = chunkdata.value['Level'].value
                #chunkXPos = chunkLvl['xPos'].value
                #chunkZPos = chunkLvl['zPos'].value
                #print("Reading blocks for chunk: (%d, %d)\n" % (chunkXPos, chunkZPos))
                ChunkReader.readBlocks(chunkLvl, vertexBuffer)
                #print("Loaded chunk %d,%d" % (chunkPosX,chunkPosZ))

                REPORTING['totalchunks'] += 1


    def _readChunkData(self, bstream, chunkOffset, chunkSectorCount): #rename this!
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


    #Hollow volumes optimisation (version1: in-chunk only)
    def _isExposedBlock(dX,dY,dZ, blockData, blockID, idAbove, skyHighLimit, depthLimit):
        #fail-fast. checks if all ortho adjacent neighbours fall inside this chunk.
        #EASY! Because it's 0-15 for both X and Z. For Y, we're iterating downward,
        #so get the previous value (the block above) passed in.

        if dX == 0 or dX == 15 or dY == 0 or dZ == 0 or dZ == 15 or blockID == 18:  #leaves
            return True
        
        if idAbove != blockID:
            return True
        
        if dY == skyHighLimit or dY == depthLimit:
            return True
        
        #GLOBALS (see readBlocks, below)
        CHUNKSIZE_X = 16    #static consts - global?
        CHUNKSIZE_Y = 128
        CHUNKSIZE_Z = 16
        _Y_SHIFT = 7    # 2**7 is 128. use for fast multiply
        _YZ_SHIFT = 11    #16 * 128 is 2048, which is 2**11
        
        #Check below:
        ngbIndex = dY-1 + (dZ << _Y_SHIFT) + (dX << _YZ_SHIFT)    #Check this lookup in readBlocks, below! Can it go o.o.b.?
        neighbour = blockData[ngbIndex]
        if neighbour != blockID:
            return True
        
        #Now checked above and below. Check all sides.
        #Check -X
        ngbIndex = dY + (dZ << _Y_SHIFT) + ((dX-1) << _YZ_SHIFT)    #Check this lookup in readBlocks, below! Can it go o.o.b.?
        neighbour = blockData[ngbIndex]
        if neighbour != blockID:
            return True
        
        #Check +X
        ngbIndex = dY + (dZ << _Y_SHIFT) + ((dX+1) << _YZ_SHIFT)    #Check this lookup in readBlocks, below! Can it go o.o.b.?
        neighbour = blockData[ngbIndex]
        if neighbour != blockID:
            return True

        #Check -Z
        ngbIndex = dY + ((dZ-1) << _Y_SHIFT) + (dX << _YZ_SHIFT)    #Check this lookup in readBlocks, below! Can it go o.o.b.?
        neighbour = blockData[ngbIndex]
        if neighbour != blockID:
            return True

        #Check +Z
        ngbIndex = dY + ((dZ+1) << _Y_SHIFT) + (dX << _YZ_SHIFT)    #Check this lookup in readBlocks, below! Can it go o.o.b.?
        neighbour = blockData[ngbIndex]
        if neighbour != blockID:
            return True

        return False


    #nb: 0 is bottom bedrock, 128 is top of sky. Sea is 64.
    def readBlocks(chunkLevelData, vertexBuffer):
        """readBlocks(chunkLevelData) -> takes a named TAG_Compound 'Level' containing a chunk's blocks, data, heightmap, xpos,zpos, etc.
    Adds the data points into a 'vertexBuffer' which is a per-named-type dictionary of ????'s. That later is made into Blender geometry via from_pydata."""
        #TODO: also TileEntities and Entities. Entities will generally be an empty list.
        #TileEntities are needed for some things to define fully...

        global unknownBlockIDs
        global OPTIONS, REPORTING
        #skyHighLimit=128
        #depthLimit=0
        skyHighLimit = OPTIONS['highlimit']
        if skyHighLimit > 127:
            skyHighLimit = 127
        depthLimit   = OPTIONS['lowlimit']

        #chunkLocation = 'xPos' 'zPos' ...
        chunkX = chunkLevelData['xPos'].value
        chunkZ = chunkLevelData['zPos'].value

        CHUNKSIZE_X = 16    #static consts - global?
        CHUNKSIZE_Y = 128
        CHUNKSIZE_Z = 16

        _Y_SHIFT = 7    # 2**7 is 128. use for fast multiply
        _YZ_SHIFT = 11    #16 * 128 is 2048, which is 2**11

        # Blocks, Data, Skylight, ... heightmap
        #Blocks contain the block ids; Data contains the extra info: 4 bits of lighting info + 4 bits of 'extra fields'
        # eg Lamp direction, crop wetness, etc.
        # Heightmap gives us quick access to the top surface of everything - ie optimise out iterating through all sky blocks.
        
        #To access a specific block from either the block or data array from XYZ coordinates, use the following formula:
        # Index = x + (y * Height + z) * Width 

        #naive starting point: LOAD ALL THE BLOCKS! :D

        blockData = chunkLevelData['Blocks'].value    #yields a TAG_Byte_Array value (bytes object)
        heightMap = chunkLevelData['HeightMap'].value
        extraData = chunkLevelData['Data'].value
        
        #256 bytes of heightmap data. 16 x 16. Each byte records the lowest level
        #in each column where the light from the sky is at full strength. Speeds up
        #computing of the SkyLight. Note: This array's indexes are ordered Z,X 
        #whereas the other array indexes are ordered X,Z,Y.

        #loadedData -> we buffer everything into lists, then batch-create the
        #vertices later. This makes the model build in Blender many, many times faster

        #list of named, distinct material meshes. add vertices to each, only in batches.
        #Optimisation: 'Hollow volumes': only add if there is at least 1 orthogonal non-same-type neighbour.
        #Aggressive optimisation: only load if there is 1 air orthogonal neighbour (or transparent materials).

        # dataX will be dX, blender X will be bX.
        for dX in range(CHUNKSIZE_X):
            #print("looping chunk x %d" % dX)
            for dZ in range(CHUNKSIZE_Z):   #-1, -1, -1):
                #get starting Y from heightmap, ignoring excess height iterations.
                #heightByte = heightMap[dX + (dZ << 4)]    # z * 16
                heightByte = 127    #Fix: always start from very top... for now
                #This makes nether load properly, plus missed objects in overworld
                #omitted due to lighting calculations being wrong.
                if heightByte > skyHighLimit:
                    heightByte = skyHighLimit
                #gives the LOWEST LEVEL where light is max. Start at this value, and y-- until we hit bedrock at y == 0.
                dY = heightByte
                oneBlockAbove = 0   #data value of the block 1 up from where we are now. (for neighbour comparisons)
                #for dY in range(CHUNKSIZE_Y): # naive method (iterate all)
                while dY >= depthLimit:

                    blockIndex = dY + (dZ << _Y_SHIFT) + (dX << _YZ_SHIFT)  # max number of bytes in a chunk is 32768. this is coming in at 32839 for XYZ: (15,71,8)
                    blockID = blockData[ blockIndex ]

                    #except IndexError:
                    #    print("X:%d Y:%d Z %d, blockID from before: %d, cx,cz: %d,%d. Blockindex: %d" % (dX,dY,dZ,blockID,chunkX,chunkZ, blockIndex))
                    #    raise IndexError
                    
                    #create this block in the output!
                    if blockID != 0 and blockID not in EXCLUDED_BLOCKS:	# 0 is air
                        REPORTING['blocksread'] += 1

                        #hollowness test:
                        
                        if blockID in BLOCKDATA:

                            if ChunkReader._isExposedBlock(dX,dY,dZ, blockData, blockID, oneBlockAbove, skyHighLimit, depthLimit):
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
                                ChunkReader.createBlock(blockID, (chunkX, chunkZ), (dX,dY,dZ), extraValue, vertexBuffer)
                            else:
                                REPORTING['blocksdropped'] += 1
                        else:
                            #print("Unrecognised Block ID: %d" % blockID)
                            #createUnknownMeshBlock()
                            unknownBlockIDs.add(blockID)
                    dY -= 1
                    oneBlockAbove = blockID   # set 'last read block' to current value


    def createBlock(blockID, chunkPos, blockPos, extraBlockData, vertBuffer):
        """adds a vertex to the blockmesh for blockID in the relevant location."""

        #chunkpos is X,Z; blockpos is x,y,z for block.
        mesh = getMCBlockType(blockID, extraBlockData)  #this could be inefficient. Perhaps create all the types at the start, then STOP MAKING THIS CHECK!
        if mesh is None:
            return

        typeName = mesh.name
        vertex = mcToBlendCoord(chunkPos, blockPos)

        if typeName in vertBuffer:
            vertBuffer[typeName].append(vertex)
        else:
            vertBuffer[typeName] = [vertex]

        #xyz is local to the 'stone' mesh for example. but that's from 0 (world).
        #regionfile can be found from chunkPos.
        #Chunkpos is an X,Z pair.
        #Blockpos is an X,Y,Z triple - within chunk.

