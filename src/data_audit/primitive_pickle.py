"""仅允许NumPy数字标量的受控pickle解码；不暴露真实NumPy构造器。"""
import copyreg
import io
import pickle
import re
import struct

_FORMATS={'f2':'e','f4':'f','f8':'d','i1':'b','i2':'h','i4':'i','i8':'q',
          'u1':'B','u2':'H','u4':'I','u8':'Q','b1':'?'}
class _DTypeToken:
    __slots__=('code','byteorder')
    def __init__(self,spec):
        if not isinstance(spec,str):raise pickle.UnpicklingError('dtype spec must be string')
        match=re.fullmatch(r'([<>=|]?)([fiu][1248]|b1)',spec)
        if not match or match.group(2) not in _FORMATS:
            raise pickle.UnpicklingError('Only fixed-width numeric/bool dtype codes allowed')
        self.byteorder=match.group(1) or '=';self.code=match.group(2)
        if self.byteorder=='|' and self.code not in {'i1','u1','b1'}:
            raise pickle.UnpicklingError('Non-byte numeric dtype cannot be endianless')
    def __setstate__(self,state):
        # NumPy原生标量dtype state只允许无fields/subarray/object的基本形式。
        if not isinstance(state,tuple) or len(state)!=8 or state[0]!=3:
            raise pickle.UnpicklingError('Unsupported numeric dtype state')
        _,order,subarray,names,fields,element_size,alignment,flags=state
        if order not in {'<','>','=','|'} or any(x is not None for x in (subarray,names,fields)):
            raise pickle.UnpicklingError('Object/structured/subarray dtype state prohibited')
        if (element_size,alignment,flags)!=(-1,-1,0):
            raise pickle.UnpicklingError('Unsupported numeric dtype state flags')
        if order=='|' and self.code not in {'i1','u1','b1'}:
            raise pickle.UnpicklingError('Invalid endianless numeric dtype')
        self.byteorder=order

def _safe_dtype(spec,align=False,copy=True):
    if not isinstance(align,bool) or not isinstance(copy,bool):
        raise pickle.UnpicklingError('Invalid dtype constructor arguments')
    return _DTypeToken(spec)

def _safe_scalar(dtype,raw):
    if type(dtype) is not _DTypeToken or type(raw) not in (bytes,bytearray):
        raise pickle.UnpicklingError('Scalar needs controlled dtype token and raw bytes')
    order='=' if dtype.byteorder=='|' else dtype.byteorder
    fmt=order+_FORMATS[dtype.code]
    if len(raw)!=struct.calcsize(fmt) or len(raw)>8:
        raise pickle.UnpicklingError('Numeric scalar byte length mismatch')
    # struct返回Python bool/int/float，不调用pickle提供的函数，也不解引用对象指针。
    return struct.unpack(fmt,raw)[0]

class NumericScalarUnpickler(pickle.Unpickler):
    def __init__(self,file):
        super().__init__(file);self.allowed_global_uses={}
    def find_class(self,module,name):
        key=module+'.'+name
        if (module,name)==('numpy','dtype'):
            self.allowed_global_uses[key]=self.allowed_global_uses.get(key,0)+1
            return _safe_dtype
        if module in {'numpy.core.multiarray','numpy._core.multiarray'} and name=='scalar':
            self.allowed_global_uses[key]=self.allowed_global_uses.get(key,0)+1
            return _safe_scalar
        raise pickle.UnpicklingError('All other globals/classes prohibited: '+key)
    def persistent_load(self,pid):
        raise pickle.UnpicklingError('All persistent IDs prohibited')

def load_numeric_scalars(raw):
    # 每次清除进程内EXT缓存，使扩展引用不能绕过find_class。
    copyreg._extension_cache.clear()
    stream=io.BytesIO(raw);reader=NumericScalarUnpickler(stream)
    obj=reader.load()
    if stream.read(1):raise pickle.UnpicklingError('Trailing bytes after pickle STOP')
    return obj,{'mode':'fixed_numeric_scalar_to_Python_primitive',
                'allowed_global_uses':dict(reader.allowed_global_uses),
                'all_other_globals_denied':True,'persistent_ids_denied':True,
                'original_numpy_scalar_dtype_not_preserved':True}
