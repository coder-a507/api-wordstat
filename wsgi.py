import ctypes
import glob
import os
import sys
import threading
import time
import traceback

# The hosting runs NixOS: there is no system-wide libstdc++, but spaCy's
# compiled dependencies (srsly, thinc, blis, ...) need it. Find a gcc lib dir
# in /nix/store and preload its libraries globally so those extensions can
# resolve them. Prefer gcc 8.3.0, the toolchain the hosting's Python is built
# with, so the library matches the glibc already loaded into the process.
_libstdcxx_log = []
_libstdcxx_done = False


def _gcc_lib_dirs():
    t = time.time()
    dirs = sorted(glob.glob("/nix/store/*-gcc-*-lib/lib"))
    _libstdcxx_log.append("glob /nix/store: %d dirs in %.1fs" % (len(dirs), time.time() - t))
    preferred = [d for d in dirs if "-gcc-8.3.0-lib/" in d + "/"]
    return preferred + [d for d in dirs if d not in preferred]


def _preload_libstdcxx():
    global _libstdcxx_done
    if _libstdcxx_done:
        return
    _libstdcxx_done = True
    dirs = _gcc_lib_dirs()
    for d in dirs:
        _libstdcxx_log.append("candidate: " + d)
    for d in dirs:
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


# DEBUG: everything below the real app is temporary diagnostics for the
# hosting. The app itself is loaded lazily on the first request, so a crash
# while loading spaCy kills only that request and /_diag/... can still be
# used to find which step fails. Remove once the hosting setup works.

def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception as e:
        return "<%s>" % e


def _mem_info():
    import resource
    lines = ["maxrss: %d MB" % (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024)]
    for name in ("RLIMIT_AS", "RLIMIT_DATA", "RLIMIT_RSS"):
        soft, hard = resource.getrlimit(getattr(resource, name))
        lines.append("%s: soft=%s hard=%s" % (name, soft, hard))
    for line in _read("/proc/self/status").splitlines():
        if line.startswith(("VmRSS", "VmPeak", "VmSize")):
            lines.append(line)
    for line in _read("/proc/meminfo").splitlines()[:3]:
        lines.append(line)
    lines.append("cgroup v1 limit: " + _read("/sys/fs/cgroup/memory/memory.limit_in_bytes"))
    lines.append("cgroup v2 limit: " + _read("/sys/fs/cgroup/memory.max"))
    lines.append("cgroup: " + _read("/proc/self/cgroup").replace("\n", " | "))
    return lines


def _diag(step):
    out = [
        "step: " + step,
        "python: " + sys.version.replace("\n", " "),
        "executable: " + sys.executable,
        "cwd: " + os.getcwd(),
        "pid: %d" % os.getpid(),
    ]
    t = time.time()
    try:
        if step in ("libs", "spacy", "model", "app"):
            _preload_libstdcxx()
        if step in ("spacy", "model"):
            import spacy
            out.append("spacy " + spacy.__version__ + " imported")
        if step == "model":
            import spacy
            spacy.load("en_core_web_sm")
            out.append("en_core_web_sm loaded")
        if step == "app":
            _load_app()
            out.append("app loaded")
    except Exception:
        out.append(traceback.format_exc())
    out.append("elapsed: %.1fs" % (time.time() - t))
    out.append("libstdc++:")
    out += ["  " + line for line in _libstdcxx_log]
    out.append("memory:")
    try:
        out += ["  " + line for line in _mem_info()]
    except Exception as e:
        out.append("  <%s>" % e)
    out.append("sys.path:")
    out += ["  " + p for p in sys.path]
    return "\n".join(out)


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


def _text(start_response, status, body):
    start_response(status, [("Content-Type", "text/plain; charset=utf-8")])
    return [body.encode("utf-8")]


def application(environ, start_response):
    path = environ.get("PATH_INFO", "")
    if path.startswith("/_diag"):
        step = path[len("/_diag"):].strip("/") or "info"
        return _text(start_response, "200 OK", _diag(step))
    try:
        real_app = _load_app()
    except Exception:
        return _text(start_response, "500 Internal Server Error",
                     traceback.format_exc() + "\n" + _diag("info"))
    return real_app(environ, start_response)


# Majordomo's uWSGI looks for `app` (wsgi:app, as in its Flask example);
# plain uWSGI looks for `application`. Expose the WSGI callable under both.
app = application
