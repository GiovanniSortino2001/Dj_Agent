import tempfile
import unittest
from pathlib import Path
import numpy as np
from dj.ml import dataset,load_dataset


class DatasetTests(unittest.TestCase):
    def test_dataset_reproducible_disjoint_split(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/'a.npz'; b=Path(d)/'b.npz'
            dataset(a,n=10,seed=1); dataset(b,n=10,seed=1)
            x=load_dataset(a); y=load_dataset(b)
            self.assertEqual(x['x_train'].shape,(8,32,5))
            self.assertEqual(x['x_val'].shape,(2,32,5))
            np.testing.assert_equal(x['x_train'],y['x_train'])
            self.assertFalse(np.array_equal(x['x_train'][0],x['x_val'][0]))
    def test_invalid_size(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): dataset(Path(d)/'x.npz',n=0)
    def test_reject_corrupt_dataset(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.npz'; dataset(p,n=10)
            arrays=load_dataset(p); arrays['x_val'][0,0,0]=np.nan
            np.savez(p,**arrays)
            with self.assertRaises(ValueError): load_dataset(p)
    def test_shape_and_target_range(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.npz'; dataset(p,n=10)
            arrays=load_dataset(p); arrays['y_train'][0,0,0]=2
            np.savez(p,**arrays)
            with self.assertRaises(ValueError): load_dataset(p)

if __name__=='__main__': unittest.main()
