import ctypes
import os
import sys
import traceback

_LIBDIRS = [
    "/nix/store/d97kkhkxwj9lxjl4ba81jlzplyzlzjb8-gcc-8.3.0-lib/lib",
]

try:
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
except Exception:
    # DEBUG: show why the app failed to load instead of a bare 500.
    # Remove this branch once the hosting setup works.
    _error = "\n".join([
        traceback.format_exc(),
        "python: " + sys.version,
        "executable: " + sys.executable,
        "cwd: " + os.getcwd(),
        "file: " + os.path.abspath(__file__),
        "sys.path:",
    ] + ["  " + p for p in sys.path])

    def application(environ, start_response):
        start_response("500 Internal Server Error",
                       [("Content-Type", "text/plain; charset=utf-8")])
        return [_error.encode("utf-8")]

# Majordomo's uWSGI looks for `app` (wsgi:app, as in its Flask example);
# plain uWSGI looks for `application`. Expose the WSGI callable under both.
app = application
