"""Root conftest — ensures src/ is on sys.path for all test runs.

This makes `from agents.xbuddy.xxx import ...` work regardless of
whether the package is installed or which pytest version is in use.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
