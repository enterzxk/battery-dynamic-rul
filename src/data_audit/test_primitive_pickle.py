import pickle
import unittest
import numpy as np
from primitive_pickle import load_numeric_scalars, _safe_dtype

class NumericScalarSafetyTests(unittest.TestCase):
    def test_numeric_scalars_and_plain_tree(self):
        tree={'float64':np.float64(1.25),'float32':np.float32(2.5),'integer':np.int64(7),'boolean':np.bool_(True),'plain':[1,None,'x']}
        obj,receipt=load_numeric_scalars(pickle.dumps(tree,protocol=4))
        self.assertEqual(obj,{'float64':1.25,'float32':2.5,'integer':7,'boolean':True,'plain':[1,None,'x']})
        self.assertIs(type(obj['float64']),float)
        self.assertTrue(receipt['all_other_globals_denied'])
    def test_other_globals_arrays_and_object_dtypes_are_denied(self):
        for obj in [complex(1,2),np.asarray([1,2,3])]:
            with self.assertRaises(pickle.UnpicklingError):load_numeric_scalars(pickle.dumps(obj,protocol=4))
        for spec in ['O8','V8','U8','f16']:
            with self.assertRaises(pickle.UnpicklingError):_safe_dtype(spec)
    def test_trailing_payload_rejected(self):
        with self.assertRaises(pickle.UnpicklingError):load_numeric_scalars(pickle.dumps([1],protocol=4)+b'x')
if __name__=='__main__':unittest.main()
