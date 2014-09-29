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
#
#
#
# Acro's Python3.2 NBT Reader for Blender Importing Minecraft

#TODO Possible Key Options for the importer:

#TODO: load custom save locations, rather than default saves folder.
#good for backup/server game reading.
# what's a good way to swap out the world-choice dialogue for a custom path input??

#"Surface only": use the heightmap and only load surface.
#Load more than just the top level, obviously, cos of cliff 
#walls, caves, etc. water should count as transparent for this process, 
#as should glass, flowers, torches, portal; all nonsolid block types.

#"Load horizon" / "load radius": should be circular, or have options

import bpy
from bpy.props import FloatVectorProperty
from mathutils import Vector
import numpy as npy
from . import blockbuild
from . import sysutil
#using blockbuild.createMCBlock(mcname, diffuseColour, mcfaceindices)
#faceindices order: (bottom, top, right, front, left, back)
#NB: this should probably change, as it was started by some uv errors.

from . import nbtreader
#level.dat, .mcr McRegion, .mca Anvil: all different formats, but all are NBT.

import sys, os, gzip
import datetime
#from struct import calcsize, unpack, error as StructError

#tag classes: switch/override the read functions once they know what they are
#and interpret payload by making more taggy bits as needed inside self.
#maybe add mcpath as a context var so it can be accessed from operators.

REPORTING = {}
REPORTING['totalchunks'] = 0
totalchunks = 0
wseed = None	#store chosen world's worldseed, handy for slimechunk calcs.

MCREGION_VERSION_ID = 0x4abc;	# Check world's level.dat 'version' property for these.
ANVIL_VERSION_ID = 0x4abd;		# 
    
#TODO: Retrieve these from bpy.props properties stuck in the scene RNA.
EXCLUDED_BLOCKS = [1, 3, 87]    #(1,3,87) # hack to reduce loading / slowdown: (1- Stone, 3- Dirt, 87 netherrack). Other usual suspects are Grass,Water, Leaves, Sand,StaticLava

LOAD_AROUND_3D_CURSOR = False  #calculates 3D cursor as a Minecraft world position, and loads around that instead of player (or SMP world spawn) position

unknownBlockIDs = set()

OPTIONS = {}

#"Profile" execution checks for measuring whether optimisations are worth it:

REPORTING['blocksread'] = 0
REPORTING['blocksdropped'] = 0
t0 = datetime.datetime.now()
tReadAndBuffered = -1
tToMesh = -1
tChunk0 = -1	#these don't need to be globals - just store the difference in the arrays.
tChunkEnd = -1
tRegion0 = -1
tRegionEnd = -1
tChunkReadTimes = []
tRegionReadTimes = []

WORLD_ROOT = None

#MCBINPATH -- in /bin, zipfile open minecraft.jar, and get terrain.png.
#Feed directly into Blender, or save into the Blender temp dir, then import.
print("Mineblend saved games location: "+sysutil.getMCPath())

#Blockdata: [name, diffuse RGB triple, texture ID list, extra data? (XD/none),
# custom model shape (or None), shape params (or None if not custom mesh),
# and finally dictionary of Cycles params (see blockbuild.)
# TexID list is [bot, top, right, front, left back] or sometimes other orders/lengths if custom model
# Texture IDs are the 1d (2d) count of location of their 16x16 square within terrain.png in minecraft.jar

#Don't store a name for air. Ignore air.
# Order for Blender cube face creation is: [bottom, top, right, front, left, back]

BLOCKDATA =  {0: ['Air'],
            1: ['Stone', (116,116,116), [308]*6],
            2: ['Grass', (95,159,53), [200,148,332,332,332,332]],
            3: ['Dirt', (150, 108, 74), [200]*6],
            4: ['Cobblestone', (94,94,94), [163]*6],
            5: ['WoodenPlank', (159,132,77), [176]*6],
            6: ['Sapling', (0,100,0), [20]*6, 'XD', 'cross'],
            7: ['Bedrock', [51,51,51], [100]*6],
            8: ['WaterFlo', (31,85,255), [2]*6, None, None, None, {'alpha': True}],
            9: ['Water', (62,190,255), [2]*6, None, None, None, {'alpha': True}],
            10: ['LavaFlo', (252,0,0), [0]*6, None, None, None, {'emit': 1.10, 'stencil': False}],
            11: ['Lava',    (230,0,0), [0]*6, None, None, None, {'emit': 1.10, 'stencil': False}],
            12: ['Sand', (214,208,152), [243]*6],
            13: ['Gravel', (154,135,135), [352]*6],
            14: ['GoldOre', (252,238,75), [331]*6],
            15: ['IronOre', (216,175,147), [395]*6],
            16: ['CoalOre', (69,69,69), [161]*6],
            17: ['Wood', (76,61,38), [452,452,451,451,451,451], 'XD'],
            18: ['Leaves', (99,128,15), [425]*6, None, None, None, {'stencil': False, 'leaf': True}],    #TODO: XD colour+texture.
            19: ['Sponge', (206,206,70), [244]*6], # FIXME - wet sponge
            20: ['Glass', (254,254,254), [263]*6, None, None, None, {'stencil': True}],
            21: ['LapisLazuliOre', (28,87,198), [418]*6],
            22: ['LapisLazuliBlock', (25,90,205), [417]*6],
            23: ['Dispenser', (42,42,42), [262,262,261,41,261,261]], # TODO - front?
            24: ['Sandstone', (215,209,153), [307,307,339,339,339,339], 'XD'], #!!
            25: ['NoteBlock', (145,88,64), [398]*6], #python sound feature? @see dr epilepsy.
            26: ['Bed'],    #inset, directional. xd: if head/foot + dirs.
            27: ['PwrRail', (204,93,22), [433]*6, 'XD', 'onehigh', None, {'stencil': True}],	#meshtype-> "rail". define as 1/16thHeightBlock, read extra data to find orientation.
            28: ['DetRail', (134,101,100), [465]*6, 'XD', 'onehigh', None, {'stencil': True}],	#change meshtype to "rail" for purposes of slanted bits. later. PLANAR, too. no bottom face.
            29: ['StickyPiston', (114,120,70), [109,491,493,493,493,493], 'XD', 'pstn'],
            30: ['Cobweb', (237,237,237), [54]*6, 'none', 'cross', None, {'stencil': True}],
            # tried 370, 434
            31: ['TallGrass', (52,79,45), [213,213,213,213,213,213], 'XD', 'cross', None, {'stencil': True}],
            32: ['DeadBush', (148,100,40), [225]*6, None, 'cross', None, {'stencil': True}],
            33: ['Piston', (114,120,70), [491,494,493,493,493,493], 'XD', 'pstn'],
            34: ['PistonHead', (188,152,98), [494]*6],	#or top is 106 if sticky (extra data)
            35: ['Wool', (235,235,235), [279]*6, 'XD'],  #XD means use xtra data...
            37: ['Dandelion', (204,211,2), [79]*6, 'no', 'cross', None, {'stencil': True}],
            38: ['Rose', (247,7,15), [207]*6, 'no', 'cross', None, {'stencil': True}],
            39: ['BrownMushrm', (204,153,120), [480]*6, 'no', 'cross', None, {'stencil': True}],
            40: ['RedMushrm', (226,18,18), [481]*6, 'no', 'cross', None, {'stencil': True}],
            41: ['GoldBlock', (255,241,68), [330]*6], # Todo: metalic
            42: ['IronBlock', (230,230,230), [394]*6],
            43: ['DblSlabs', (255,255,0), [53,53,21,21,21,21], 'XD', 'twoslab'],	#xd for type
            44: ['Slabs', (255,255,0), [53,53,21,21,21,21], 'XD', 'slab'],	#xd for type
            45: ['BrickBlock', (124,69,24), [101]*6],
            46: ['TNT', (219,68,26), [245,309,277,277,277,277]],
            47: ['Bookshelf', (180,144,90), [144,144,5,5,5,5]],
            48: ['MossStone', (61,138,61), [164]*6],
            49: ['Obsidian', (60,48,86), [141]*6],
            50: ['Torch', (240,150,50), [426]*6, 'XD', 'inset', [0,6,7], {'stencil': True}],
            51: ['Fire', (255,100,100), [56]*6, None, 'hash', None, {'emit': 1.0, 'stencil': True}],	#TODO: Needed for Nether. maybe use hash mesh '#'
            52: ['MonsterSpawner', (27,84,124), [65]*6, None, None, None, {'stencil': True}],	#xtra data for what's spinning inside it??
            53: ['WoodenStairs', (159,132,77), [4,4,4,4,4,4], 'XD', 'stairs'], # TODO
            54: ['Chest', (164,114,39), [25,25,26,27,26,26], 'XD', 'chest'],    #texface ordering is wrong # TODO
            55: ['RedStnWire', (255,0,3), [434]*6, 'XD', 'onehigh', None, {'stencil': True}],	#FSM-dependent, may need XD. Also, texture needs to act as bitmask alpha only, onto material colour on this thing. # TODO alpha color
            56: ['DiamondOre', (93,236,245), [168]*6],
            57: ['DiamondBlock', (93,236,245), [136]*6],
            58: ['CraftingTbl', (160,105,60), [197,197,196,195,196,195]],
            59: ['Seeds', (160,184,0), [310]*6, 'XD', 'crops', None, {'stencil': True}],
            60: ['Farmland', (69,41,21), [200,110,200,200,200,200]],
            61: ['Furnace', (42,42,42), [262,262,261,259,261,261]],		#[bottom, top, right, front, left, back]
            62: ['Burnace', (50,42,42), [262,262,261,259,261,261]],
            63: ['SignPost', (159,132,77), [579]*6, 'XD', 'sign'],
            64: ['WoodDoor', (145,109,56), [193,193,283,283,283,283], 'XD', 'door', None, {'stencil': True}], # FIXME top/bot
            65: ['Ladder', (142,115,60), [416]*6, None, None, None, {'stencil': True}],
            66: ['Rail', (172,136,82), [82]*6, 'XD', 'onehigh', None, {'stencil': True}],	#to be refined for direction etc.
            67: ['CobbleStairs', (77,77,77), [163]*6, 'XD', 'stairs'],
            68: ['WallSign', (159,132,77), [579]*6, 'XD', 'wallsign'],	#TODO: UVs! + Model!
            69: ['Lever', (105,84,51), [426]*6, 'XD', 'lever'],
            70: ['StnPressPlate', (110,110,110), [372]*6, 'no', 'onehigh'],
            71: ['IronDoor', (183,183,183), [187,187,187,187,187,187], 'XD', 'door', None, {'stencil': True}], # TODO top/bot
            72: ['WdnPressPlate', (159,132,77), [4]*6, 'none', 'onehigh'], #TODO
            73: ['RedstOre', (151,3,3), [51]*6],
            74: ['RedstOreGlowing', (255,3,3), [51]*6],	#wth!
            75: ['RedstTorchOff', (86,0,0), [83]*6, 'XD', 'inset', [0,6,7]],  #TODO Proper RStorch mesh
            76: ['RedstTorchOn', (253,0,0), [115]*6, 'XD', 'inset', [0,6,7]],  #todo: 'rstorch'
            77: ['StoneButton', (116,116,116), [1]*6, 'btn'], # TODO
            78: ['Snow', (240,240,240), [180]*6, 'XD', 'onehigh'],	#snow has height variants 0-7. 7 is full height block. Curses!
            79: ['Ice', (220,220,255), [391]*6],
            80: ['SnowBlock', (240,240,240), [180]*6],   #xd determines height.
            81: ['Cactus', (20,141,36), [70,70,38,38,38,38], 'none', 'cactus'],
            82: ['ClayBlock', (170,174,190), [135]*6],
            83: ['SugarCane', (130,168,89), [147]*6, None, 'cross', None, {'stencil': True}],
            84: ['Jukebox', (145,88,64), [489,399,489,489,489,489]],	#XD
            85: ['Fence', (160,130,70), [4]*6, 'none', 'fence'],	#fence mesh, extra data. #TODO
            86: ['Pumpkin', (227,144,29), [113,113,17,464,17,17]],
            87: ['Netherrack', (137,15,15), [488]*6],
            88: ['SoulSand', (133,109,94), [212]*6],
            89: ['Glowstone', (114,111,73), [329]*6, None, None, None, {'emit': 0.95, 'stencil': False}],	#cycles: emitter!
            90: ['Portal', (150,90,180), None], # TODO - shouldn't this be [208]*6?
            91: ['JackOLantern',(227,144,29), [113,113,17,496,17,17], 'XD'],	#needs its facing dir.
            92: ['Cake', (184,93,39), [124,71,39,39,39,39], 'XD', 'inset', [0,8,1]], # TODO - bot
            93: ['RedRepOff', (176,176,176), [179]*6, 'xdcircuit', 'onehigh'],	#TODO 'redrep' meshtype
            94: ['RedRepOn', (176,176,176), [211]*6, 'xdcircuit', 'onehigh'],	#TODO 'redrep' meshtype
            #95: ['LockedChest', (164,114,39), [25,25,26,27,26,26], 'xd', 'chest'], #texface order wrong (see #54)
            # When stencil set, blocks are non-textured and opaque... unanticipated state?
            95: ['StainedGlass', (164,114,39), [327]*6, 'XD', None, None, {'alpha': True}], #texface order wrong (see #54)
            96: ['Trapdoor', (117,70,34), [373]*6, 'XD', 'inset', [0,13,0]],
            97: ['HiddenSfish', (116,116,116), [335]*6],
            98: ['StoneBricks', (100,100,100), [85]*6, 'XD'],
            99: ['HgRedM', (210,177,125), [462]*6, 'XD'],	#XD for part/variant/colour (stalk/main)
            100: ['HgBrwM', (210,177,125), [461]*6, 'XD'],
            101: ['IronBars', (171,171,173), [393]*6, 'XD', 'pane'],
            102: ['GlassPane', (254,254,254), [263]*6, 'XD', 'pane', None, {'stencil': True}],
            103: ['Melon', (166,166,39), [458,458,455,455,455,455]],
            104: ['PumpkinStem'], # TODO 457?
            105: ['MelonStem'], # TODO 457?
            106: ['Vines', (39,98,13), [469]*6, 'XD', 'wallface'],
            107: ['FenceGate', (143,115,73), [4]*6], #TODO
            108: ['BrickStairs', (135,74,58), [101]*6, 'XD', 'stairs'], #TODO
            109: ['StoneBrickStairs', (100,100,100), [85]*6, 'XD', 'stairs'], #TODO
            110: ['Mycelium', (122,103,108), [200,483,482,482,482,482]],	#useful to ignore option? as this is Dirt top in Mushroom Biomes.
            111: ['LilyPad', (12,94,19), [22]*6, 'none', 'onehigh', None, {'stencil': True}],
            112: ['NethrBrick', (48,24,28), [484]*6],
            113: ['NethrBrickFence', (48,24,28), [484]*6, 'none', 'fence'],
            114: ['NethrBrickStairs', (48,24,28), [484]*6, 'XD', 'stairs'],
            115: ['NethrWart', (154,39,52), [487]*6],
            116: ['EnchantTab', (116,30,29), [141,205,173,173,173,173], 'none', 'inset', [0,4,0]],  #TODO enchantable with book?
            117: ['BrewStnd', (207,227,186), [157]*6, 'x', 'brewstand'],    #fully custom model # TODO
            118: ['Cauldron', (55,55,55), [139,138,154,154,154,154]],  #fully custom model # TODO
            119: ['EndPortal', (0,0,0), None], #TODO
            120: ['EndPortalFrame', (144,151,110), [237,175,78,46,46,46,46]],
            121: ['EndStone', (144,151,110), [237]*6],
            122: ['DragonEgg', (0,0,0)], #TODO
            123: ['RedstLampOff', (140,80,44), [498]*6],
            124: ['RedstLampOn',  (247,201,138), [19]*6, None, None, None, {'emit': 0.95, 'stencil': False}],
            129: ['EmeraldOre', (140,80,44), [109]*6],
            133: ['EmeraldBlock', (140,80,44), [77]*6],
            138: ['Beacon',  (247,201,138), [96]*6, None, None, None, {'emit': 1.2, 'stencil': False}], # TODO - encased in glass
            152: ['Redstone',  (247,201,138), [337]*6],
            153: ['NetherQuartzOre',  (247,201,138), [369]*6],
            155: ['Quartz',  (247,201,138), [145]*6], # TODO - variants
            159: ['StainedClay',  (247,201,138), [384]*6, 'XD'],
            162: ['Acacia',  (247,201,138), [428,428,427,427,427,427]], # TODO - dark oak
            168: ['Prismarine', (127, 255, 212), [432]*6, 'XD'],
            169: ['SeaLantern',  (247,201,138), [116]*6, None, None, None, {'emit': 1.2, 'stencil': False}], # TODO - encased in glass
            170: ['HayBale', (247,201,138), [387,387,386,386,386,386]],
            172: ['HardenedClay', (247,201,138), [353]*6],
            173: ['BlockOfCoal', (247,201,138), [160]*6],
            174: ['PackedIce', (247,201,138), [392]*6],
            179: ['RedSandstone', (247,201,138), [306,306,242,242,242,242]*6]
            }
            #And anything new Mojang add in with each update!

BLOCKVARIANTS = {
                #Saplings: normal, spruce, birch and jungle types
                6:  [ [''],
                      ['Spruce', (57,90,57), [63]*6],
                      ['Birch', (207,227,186), [79]*6],
                      ['Jungle', (57,61,13), [30]*6]
                    ],

                17: [ [''],#normal wood (oak)
                      ['Spruce',(76,61,38), [454,454,453,453,453,453]],
                      ['Birch', (76,61,38), [448,448,431,431,431,431]],
                      ['Jungle',(89,70,27), [450,450,449,449,449,449]],
                    ],
                #TODO: adjust leaf types, too!
                
                24: [ [''],#normal 'cracked' sandstone
                      ['Decor', (215,209,153), [403,403,301,301,301,301]],
                      ['Smooth',(215,209,153), [403,403,371,371,371,371]],
                    ],

                # Tallgrass - TODO
                #31: [ [''],
                #      ['', (,,), []*6],
                #      ['', (,,), []*6],
                #      ],
                # Wool
                35: [ [''],
                      ['Orange', (255,150,54), [119]*6],	#custom tex coords!
                      ['Magenta', (227,74,240), [87]*6],
                      ['LightBlue', (83,146,255), [23]*6],
                      ['Yellow', (225,208,31), [311]*6],
                      ['LightGreen', (67,218,53), [55]*6],
                      ['Pink', (248,153,178), [151]*6],
                      ['Grey', (75,75,75), [470]*6],
                      ['LightGrey', (181,189,189), [247]*6],
                      ['Cyan', (45,134,172), [438]*6],
                      ['Purple', (134,53,204), [183]*6],
                      ['Blue', (44,58,176), [374]*6],
                      ['Brown', (99,59,32), [406]*6],
                      ['DarkGreen', (64,89,27), [502]*6],
                      ['Red', (188,51,46), [215]*6],
                      ['Black', (28,23,23), [342]*6]
                    ],
                #doubleslabs
                #38: [ [''],] # TODO - flowers

                43: [ [''], #stone slabs (default)
                      ['SndStn', (215,209,153), [339]*6],
                      ['Wdn', (159,132,77), [176]*6],
                      ['Cobl', (94,94,94), [163]*6],
                      ['Brick', (124,69,24), [101]*6],
                      ['StnBrk', (100,100,100), [85]*6],
                      [''],
                    ],
                
                #slabs
                44: [ [''], #stone slabs (default)
                      ['SndStn', (215,209,153), [192]*6],
                      ['Wdn', (159,132,77), [4]*6],
                      ['Cobl', (94,94,94), [16]*6],
                      ['Brick', (124,69,24), [7]*6],
                      ['StnBrk', (100,100,100), [54]*6],
                      [''],
                    ],
                    
                50: [ [''], #nowt on 0...
                      ['Ea'],	#None for colour, none Tex, then: CUSTOM MESH
                      ['We'],
                      ['So'],
                      ['Nr'],
                      ['Up']
                    ],
                    
                59: [ ['0', (160,184,0), [88]*6],   #?
                      ['1', (160,184,0), [89]*6],
                      ['2', (160,184,0), [90]*6],
                      ['3', (160,184,0), [91]*6],
                      ['4', (160,184,0), [92]*6],
                      ['5', (160,184,0), [93]*6],
                      ['6', (160,184,0), [94]*6],
                      ['7', (160,184,0), [95]*6],
                    ],
                # stained glass
                95: [ ['White', (255,255,255), [327]*6],
                      ['Orange', (255,150,54), [289]*6],	#custom tex coords!
                      ['Magenta', (227,74,240), [288]*6],
                      ['LightBlue', (83,146,255), [267]*6],
                      ['Yellow', (225,208,31), [328]*6],
                      ['LightGreen', (67,218,53), [271]*6],
                      ['Pink', (248,153,178), [323]*6],
                      ['Grey', (75,75,75), [268]*6],
                      ['LightGrey', (181,189,189), [326]*6],
                      ['Cyan', (45,134,172), [270]*6],
                      ['Purple', (134,53,204), [324]*6],
                      ['Blue', (44,58,176), [265]*6],
                      ['Brown', (99,59,32), [266]*6],
                      ['DarkGreen', (64,89,27), [269]*6],
                      ['Red', (188,51,46), [325]*6],
                      ['Black', (28,23,23), [264]*6]
                      ],
                
                #stone brick moss/crack/circle variants:
                98: [ [''],
                      ['Mossy',  (100,100,100), [181]*6],
                      ['Cracked',(100,100,100), [149]*6],
                      ['Circle', (100,100,100), [117]*6],
                    ],
                #hugebrownmush:
                99: [ [''], #default (pores on all sides)
                      ['CrTWN',(210,177,125),[142,126,142,142,126,126]],#1
                      ['SdTN',(210,177,125),[142,126,142,142,142,126]],#2
                      ['CrTEN',(210,177,125),[142,126,126,142,142,126]],#3
                      ['SdTW',(210,177,125),[142,126,142,142,126,142]],#4
                      ['Top',(210,177,125),[142,126,142,142,142,142]],#5
                      ['SdTE',(210,177,125),[142,126,126,142,142,142]],#6
                      ['CrTSW',(210,177,125),[142,126,142,126,126,142]],#7
                      ['SdTS',(210,177,125),[142,126,142,126,142,142]],#8
                      ['CrTES',(210,177,125),[142,126,126,126,142,142]],#9
                      ['Stem',(215,211,200),[142,142,141,141,141,141]]#10
                    ],
                #hugeredmush:
                100:[ [''], #default (pores on all sides)
                      ['CrTWN',(188,36,34),[142,125,142,142,125,125]],#1
                      ['SdTN',(188,36,34),[142,125,142,142,142,125]],#2
                      ['CrTEN',(188,36,34),[142,125,125,142,142,125]],#3
                      ['SdTW',(188,36,34),[142,125,142,142,125,142]],#4
                      ['Top',(188,36,34),[142,125,142,142,142,142]],#5
                      ['SdTE',(188,36,34),[142,125,125,142,142,142]],#6
                      ['CrTSW',(188,36,34),[142,125,142,125,125,142]],#7
                      ['SdTS',(188,36,34),[142,125,142,125,142,142]],#8
                      ['CrTES',(188,36,34),[142,125,125,125,142,142]],#9
                      ['Stem',(215,211,200),[142,142,141,141,141,141]]#10
                    ],

                # stained clay
                159: [[''], # ['White', (255,255,255), [384]*6],
                      ['Orange', (255,150,54), [363]*6],	#custom tex coords!
                      ['Magenta', (227,74,240), [362]*6],
                      ['LightBlue', (83,146,255), [355]*6],
                      ['Yellow', (225,208,31), [385]*6],
                      ['LightGreen', (67,218,53), [361]*6],
                      ['Pink', (248,153,178), [364]*6],
                      ['Grey', (75,75,75), [358]*6],
                      ['LightGrey', (181,189,189), [367]*6],
                      ['Cyan', (45,134,172), [357]*6],
                      ['Purple', (134,53,204), [365]*6],
                      ['Blue', (44,58,176), [354]*6],
                      ['Brown', (99,59,32), [356]*6],
                      ['DarkGreen', (64,89,27), [359]*6],
                      ['Red', (188,51,46), [366]*6],
                      ['Black', (28,23,23), [354]*6]
                      ],

                # prismarine
                168: [[''],
                      ['Bricks', (127, 255, 212), [368]*6],
                      ['Dark', (127, 255, 212), [400]*6],
                      ]
                }

def readLevelDat():
    """Reads the level.dat for info like the world name, player inventory..."""
    lvlfile = gzip.open('level.dat', 'rb')

    #first byte must be a 10 (TAG_Compound) containing all else.
    #read a TAG_Compound...
    #rootTag = Tag(lvlfile)

    rootTag = nbtreader.TagReader.readNamedTag(lvlfile)[1]    #don't care about the name... or do we? Argh, it's a named tag but we throw the blank name away.

    print(rootTag.printTree(0))    #give it repr with an indent param...?


def readRegion(fname, vertexBuffer):
    #A region has an 8-KILObyte header, of 1024 locations and 1024 timestamps.
    #Then from 8196 onwards, it's chunk data and (arbitrary?) gaps.
    #Chunks are zlib compressed & have their own structure, more on that later.
    print('== Reading region %s ==' % fname)

    rfile = open(fname, 'rb')
    regionheader = rfile.read(8192)

    chunklist = []
    chunkcount = 0
    cio = 0    #chunk index offset
    while cio+4 <= 4096:    #only up to end of the locations! (After that is timestamps)
        cheadr = regionheader[cio:cio+4]
        # 3 bytes "offset"         -- how many 4kiB disk sectors away the chunk data is from the start of the file.
        # 1 byte "sector count"    -- how many 4kiB disk sectors long the chunk data is.
        #(sector count is rounded up during save, so gives the last disk sector in which there's data for this chunk)

        offset = unpack(">i", b'\x00'+cheadr[0:3])[0]
        chunksectorcount = cheadr[3]    #last of the 4 bytes is the size (in 4k sectors) of the chunk
        
        chunksLoaded = 0
        if offset != 0 and chunksectorcount != 0:    #chunks not generated as those coordinates yet will be blank!
            chunkdata = readChunk(rfile, offset, chunksectorcount)    #TODO Make sure you seek back to where you were to start with ...
            chunksLoaded += 1
            chunkcount += 1

            chunklist.append((offset,chunksectorcount))

        cio += 4

    rfile.close()

    print("Region file %s contains %d chunks." % (fname, chunkcount))
    return chunkcount

def toChunkPos(pX,pZ):
    return (pX/16, pZ/16)

def batchBuild(meshBuffer):
    #build all geom from pydata as meshes in one shot. :) This is fast.
    for meshname in (meshBuffer.keys()):
        me = bpy.data.meshes[meshname]
        me.from_pydata(meshBuffer[meshname], [], [])
        me.update()


def mcToBlendCoord(chunkPos, blockPos):
    """Converts a Minecraft chunk X,Z pair and a Minecraft ordered X,Y,Z block
location triple into a Blender coordinate vector Vx,Vy,Vz.
Just remember: in Minecraft, Y points to the sky."""

    # Mapping Minecraft coords -> Blender coords
    # In Minecraft, +Z (west) <--- 0 ----> -Z (east), while North is -X and South is +X
    # In Blender, north is +Y, south is-Y, west is -X and east is +X.
    # So negate Z and map it as X, and negate X and map it as Y. It's slightly odd!

    vx = -(chunkPos[1] << 4) - blockPos[2]
    vy = -(chunkPos[0] << 4) - blockPos[0]   # -x of chunkpos and -x of blockPos (x,y,z)
    vz = blockPos[1]    #Minecraft's Y.
    
    return Vector((vx,vy,vz))


def getMCBlockType(blockID, extraBits):
    """Gets reference to a block type mesh, or creates it if it doesn't exist.
The mesh created depends on meshType from the global blockdata (whether it's torch or repeater, not a cube)
These also have to be unique and differently named for directional versions of the same thing - eg track round a corner or up a slope.
This also ensures material and name are set."""
    from . import blockbuild
    global OPTIONS  #, BLOCKDATA (surely!?)

    bdat = BLOCKDATA[blockID]

    corename = bdat[0]    # eg mcStone, mcTorch

    if len(bdat) > 1:
        colourtriple = bdat[1]
    else:
        colourtriple = [214,127,255] #shocking pink

    mcfaceindices = None    #[]
    if len(bdat) > 2 and bdat[2] is not None:
        mcfaceindices = bdat[2]

    usesExtraBits = False
    if len(bdat) > 3:
        usesExtraBits = (bdat[3] == 'XD')

    if not usesExtraBits:	#quick early create...
        landmeshname = "".join(["mc", corename])
        if landmeshname in bpy.data.meshes:
            return bpy.data.meshes[landmeshname]
        else:
            extraBits = None

    objectShape = "box"	#but this can change based on extra data too...
    if len(bdat) > 4:
        objectShape = bdat[4]

    shapeParams = None
    if len(bdat) > 5:   #and objectShape = 'insets'
        shapeParams = bdat[5]
    
    cycParams = None
    if OPTIONS['usecycles']:
        if len(bdat) > 6:
            cycParams = bdat[6]
        if cycParams is None:
            cycParams = {'emit': 0.0, 'stencil': False}
    
    nameVariant = ''
    if blockID in BLOCKVARIANTS:
        variants = BLOCKVARIANTS[blockID]
        if extraBits is not None and extraBits >= 0 and extraBits < len(variants):
            variantData = variants[extraBits]
            if len(variantData) > 0:
                nameVariant = variantData[0]
                #print("%d Block uses extra data: {%d}. So name variant is: %s" % (blockID, extraBits, nameVariant))
                #Now apply each available variant datum: RGB triple, texture faces, and blockbuild variation.
                if len(variantData) > 1:	#read custom RGB
                    colourtriple = variantData[1]
                    if len(variantData) > 2:
                        mcfaceindices = variantData[2]
                        #mesh constructor...
    corename = "".join([corename, nameVariant])
    meshname = "".join(["mc", corename])

    dupblock = blockbuild.construct(blockID, corename, colourtriple, mcfaceindices, extraBits, objectShape, shapeParams, cycParams)
    blockname = dupblock.name
    landmeshname = "".join(["mc", blockname.replace('Block', '')])

    if landmeshname in bpy.data.meshes:
        return bpy.data.meshes[landmeshname]

    landmesh = bpy.data.meshes.new(landmeshname)
    landob = bpy.data.objects.new(landmeshname, landmesh)
    bpy.context.scene.objects.link(landob)

    global WORLD_ROOT	#Will have been inited by now. Parent the land to it. (a bit messy, but... meh)
    landob.parent = WORLD_ROOT
    dupblock.parent = landob
    landob.dupli_type = "VERTS"
    return landmesh


def slimeOn():
    """Creates the cloneable slime block (area marker) and a mesh to duplivert it."""
    if 'slimeChunks' in bpy.data.objects:
        return

    #Create cube! (maybe give it silly eyes...)
    #ensure 3d cursor at 0...
    
    bpy.ops.mesh.primitive_cube_add()
    slimeOb = bpy.context.object    #get ref to last created ob.
    slimeOb.name = 'slimeMarker'
    #Make it chunk-sized. It starts 2x2x2
    bpy.ops.transform.resize(value=(8, 8, 8))
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # create material for the markers
    slimeMat = None
    smname = "mcSlimeMat"
    if smname in bpy.data.materials:
        slimeMat = bpy.data.materials[smname]
    else:
        slimeMat = bpy.data.materials.new(smname)
        #FIXME - hard code color
        slimeMat.diffuse_color = [86/256.0, 139.0/256.0, 72.0/256.0]
        slimeMat.diffuse_shader = 'OREN_NAYAR'
        slimeMat.diffuse_intensity = 0.8
        slimeMat.roughness = 0.909
        #slimeMat.use_shadeless = True	#traceable false!
        slimeMat.use_transparency = True
        slimeMat.alpha = .25

    slimeOb.data.materials.append(slimeMat)
    slimeChunkmesh = bpy.data.meshes.new("slimeChunks")
    slimeChunkob = bpy.data.objects.new("slimeChunks", slimeChunkmesh)
    bpy.context.scene.objects.link(slimeChunkob)
    slimeOb.parent = slimeChunkob
    slimeChunkob.dupli_type = "VERTS"
    global WORLD_ROOT
    slimeChunkob.parent = WORLD_ROOT


def batchSlimeChunks(slimes):
    #Populate all slime marker centres into the dupli-geom from pydata.
    me = bpy.data.meshes["slimeChunks"]
    me.from_pydata(slimes, [], [])
    me.update()


def getWorldSelectList():
    worldList = []
    MCSAVEPATH=sysutil.getMCSavePath()
    if os.path.exists(MCSAVEPATH):
        startpath = os.getcwd()
        os.chdir(MCSAVEPATH)
        saveList = os.listdir()
        saveFolders = [f for f in saveList if os.path.isdir(f)]
        wcount = 0
        for sf in saveFolders:
            if os.path.exists(sf + "/level.dat"):
                #Read the actual world name (not just folder name)
                wData = None
                try:
                    with gzip.open(sf + '/level.dat', 'rb') as levelDat:
                        wData = nbtreader.readNBT(levelDat)
                        #catch errors if level.dat wasn't a gzip...
                except IOError:
                    print("Unknown problem with level.dat format for %s" % sf)
                    continue
					
                # FIXME - having a problem
                try:
                    if 'LevelName' in wData.value['Data'].value:
                        wname = wData.value['Data'].value['LevelName'].value
                    else:
                        wname = "<no name>"
					
                    wsize = wData.value['Data'].value['SizeOnDisk'].value
                    readableSize = "(%0.1f)" % (wsize / (1024*1024))
                    worldList.append((sf, sf, wname + " " + readableSize))
                    wcount += 1
                except KeyError:
                    print("key not found in %s" % wData.value['Data'])
        os.chdir(startpath)

    if worldList != []:
        return worldList
    else:
        return None


def hasNether(worldFolder):
    if worldFolder == "":
        return False
    worldList = []
    MCSAVEPATH=sysutil.getMCSavePath()
    if os.path.exists(MCSAVEPATH):
        worldList = os.listdir(MCSAVEPATH)
        if worldFolder in worldList:
            wp = os.path.join(MCSAVEPATH, worldFolder, 'DIM-1')
            return os.path.exists(wp)
            #and: contains correct files? also check regions aren't empty.
    return False

def hasEnd(worldFolder):
    if worldFolder == "":
        return False
    worldList = []
    MCSAVEPATH=sysutil.getMCSavePath()
    if os.path.exists(MCSAVEPATH):
        worldList = os.listdir(MCSAVEPATH)
        if worldFolder in worldList:
            wp = os.path.join(MCSAVEPATH, worldFolder, 'DIM1')
            return os.path.exists(wp)
            #and: contains correct files? also check regions aren't empty.
    return False


def readMinecraftWorld(worldFolder, loadRadius, toggleOptions):
    global unknownBlockIDs, wseed
    global EXCLUDED_BLOCKS
    global WORLD_ROOT
    global OPTIONS, REPORTING
    OPTIONS = toggleOptions

    #timing/profiling:
    global tChunkReadTimes

    if worldFolder == "":
        #World selected was blank. No saves. i.e. only when world list is empty
        print("No valid saved worlds were available to load.")
        return

#    print("[!] OmitStone: ", toggleOptions['omitstone'])
    if not OPTIONS['omitstone']:
        EXCLUDED_BLOCKS = []

#    print('[[[exluding these blocks: ', EXCLUDED_BLOCKS, ']]]')
    worldList = []

    MCSAVEPATH=sysutil.getMCSavePath()
    if os.path.exists(MCSAVEPATH):
        worldList = os.listdir(MCSAVEPATH)
        #print("MC Path exists! %s" % os.listdir(MCPATH))
        #wherever os was before, save it, and restore it after this completes.
        os.chdir(MCSAVEPATH)

    worldSelected = worldFolder

    os.chdir(os.path.join(MCSAVEPATH, worldSelected))

    # If there's a folder DIM-1 in the world folder, you've been to the Nether!
    # ...And generated Nether regions.
    if os.path.exists('DIM-1'):
        if OPTIONS['loadnether']:
            print('nether LOAD!')
        else:
            print('Nether is present, but not chosen to load.')
    
    if os.path.exists('DIM1'):
        if OPTIONS['loadend']:
            print('load The End...')
        else:
            print('The End is present, but not chosen to load.')

    #if the player didn't save out in those dimensions, we HAVE TO load at 3D cursor (or 0,0,0)

    worldData = None
    pSaveDim = None
    worldFormat = 'mcregion'	#assume initially

    with gzip.open('level.dat', 'rb') as levelDat:
        worldData = nbtreader.readNBT(levelDat)
    #print(worlddata.printTree(0))

    #Check if it's a multiplayer saved game (that's been moved into saves dir)
    #These don't have the Player tag.
    if 'Player' in worldData.value['Data'].value:
        #It's singleplayer
        pPos = [posFloat.value for posFloat in worldData.value['Data'].value['Player'].value['Pos'].value ]     #in NBT, there's a lot of value...
        pSaveDim = worldData.value['Data'].value['Player'].value['Dimension'].value
        print('Player: '+str(pSaveDim)+', ppos: '+str(pPos))
    else:
        #It's multiplayer.
        #Get SpawnX, SpawnY, SpawnZ and centre around those. OR
        #TODO: Check for another subfolder: 'players'. Read each NBT .dat in
        #there, create empties for all of them, but load around the first one.
        spX = worldData.value['Data'].value['SpawnX'].value
        spY = worldData.value['Data'].value['SpawnY'].value
        spZ = worldData.value['Data'].value['SpawnZ'].value
        pPos = [float(spX), float(spY), float(spZ)]
        
        #create empty markers for each player.
        #and: could it load multiplayer nether/end based on player loc?

    if 'version' in worldData.value['Data'].value:
        fmtVersion = worldData.value['Data'].value['version'].value
        #19133 for Anvil. 19132 is McRegion.
        if fmtVersion == MCREGION_VERSION_ID:
            print("World is in McRegion format")
        elif fmtVersion == ANVIL_VERSION_ID:
            print("World is in Anvil format")
            worldFormat = "anvil"

    wseed = worldData.value['Data'].value['RandomSeed'].value	#it's a Long
    print("World Seed : %d" % (wseed))	# or self.report....

    #NB: we load at cursor if player location undefined loading into Nether
    if OPTIONS['atcursor'] or (OPTIONS['loadnether'] and (pSaveDim is None or int(pSaveDim) != -1)):
        cursorPos = bpy.context.scene.cursor_location
        #that's an x,y,z vector (in Blender coords)
        #convert to insane Minecraft coords! (Minecraft pos = -Y, Z, -X)
        pPos = [ -cursorPos[1], cursorPos[2], -cursorPos[0]]

    if OPTIONS['loadnether']:
        os.chdir(os.path.join("DIM-1", "region"))
    elif OPTIONS['loadend']:
        os.chdir(os.path.join("DIM1", "region"))
    else:
        os.chdir("region")

    meshBuffer = {}
    blockBuffer = {}

    #Initialise the world root - an empty to parent all land objects to.
    WORLD_ROOT = bpy.data.objects.new(worldSelected, None)	#,None => EMPTY!
    bpy.context.scene.objects.link(WORLD_ROOT)
    WORLD_ROOT.empty_draw_size = 2.0
    WORLD_ROOT.empty_draw_type = 'SPHERE'
    
    regionfiles = []
    regionreader = None
    if worldFormat == 'mcregion':
        regionfiles = [f for f in os.listdir() if f.endswith('.mcr')]
        from .mcregionreader import ChunkReader
        regionreader = ChunkReader()  #work it with the class, not an instance?
        #all this importing is now very messy.

    elif worldFormat == 'anvil':
        regionfiles = [f for f in os.listdir() if f.endswith('.mca')]
        from .mcanvilreader import AnvilChunkReader
        regionreader = AnvilChunkReader()

    #except when loading nether...
    playerChunk = toChunkPos(pPos[0], pPos[2])  # x, z
    
    print("Loading %d blocks around centre." % loadRadius)
    #loadRadius = 10 #Sane amount: 5 or 4.

    if not OPTIONS['atcursor']:	#loading at player
        #Add an Empty to show where the player is. (+CENTRE CAMERA ON!)
        playerpos = bpy.data.objects.new('PlayerLoc', None)
        #set its coordinates...
        #convert Minecraft coordinate position of player into Blender coords:
        playerpos.location[0] = -pPos[2]
        playerpos.location[1] = -pPos[0]
        playerpos.location[2] = pPos[1]
        bpy.context.scene.objects.link(playerpos)
        playerpos.parent = WORLD_ROOT

    #total chunk count across region files:
    REPORTING['totalchunks'] = 0
    
    pX = int(playerChunk[0])
    pZ = int(playerChunk[1])
    
    print('Loading a square halfwidth of %d chunks around load position, so creating chunks: %d,%d to %d,%d' % (loadRadius, pX-loadRadius, pZ-loadRadius, pX+loadRadius, pZ+loadRadius))

    if (OPTIONS['showslimes']):
        slimeOn()
        from . import slimes
        slimeBuffer = []

    # FIXME - need deltaX/Y/Z to get array index
    zeroAdjX = -1 * (pZ-loadRadius)
    zeroAdjZ = -1 * (pX-loadRadius)

    for z in range(pZ-loadRadius, pZ+loadRadius):
        for x in range(pX-loadRadius, pX+loadRadius):

            tChunk0 = datetime.datetime.now()
            if (OPTIONS['surfaceOnly']): # new method
                numElements=(loadRadius*2+1)*16 # chunks * blocks
                blockBuffer = npy.zeros((numElements,numElements,numElements))

                # FIXME - currently only supported by anvil reader
                regionreader.readChunk2(x,z, blockBuffer, zeroAdjX, zeroAdjZ)
            else: # old
                regionreader.readChunk(x,z, meshBuffer) #may need to be further broken down to block level. maybe rename as loadChunk.
            tChunk1 = datetime.datetime.now()
            chunkTime = tChunk1 - tChunk0
            tChunkReadTimes.append(chunkTime.total_seconds())	#tString = "%.2f seconds" % chunkTime.total_seconds() it's a float.

            if (OPTIONS['showslimes']):
                if slimes.isSlimeSpawn(wseed, x, z):
                    slimeLoc = mcToBlendCoord((x,z), (8,8,8))	#(8,8,120)
                    slimeLoc += Vector((0.5,0.5,-0.5))
                    slimeBuffer.append(slimeLoc)

    tBuild0 = datetime.datetime.now()
    batchBuild(meshBuffer)
    if (OPTIONS['showslimes']):
        batchSlimeChunks(slimeBuffer)
    tBuild1 = datetime.datetime.now()
    tBuildTime = tBuild1 - tBuild0
    print("Built meshes in %.2fs" % tBuildTime.total_seconds())

    print("%s: loaded %d chunks" % (worldSelected, totalchunks))
    if len(unknownBlockIDs) > 0:
        print("Unknown new Minecraft datablock IDs encountered:")
        print(" ".join(["%d" % bn for bn in unknownBlockIDs]))
    
    #Viewport performance hides:
    if (OPTIONS['fasterViewport']):
        hideIfPresent('mcStone')
        hideIfPresent('mcDirt')
        hideIfPresent('mcSandstone')
        hideIfPresent('mcIronOre')
        hideIfPresent('mcGravel')
        hideIfPresent('mcCoalOre')
        hideIfPresent('mcBedrock')
        hideIfPresent('mcRedstoneOre')

    #Profile/run stats:
    chunkReadTotal = tChunkReadTimes[0]
    for tdiff in tChunkReadTimes[1:]:
        chunkReadTotal = chunkReadTotal + tdiff
    print("Total chunk reads time: %.2fs" % chunkReadTotal)  #I presume that's in seconds, ofc... hm.
    chunkMRT = chunkReadTotal / len(tChunkReadTimes)
    print("Mean chunk read time: %.2fs" % chunkMRT)
    print("Block points processed: %d" % REPORTING['blocksread'])
    print("of those, verts dumped: %d" % REPORTING['blocksdropped'])
    if REPORTING['blocksread'] > 0:
        print("Difference (expected vertex count): %d" % (REPORTING['blocksread'] - REPORTING['blocksdropped']))
        print("Hollowing has made the scene %d%% lighter" % ((REPORTING['blocksdropped'] / REPORTING['blocksread']) * 100))

    #increase viewport clip dist to see the world! (or decrease mesh sizes)
    #bpy.types.Space...
    #Actually: scale world root down to 0.05 by default?

def hideIfPresent(mName):
    if mName in bpy.data.objects:
        bpy.data.objects[mName].hide = True


# Feature TODOs
# surface load (skin only, not block instances)
# torch, stairs, rails, redrep meshblocks.
# nether load
# mesh optimisations
# multiple loads per run -- need to name new meshes each time load performed, ie mcGrass.001
# ...
