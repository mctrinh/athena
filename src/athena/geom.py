import struct
import itertools
from collections import namedtuple

from plyfile import PlyData, PlyElement
import numpy as np

from PySide2.QtGui import QColor, QQuaternion, QVector3D as vec3d
from PySide2.QtCore import QUrl, QByteArray, Qt
from PySide2.Qt3DExtras import Qt3DExtras
from PySide2.Qt3DRender import Qt3DRender
from PySide2.Qt3DCore import Qt3DCore
from PySide2.QtQml import QQmlEngine, QQmlComponent

from athena import plymesh

# Geometry utilities


# The base types enumeration
basetypes = Qt3DRender.QAttribute.VertexBaseType

# Map from the enumeration to (byte_width, struct_code) pairs
# This dict is unzipped into two convenience dicts below.
basetype_data = { basetypes.Byte : (1,'b'), basetypes.UnsignedByte : (1,'B'),
                  basetypes.Short: (2, 'h'), basetypes.UnsignedShort : (2,'H'),
                  basetypes.Int  : (4, 'i'), basetypes.UnsignedInt : (4,'I'),
                  basetypes.HalfFloat : (2, 'e'),
                  basetypes.Float : (4, 'f'),
                  basetypes.Double : (8, 'd') }

# Map of Qt3D base types to byte widths
basetype_widths = { k: v[0] for k,v in basetype_data.items()}

# Map of Qt3D base types to codes for struct.unpack
basetype_struct_codes = { k: v[1] for k,v in basetype_data.items()}

# Map of Qt3D base types to numpy types
basetype_numpy_codes = { k: np.sctypeDict[v] for k,v in basetype_struct_codes.items()}

# And the reverse
basetype_numpy_codes_reverse = { np.sctypeDict[v] : k for k, v in basetype_struct_codes.items() }

def rotateAround( v1, v2, angle ):
    q = QQuaternion.fromAxisAndAngle( v2, angle )
    return q.rotatedVector( v1 )

AttrSpec = namedtuple('AttrSpec', 'name, column, numcols')

def buildVertexAttrs(parent, array, attrspecs ):

    # Measure the input array
    rows = len(array)
    columns = len(array[0])
    basetype = basetype_numpy_codes_reverse[array.dtype.type]
    basetype_width = basetype_widths[ basetype ]
    row_width = columns * basetype_width
    #print(columns, rows, basetype, basetype_width, row_width)

    # Convert input to a qt buffer
    rawstring = array.tobytes()
    byte_array = QByteArray(rawstring)
    qbuffer = Qt3DRender.QBuffer(parent)
    qbuffer.setData(byte_array)

    attrs = list()
    for asp in attrspecs:
        attr = Qt3DRender.QAttribute( parent )
        attr.setName( asp.name )
        attr.setVertexBaseType( basetype )
        attr.setVertexSize(asp.numcols)
        attr.setAttributeType(Qt3DRender.QAttribute.VertexAttribute)
        attr.setBuffer(qbuffer)
        attr.setByteStride(row_width)
        attr.setByteOffset(asp.column * basetype_width)
        attr.setCount(rows)
        attrs.append(attr)
    return attrs


def buildIndexAttr(parent, array):

    basetype = basetype_numpy_codes_reverse[array.dtype.type]
    basetype_width = basetype_widths[ basetype ]

    basetype_width = array.itemsize
    rawstring = array.tobytes()
    byte_array = QByteArray(rawstring)
    qbuffer = Qt3DRender.QBuffer(parent)
    qbuffer.setData(byte_array)

    attr = Qt3DRender.QAttribute(parent)
    attr.setVertexBaseType(basetype)
    attr.setAttributeType(Qt3DRender.QAttribute.IndexAttribute)
    attr.setBuffer(qbuffer)
    attr.setCount(array.size)

    return attr


def iterAttr( att ):
    '''Iterator over a Qt3DRender.QAttribute'''
    basetype = att.vertexBaseType()
    width = basetype_widths[ basetype ]
    struct_code = basetype_struct_codes[ basetype ]
    att_data = att.buffer().data().data()
    byteOffset = att.byteOffset()
    byteStride = att.byteStride()
    count = att.count()
    vertex_size = att.vertexSize()
    #print( width, struct_code, byteOffset, byteStride, vertex_size, count )
    # Support index attributes, which report zero stride and size
    if byteStride == 0:
        byteStride = width
    if vertex_size == 0:
        vertex_size = 1
    for i in range (byteOffset, byteOffset + byteStride * count, byteStride ):
        datum = struct.unpack( struct_code*vertex_size, bytes(att_data[i:i+(width*vertex_size)]) )
        yield datum

def grouper(i, n):
    '''from the itertools recipe list: yield n-sized lists of items from iterator i'''
    args = [iter(i)]*n
    return itertools.zip_longest(*args)
    #return iter( lambda: list(itertools.islice(iter(i), n)), [])

def getQAttribute( geom, att_type=Qt3DRender.QAttribute.VertexAttribute, att_name=None ):
    for att in geom.attributes():
        if att.attributeType() == att_type and (att_name is None or att.name() == att_name):
            return att
    return None

def dumpGeometry( geom, dumpf=print ):
    if geom is None:
        dumpf( "No geometry" )
        return
    atts = geom.attributes()
    for att in atts:
        att_type = att.attributeType()
        basetype = att.vertexBaseType()
        dumpf('{type} "{name}" '.format( type=str(att_type).split('AttributeType.')[-1], name=att.name()), end='' )
        dumpf( 'with base type {basetype}'.format(basetype = str(basetype).split('BaseType.')[-1]) )
        width = basetype_widths[ basetype ]
        code = basetype_struct_codes[ basetype ]

        if( att_type == Qt3DRender.QAttribute.AttributeType.VertexAttribute ):
            for vtx in iterAttr( att ):
                dumpf(vtx)
        elif att_type == Qt3DRender.QAttribute.AttributeType.IndexAttribute :
            count = att.count()
            num_tris = int(count / 3)
            dumpf( num_tris, "triangles" )
            for tri in grouper(iterAttr(att), 3):
                dumpf(tri)
class AABB:
    '''
    An axis-aligned bounding box around the given geometry
    '''
    def __init__(self, geom):
        if hasattr(geom, 'allVertices'):
            # Something lke bildparser.OutputDecorations
            it = geom.allVertices()
        else:
            # assume it's a qt3d geometry
            vertices = getQAttribute( geom, att_name = Qt3DRender.QAttribute.defaultPositionAttributeName() )
            it = iterAttr(vertices)
        v0 = next(it)
        self.min = vec3d( v0[0], v0[1], v0[2])
        self.max = vec3d( self.min  )
        for v in it:
            self.min.setX( min( self.min.x(), v[0] ) )
            self.min.setY( min( self.min.y(), v[1] ) )
            self.min.setZ( min( self.min.z(), v[2] ) )
            self.max.setX( max( self.max.x(), v[0] ) )
            self.max.setY( max( self.max.y(), v[1] ) )
            self.max.setZ( max( self.max.z(), v[2] ) )
        self.center = (self.min+self.max) / 2.0

    def iterCorners(self, cons = vec3d):
        '''
        Iterator over the eight corners of the AABB.
        '''
        for x in [self.min.x(), self.max.x()]:
            for y in [self.min.y(), self.max.y()]:
                for z in [self.min.z(), self.max.z()]:
                    yield cons(x, y, z)

    def dimensions(self):
        v = self.max - self.min
        return v.x(), v.y(), v.z()

def transformBetween( aabb1, aabb2 ):
    '''
    Return a function mapping corners of aabb1 onto those of aabb2

    If the boxes are flat (all zero z-values), the transformation will be modified
    so that Z coordinates scale uniformly with the X and Y coordinates.  This ensures
    the returned transformation doesn't pancake all 3D inputs.
    '''

    def np_coords_from_aabb(aabb):
        return np.array( list ( aabb.iterCorners(cons=lambda *x:np.array([*x]) ) ) )

    coord_from = np_coords_from_aabb( aabb1 )
    coord_to = np_coords_from_aabb( aabb2 )

    def all_zero(x): return all([x==0 for x in x])
    if all_zero(coord_to[:,2]) and all_zero(coord_from[:,2]):
        # Both boxes are flat in Z, so ensure Z direction scales uniformly with x and y in the returned transformation
        span_from = aabb1.dimensions()[0:2]
        span_to = aabb2.dimensions()[0:2]
        ratio_x = span_to[0] / span_from[0]
        ratio_y = span_to[1] / span_from[1]
        ratio = (ratio_x + ratio_y) / 2
        min_rows = (0,2,4,6)
        max_rows = (1,3,5,7)
        coord_from[min_rows,2] = -1
        coord_from[max_rows,2] = 1
        coord_to[min_rows,2] = -ratio
        coord_to[max_rows,2] = ratio

    # https://stackoverflow.com/questions/20546182/how-to-perform-coordinates-affine-transformation-using-python-part-2

    n = coord_from.shape[0]
    pad = lambda x: np.hstack([x, np.ones((x.shape[0],1))])
    unpad = lambda x: x[:,:-1]

    X = pad(coord_from)
    Y = pad(coord_to)

    A, res, rank, s = np.linalg.lstsq(X, Y, rcond=None)

    transform = lambda x: unpad(np.dot(pad(x), A))

    return transform




