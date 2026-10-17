import ctypes
import glob
import os
import sys
import threading
import traceback

# The hosting runs NixOS: there is no system-wide libstdc++, but spaCy's
# compiled dependencies (srsly, thinc, blis, ...) need it. Find a gcc lib dir
# in /nix/store and preload its libraries globally so those extensions can
# resolve them. Prefer gcc 8.3.0, the toolchain the hosting's Python is built
# with, so the library matches the glibc already loaded into the process.
# Elsewhere (Windows, regular Linux) the glob finds nothing and this is a no-op.


def _gcc_lib_dirs():
    dirs = sorted(glob.glob("/nix/store/*-gcc-*-lib/lib"))
    preferred = [d for d in dirs if d.endswith("-gcc-8.3.0-lib/lib")]
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
            return
        except OSError:
            continue


# The app (and with it spaCy and its model) is loaded on the first request,
# not at import: loading it while uWSGI starts the worker made the hosting
# answer 502. A failed load is retried on the next request.
_app = None
_app_lock = threading.Lock()


def _load_app():
    global _app
    with _app_lock:
        if _app is None:
            _preload_libstdcxx()
            from a2wsgi import ASGIMiddleware
            from app.main import app as asgi_app
            _app = ASGIMiddleware(asgi_app)
    return _app


def application(environ, start_response):
    try:
        real_app = _load_app()
    except Exception:
        traceback.print_exc(file=sys.stderr)
        start_response("500 Internal Server Error",
                       [("Content-Type", "text/plain; charset=utf-8")])
        return [b"Internal Server Error: the application failed to load"]
    return real_app(environ, start_response)


# Majordomo's uWSGI looks for `app` (wsgi:app, as in its Flask example);
# plain uWSGI looks for `application`. Expose the WSGI callable under both.
app = application
