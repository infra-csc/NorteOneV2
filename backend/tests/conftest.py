import os
import sys

# Ensure the backend root (which contains the `app` package) is importable
# regardless of the directory pytest is invoked from.
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)
