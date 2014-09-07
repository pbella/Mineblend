# io_import_minecraft

# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

bl_info = {
    "name": "Import: Minecraft b1.7+",
    "description": "Importer for viewing Minecraft worlds",
    "author": "Adam Crossan (acro)",
    "version": (1,6,1),
    "blender": (2, 6, 0),
    "api": 41226,
    "location": "File > Import > Minecraft",
    "warning": '', # used for warning icon and text in addons panel
    "wiki_url": "http://randomsamples.info/project/mineblend",
    "category": "Import-Export"}

# To support reload properly, try to access a package var, if it's there, reload everything
if "bpy" in locals():
    import imp
    if "mineregion" in locals():
        imp.reload(mineregion)

import bpy
from bpy.props import StringProperty, FloatProperty, IntProperty, BoolProperty, EnumProperty
from . import mineregion

#def setSceneProps(scn):
#    #Set up scene-level properties
#    bpy.types.Scene.MCLoadNether = BoolProperty(
#        name = "Load Nether", 
#        description = "Load Nether (if present) instead of Overworld.",
#        default = False)

#    scn['MCLoadNether'] = False
#    return
#setSceneProps(bpy.context.scene)

#Menu 'button' for the import menu (which calls the world selector)...
class MinecraftWorldSelector(bpy.types.Operator):
    """An operator defining a dialogue for choosing one on-disk Minecraft world to load.
This supplants the need to call the file selector, since Minecraft worlds require
a preset specific folder structure of multiple files which cannot be selected singly."""

    bl_idname = "mcraft.selectworld"
    bl_label = "Select Minecraft World"
    
    #bl_space_type = "PROPERTIES"
    #Possible placements for these:
    bl_region_type = "WINDOW"

    mcLoadAtCursor = bpy.props.BoolProperty(name='Use 3D Cursor as Player', description='Loads as if 3D cursor offset in viewport was the player (load) position.', default=False)

    #TODO: Make this much more intuitive for the user!
    mcLowLimit = bpy.props.IntProperty(name='Load Floor', description='The lowest depth layer to load. (High=256, Sea=64, Low=0)', min=0, max=256, step=1, default=0, subtype='UNSIGNED')
    mcHighLimit = bpy.props.IntProperty(name='Load Ceiling', description='The highest layer to load. (High=256, Sea=64, Low=0)', min=0, max=256, step=1, default=256, subtype='UNSIGNED')

    mcLoadRadius = bpy.props.IntProperty(name='Load Radius', description="""The half-width of the load range around load-pos.
e.g, 4 will load 9x9 chunks around the load centre
WARNING! Above 10, this gets slow and eats LOTS of memory!""", min=1, max=50, step=1, default=5, subtype='UNSIGNED')    #soft_min, soft_max?
    #optimiser algorithms/detail omissions

    mcOmitStone = bpy.props.BoolProperty(name='Omit Stone', description='Check this to not load stone blocks (block id 1). Speeds up loading and viewport massively', default=True)
    
    mcLoadNether = bpy.props.BoolProperty(name='Load Nether', description='Load Nether (if present) instead of Overworld.', default=False)

    mcLoadEnd = bpy.props.BoolProperty(name='Load The End', description='Load The End (if present) instead of Overworld.', default=False)

    mcShowSlimeSpawns = bpy.props.BoolProperty(name='Slime Spawns', description='Display green markers showing slime-spawn locations', default=False)

    mcUseCyclesMats = bpy.props.BoolProperty(name='Use Cycles', description='Set up default materials for use with Cycles Render Engine instead of Blender Internal', default=False)

    #may need to define loadnether and loadend as operators...?

    # omit Dirt toggle option.
    
    # height-limit option (only load down to a specific height) -- could be semi-dynamic and delve deeper when air value for the 
    # column in question turns out to be lower than the loading threshold anyway.
    
    #surfaceOnly ==> only load surface, discard underground areas. Doesn't count for nether.
    # Load Nether is, obviously, only available if selected world has nether)
    # Load End. Who has The End?! Not I!

    #When specifying a property of type EnumProperty, ensure you call the constructing method correctly.
    #Note that items is a set of (identifier, value, description) triples, and default is a string unless you switch on options=ENUM_FLAG in which case make default a set of 1 string.
    #Need a better way to handle this variable: (possibly set it as a screen property)

    from . import mineregion
    wlist = mineregion.getWorldSelectList()
    if wlist is not None:
        revwlist = wlist[::-1]
        #temp debug REMOVE!
        ###dworld = None
        ###wnamelist = [w[0] for w in revwlist]
        ###if "AnviliaWorld" in wnamelist:
        #####build the item for it to be default-selected...? Or work out if ENUM_FLAG is on?
        ###    dworld = "%d" % wnamelist.index("AnviliaWorld") #set(["AnviliaWorld"])
        ###if dworld is None:
        mcWorldSelectList = bpy.props.EnumProperty(items=wlist[::-1], name="World", description="Which Minecraft save should be loaded?")	#default='0', update=worldchange
        ###else:
        ###    mcWorldSelectList = bpy.props.EnumProperty(items=wlist[::-1], name="World", description="Which Minecraft save should be loaded?", default=dworld)   #, options={'ENUM_FLAG'}
    else:
        mcWorldSelectList = bpy.props.EnumProperty(items=[], name="World", description="Which Minecraft save should be loaded?") #, update=worldchange

        #TODO: on select, check presence of DIM-1 etc.
    #print("wlist:: ", wlist)
    netherWorlds = [w[0] for w in wlist if mineregion.hasNether(w[0])]
    #print("List of worlds with Nether: ", netherWorlds)

    endWorlds = [e[0] for e in wlist if mineregion.hasEnd(e[0])]
    #print("List of worlds with The End: ", endWorlds)

    #my_worldlist = bpy.props.EnumProperty(items=[('0', "A", "The A'th item"), ('1', 'B', "Bth item"), ('2', 'C', "Cth item"), ('3', 'D', "dth item"), ('4', 'E', 'Eth item')][::-1], default='2', name="World", description="Which Minecraft save should be loaded?")


    def execute(self, context): 
        #self.report({"INFO"}, "Loading world: " + str(self.mcWorldSelectList))
        #thread.sleep(30)
        #self.report({"WARNING"}, "Foo!")
        
        #from . import mineregion
        scn = context.scene

        opts = {"omitstone": self.mcOmitStone, "showslimes": self.mcShowSlimeSpawns, "atcursor": self.mcLoadAtCursor,
            "highlimit": self.mcHighLimit, "lowlimit": self.mcLowLimit, "loadnether": self.mcLoadNether,    #scn['MCLoadNether']
            "loadend": self.mcLoadEnd, "usecycles": self.mcUseCyclesMats}
        #get selected world name instead via bpy.ops.mcraft.worldselected -- the enumeration as a property/operator...?
        mineregion.readMinecraftWorld(str(self.mcWorldSelectList), self.mcLoadRadius, opts)
        for s in bpy.context.area.spaces: # iterate all space in the active area
            if s.type == "VIEW_3D": # check if space is a 3d-view
                space = s
                space.clip_end = 10000.0
        #run minecraftLoadChunks
        
        return {'FINISHED'}


    def invoke(self, context, event):
        context.window_manager.invoke_props_dialog(self, width=350,height=250)
        return {'RUNNING_MODAL'}


    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.label(text="Choose import options")

        row = col.row()
        row.prop(self, "mcLoadAtCursor")
        row.prop(self, "mcOmitStone")
        
        row = col.row()
        
        sub = col.split(percentage=0.5)
        colL = sub.column(align=True)
        colL.prop(self, "mcShowSlimeSpawns")
        colR = sub.column(align=True)
        ##colR.active = self.mcWorldSelectList in self.netherWorlds #self.mcworld_has_nether(self.mcWorldSelectList)    #in self.netherWorlds / in self.endWorlds
        colR.prop(self, "mcLoadNether")

        rowEnd = colR.row()
        ##rowEnd.active = self.mcWorldSelectList in self.endWorlds
        rowEnd.prop(self, "mcLoadEnd")

        cycles = None
        if hasattr(bpy.context.scene, 'cycles'):
            cycles = bpy.context.scene.cycles
        row2 = col.row()
        if cycles is not None:
            row2.active = (cycles is not None)
            row2.prop(self, "mcUseCyclesMats")
        #if cycles:
        #like this from properties_data_mesh.py:
        ##layout = self.layout
        ##mesh = context.mesh
        ##split = layout.split()
        ##col = split.column()
        ##col.prop(mesh, "use_auto_smooth")
        ##sub = col.column()
        ##sub.active = mesh.use_auto_smooth
        ##sub.prop(mesh, "auto_smooth_angle", text="Angle")
        #row.operator(
        #row.prop(self, "mcLoadEnd")	#detect folder first (per world...)
        
        #label: "loading limits"
        row = layout.row()
        row.prop(self, "mcLowLimit")
        row = layout.row()
        row.prop(self, "mcHighLimit")
        row = layout.row()
        row.prop(self, "mcLoadRadius")

        row = layout.row()
        row.prop(self, "mcWorldSelectList")
        #row.operator("mcraft.worldlist", icon='')
        col = layout.column()

def worldchange(self, context):
    ##UPDATE (ie read then write back the value of) the property in the panel
    #that needs to be updated. ensure it's in the scene so we can get it...
    #bpy.ops.mcraft.selectworld('INVOKE_DEFAULT')
    #if the new world selected has nether, then update the nether field...
    #in fact, maybe do that even if it doesn't.
    #context.scene['MCLoadNether'] = True
    return {'FINISHED'}

class MineMenuItemOperator(bpy.types.Operator):
    bl_idname = "mcraft.launchselector"
    bl_label = "Needs label but label not used"

    def execute(self, context):
        bpy.ops.mcraft.selectworld('INVOKE_DEFAULT')
        return {'FINISHED'}

bpy.utils.register_class(MinecraftWorldSelector)
bpy.utils.register_class(MineMenuItemOperator)
#bpy.utils.register_class(MCraft_PT_worldlist)

#Forumsearch tip!! FINDME:
#Another way would be to update a property that is displayed in your panel via layout.prop(). AFAIK these are watched and cause a redraw on update.

def mcraft_filemenu_func(self, context):
    self.layout.operator("mcraft.launchselector", text="Minecraft (.region)", icon='MESH_CUBE')


def register():
    #bpy.utils.register_module(__name__)
    bpy.types.INFO_MT_file_import.append(mcraft_filemenu_func)	# adds the operator action func to the filemenu

def unregister():
    #bpy.utils.unregister_module(__name__)
    bpy.types.INFO_MT_file_import.remove(mcraft_filemenu_func)	# removes the operator action func from the filemenu

if __name__ == "__main__":
    register()
