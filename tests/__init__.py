''' TGAP test suite. Run from the tgap root folder:

    python -m unittest discover -s tests -v

The sys.path shim below makes `core` importable regardless of how the
test runner sets the working directory. '''

import os
import sys

_TGAP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TGAP_ROOT not in sys.path:
    sys.path.insert(0, _TGAP_ROOT)
