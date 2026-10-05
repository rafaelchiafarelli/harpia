"""pytest configuration for the generated suite: import the project from
this checkout (``harpia_generated`` / ``harpia_runtime`` next to ``tests/``)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
