import bpy

def writeNoodleBuilder(material):
    """Takes a node tree from a material, and writes out a new script that creates
    the node tree in question."""
    
    nodeTree = material.node_tree
    
    nodes = []
    links = []
    
    for n in nodeTree.nodes:
        pos = (n.location[0], n.location[1])
        ins = []    #record default values where set.
        op = None

        for i in n.inputs:
            if hasattr(i, 'default_value'):
                ins.append((i.name, i.default_value))
            #else don't need it.
        
        if hasattr(n, "operation"):
            #it's a mathnode with operation, etc etc
            op = n.operation

        nodes.append((n.name, n.label, pos, ins, n.type, op))
    
    for l in nodeTree.links:
        linkData = (l.from_node.name, l.from_socket.name, l.to_node.name, l.to_socket.name)
        links.append(linkData)

    #create a script to recreate this exact layout on demand.
    
    t = bpy.data.texts.new(name="noodleBuilder1.py")
    t.write("import bpy\n")
    t.write("mat = bpy.data.materials['JIMMY']\nntree = mat.node_tree\n")
    t.write("ntree.nodes.clear()\n\n#Now recreate from scripted structure:\n")
    #
    for nspec in nodes:
        #line to create the node and position it:
        t.write("nn = ntree.nodes.new(type=\"{0}\")\n".format(nspec[4]))
        t.write("nn.name = \"{0}\"\n".format(nspec[0]))
        if nspec[5] is not None:
            t.write("nn.operation = '{0}'\n".format(nspec[5]))
        if nspec[1] != "":
            t.write("nn.label = \"%s\"\n" % nspec[1])
        t.write("nn.location = Vector(({:.3f}, {:.3f}))\n".format(nspec[2][0], nspec[2][1]))
        for ins in nspec[3]:
            t.write("nn.inputs['"+ins[0]+"'].default_value = "+ ins[1].__repr__() + "\n")   #doesn't work for text-type values
    t.write("#link creation\n")
    t.write("nd = ntree.nodes\nlinks = ntree.links\n")
    for lspec in links:
        #it's from_node, from_socket, to_node, to_socket.
        #Creation lines look like this:
        t.write("links.new(input=nd['%s'].outputs['%s'], output=nd['%s'].inputs['%s'])\n" % lspec)
    
    
    
    

#Now use this to get the node script for material X!
mat = bpy.data.materials['RailMat']

writeNoodleBuilder(mat)

#Check scripts! There should now be a new one.