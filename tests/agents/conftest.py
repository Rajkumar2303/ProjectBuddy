import sys
from pathlib import Path

# Ensure src/ is on sys.path regardless of how pytest is invoked or which
# Python environment is active. This file is co-located with the tests so
# pytest always loads it before collecting this directory.
_src = Path(__file__).parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))
