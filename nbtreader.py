
# NBT Reader module

from struct import calcsize, unpack, error as StructError

# An NBT file contains one root TAG_Compound.
TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11

INDENTCHAR = "  "


#to read level.dat: compound, long, list short byte. int. ... end.

#Why not just do this as a 10 element array of classes, and instantiate them as list[6](bstream) ?! MAGIC!
# that's what the py NBT guy does already!
# See struct - for handling types and bitpacking and converting to/from bytes.

#pass classes around as objects. ie class Tag... we now have Tag in the namespace and can instantiate it by calling that one's __init__ method.

# Note that ONLY Named Tags carry the name and tagType data. Explicitly identified Tags (such as TAG_String) only contains the payload.

# read binary, py 3.2 etc, you get a bytes object.
# seek(pos-in-file), tell() (number of bytes read) and read(n) read n bytes...


class TagReader:
    #a class to generate tags based on ids.
    
    def readNamedTag(bstream):
        """Reads a named Tag from the bytestream provided. Returns a tuple of (name, tag) (where tag object is the payload). Name will be empty for Tag_END. """
        #print("Reading Named Tag\n")
        tbyte = bstream.read(1)[0]    # read 1 byte and get its numerical value        #read 1 byte, switch type generated depending (stream-reader type 'abstract?' factory
        #print("Byte read: %d" % tbyte)
        tname = TAG_String(bstream).value
        #print("Name read: %s" % tname)
        #print("RNamedT - name is %s" %tname)
        tpayload = TAGLIST[tbyte](bstream)
        tpayload.name = tname
        return (tname, tpayload)
        #object type = bleh based on the number 0-255 you just read. Which should be a 10... for TAG_Compound.


def readNBT(bstream):
    rootname, rootTag = TagReader.readNamedTag(bstream)
    rootTag.name = rootname

    #check if not at end of string and read more NBT tags if present...?
    #nfile.close()
    return rootTag


    ##DONT PASS THE TYPE IN TO EVERY INSTANCE WHEN ITS ALWAYS THE SAME! DEFINE IT AS A CLASS VAR IN THE SUBCLASSES.






class Tag:
    type = None

    def __init__(self, bstream):
        """Reads self-building data for this type from the bytestream given, until a complete tag instance is ready."""
        # Tag itself doesn't do this. Must be overridden.
        self.name = ""
        ## named tags..? Are named tags only named when in a tag_compound that defines their names? And tag_compounds are always named?
        #self.value = "" needed?
        #payload... varies by subclass.
        self._parseContent(bstream)

    #Needed at all?!
    def __readName(self, bstream):
        """Only if called on a named tag .... will this be needed. may be Defined instead ... as a class method later"""
        raise NotImplementedError(self.__class__.__name__)
        pass

    def _parseContent(self, bstream):
        raise NotImplementedError(self.__class__.__name__)
        pass    # raise notimplemented...?        # SUBCLASSES IMPLEMENT THIS!

    #external code. not sure about these at all.
    #Printing / bitformatting as tree
    def toString(self):
        return self.__class__.__name__ + ('("%s")'%self.name if self.name else "") + ": " + self.__repr__()    #huh... self.repr build tree

    def printTree(self, indent=0):
        return (INDENTCHAR*indent) + self.toString()


        #could just skip this class....?
class TAG_End(Tag):
    type = TAG_END

    def _parseContent(self, bstream):
        pass
    #so, in fact... no need for this at all!?!


class _TAG_Numeric(Tag):
    """parses one of the numeric types (actual type defined by subclass)"""
    #uses struct bitformats (within each subclass) to parse the value from the data stream...
    bitformat = ""    #class, not instance, var.nB: make this something that will crash badly if not overwritten properly!

    def __init__(self, bstream):
        #if self.bitformat == "":
        #    print("INCONCEIVABLE!")
        #    raise NotImplementedError(self.__class__.__name__)
        #print("fmt is: %s" % self.bitformat)
        self.size = calcsize(self.bitformat)
        super(_TAG_Numeric, self).__init__(bstream)

    def _parseContent(self, bstream):
        #struct parse it using bitformat.
        self.value = unpack(self.bitformat, bstream.read(self.size))[0]	#[0] because this always returns a tuple

    def __repr__(self):
        return "%d" % self.value

class TAG_Byte(_TAG_Numeric):
    bitformat = ">b"    # class variable, NOT INSTANCE VARIABLE.
    #easy, it's read 1 byte!
    #def __parseContent(self, bstream):
    #    self.value = bstream.read(1)[0]    #grab next 1 byte in stream. That's the TAG_Byte's payload.
    #    #or rather, set bitformat to ">c"

class TAG_Short(_TAG_Numeric):
#    type = TAG_SHORT
    bitformat = ">h"

class TAG_Int(_TAG_Numeric):
    bitformat = ">i"

class TAG_Long(_TAG_Numeric):
#    id = TAG_LONG
    bitformat = ">q"

class TAG_Float(_TAG_Numeric):
#    id = TAG_FLOAT
    bitformat = ">f"
    
    def __repr__(self):
        return "%0.2f" % self.value

class TAG_Double(_TAG_Numeric):
#    id = TAG_DOUBLE
    bitformat = ">d"
    
    def __repr__(self):
        return "%0.2f" % self.value

class TAG_Byte_Array(Tag):
    type = TAG_BYTE_ARRAY
    def _parseContent(self, bstream):
        #read the length, then grab the bytes.
        length = TAG_Int(bstream)
        self.value = bstream.read(length.value)    #read n bytes from the file, where n is the numerical value of the length. Hope this works OK!

    def __repr__(self):
        return "[%d bytes array]" % len(self.value)
        
class TAG_String(Tag):
    type = TAG_STRING
    
    def _parseContent(self, bstream):
        #print ("Parsing TAG_String")
        length = TAG_Short(bstream)
        readbytes = bstream.read(length.value)
        if len(readbytes) != length.value:
            raise StructError()
        self.value = readbytes.decode('utf-8')    #unicode(read, "utf-8")

    def __repr__(self):
        return self.value

class TAG_List(Tag):
    type = TAG_LIST

    def _parseContent(self, bstream):
        tagId = TAG_Byte(bstream).value
        length = TAG_Int(bstream).value
        self.value = []
        for t in range(length):
            self.value.append(TAGLIST[tagId](bstream))    #so that's just the tags, not the repeated type ids. makes sense.

    def __repr__(self):    # use repr for outputting payload values, but printTree(indent) for outputting all. Perhaps.
        if len(self.value) > 0:
            return "%d items of type %s\r\n" % (len(self.value), self.value[0].__class__.__name__)    #"\r\n".join([k for k in self.value.keys()])    #to be redone!
        else:
            return "Empty List: No Items!"
        #represent self as nothing (type and name already output in printtree by the super().printTree call. Take a new line, and the rest will be output as subelements...
            
    def printTree(self, indent):
        outstr = super(TAG_List, self).printTree(indent)
        for tag in self.value:
            outstr += indent*INDENTCHAR + tag.printTree(indent+1) + "\r\n"
        
        return outstr
    

class TAG_Compound(Tag):
    type = TAG_COMPOUND
        #A sequential list of Named Tags. This array keeps going until a TAG_End is found.
        #NB: "Named tags" are:
        #byte tagType
        #TAG_String name
        #[payload]

    # This is where things get named. All names must be unique within the tag-compound. So its value is a dict.
    # it's named. so first thing is, read name.
    # then, keep on reading until you get a Tag_END
    #but, in-place create tags as you go and add them to an internal tag list...
    #essentially this parses the PAYLOAD of a named TAG_Compound...
    def _parseContent(self, bstream):
        #tagnext = readNamedTag()
    
        self.value = {}
        #print("Parsing TAG_Compound!")
        readType = bstream.read(1)[0]    #rly?
        #print("First compound inner tag type byte is: %d" % readType)
        while readType != TAG_END:
            tname = TAG_String(bstream).value
            #print ("Tag name read as: %s" % tname)
            payload = TAGLIST[readType](bstream)
            payload.name = tname
            self.value[tname] = payload
            readType = bstream.read(1)[0]

    def __repr__(self):    # use repr for outputting payload values, but printTree(indent) for outputting all. Perhaps.
        return "\r\n"
        #represent self as nothing (type and name already output in printtree by the super().printTree call. Take a new line, and the rest will be output as subelements...
            
    def printTree(self, indent):
        outstr = super(TAG_Compound, self).printTree(indent)
        keys = self.value.keys()
        for k in keys:
            outstr += indent*INDENTCHAR + self.value[k].printTree(indent+1) + "\r\n"
        
        return outstr

class TAG_Int_Array(Tag):
    type = TAG_INT_ARRAY
    def _parseContent(self, bstream):
        #read the length, then grab the bytes. split those out as 4-byte integers. we hope...
        tagLen = TAG_Int(bstream)
        #read out all other values as tag_ints too.
        ilength = tagLen.value
        self.value = []
        for t in range(ilength):
            self.value.append(TAG_Int(bstream).value)

    def __repr__(self):
        #printslist = [str(i) for i in self.value]
        #prout = ', '.join(printslist)
        #return "[%d ints array] [%s]" % (len(self.value), prout)
        return "[%d ints array]" % len(self.value)


TAGLIST = {TAG_BYTE: TAG_Byte, TAG_SHORT: TAG_Short, TAG_INT: TAG_Int, 
    TAG_LONG:TAG_Long, TAG_FLOAT:TAG_Float, TAG_DOUBLE:TAG_Double, 
    TAG_BYTE_ARRAY:TAG_Byte_Array, TAG_STRING:TAG_String,
    TAG_LIST: TAG_List, TAG_COMPOUND:TAG_Compound, TAG_INT_ARRAY: TAG_Int_Array}
