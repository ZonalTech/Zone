"""zonal — a lightweight, "bench"-style development framework for ZT POS.

`zonal` is a small CLI you install **once** on your machine. You then use it to
create and drive any number of independent ZT POS "zones" (one cloned project
each, like a bench), from setup through serving, migrating, building and
releasing — instead of remembering a dozen separate scripts and .bat files.

Typical flow (Windows):
    zonal get https://github.com/<org>/zt-pos.git   :: clone a new zone
    cd zt-pos
    zonal setup --seed                               :: make .venv, deps, DB, samples
    zonal start                                      :: dev server + live logs + browser

How it locates a zone:
    Every command (except `get`/`version`/`help`) operates on the zone that
    contains the current directory — zonal walks up from the CWD looking for a
    ZT POS project (an `app.py` + `config.py` pair), exactly like `bench` finds
    its bench root. Commands that run POS code re-exec themselves inside that
    zone's `.venv`, so each zone stays isolated.

Run `zonal help` (or `zonal <command> -h`) for the full command list.
"""
import argparse
import os
import shutil
import subprocess
import sys

# Status lines use ✓/✗ — force UTF-8 so they don't crash a legacy cp1252 console.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ZONAL_VERSION = "0.3.0"

# A zone is a workspace (created by `zonal init`) holding a shared .venv and an
# apps/ folder; apps are cloned into apps/<name> by `zonal get`. The globals
# below are bound in main(): ZONE = the zone root, ROOT = the active app dir.
ZONE = None         # zone root (holds .venv, .zonal/, apps/)
ROOT = None         # active app directory  (apps/<name>) — what commands act on
STATE_DIR = None    # <zone>/.zonal
PID_FILE = None     # <zone>/.zonal/serve-<app>.pid

ZONE_MARKER = os.path.join(".zonal", "zone.json")


# --------------------------------------------------------------------------- #
# Zone & app discovery + the zone's shared virtualenv
# --------------------------------------------------------------------------- #
def is_app(path):
    """A directory is an app if it holds both app.py and config.py."""
    return (os.path.isfile(os.path.join(path, "app.py"))
            and os.path.isfile(os.path.join(path, "config.py")))


def is_zone_root(path):
    """A directory is a zone root if it carries the .zonal/zone.json marker."""
    return os.path.isfile(os.path.join(path, ZONE_MARKER))


def find_zone(start=None):
    """Walk up from `start` (default: CWD) to the enclosing zone root, or None."""
    d = os.path.abspath(start or os.getcwd())
    while True:
        if is_zone_root(d):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def apps_dir(zone):
    return os.path.join(zone, "apps")


def zone_apps(zone):
    """Names of the apps installed in a zone (dirs under apps/ that look like apps)."""
    ad = apps_dir(zone)
    if not os.path.isdir(ad):
        return []
    return sorted(n for n in os.listdir(ad) if is_app(os.path.join(ad, n)))


def resolve_app(zone, explicit=None, start=None):
    """Pick which app a command targets: --app, else the CWD's app, else the only one."""
    ad = apps_dir(zone)
    if explicit:
        p = os.path.join(ad, explicit)
        if is_app(p):
            return p
        die(f"No app named '{explicit}' in this zone. Installed: "
            f"{', '.join(zone_apps(zone)) or '(none)'}")
    cwd = os.path.abspath(start or os.getcwd())
    for name in zone_apps(zone):
        ap = os.path.join(ad, name)
        if cwd == ap or cwd.startswith(ap + os.sep):
            return ap
    apps = zone_apps(zone)
    if len(apps) == 1:
        return os.path.join(ad, apps[0])
    if not apps:
        die("This zone has no apps yet — add one with:  zonal get <repo-url>")
    die("This zone has several apps — name one:\n  "
        + ", ".join(apps) + f"\n  e.g.  zonal start {apps[0]}   "
        f"(or add  --app {apps[0]}  to other commands)")


def _set_zone(zone):
    global ZONE, STATE_DIR
    ZONE = zone
    STATE_DIR = os.path.join(zone, ".zonal")


def _set_app(app_dir):
    """Bind the active app and its per-app server pidfile (kept under the zone)."""
    global ROOT, PID_FILE
    ROOT = app_dir
    PID_FILE = os.path.join(STATE_DIR, f"serve-{os.path.basename(app_dir)}.pid")


def venv_dir(zone):
    return os.path.join(zone, ".venv")


def venv_python(zone):
    """Path to the zone's shared venv interpreter (created by `zonal init`)."""
    if os.name == "nt":
        return os.path.join(zone, ".venv", "Scripts", "python.exe")
    return os.path.join(zone, ".venv", "bin", "python")


def has_venv(zone):
    return bool(zone) and os.path.isfile(venv_python(zone))


def in_zone_venv(zone):
    """True if we're already running under the zone's venv interpreter."""
    try:
        return (os.path.normcase(os.path.abspath(sys.executable))
                == os.path.normcase(os.path.abspath(venv_python(zone))))
    except Exception:
        return False


def reexec_in_venv(zone, app_dir, argv):
    """Re-run `zonal <argv>` under the zone's venv, anchored in the app dir.

    App code (app, config, models, …) is installed in the zone's shared venv,
    not in whatever interpreter launched zonal, so any command that imports it
    bounces through here first. cwd=app_dir means the child re-resolves the same
    app from its location; ZONAL_IN_VENV stops it from bouncing again.
    """
    py = venv_python(zone)
    if not os.path.isfile(py):
        die("This zone has no virtual environment yet — run `zonal init` (or `zonal setup`).")
    env = dict(os.environ, ZONAL_IN_VENV="1")
    return subprocess.call([py, os.path.abspath(__file__), *argv], cwd=app_dir, env=env)


# --------------------------------------------------------------------------- #
# Small output helpers
# --------------------------------------------------------------------------- #
def ok(msg):    print(f"✓ {msg}")
def warn(msg):  print(f"! {msg}")
def fail(msg):  sys.stdout.flush(); print(f"✗ {msg}", file=sys.stderr)
def head(msg):  print(f"\n\033[1m{msg}\033[0m" if sys.stdout.isatty() else f"\n{msg}")


def die(msg, code=1):
    fail(msg)
    raise SystemExit(code)


def confirm(prompt):
    """Ask a yes/no question. Honoured only on a TTY; otherwise require --yes."""
    try:
        return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def run_bat(name, *args):
    """Run a project .bat (Windows-only build/release helpers)."""
    path = os.path.join(ROOT, name)
    if not os.path.isfile(path):
        die(f"{name} not found in {ROOT}")
    if os.name != "nt":
        die(f"{name} is a Windows batch file; run this command on Windows.")
    return subprocess.call(["cmd", "/c", path, *args], cwd=ROOT)


def _write_pidfile(pid, argv):
    """Record the running dev server so `zonal restart`/`refresh` can find it."""
    import json
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(PID_FILE, "w", encoding="utf-8") as fh:
        json.dump({"pid": pid, "argv": argv}, fh)


def _read_pidfile():
    import json
    try:
        with open(PID_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _pid_alive(pid):
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                             capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def terminate_pid(pid):
    """Kill a process (and its children) cross-platform."""
    if os.name == "nt":
        return subprocess.call(["taskkill", "/PID", str(pid), "/F", "/T"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    import signal
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except OSError:
        return False


def _relaunch_serve(argv):
    """Start `zonal serve/start …` again, detached, in its own console/session.

    Called from inside the zone's venv (restart/refresh both run there), so
    sys.executable is already the venv Python; ZONAL_IN_VENV keeps it that way.
    """
    cmd = [sys.executable, os.path.abspath(__file__)] + argv
    env = dict(os.environ, ZONAL_IN_VENV="1")
    if os.name == "nt":
        CREATE_NEW_CONSOLE = 0x00000010
        subprocess.Popen(cmd, cwd=ROOT, creationflags=CREATE_NEW_CONSOLE, env=env)
    else:
        subprocess.Popen(cmd, cwd=ROOT, start_new_session=True, env=env)


def _stop_running_server():
    """Stop the dev server recorded in the pidfile. Returns its serve argv or None."""
    info = _read_pidfile()
    if not info:
        return None
    pid, argv = info.get("pid"), info.get("argv", ["serve"])
    if pid and _pid_alive(pid):
        terminate_pid(pid)
        ok(f"Stopped dev server (pid {pid}).")
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    return argv


def touch_static():
    """Bump the mtime of CSS/JS so the browser/WebView revalidates cached assets."""
    import glob
    n = 0
    for pat in ("static/css/*.css", "static/js/*.js"):
        for f in glob.glob(os.path.join(ROOT, pat)):
            os.utime(f, None)
            n += 1
    ok(f"Refreshed {n} static asset(s) (cache-bust).")


def find_mariadb_tool(*names):
    """Locate a MariaDB client binary (mysqldump/mysql or the mariadb-* names).

    Searches PATH first, then the usual `C:\\Program Files\\MariaDB *\\bin`.
    """
    for n in names:
        found = shutil.which(n)
        if found:
            return found
    if os.name == "nt":
        import glob
        for base in (r"C:\Program Files\MariaDB *\bin", r"C:\Program Files (x86)\MariaDB *\bin"):
            for d in sorted(glob.glob(base), reverse=True):
                for n in names:
                    cand = os.path.join(d, n if n.endswith(".exe") else n + ".exe")
                    if os.path.isfile(cand):
                        return cand
    return None


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_version(args):
    print(f"zonal CLI   v{ZONAL_VERSION}")
    print(f"Python      {sys.version.split()[0]}")
    zone = find_zone()
    if not zone:
        print("zone        (none here — create one with `zonal init <name>`)")
        return
    print(f"zone        {zone}")
    apps = zone_apps(zone)
    if not apps:
        print("apps        (none yet — add one with `zonal get <repo-url>`)")
        return
    for name in apps:
        vf = os.path.join(apps_dir(zone), name, "VERSION")
        ver = open(vf, encoding="utf-8").read().strip() if os.path.isfile(vf) else "?"
        print(f"app         {name}  v{ver}")


def _base_python():
    """The interpreter used to *build* a zone's venv (zonal's own Python)."""
    return sys.executable


def cmd_init(args):
    """Create a new zone: a workspace with its own shared .venv and apps/ folder."""
    zone = os.path.abspath(args.name or ".")
    name = os.path.basename(zone) or zone
    os.makedirs(zone, exist_ok=True)
    if os.listdir(zone) and not is_zone_root(zone):
        warn(f"'{zone}' is not empty; initializing a zone in it anyway.")
    head(f"Initializing zone '{name}'")
    os.makedirs(apps_dir(zone), exist_ok=True)
    os.makedirs(os.path.join(zone, ".zonal"), exist_ok=True)
    if not is_zone_root(zone):
        import json
        with open(os.path.join(zone, ZONE_MARKER), "w", encoding="utf-8") as fh:
            json.dump({"zone": name, "zonal": ZONAL_VERSION}, fh, indent=2)
    # Build the zone's shared virtualenv (apps install their deps into it).
    py = venv_python(zone)
    if os.path.isfile(py):
        ok(".venv already present.")
    else:
        head("Creating the zone virtual environment (.venv)")
        if subprocess.call([_base_python(), "-m", "venv", venv_dir(zone)]) != 0 \
                or not os.path.isfile(py):
            die("Could not create .venv (is the base Python's venv module available?).")
        subprocess.call([py, "-m", "pip", "install", "-q", "--upgrade", "pip"])
        ok("Created .venv")
    ok(f"Zone ready at {zone}")
    cd = "" if zone == os.path.abspath(os.getcwd()) else f"  cd {args.name}\n"
    print(f"\nNext:\n{cd}  zonal get <repo-url>   :: clone an app (e.g. ZT POS) into the zone")


def cmd_get(args):
    """Clone an app repository from GitHub into this zone's apps/ folder."""
    git = shutil.which("git")
    if not git:
        die("git was not found on PATH. Install Git for Windows and retry.")
    repo = args.repo
    name = args.name or os.path.splitext(os.path.basename(repo.rstrip("/")))[0]
    dest = os.path.join(apps_dir(ZONE), name)
    if os.path.exists(dest) and os.listdir(dest):
        die(f"App '{name}' already exists in this zone (apps/{name}).")
    os.makedirs(apps_dir(ZONE), exist_ok=True)
    cmd = [git, "clone"]
    if args.branch:
        cmd += ["--branch", args.branch]
    cmd += [repo, dest]
    head(f"Cloning {repo} → apps/{name}/")
    if subprocess.call(cmd) != 0:
        die("git clone failed.")
    if not is_app(dest):
        warn(f"Cloned, but apps/{name} doesn't look like an app (no app.py/config.py).")
    # Install the app's dependencies into the zone's shared venv.
    req = os.path.join(dest, "requirements.txt")
    if has_venv(ZONE) and os.path.isfile(req):
        head(f"Installing {name}'s dependencies into the zone .venv")
        if _pip_install_venv(["-r", "requirements.txt"], cwd=dest, quiet=True) != 0:
            warn("Dependency install hit an error — re-run `zonal setup` after checking it.")
        else:
            ok("Dependencies installed.")
    elif not has_venv(ZONE):
        warn("Zone has no .venv (was it created with `zonal init`?). Run `zonal setup` next.")
    ok(f"App added at apps/{name}")
    print(f"  Set up & run it:  zonal setup {name} --seed   then   zonal start {name}")


def _pip_install_venv(pip_args, cwd=None, quiet=False):
    """pip install … into the zone's shared venv (defaults cwd to the active app)."""
    py = venv_python(ZONE)
    cmd = [py, "-m", "pip", "install"] + (["-q"] if quiet else []) + list(pip_args)
    return subprocess.call(cmd, cwd=cwd or ROOT)


def _ensure_zone_venv():
    """Make sure the zone venv exists (it normally does, from `zonal init`)."""
    py = venv_python(ZONE)
    if os.path.isfile(py):
        return py
    head("Creating the zone virtual environment (.venv)")
    if subprocess.call([_base_python(), "-m", "venv", venv_dir(ZONE)]) != 0 \
            or not os.path.isfile(py):
        die("Could not create .venv (is the base Python's venv module available?).")
    subprocess.call([py, "-m", "pip", "install", "-q", "--upgrade", "pip"])
    ok("Created .venv")
    return py


def cmd_install(args):
    """Install the active app's dependencies into the zone's shared .venv."""
    _ensure_zone_venv()
    head("Installing runtime dependencies")
    rc = _pip_install_venv(["-r", "requirements.txt"])
    if rc == 0:
        ok("Runtime dependencies installed.")
    if args.build:
        head("Installing build dependencies")
        rc2 = _pip_install_venv(["-r", "build-requirements.txt"])
        if rc2 == 0:
            ok("Build dependencies installed.")
        rc = rc or rc2
    raise SystemExit(rc)


def cmd_ensure_env(args=None):
    """Create .env from .env.example if it doesn't exist yet."""
    env_path = os.path.join(ROOT, ".env")
    example = os.path.join(ROOT, ".env.example")
    if os.path.isfile(env_path):
        ok(".env already present.")
        return
    if os.path.isfile(example):
        shutil.copyfile(example, env_path)
        ok("Created .env from .env.example — edit it if your MariaDB password differs.")
    else:
        warn("No .env or .env.example found; using built-in defaults (root / pos_db).")


def cmd_initdb(args):
    """Create the database, all tables, and the default admin (idempotent)."""
    import init_db
    head("Initializing database")
    try:
        init_db.create_database()
        init_db.create_tables()
        if init_db.ensure_default_admin():
            ok(f"Created default admin '{init_db.DEFAULT_ADMIN['username']}' "
               f"(password '{init_db.DEFAULT_ADMIN['password']}') — change it after first login!")
    except Exception as e:
        die(f"Could not initialize the database.\n  {type(e).__name__}: {e}\n"
            f"  Is MariaDB running, and do DB_USER/DB_PASSWORD in .env match?")
    ok("Database ready.")


def cmd_migrate(args):
    """Apply idempotent schema upgrades to an existing database."""
    import migrate
    head("Migrating database")
    try:
        migrate.create_new_tables()
        migrate.upgrade_sales_table()
        migrate.upgrade_users_table()
        migrate.upgrade_products_table()
        import init_db
        if init_db.ensure_default_admin():
            ok("Created default admin (password 'admin') — change it after first login!")
    except Exception as e:
        die(f"Migration failed.\n  {type(e).__name__}: {e}")
    ok("Migration complete.")


def cmd_seed(args):
    """Insert sample products so the POS is usable immediately."""
    import seed
    head("Seeding sample data")
    seed.run()


def cmd_setup(args):
    """First-time app setup: .env → deps into the zone .venv → DB → (optionally) seed.

    Runs under zonal's own interpreter (so it can install into the zone venv),
    then bounces the database steps into that venv where the app code and its
    dependencies live.
    """
    head(f"Setting up app '{os.path.basename(ROOT)}'")
    cmd_ensure_env()
    if not args.skip_install:
        _ensure_zone_venv()
        head("Installing runtime dependencies")
        if _pip_install_venv(["-r", "requirements.txt"], quiet=True) != 0:
            die("Dependency install failed.")
        ok("Dependencies installed.")
    elif not has_venv(ZONE):
        warn("--skip-install given but this zone has no .venv yet; "
             "database steps need one. Run `zonal install` first.")
        return
    # initdb (+ seed) need the app code, so run them inside the zone's venv.
    if reexec_in_venv(ZONE, ROOT, ["initdb"]) != 0:
        die("Database initialization failed.")
    if args.seed and reexec_in_venv(ZONE, ROOT, ["seed"]) != 0:
        die("Seeding failed.")
    print("\nSetup done. Start the app with:  zonal start   "
          "(or  zonal launch  for the desktop window)")


def _pick_port(host, preferred):
    """Return `preferred` if free, else an OS-assigned free port (avoids 'port in use')."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, int(preferred)))
            return int(preferred)
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
        s2.bind((host, 0))
        return s2.getsockname()[1]


def _wait_until_up(url, timeout=15.0):
    """Poll the local server until it answers, so the window opens to a ready app."""
    import time, urllib.request, urllib.error
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except urllib.error.HTTPError:
            return True   # any HTTP response means it's up
        except Exception:
            time.sleep(0.3)
    return False


def _serve_block(url):
    """Keep the background server alive without a window — and WITHOUT a browser."""
    import time
    print(f"\nServer still running at {url} — open it manually if you like. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


def cmd_serve(args):
    """Run the Flask dev server headless: logs only, no window and no browser."""
    from app import app
    from config import Config
    host, port = args.host or Config.HOST, args.port or Config.PORT
    os.environ.setdefault("FLASK_DEBUG", "1" if args.reload else "0")
    serve_argv = ["serve"]
    if args.port: serve_argv += ["--port", str(args.port)]
    if args.host: serve_argv += ["--host", args.host]
    if args.reload: serve_argv.append("--reload")
    if args.prod: serve_argv.append("--prod")
    # With the reloader on, only the serving child (not the watchdog) records the pid.
    if not (args.reload and not args.prod and os.environ.get("WERKZEUG_RUN_MAIN") != "true"):
        _write_pidfile(os.getpid(), serve_argv)
    try:
        if args.prod:
            head(f"Serving (waitress) on http://{host}:{port}")
            from waitress import serve
            serve(app, host=host, port=port, threads=8)
        else:
            head(f"Serving (Flask dev server) on http://{host}:{port}  reload={args.reload}")
            app.run(host=host, port=port, debug=args.reload, use_reloader=args.reload)
    finally:
        if PID_FILE and os.path.isfile(PID_FILE):
            try: os.remove(PID_FILE)
            except OSError: pass


def cmd_start(args):
    """Start the dev server with LIVE LOGS and render the app in a native desktop window.

    No browser: the UI opens in an embedded WebView2 window (via pywebview),
    just like the packaged app, while the dev server's request log streams to
    this console. The server runs on a background thread because the window must
    own the main thread; close the window (or press Ctrl+C) to stop.
    """
    import threading
    from app import app as flask_app
    from config import Config
    host = args.host or Config.HOST
    port = _pick_port(host, args.port or Config.PORT)
    url_host = "127.0.0.1" if host in ("0.0.0.0", "", "::") else host
    url = f"http://{url_host}:{port}"

    serve_argv = ["start"]
    if args.port: serve_argv += ["--port", str(args.port)]
    if args.host: serve_argv += ["--host", args.host]
    if args.no_window: serve_argv.append("--no-window")
    _write_pidfile(os.getpid(), serve_argv)

    head(f"Starting {os.path.basename(ROOT)} — live logs below; "
         f"close the window (or Ctrl+C) to stop")
    print(f"  dev server: {url}")

    # Serve in the background (no reloader — the window owns the main thread);
    # the request log streams straight to this console.
    threading.Thread(
        target=lambda: flask_app.run(host=host, port=port, debug=False,
                                     use_reloader=False, threaded=True),
        daemon=True,
    ).start()
    _wait_until_up(url)

    if args.no_window:
        _serve_block(url)
        return
    try:
        import webview
        title = getattr(Config, "STORE_NAME", None) or os.path.basename(ROOT)
        webview.create_window(title, url, width=1280, height=820, min_size=(1000, 680))
        icon = None
        try:
            from config import resource_path
            cand = resource_path("assets/icon.ico")
            icon = cand if os.path.isfile(cand) else None
        except Exception:
            icon = None
        try:
            webview.start(icon=icon) if icon else webview.start()
        except TypeError:
            webview.start()  # older pywebview without the icon argument
    except ImportError:
        warn("pywebview isn't installed in this zone, so the desktop window can't open.")
        warn("Install the app's deps with `zonal install`, then run `zonal start` again.")
        _serve_block(url)
    except Exception as e:
        warn(f"Native window unavailable ({e}).")
        _serve_block(url)
    finally:
        if PID_FILE and os.path.isfile(PID_FILE):
            try: os.remove(PID_FILE)
            except OSError: pass


def cmd_restart(args):
    """Stop and relaunch the dev server recorded by `zonal start`/`serve`."""
    head("Restarting dev server")
    argv = _stop_running_server()
    if argv is None:
        warn("No running dev server found (start one with `zonal start`).")
        return
    _relaunch_serve(argv)
    ok(f"Relaunched: zonal {' '.join(argv)} (in a new window).")


def cmd_launch(args):
    """Run the full desktop app (native window via launcher.py)."""
    import launcher
    head(f"Launching {os.path.basename(ROOT)} desktop app")
    launcher.serve()


def cmd_shell(args):
    """Open a Python REPL inside the app context (db + models preloaded)."""
    import code
    from app import app
    from models import db
    import models
    ctx = app.app_context()
    ctx.push()
    banner = ("ZT POS shell — `app`, `db`, and `models` are available; an app "
              "context is active.\nType exit() to quit.")
    ns = {"app": app, "db": db, "models": models}
    try:
        code.interact(banner=banner, local=ns)
    finally:
        ctx.pop()


def cmd_db(args):
    """Open the MariaDB client connected to the POS database."""
    from config import Config
    client = find_mariadb_tool("mysql", "mariadb")
    if not client:
        die("Could not find the mysql/mariadb client. Add MariaDB's bin/ to PATH.")
    cmd = [client, "-h", Config.DB_HOST, "-P", str(Config.DB_PORT),
           "-u", Config.DB_USER, Config.DB_NAME]
    env = dict(os.environ)
    if Config.DB_PASSWORD:
        env["MYSQL_PWD"] = Config.DB_PASSWORD  # avoids password on the command line
    raise SystemExit(subprocess.call(cmd, env=env))


def cmd_backup(args):
    """Dump the POS database to backups/ as a timestamped .sql file."""
    import datetime
    from config import Config
    dump = find_mariadb_tool("mysqldump", "mariadb-dump")
    if not dump:
        die("Could not find mysqldump/mariadb-dump. Add MariaDB's bin/ to PATH.")
    backups = os.path.join(ROOT, "backups")
    os.makedirs(backups, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = args.output or os.path.join(backups, f"{Config.DB_NAME}-{stamp}.sql")
    cmd = [dump, "-h", Config.DB_HOST, "-P", str(Config.DB_PORT),
           "-u", Config.DB_USER, "--single-transaction", "--routines",
           "--databases", Config.DB_NAME]
    env = dict(os.environ)
    if Config.DB_PASSWORD:
        env["MYSQL_PWD"] = Config.DB_PASSWORD
    head(f"Backing up '{Config.DB_NAME}'")
    with open(out, "w", encoding="utf-8") as fh:
        rc = subprocess.call(cmd, stdout=fh, env=env)
    if rc != 0:
        die("Backup failed (see messages above).")
    ok(f"Saved {out} ({os.path.getsize(out) // 1024} KB)")


def cmd_restore(args):
    """Restore the database from a .sql dump (DESTRUCTIVE — overwrites data)."""
    from config import Config
    if not os.path.isfile(args.file):
        die(f"Dump not found: {args.file}")
    client = find_mariadb_tool("mysql", "mariadb")
    if not client:
        die("Could not find the mysql/mariadb client. Add MariaDB's bin/ to PATH.")
    if not args.yes and not confirm(
            f"Restore '{args.file}' into '{Config.DB_NAME}', overwriting current data?"):
        die("Aborted.", code=0)
    cmd = [client, "-h", Config.DB_HOST, "-P", str(Config.DB_PORT), "-u", Config.DB_USER]
    env = dict(os.environ)
    if Config.DB_PASSWORD:
        env["MYSQL_PWD"] = Config.DB_PASSWORD
    head(f"Restoring into '{Config.DB_NAME}'")
    with open(args.file, "r", encoding="utf-8") as fh:
        rc = subprocess.call(cmd, stdin=fh, env=env)
    if rc != 0:
        die("Restore failed.")
    ok("Restore complete.")


def cmd_reset_db(args):
    """Drop and recreate the database from scratch (DESTRUCTIVE)."""
    import sqlalchemy
    from sqlalchemy import text
    from config import Config, server_uri
    if not args.yes and not confirm(
            f"Drop and recreate '{Config.DB_NAME}'? ALL DATA WILL BE LOST."):
        die("Aborted.", code=0)
    head(f"Resetting '{Config.DB_NAME}'")
    engine = sqlalchemy.create_engine(server_uri())
    with engine.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS `{Config.DB_NAME}`"))
        conn.commit()
    engine.dispose()
    ok("Dropped.")
    cmd_initdb(args)
    if args.seed:
        cmd_seed(args)


def cmd_doctor(args):
    """Check that the zone is ready to run the app."""
    # Package checks must run inside the zone's venv to be meaningful, so bounce
    # there when it exists and we aren't already in it.
    if (has_venv(ZONE) and not os.environ.get("ZONAL_IN_VENV")
            and not in_zone_venv(ZONE)):
        raise SystemExit(reexec_in_venv(ZONE, ROOT, ["doctor"]))

    head(f"Environment check — app '{os.path.basename(ROOT)}'")
    problems = 0

    py_ok = sys.version_info[:2] >= (3, 9)
    (ok if py_ok else fail)(f"Python {sys.version.split()[0]} "
                            f"({'>= 3.9' if py_ok else 'upgrade to 3.9+'})")
    problems += 0 if py_ok else 1

    if has_venv(ZONE):
        ok("Zone .venv present.")
    else:
        fail("No .venv for this zone (run `zonal init` / `zonal setup`).")
        problems += 1

    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    (ok if in_venv else warn)("Virtual environment active." if in_venv
                              else "Not in a virtualenv (recommended: .venv).")

    env_ok = os.path.isfile(os.path.join(ROOT, ".env"))
    (ok if env_ok else warn)(".env present." if env_ok else "No .env (run `zonal setup`).")

    for mod in ("flask", "sqlalchemy", "pymysql", "dotenv", "waitress"):
        try:
            __import__(mod)
            ok(f"package: {mod}")
        except ImportError:
            fail(f"package missing: {mod} (run `zonal install`)")
            problems += 1

    try:
        from provision import can_connect
        from config import Config, server_uri
        if can_connect(server_uri(), timeout=4):
            ok(f"MariaDB server reachable at {Config.DB_HOST}:{Config.DB_PORT}")
        else:
            fail(f"MariaDB server not reachable at {Config.DB_HOST}:{Config.DB_PORT} "
                 f"(is the service running? are credentials right?)")
            problems += 1
        if can_connect(Config.SQLALCHEMY_DATABASE_URI, timeout=4):
            ok(f"Database '{Config.DB_NAME}' reachable.")
        else:
            warn(f"Database '{Config.DB_NAME}' not found (run `zonal initdb`).")
    except Exception as e:
        fail(f"DB check error: {type(e).__name__}: {e}")
        problems += 1

    tool = find_mariadb_tool("mysqldump", "mariadb-dump")
    (ok if tool else warn)(f"mysqldump found ({tool})." if tool
                           else "mysqldump not on PATH (backup/restore unavailable).")

    print()
    if problems:
        die(f"{problems} problem(s) found.")
    ok("All good — the app is ready to run.")


def cmd_config(args):
    """Print the effective configuration (password masked)."""
    from config import Config
    head("Effective configuration")
    rows = [
        ("STORE_NAME", Config.STORE_NAME),
        ("CURRENCY", Config.CURRENCY),
        ("DB_HOST", Config.DB_HOST),
        ("DB_PORT", Config.DB_PORT),
        ("DB_NAME", Config.DB_NAME),
        ("DB_USER", Config.DB_USER),
        ("DB_PASSWORD", "•••" if Config.DB_PASSWORD else "(empty)"),
        ("POS host:port", f"{Config.HOST}:{Config.PORT}"),
    ]
    for k, v in rows:
        print(f"  {k:<16} {v}")


def cmd_routes(args):
    """List all registered URL routes."""
    from app import app
    head("Routes")
    rules = sorted(app.url_map.iter_rules(), key=lambda r: str(r))
    for r in rules:
        methods = ",".join(sorted(m for m in r.methods if m not in ("HEAD", "OPTIONS")))
        print(f"  {str(r):<34} {methods:<18} {r.endpoint}")


def cmd_bump(args):
    """Bump the app version and roll the changelog."""
    sys.argv = ["bump_version.py", args.part]
    import bump_version
    bump_version.main()


def _build_app_payload():
    """Compile POS.exe and repackage release/ZTPOS-<ver>.zip + manifest.json."""
    head("Building app payload (POS.exe + release zip + manifest)")
    if run_bat("build-setup.bat") != 0:
        die("build-setup.bat failed.")
    ok("App payload built into release/.")


def _build_setup_file():
    """Rebuild the online installer setup/ZTPOS-Online-Setup.exe."""
    head("Building setup file (online installer)")
    if run_bat("build-online-setup.bat") != 0:
        die("build-online-setup.bat failed.")
    ok("Setup file built: setup/ZTPOS-Online-Setup.exe")


def cmd_build(args):
    """Build the app payload, the setup file, or both."""
    if args.target in ("app", "all"):
        _build_app_payload()
    if args.target in ("setup", "all"):
        _build_setup_file()
    ok("Build complete.")


def cmd_update(args):
    """Bump the version, rebuild the app payload, and rebuild the setup file.

    This is the 'build and update the app locally + refresh the setup file'
    one-shot: it bumps the version (so the new local build carries a new number),
    repackages the release zip/manifest, and rebuilds the installer.
    """
    if not args.no_bump:
        head(f"Bumping version ({args.part})")
        sys.argv = ["bump_version.py", args.part]
        import bump_version
        bump_version.main()
    _build_app_payload()
    if not args.no_setup:
        _build_setup_file()
    ver = open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip()
    print(f"\nLocal update ready — v{ver}. Artifacts in release/ and setup/.")


def cmd_refresh(args):
    """Fast local-dev refresh (no PyInstaller): deps, migrate, static, restart."""
    head("Refreshing local development environment")
    if not args.no_deps:
        subprocess.call([sys.executable, "-m", "pip", "install", "-q", "-r",
                         os.path.join(ROOT, "requirements.txt")], cwd=ROOT)
        ok("Dependencies up to date.")
    if not args.no_migrate:
        try:
            cmd_migrate(args)
        except SystemExit:
            warn("Skipped migrate (database not reachable).")
    touch_static()
    if not args.no_restart:
        argv = _stop_running_server()
        if argv is None:
            warn("No running dev server to restart (start one with `zonal start`).")
        else:
            _relaunch_serve(argv)
            ok(f"Relaunched: zonal {' '.join(argv)} (in a new window).")
    print("\nRefresh done.")


def cmd_release(args):
    """Cut a GitHub release (delegates to release-github.bat)."""
    head("Releasing via release-github.bat")
    raise SystemExit(run_bat("release-github.bat"))


# --------------------------------------------------------------------------- #
# Argument parser
# --------------------------------------------------------------------------- #
def build_parser():
    p = argparse.ArgumentParser(
        prog="zonal",
        description="Local development framework for ZT POS (a lightweight 'bench').",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("-V", "--version", action="store_true", help="Show versions and exit.")
    p.add_argument("-a", "--app", metavar="NAME",
                   help="Which app in the zone to act on (when it has more than one).")
    sub = p.add_subparsers(dest="command", metavar="<command>")

    def add(name, fn, help, aliases=(), needs_zone=True, needs_app=True, needs_venv=True):
        sp = sub.add_parser(name, help=help, aliases=aliases, description=fn.__doc__)
        # needs_zone: must be inside a zone.  needs_app: also resolves an active
        # app (chdir into it).  needs_venv: re-exec under the zone .venv first.
        sp.set_defaults(func=fn, needs_zone=needs_zone, needs_app=needs_app,
                        needs_venv=needs_venv)
        return sp

    add("version", cmd_version, "Show zonal / Python / zone versions.",
        needs_zone=False, needs_app=False, needs_venv=False)

    sp = add("init", cmd_init, "Create a new zone (workspace + shared .venv + apps/).",
             needs_zone=False, needs_app=False, needs_venv=False)
    sp.add_argument("name", nargs="?", help="Zone folder to create (default: current dir).")

    sp = add("get", cmd_get, "Clone an app from GitHub into this zone's apps/.",
             aliases=("clone",), needs_app=False, needs_venv=False)
    sp.add_argument("repo", help="Git URL of the app repository.")
    sp.add_argument("name", nargs="?", help="App folder name under apps/ (default: repo name).")
    sp.add_argument("--branch", help="Clone a specific branch/tag.")

    # setup/install install into the zone venv themselves, so they don't need to
    # be re-exec'd *inside* it (needs_venv=False).
    sp = add("setup", cmd_setup, "Set up the app: .env, deps, database, optional seed.",
             needs_venv=False)
    sp.add_argument("app_name", nargs="?", help="App to set up (default: the zone's app).")
    sp.add_argument("--seed", action="store_true", help="Also insert sample products.")
    sp.add_argument("--skip-install", action="store_true", help="Skip the dependency step.")
    add("install", cmd_install, "Install the app's dependencies into the zone .venv.",
        needs_venv=False) \
        .add_argument("--build", action="store_true", help="Also install build deps.")
    add("initdb", cmd_initdb, "Create database, tables, and default admin.", aliases=("init-db",))
    add("migrate", cmd_migrate, "Apply idempotent schema upgrades.")
    add("seed", cmd_seed, "Insert sample products.")

    sp = add("start", cmd_start,
             "Run an app: live logs + native window.  e.g. zonal start zt-pos")
    sp.add_argument("app_name", nargs="?", help="App to run (default: the zone's app).")
    sp.add_argument("--port", type=int, help="Port (default from config).")
    sp.add_argument("--host", help="Host (default from config).")
    sp.add_argument("--no-window", action="store_true",
                    help="Don't open the desktop window; just serve with live logs.")

    sp = add("serve", cmd_serve, "Run the Flask dev server (browser, no auto-open).")
    sp.add_argument("--port", type=int, help="Port (default from config).")
    sp.add_argument("--host", help="Host (default from config).")
    sp.add_argument("--reload", action="store_true", help="Auto-reload on code changes.")
    sp.add_argument("--prod", action="store_true", help="Use the waitress WSGI server.")

    add("launch", cmd_launch, "Run the desktop app (native window).")
    add("restart", cmd_restart, "Stop and relaunch the dev server.")

    sp = add("refresh", cmd_refresh, "Fast local-dev refresh: deps, migrate, static, restart.")
    sp.add_argument("--no-deps", action="store_true", help="Skip pip install.")
    sp.add_argument("--no-migrate", action="store_true", help="Skip DB migration.")
    sp.add_argument("--no-restart", action="store_true", help="Don't restart the dev server.")

    add("shell", cmd_shell, "Python REPL with app context (db, models).", aliases=("console",))
    add("db", cmd_db, "Open the MariaDB client on the POS database.", aliases=("mariadb",))

    sp = add("backup", cmd_backup, "Dump the database to backups/.")
    sp.add_argument("-o", "--output", help="Write to this file instead of backups/.")

    sp = add("restore", cmd_restore, "Restore the database from a .sql dump (destructive).")
    sp.add_argument("file", help="Path to the .sql dump.")
    sp.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")

    sp = add("reset-db", cmd_reset_db, "Drop and recreate the database (destructive).")
    sp.add_argument("--seed", action="store_true", help="Also re-seed sample products.")
    sp.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")

    add("doctor", cmd_doctor, "Check the app/zone is ready.", needs_venv=False)
    add("config", cmd_config, "Print effective configuration (password masked).")
    add("routes", cmd_routes, "List registered URL routes.")

    add("bump", cmd_bump, "Bump version + changelog.", needs_venv=False) \
        .add_argument("part", nargs="?", default="patch",
                      help="major | minor | patch | X.Y.Z (default: patch).")

    sp = add("build", cmd_build, "Build the app payload, the setup file, or both.",
             needs_venv=False)
    sp.add_argument("target", nargs="?", choices=("app", "setup", "all"), default="app",
                    help="app = POS.exe + release zip (default); setup = installer; all = both.")

    sp = add("update", cmd_update, "Bump version + rebuild app payload + rebuild setup file.",
             needs_venv=False)
    sp.add_argument("part", nargs="?", default="patch",
                    help="major | minor | patch | X.Y.Z (default: patch).")
    sp.add_argument("--no-bump", action="store_true", help="Don't bump the version.")
    sp.add_argument("--no-setup", action="store_true", help="Skip rebuilding the setup file.")

    add("release", cmd_release, "Cut a GitHub release.", needs_venv=False)
    return p


def main(argv=None):
    parser = build_parser()
    raw = sys.argv[1:] if argv is None else list(argv)
    # `zonal help` / `zonal help <cmd>` → friendly usage (argparse uses -h/--help).
    if raw and raw[0] == "help":
        if len(raw) > 1 and raw[1] in parser._subparsers._group_actions[0].choices:
            parser._subparsers._group_actions[0].choices[raw[1]].print_help()
        else:
            parser.print_help()
        return
    args = parser.parse_args(argv)
    if args.version:
        return cmd_version(args)
    if not getattr(args, "command", None):
        parser.print_help()
        return

    # Locate the zone (every command except init/get-from-anywhere/version).
    if getattr(args, "needs_zone", True):
        zone = find_zone()
        if not zone:
            die("Not inside a zone.\n"
                "  Create one with:  zonal init <name>\n"
                "  then add an app:  zonal get <repo-url>")
        _set_zone(zone)

        if getattr(args, "needs_app", True):
            # Pick the app this command targets, move into it, import from it.
            # Precedence: positional (e.g. `zonal start zt-pos`) > global --app > auto.
            explicit = getattr(args, "app_name", None) or getattr(args, "app", None)
            app_dir = resolve_app(zone, explicit=explicit)
            _set_app(app_dir)
            os.chdir(app_dir)
            if app_dir not in sys.path:
                sys.path.insert(0, app_dir)

            # Commands that import app code run under the zone's shared .venv.
            if (getattr(args, "needs_venv", True)
                    and not os.environ.get("ZONAL_IN_VENV")
                    and not in_zone_venv(zone)):
                if not has_venv(zone):
                    die("This zone has no virtual environment yet — run `zonal setup` first.")
                raise SystemExit(reexec_in_venv(zone, app_dir, raw))
        else:
            os.chdir(zone)  # zone-only commands (e.g. `get`) operate at the root

    args.func(args)


if __name__ == "__main__":
    main()
