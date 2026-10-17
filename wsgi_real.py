import ctypes
import os

_LIBDIRS = [
    "/nix/store/d97kkhkxwj9lxjl4ba81jlzplyzlzjb8-gcc-8.3.0-lib/lib",
]

for _d in _LIBDIRS:
    if os.path.exists(os.path.join(_d, "libstdc++.so.6")):
        for _lib in ("libgcc_s.so.1", "libstdc++.so.6"):
            _p = os.path.join(_d, _lib)
            if os.path.exists(_p):
                ctypes.CDLL(_p, mode=ctypes.RTLD_GLOBAL)
        break

from a2wsgi import ASGIMiddleware
from app.main import app as asgi_app

application = ASGIMiddleware(asgi_app)