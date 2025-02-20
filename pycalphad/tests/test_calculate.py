"""
The calculate test module verifies that calculate() calculates
Model quantities correctly.
"""

import nose.tools
from pycalphad import Database, calculate
try:
    # Python 2
    from StringIO import StringIO
except ImportError:
    # Python 3
    from io import StringIO

from pycalphad.tests.datasets import ALCRNI_TDB as TDB_TEST_STRING


DBF = Database(TDB_TEST_STRING)

def test_surface():
    "Bare minimum: calculation produces a result."
    calculate(DBF, ['AL', 'CR', 'NI'], 'L12_FCC',
                T=1273., mode='numpy')

@nose.tools.raises(AttributeError)
def test_unknown_model_attribute():
    "Sampling an unknown model attribute raises exception."
    calculate(DBF, ['AL', 'CR', 'NI'], 'L12_FCC',
                T=1400.0, output='_fail_')

def test_statevar_upcast():
    "Integer state variable values are cast to float."
    calculate(DBF, ['AL', 'CR', 'NI'], 'L12_FCC',
                T=1273, mode='numpy')
