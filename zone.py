"""zone — a small development CLI for ZT POS and apps built on it.

Install `zone` once, then use it to create **zones** (workspaces, each with a
shared `.venv` and an `apps/` folder), clone apps into them, and drive the whole
dev lifecycle — set up, serve, migrate, seed, back up, build, release — without
juggling a dozen separate scripts and .bat files.

Typical flow (Windows):
    zone init mystore                               :: create a zone (workspace + .venv)
    cd mystore
    zone get https://github.com/<org>/zt-pos.git    :: clone an app into apps/
    zone setup zt-pos --seed                        :: .env, deps, DB, samples
    zone start zt-pos                               :: dev server: live logs + native window

How it locates a zone and app:
    Most commands (all but `init`/`get`/`version`/`upgrade`/`help`) act on the
    zone containing the current directory: `zone` walks up from the CWD to the
    `.zone/zone.json` marker. Within that zone it targets the named app
    (`zone start zt-pos`), the app whose folder you're in, or the zone's only
    app. Commands that run app code re-exec inside the zone's shared `.venv`, so
    zones stay isolated.

Run `zone help` (or `zone <command> -h`) for the full command list.
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

ZONE_VERSION = "1.0.0"
# Where the zone CLI itself lives, for version checks and `zone upgrade`.
ZONE_REPO = os.environ.get("ZONE_REPO", "ZonalTech/Zone")

# Bound in main() once the zone and active app are located.
ZONE = None         # zone root (holds .venv, .zone/, apps/)
ROOT = None         # active app directory (apps/<name>)
STATE_DIR = None    # <zone>/.zone
PID_FILE = None     # <zone>/.zone/serve-<app>.pid

ZONE_MARKER = os.path.join(".zone", "zone.json")


# --------------------------------------------------------------------------- #
# Zone & app discovery + the zone's shared virtualenv
# --------------------------------------------------------------------------- #
def is_app(path):
    """A directory is an app if it holds both app.py and config.py."""
    return (os.path.isfile(os.path.join(path, "app.py"))
            and os.path.isfile(os.path.join(path, "config.py")))


def is_zone_root(path):
    """A directory is a zone root if it carries the .zone/zone.json marker."""
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
        die("This zone has no apps yet — add one with:  zone get <repo-url>")
    die("This zone has several apps — name one:\n  "
        + ", ".join(apps) + f"\n  e.g.  zone start {apps[0]}   "
        f"(or add  --app {apps[0]}  to other commands)")


def _set_zone(zone):
    global ZONE, STATE_DIR
    ZONE = zone
    STATE_DIR = os.path.join(zone, ".zone")


def _set_app(app_dir):
    """Bind the active app and its per-app server pidfile (kept under the zone)."""
    global ROOT, PID_FILE
    ROOT = app_dir
    PID_FILE = os.path.join(STATE_DIR, f"serve-{os.path.basename(app_dir)}.pid")


def venv_dir(zone):
    return os.path.join(zone, ".venv")


def venv_python(zone):
    """Path to the zone's shared venv interpreter (created by `zone init`)."""
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
    """Re-run `zone <argv>` under the zone's venv, anchored in the app dir.

    App code lives in the zone's venv, so commands that import it bounce here.
    cwd=app_dir lets the child re-resolve the same app; ZONE_IN_VENV stops loops.
    """
    py = venv_python(zone)
    if not os.path.isfile(py):
        die("This zone has no virtual environment yet — run `zone init` (or `zone setup`).")
    env = dict(os.environ, ZONE_IN_VENV="1")
    proc = subprocess.Popen([py, os.path.abspath(__file__), *argv], cwd=app_dir, env=env)
    try:
        return proc.wait()
    except KeyboardInterrupt:
        # Ctrl+C reaches the child too; let it shut down its server/window, then
        # exit quietly. Force it down only if it hangs. No traceback.
        try:
            proc.wait(timeout=10)
        except (KeyboardInterrupt, subprocess.TimeoutExpired):
            terminate_pid(proc.pid)
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
        return proc.returncode if proc.returncode is not None else 0


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
    """Run one of the app's .bat helpers (Windows-only build/release scripts)."""
    path = os.path.join(ROOT, name)
    if not os.path.isfile(path):
        die(f"{name} not found in {ROOT}")
    if os.name != "nt":
        die(f"{name} is a Windows batch file; run this command on Windows.")
    return subprocess.call(["cmd", "/c", path, *args], cwd=ROOT)


def _write_pidfile(pid, argv):
    """Record the running dev server so `zone restart`/`refresh` can find it."""
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
    """Start `zone serve/start …` again, detached, in its own console/session.

    Called from inside the zone's venv (restart/refresh both run there), so
    sys.executable is already the venv Python; ZONE_IN_VENV keeps it that way.
    """
    cmd = [sys.executable, os.path.abspath(__file__)] + argv
    env = dict(os.environ, ZONE_IN_VENV="1")
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
    print(f"zone CLI   v{ZONE_VERSION}")
    print(f"Python      {sys.version.split()[0]}")
    zone = find_zone()
    if not zone:
        print("zone        (none here — create one with `zone init <name>`)")
        return
    print(f"zone        {zone}")
    apps = zone_apps(zone)
    if not apps:
        print("apps        (none yet — add one with `zone get <repo-url>`)")
        return
    for name in apps:
        vf = os.path.join(apps_dir(zone), name, "VERSION")
        ver = open(vf, encoding="utf-8").read().strip() if os.path.isfile(vf) else "?"
        print(f"app         {name}  v{ver}")


def _version_tuple(v):
    """Loose version → comparable tuple ('0.4.0' -> (0, 4, 0))."""
    out = []
    for part in str(v).split("."):
        num = "".join(ch for ch in part if ch.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out)


def _latest_zone_version(timeout=3.0):
    """Fetch the newest zone CLI version from the repo's pyproject (None if offline)."""
    import re, urllib.request
    for branch in ("main", "master"):
        url = f"https://raw.githubusercontent.com/{ZONE_REPO}/{branch}/pyproject.toml"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                text = r.read().decode("utf-8", "replace")
        except Exception:
            continue
        m = re.search(r'(?m)^\s*version\s*=\s*["\']([^"\']+)["\']', text)
        if m:
            return m.group(1)
    return None


def _check_zone_update(timeout=3.0):
    """Show current vs latest zone CLI version. Returns latest (or None if offline)."""
    latest = _latest_zone_version(timeout=timeout)
    if not latest:
        return None
    if _version_tuple(latest) > _version_tuple(ZONE_VERSION):
        warn(f"zone CLI update available: {ZONE_VERSION} -> {latest}   (run `zone upgrade`)")
    else:
        ok(f"zone CLI v{ZONE_VERSION} (up to date)")
    return latest


def cmd_upgrade(args):
    """Upgrade the zone CLI itself to the latest from its Git repo."""
    head(f"Upgrading the zone CLI (current v{ZONE_VERSION})")
    latest = _latest_zone_version()
    if latest:
        print(f"  {ZONE_VERSION} -> {latest}")
        if _version_tuple(latest) <= _version_tuple(ZONE_VERSION) and not args.force:
            ok("Already up to date. (use --force to reinstall anyway)")
            return
    else:
        warn("Couldn't reach the repo to check the latest version; upgrading anyway.")
    src = os.path.dirname(os.path.abspath(__file__))
    git = shutil.which("git")
    if git and os.path.isdir(os.path.join(src, ".git")):
        # Source/editable install: pull the latest commits in place.
        head(f"git pull in {src}")
        if subprocess.call([git, "-C", src, "pull", "--ff-only"]) != 0:
            die("git pull failed (uncommitted changes or diverged history?). "
                "Resolve it in the CLI source and retry.")
    else:
        # Installed from a Git URL: reinstall the newest from the repo.
        url = f"git+https://github.com/{ZONE_REPO}.git"
        head(f"pip install --upgrade {url}")
        if subprocess.call([sys.executable, "-m", "pip", "install", "--upgrade", url]) != 0:
            die("pip upgrade failed.")
    ok("Upgrade complete. Run `zone --version` to confirm "
       "(reopen the terminal if the version looks unchanged).")


def _base_python():
    """The interpreter used to *build* a zone's venv (zone's own Python)."""
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
    os.makedirs(os.path.join(zone, ".zone"), exist_ok=True)
    if not is_zone_root(zone):
        import json
        with open(os.path.join(zone, ZONE_MARKER), "w", encoding="utf-8") as fh:
            json.dump({"zone": name, "zone": ZONE_VERSION}, fh, indent=2)
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
    print(f"\nNext:\n{cd}  zone get <repo-url>   :: clone an app (e.g. ZT POS) into the zone")


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
            warn("Dependency install hit an error — re-run `zone setup` after checking it.")
        else:
            ok("Dependencies installed.")
    elif not has_venv(ZONE):
        warn("Zone has no .venv (was it created with `zone init`?). Run `zone setup` next.")
    ok(f"App added at apps/{name}")
    print(f"  Set up & run it:  zone setup {name} --seed   then   zone start {name}")


def _pip_install_venv(pip_args, cwd=None, quiet=False):
    """pip install … into the zone's shared venv (defaults cwd to the active app)."""
    py = venv_python(ZONE)
    cmd = [py, "-m", "pip", "install"] + (["-q"] if quiet else []) + list(pip_args)
    return subprocess.call(cmd, cwd=cwd or ROOT)


def _ensure_zone_venv():
    """Make sure the zone venv exists (it normally does, from `zone init`)."""
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
        ok("Created .env from .env.example.")
    else:
        warn("No .env or .env.example found; using built-in defaults (root / pos_db).")


def _env_path():
    return os.path.join(ROOT, ".env")


def _read_env_value(key):
    """Read KEY's value from the app's .env (None if the file/key is absent)."""
    p = _env_path()
    if not os.path.isfile(p):
        return None
    for line in open(p, encoding="utf-8"):
        s = line.strip()
        if s.startswith(key + "="):
            return s[len(key) + 1:]
    return None


def _set_env_var(key, value):
    """Set/replace KEY=value in the app's .env (creating the file if needed)."""
    p = _env_path()
    lines = open(p, encoding="utf-8").read().splitlines() if os.path.isfile(p) else []
    for i, l in enumerate(lines):
        s = l.lstrip()
        if s.startswith(key + "=") or s.startswith("#" + key + "="):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def _is_db_auth_error(exc):
    """True if a DB error looks like bad/missing credentials (vs. server down)."""
    msg = str(exc).lower()
    return any(s in msg for s in (
        "access denied", "authentication plugin", "1045", "1698", "2059",
        "using password",
    ))


def _prompt_db_password(force=False):
    """Make sure .env carries a DB password before we create the database.

    The default .env ships with an empty DB_PASSWORD, which makes MariaDB try an
    auth plugin pymysql can't speak (error 2059). So if no password is set yet,
    prompt for the MariaDB user's password (hidden) and save it to .env.
    """
    import getpass
    if not force and os.environ.get("ZONE_DB_PROMPTED"):
        return
    user = _read_env_value("DB_USER") or "root"
    pw = _read_env_value("DB_PASSWORD")
    if pw and not force:
        return  # already configured
    if not (sys.stdin and sys.stdin.isatty()):
        return  # non-interactive: leave .env as-is and let the connection speak
    head("MariaDB credentials")
    print(f"  Enter the MariaDB password for user '{user}' so the database can be created.")
    print("  (Press Enter to leave it blank only if this MariaDB truly has no password.)")
    try:
        entered = getpass.getpass(f"  {user} password: ")
    except (EOFError, KeyboardInterrupt):
        print()
        return
    _set_env_var("DB_USER", user)
    _set_env_var("DB_PASSWORD", entered)
    ok("Saved DB credentials to .env")


def cmd_initdb(args):
    """Create the database, all tables, and the default admin (idempotent)."""
    # Ensure a password is set first — .env is read at import time below, so this
    # has to run before `import init_db` pulls in config.
    _prompt_db_password()
    head("Initializing database")
    try:
        import init_db
        init_db.create_database()
        init_db.create_tables()
        if init_db.ensure_default_admin():
            ok(f"Created default admin '{init_db.DEFAULT_ADMIN['username']}' "
               f"(password '{init_db.DEFAULT_ADMIN['password']}') — change it after first login!")
    except Exception as e:
        # Bad/missing credentials: re-prompt and retry once in a fresh process
        # (so config re-reads .env). A guard env stops an endless loop.
        if (_is_db_auth_error(e) and not os.environ.get("ZONE_DB_RETRY")
                and sys.stdin and sys.stdin.isatty()):
            warn(f"MariaDB rejected the credentials ({type(e).__name__}).")
            _prompt_db_password(force=True)
            os.environ["ZONE_DB_RETRY"] = "1"
            os.environ["ZONE_DB_PROMPTED"] = "1"
            raise SystemExit(reexec_in_venv(ZONE, ROOT, ["initdb"]))
        die(f"Could not initialize the database.\n  {type(e).__name__}: {e}\n"
            f"  Is MariaDB running, and is the DB_USER/DB_PASSWORD in .env correct?")
    ok("Database ready.")


def cmd_migrate(args):
    """Apply schema upgrades and refresh assets — only while the app is running."""
    # Migrate runs against a started app: require a live `zone start`/`serve`.
    # (refresh manages the server itself, so it skips this check.)
    if not getattr(args, "skip_running_check", False):
        info = _read_pidfile()
        pid = info.get("pid") if info else None
        if not (pid and _pid_alive(pid)):
            app = os.path.basename(ROOT)
            die(f"App '{app}' isn't running — start it first:  zone start {app}\n"
                f"  (migrate runs against the running app).")
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
    # Rebuild/refresh assets so the app serves the latest CSS/JS (cache-bust).
    if not getattr(args, "no_assets", False):
        head("Refreshing assets")
        touch_static()


def cmd_seed(args):
    """Insert sample products so the POS is usable immediately."""
    import seed
    head("Seeding sample data")
    seed.run()


def cmd_set_db_password(args):
    """Set the MariaDB connection password (and optionally user) in the app's .env."""
    if not os.path.isfile(_env_path()):
        cmd_ensure_env()
    pw = args.password
    if pw is None:
        import getpass
        if not (sys.stdin and sys.stdin.isatty()):
            die('Provide the password:  zone set-db-password "<password>"')
        who = args.user or _read_env_value("DB_USER") or "root"
        pw = getpass.getpass(f"MariaDB password for '{who}': ")
    if args.user:
        _set_env_var("DB_USER", args.user)
    _set_env_var("DB_PASSWORD", pw)
    shown = args.user or _read_env_value("DB_USER") or "root"
    ok(f"Saved DB credentials to .env (user '{shown}').")
    print("Next:  zone setup   (or  zone initdb)  to create the database with these.")


def cmd_set_admin_password(args):
    """Set an app login user's password (the app's 'admin' by default)."""
    from app import app
    from models import db, User
    username = args.user
    new = args.password
    if new is None:
        import getpass
        if not (sys.stdin and sys.stdin.isatty()):
            die('Provide the new password:  zone set-admin-password "<password>"')
        new = getpass.getpass(f"New password for '{username}': ")
        if new != getpass.getpass("Confirm new password: "):
            die("Passwords don't match.")
    if not new:
        die("Password cannot be empty.")
    head(f"Setting password for '{username}' on app '{os.path.basename(ROOT)}'")
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if not user:
            die(f"No login user '{username}' in this app's database "
                f"(set the app up first with `zone setup`).")
        user.set_password(new)
        if hasattr(user, "must_change_password"):
            user.must_change_password = bool(args.require_change)
        db.session.commit()
    ok(f"Password updated for '{username}'.")


def cmd_setup(args):
    """First-time app setup: .env → deps into the zone .venv → DB → (optionally) seed."""
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
             "database steps need one. Run `zone install` first.")
        return
    # Ask for the MariaDB password up front (here, where we're interactive),
    # save it to .env, and tell the initdb child not to prompt again.
    _prompt_db_password()
    os.environ["ZONE_DB_PROMPTED"] = "1"
    # initdb (+ seed) need the app code, so run them inside the zone's venv.
    if reexec_in_venv(ZONE, ROOT, ["initdb"]) != 0:
        die("Database initialization failed.")
    if args.seed and reexec_in_venv(ZONE, ROOT, ["seed"]) != 0:
        die("Seeding failed.")
    print("\nSetup done. Start the app with:  zone start   "
          "(or  zone launch  for the desktop window)")


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
    """Keep the background server alive with neither a window nor a browser."""
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


def _watch_app_files(root, on_change, interval=1.0):
    """Poll the app's source files; call on_change() whenever one changes.

    Generic for any app a zone runs — watches code/templates/static under the
    app dir, ignoring venv/git/cache folders.
    """
    import time
    exts = (".py", ".html", ".htm", ".css", ".js", ".jinja", ".jinja2", ".json")
    skip = {".venv", ".git", "__pycache__", "node_modules", ".zone", "backups"}

    def snapshot():
        snap = {}
        for dp, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in skip]
            for f in files:
                if f.endswith(exts):
                    p = os.path.join(dp, f)
                    try:
                        snap[p] = os.path.getmtime(p)
                    except OSError:
                        pass
        return snap

    prev = snapshot()
    while True:
        time.sleep(interval)
        try:
            cur = snapshot()
        except Exception:
            continue
        if cur != prev:
            prev = cur
            on_change()


def cmd_start(args):
    """Run an app in a native desktop window with live logs (and optional auto-reload).

    No browser: the UI opens in an embedded WebView2 window (via pywebview) while
    the dev server's request log streams to this console. With --reload, edits to
    the app's code/templates/static are picked up automatically and the window
    refreshes — works for any Flask app a zone serves. Close the window (or press
    Ctrl+C) to stop.
    """
    import threading
    # Track the zone CLI version: show current -> latest and nudge to upgrade.
    if not args.no_version_check:
        _check_zone_update()
    from config import Config
    host = args.host or Config.HOST
    port = _pick_port(host, args.port or Config.PORT)
    url_host = "127.0.0.1" if host in ("0.0.0.0", "", "::") else host
    url = f"http://{url_host}:{port}"

    serve_argv = ["start"]
    if args.port: serve_argv += ["--port", str(args.port)]
    if args.host: serve_argv += ["--host", args.host]
    if args.no_window: serve_argv.append("--no-window")
    if args.reload: serve_argv.append("--reload")
    _write_pidfile(os.getpid(), serve_argv)

    head(f"Starting {os.path.basename(ROOT)} — live logs below; "
         f"close the window (or Ctrl+C) to stop")
    print(f"  dev server: {url}" + ("   (auto-reload on edits)" if args.reload else ""))

    server_proc = None
    if args.reload:
        # Run the server as a subprocess so Werkzeug's reloader can restart it on
        # code edits without killing the window. Reuses `zone serve --reload`,
        # which works for any Flask app; its log streams to this console.
        cmd = [sys.executable, os.path.abspath(__file__), "serve", "--reload",
               "--port", str(port), "--host", host]
        server_proc = subprocess.Popen(cmd, cwd=ROOT,
                                       env=dict(os.environ, ZONE_IN_VENV="1"))
    else:
        # Serve in a daemon thread; the window owns the main thread.
        from app import app as flask_app
        threading.Thread(
            target=lambda: flask_app.run(host=host, port=port, debug=False,
                                         use_reloader=False, threaded=True),
            daemon=True,
        ).start()
    _wait_until_up(url)

    try:
        if args.no_window:
            _serve_block(url)
            return
        import webview
        title = getattr(Config, "STORE_NAME", None) or os.path.basename(ROOT)
        window = webview.create_window(title, url, width=1280, height=820,
                                       min_size=(1000, 680))
        if args.reload:
            def _refresh():
                _wait_until_up(url, timeout=8)   # let the server finish reloading
                try:
                    window.load_url(url)
                    print("↻ reloaded (change detected)")
                except Exception:
                    pass
            threading.Thread(target=_watch_app_files, args=(ROOT, _refresh),
                             daemon=True).start()
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
    except KeyboardInterrupt:
        pass  # Ctrl+C: fall through to a clean shutdown
    except ImportError:
        warn("pywebview isn't installed in this zone, so the desktop window can't open.")
        warn("Install the app's deps with `zone install`, then run `zone start` again.")
        _serve_block(url)
    except Exception as e:
        warn(f"Native window unavailable ({e}).")
        _serve_block(url)
    finally:
        if server_proc:                      # stop the reload subprocess + its child
            try: terminate_pid(server_proc.pid)
            except Exception: pass
        print("\nStopped.")
        if PID_FILE and os.path.isfile(PID_FILE):
            try: os.remove(PID_FILE)
            except OSError: pass


def cmd_restart(args):
    """Stop and relaunch the dev server recorded by `zone start`/`serve`."""
    head("Restarting dev server")
    argv = _stop_running_server()
    if argv is None:
        warn("No running dev server found (start one with `zone start`).")
        return
    _relaunch_serve(argv)
    ok(f"Relaunched: zone {' '.join(argv)} (in a new window).")


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
    if (has_venv(ZONE) and not os.environ.get("ZONE_IN_VENV")
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
        fail("No .venv for this zone (run `zone init` / `zone setup`).")
        problems += 1

    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    (ok if in_venv else warn)("Virtual environment active." if in_venv
                              else "Not in a virtualenv (recommended: .venv).")

    env_ok = os.path.isfile(os.path.join(ROOT, ".env"))
    (ok if env_ok else warn)(".env present." if env_ok else "No .env (run `zone setup`).")

    for mod in ("flask", "sqlalchemy", "pymysql", "dotenv", "waitress"):
        try:
            __import__(mod)
            ok(f"package: {mod}")
        except ImportError:
            fail(f"package missing: {mod} (run `zone install`)")
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
            warn(f"Database '{Config.DB_NAME}' not found (run `zone initdb`).")
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

    One-shot local update: bumps the version so the new build carries a fresh
    number, repackages the release zip/manifest, then rebuilds the installer.
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
            args.no_assets = True          # refresh does its own touch_static below
            args.skip_running_check = True  # refresh manages the server lifecycle
            cmd_migrate(args)
        except SystemExit:
            warn("Skipped migrate (database not reachable).")
    touch_static()
    if not args.no_restart:
        argv = _stop_running_server()
        if argv is None:
            warn("No running dev server to restart (start one with `zone start`).")
        else:
            _relaunch_serve(argv)
            ok(f"Relaunched: zone {' '.join(argv)} (in a new window).")
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
        prog="zone",
        description="Development CLI for ZT POS and apps built on it.",
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

    add("version", cmd_version, "Show zone CLI / Python / app versions.",
        needs_zone=False, needs_app=False, needs_venv=False)

    add("upgrade", cmd_upgrade, "Upgrade the zone CLI itself to the latest.",
        aliases=("self-update",), needs_zone=False, needs_app=False, needs_venv=False) \
        .add_argument("--force", action="store_true",
                      help="Reinstall even if already on the latest version.")

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
    sp = add("migrate", cmd_migrate,
             "Apply schema upgrades + refresh assets (app must be running).")
    sp.add_argument("app_name", nargs="?", help="App to migrate (default: the zone's app).")
    sp.add_argument("--no-assets", action="store_true",
                    help="Skip refreshing static assets (DB schema only).")
    add("seed", cmd_seed, "Insert sample products.")

    sp = add("set-db-password", cmd_set_db_password,
             "Set the MariaDB connection password in the app's .env.",
             aliases=("set-db-pass",), needs_venv=False)
    sp.add_argument("password", nargs="?", help="DB password (prompted if omitted).")
    sp.add_argument("--user", help="Also set DB_USER (e.g. root).")

    sp = add("set-admin-password", cmd_set_admin_password,
             "Set an app login user's password (default user 'admin').",
             aliases=("reset-admin",))
    sp.add_argument("password", nargs="?", help="New password (prompted if omitted).")
    sp.add_argument("--user", default="admin", help="Login username (default: admin).")
    sp.add_argument("--require-change", action="store_true",
                    help="Force a password change at next login.")

    sp = add("start", cmd_start,
             "Run an app: live logs + native window.  e.g. zone start zt-pos")
    sp.add_argument("app_name", nargs="?", help="App to run (default: the zone's app).")
    sp.add_argument("--port", type=int, help="Port (default from config).")
    sp.add_argument("--host", help="Host (default from config).")
    sp.add_argument("--no-window", action="store_true",
                    help="Don't open the desktop window; just serve with live logs.")
    sp.add_argument("--reload", action="store_true",
                    help="Auto-reload on code edits and refresh the window (local dev).")
    sp.add_argument("--no-version-check", action="store_true",
                    help="Skip the zone CLI update check on startup.")

    sp = add("serve", cmd_serve, "Run the Flask dev server headless (logs only, no window).")
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
    # `zone help` / `zone help <cmd>` → friendly usage (argparse uses -h/--help).
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
                "  Create one with:  zone init <name>\n"
                "  then add an app:  zone get <repo-url>")
        _set_zone(zone)

        if getattr(args, "needs_app", True):
            # Pick the app this command targets, move into it, import from it.
            # Precedence: positional (e.g. `zone start zt-pos`) > global --app > auto.
            explicit = getattr(args, "app_name", None) or getattr(args, "app", None)
            app_dir = resolve_app(zone, explicit=explicit)
            _set_app(app_dir)
            os.chdir(app_dir)
            if app_dir not in sys.path:
                sys.path.insert(0, app_dir)

            # Commands that import app code run under the zone's shared .venv.
            if (getattr(args, "needs_venv", True)
                    and not os.environ.get("ZONE_IN_VENV")
                    and not in_zone_venv(zone)):
                if not has_venv(zone):
                    die("This zone has no virtual environment yet — run `zone setup` first.")
                raise SystemExit(reexec_in_venv(zone, app_dir, raw))
        else:
            os.chdir(zone)  # zone-only commands (e.g. `get`) operate at the root

    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Ctrl+C anywhere: exit quietly with the conventional code, no traceback.
        print()
        raise SystemExit(130)
