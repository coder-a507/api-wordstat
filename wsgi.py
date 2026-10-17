import ctypes
import glob
import os
import sys
import traceback

# The hosting runs NixOS: there is no system-wide libstdc++, but spaCy's
# compiled dependencies (srsly, thinc, blis, ...) need it. Find a gcc lib dir
# in /nix/store and preload its libraries globally so those extensions can
# resolve them. Prefer gcc 8.3.0, the toolchain the hosting's Python is built
# with, so the library matches the glibc already loaded into the process.
_libstdcxx_log = []


def _gcc_lib_dirs():
    dirs = sorted(glob.glob("/nix/store/*-gcc-*-lib/lib"))
    preferred = [d for d in dirs if "-gcc-8.3.0-lib/" in d + "/"]
    return preferred + [d for d in dirs if d not in preferred]


def _preload_libstdcxx():
    for d in _gcc_lib_dirs():
        if not os.path.exists(os.path.join(d, "libstdc++.so.6")):
            continue
        try:
            for lib in ("libgcc_s.so.1", "libstdc++.so.6"):
                p = os.path.join(d, lib)
                if os.path.exists(p):
                    ctypes.CDLL(p, mode=ctypes.RTLD_GLOBAL)
            _libstdcxx_log.append("loaded: " + d)
            return
        except OSError as e:
            _libstdcxx_log.append("failed: " + d + ": " + str(e))
    _libstdcxx_log.append("no usable libstdc++.so.6 found in /nix/store")


try:
    _preload_libstdcxx()

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
        "libstdc++:",
    ] + ["  " + line for line in _libstdcxx_log] + [
        "gcc lib dirs:",
    ] + ["  " + d for d in _gcc_lib_dirs()] + [
        "sys.path:",
    ] + ["  " + p for p in sys.path])

    def application(environ, start_response):
        start_response("500 Internal Server Error",
                       [("Content-Type", "text/plain; charset=utf-8")])
        return [_error.encode("utf-8")]

# Majordomo's uWSGI looks for `app` (wsgi:app, as in its Flask example);
# plain uWSGI looks for `application`. Expose the WSGI callable under both.
app = application
