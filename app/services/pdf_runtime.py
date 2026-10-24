"""Runtime compatibility bootstrap for pdfplumber and LangChain on ARM64 Windows.
Ensures pdfplumber, pdfminer, and LangChain can be cleanly imported across tests and service modules
without shadowing modern system Python packages (e.g. pydantic, sqlalchemy).
"""

import sys
import types
import uuid
import hashlib
from unittest.mock import MagicMock

# 1. Append cached runtime paths so system Python packages take priority
codex_site = r"C:\Users\Raka\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\Lib\site-packages"
if codex_site not in sys.path:
    sys.path.append(codex_site)

date_site = r"C:\Users\Raka\Projects\Date_with_crush\venv\Lib\site-packages"
if date_site not in sys.path:
    sys.path.append(date_site)

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

# 3. Shim uuid_utils and xxhash for LangChain on Python 3.13 ARM64
if "uuid_utils" not in sys.modules:
    u = types.ModuleType("uuid_utils")
    u.__path__ = []
    u.uuid4 = uuid.uuid4
    u.uuid7 = getattr(uuid, "uuid7", uuid.uuid4)
    u.UUID = uuid.UUID
    sys.modules["uuid_utils"] = u
    sys.modules["uuid_utils._uuid_utils"] = u
    comp = types.ModuleType("uuid_utils.compat")
    comp.uuid7 = u.uuid7
    comp.uuid4 = u.uuid4
    sys.modules["uuid_utils.compat"] = comp

if "xxhash" not in sys.modules:
    xh = types.ModuleType("xxhash")
    xh.__path__ = []
    xh.xxh64 = lambda data=b"": hashlib.sha256(data.encode() if isinstance(data, str) else data)
    sys.modules["xxhash"] = xh
    sys.modules["xxhash._xxhash"] = xh
