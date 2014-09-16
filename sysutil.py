import os, sys

#TODO: tidy this up to one location (double defined here from mineregion)
MCPATH = ''
if sys.platform == 'darwin':
    MCPATH = os.path.join(os.environ['HOME'], 'Library', 'Application Support', 'minecraft')
elif sys.platform == 'linux':
    MCPATH = os.path.join(os.environ['HOME'], '.minecraft')
else:
    MCPATH = os.path.join(os.environ['APPDATA'], '.minecraft')
# This needs to be set by the addon during initial inclusion. Set as a bpy.props.StringProperty within the Scene, then refer to it all over this addon.

MCSAVEPATH = os.path.join(MCPATH, 'saves/')

def getMCPath():
    return MCPATH

def getMCSavePath():
    return MCSAVEPATH
