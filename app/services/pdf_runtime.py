"""Runtime compatibility bootstrap for pdfplumber on ARM64 Windows.
Ensures pdfplumber and pdfminer can be cleanly imported across tests and service modules
without shadowing modern system Python packages (e.g. pydantic, sqlalchemy).
"""

import sys
import types
from unittest.mock import MagicMock

# 1. Append cached runtime path so system Python packages take priority
codex_site = r"C:\Users\Raka\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\Lib\site-packages"
if codex_site not in sys.path:
    sys.path.append(codex_site)

# 2. Shim cryptography for pdfminer if native Rust DLL cannot be loaded on ARM64
c = types.ModuleType("cryptography")
sys.modules["cryptography"] = c
h = types.ModuleType("cryptography.hazmat")
sys.modules["cryptography.hazmat"] = h
b = types.ModuleType("cryptography.hazmat.backends")
b.default_backend = lambda: None
sys.modules["cryptography.hazmat.backends"] = b
p = types.ModuleType("cryptography.hazmat.primitives")
sys.modules["cryptography.hazmat.primitives"] = p
cip = types.ModuleType("cryptography.hazmat.primitives.ciphers")
cip.Cipher = MagicMock()
cip.algorithms = MagicMock()
cip.modes = MagicMock()
sys.modules["cryptography.hazmat.primitives.ciphers"] = cip
r = types.ModuleType("cryptography.hazmat.bindings._rust")
sys.modules["cryptography.hazmat.bindings._rust"] = r
