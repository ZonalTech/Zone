# zonal — a bench-style dev CLI

`zonal` is a small command-line tool you install **once** on your machine. You
then use it to create and drive any number of independent app **zones** — one
cloned project each, with its own virtualenv and database — through their whole
dev lifecycle (set up, serve, migrate, seed, back up, build, release). Think of
it as a lightweight `bench`: it can run any app built to its contract, with
**ZT POS** as the reference app.

```
install zonal  ──►  zonal get <app repo>  ──►  zonal setup  ──►  zonal start
   (once)            (clone a zone)            (.venv+DB)        (run + live logs)
```

---

## 1. Prerequisites

| Need | Why | Check |
|---|---|---|
| **Python 3.9+** | zonal runs on it; it builds each zone's `.venv` from it | `py --version` |
| **Git** | `zonal get` is a `git clone` wrapper | `git --version` |
| **pipx** *(recommended)* | installs zonal isolated + on `PATH` | `pipx --version` |
| App-specific services | e.g. ZT POS needs **MariaDB/MySQL** running | see the app's README |

> No pipx yet? Install it once, then **open a new terminal** so `PATH` updates:
> ```bat
> py -m pip install --user pipx
> py -m pipx ensurepath
> ```

---

## 2. Install zonal locally

You have the `zonal/` source folder on disk (this directory). Install from it.

### Option A — pipx (recommended)

```bat
cd path\to\zonal
install.bat
```

`install.bat` runs `pipx install` (or falls back to `pip install --user` if
pipx is missing). Equivalent manual command:

```bat
pipx install path\to\zonal
```

### Option B — pip into your current Python

```bat
py -m pip install --user path\to\zonal
```

### Option C — editable/dev install (if you're hacking on zonal itself)

```bat
py -m pip install -e path\to\zonal
```
Changes to `zonal.py` take effect immediately, no reinstall.

### Verify

Open a **new** terminal (so `PATH` refreshes) and run:

```bat
zonal --version
```
You should see the zonal CLI version and your Python version.

> **Windows PATH note:** if `zonal` isn't found after install, the Scripts
> directory isn't on `PATH`. With pipx, run `pipx ensurepath` and reopen the
> terminal. With `pip --user`, add your user `Scripts` folder
> (`py -m site --user-base` → `…\Python3xx\Scripts`) to `PATH`.

---

## 3. Get an app (e.g. ZT POS)

`zonal get` clones an app repo into a new **zone** — a self-contained project
directory with its own virtualenv and database.

```bat
zonal get https://github.com/<org>/zt-pos.git
```

Options:

```bat
zonal get <repo-url> mystore        :: clone into folder "mystore" instead of the repo name
zonal get <repo-url> --branch dev   :: clone a specific branch or tag
```

`get` works from **any** directory and doesn't need a zone to already exist —
it's how you create one. After cloning it prints the next steps.

---

## 4. Set up and run the zone

```bat
cd zt-pos
zonal setup --seed
zonal start
```

- **`zonal setup --seed`** — first-time setup for this zone: copies `.env`,
  creates a `.venv`, installs the app's dependencies into it, creates the
  database + default admin, and inserts sample data (`--seed` is optional).
- **`zonal start`** — runs the dev server in the foreground with **live logs**,
  **auto-reload** on code changes, and **opens the app in your browser**.
  Press **Ctrl+C** to stop.

For ZT POS the first login is **admin / admin** (you'll be forced to change it).

---

## 5. How zonal finds a zone

Every command except `get` / `version` / `help` operates on the zone that
contains your **current directory** — zonal walks up from the CWD looking for an
app project (an `app.py` + `config.py` pair), exactly like `bench` finds its
bench root. Commands that run app code automatically re-exec inside that zone's
`.venv`, so zones stay isolated and you never activate a virtualenv by hand.

Because of this, you can keep as many zones side by side as you like — there's
nothing to "switch", just `cd` into the one you want:

```
C:\dev\
  store-a\     :: zonal get <repo> store-a   →  cd store-a   →  zonal setup  →  zonal start
  store-b\     :: zonal get <repo> store-b   →  cd store-b   →  zonal setup  →  zonal start
```

---

## 6. Commands

| Command | What it does |
|---|---|
| `get REPO [DIR] [--branch B]` | Clone an app repo into a new zone (git clone wrapper). |
| `setup [--seed] [--skip-install]` | First-time setup for the current zone: `.env` → `.venv` + deps → database → optional sample data. |
| `install [--build]` | Create the zone `.venv` and install runtime deps (`requirements.txt`); `--build` also installs build deps. |
| `initdb` | Create the database, all tables, and the default admin (idempotent). |
| `migrate` | Apply idempotent schema upgrades to an existing database. |
| `seed` | Insert sample products (safe to re-run). |
| `start [--port] [--host] [--no-reload] [--no-browser] [--prod]` | **Everyday dev server**: foreground, live logs, auto-reload, opens the app in your browser. |
| `serve [--port] [--host] [--reload] [--prod]` | Lower-level dev server (no auto-open browser). `--prod` uses waitress. |
| `launch` | Run the full desktop app in a native window (via `launcher.py`). |
| `restart` | Stop and relaunch the dev server started by `zonal start`/`serve`. |
| `refresh [--no-deps] [--no-migrate] [--no-restart]` | **Fast local-dev cycle** (no PyInstaller): install deps → migrate DB → cache-bust static → restart the dev server. |
| `shell` | Python REPL with an active app context; `app`, `db`, `models` preloaded. |
| `db` | Open the MariaDB client connected to the app database. |
| `backup [-o FILE]` | Dump the database to `backups/<db>-<timestamp>.sql`. |
| `restore FILE [--yes]` | Restore the database from a `.sql` dump (**destructive**). |
| `reset-db [--seed] [--yes]` | Drop and recreate the database (**destructive**). |
| `doctor` | Check the zone: Python, `.venv`, deps, MariaDB, `.env`. |
| `config` | Print the effective configuration (password masked). |
| `routes` | List all registered URL routes. |
| `bump [part]` | Bump the version (`major`/`minor`/`patch`/`X.Y.Z`) and roll the changelog. |
| `build [app\|setup\|all]` | Build the **app payload** (POS.exe + release zip/manifest via `build-setup.bat`), the **setup file** (installer via `build-online-setup.bat`), or `all`. |
| `update [part] [--no-bump] [--no-setup]` | **One-shot local update**: bump version → rebuild app payload → rebuild setup file. |
| `release` | Cut a GitHub release (delegates to `release-github.bat`). |
| `version` | Show zonal / Python / zone versions. |

Run `zonal help` or `zonal help <command>` for details.

### Build & update workflows (ZT POS)

There are two distinct build outputs:

- **App payload** — `release/ZTPOS-<ver>.zip` + `manifest.json` (the compiled
  `POS.exe`). This is what the in-app updater and installer download.
- **Setup file** — `setup/ZTPOS-Online-Setup.exe`, the shippable installer.

```bat
zonal refresh                :: inner dev loop: deps + migrate + cache-bust static + restart
zonal update                 :: bump patch → rebuild payload → rebuild setup file
zonal update minor           :: bump minor instead
zonal update --no-setup      :: only rebuild the app payload
zonal build app|setup|all    :: run the raw builds individually
```

`refresh` never runs PyInstaller, so it's fast; `update`/`build` produce
distributable artifacts.

---

## 7. What makes an app "built on zonal"?

`zonal get` can clone **any** repo, but the lifecycle commands expect a small
contract. An app is zonal-compatible when its repo root provides:

### Required (zone detection + serving)

| File | Must expose | Used by |
|---|---|---|
| `app.py` | a Flask `app` object | zone detection, `start`, `serve`, `routes`, `shell` |
| `config.py` | `Config` (with `HOST`, `PORT`, `DB_*`, `SQLALCHEMY_DATABASE_URI`) and `server_uri()` | zone detection, `config`, `db`, `backup`, `doctor` |
| `requirements.txt` | runtime dependencies | `setup`, `install`, `refresh` |

> The **presence of `app.py` + `config.py`** in a directory is exactly what
> marks it as a zone. That's the minimum to be discovered.

### Optional (unlock more commands)

| File | Must expose | Unlocks |
|---|---|---|
| `.env.example` | sample env | `setup` copies it to `.env` |
| `init_db.py` | `create_database()`, `create_tables()`, `ensure_default_admin()`, `DEFAULT_ADMIN` | `initdb` |
| `migrate.py` | `create_new_tables()`, `upgrade_*()` | `migrate` |
| `seed.py` | `run()` | `seed` |
| `models.py` | `db` | `shell` |
| `provision.py` | `can_connect(uri)` | `doctor` DB checks |
| `launcher.py` | `serve()` | `launch` (desktop window) |
| `bump_version.py` | `main()` | `bump`, `update` |
| `VERSION` | version string | `version`, `update` |
| `build-setup.bat`, `build-online-setup.bat`, `release-github.bat` | — | `build`, `update`, `release` |

ZT POS implements all of the above, which is why every `zonal` command works on
it. A leaner app that only ships `app.py`, `config.py`, and `requirements.txt`
still gets `get` / `setup` / `install` / `start` / `serve` / `doctor` /
`config` / `routes`.

---

## 8. Update or uninstall zonal

```bat
pipx reinstall zonal            :: after pulling new CLI source
pipx uninstall zonal            :: remove the CLI (zones on disk are untouched)
```

(With a `pip --user` install: `py -m pip install --user --upgrade path\to\zonal`
and `py -m pip uninstall zonal`.)

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `zonal` not found after install | Reopen the terminal; run `pipx ensurepath`; or add the Scripts dir to `PATH`. |
| `Not inside a ZT POS zone` | `cd` into a cloned zone, or create one with `zonal get`. |
| `This zone has no virtual environment yet` | Run `zonal setup` (or `zonal install`) in that zone first. |
| `git was not found on PATH` | Install Git for Windows, reopen the terminal. |
| DB errors on `setup`/`start` | Ensure the app's database service (MariaDB for ZT POS) is running and the credentials in `.env` are correct — `zonal doctor` reports specifics. |
| Port already in use | `zonal start --port 5050` (or pick another free port). |

---

## How the CLI is packaged

`zonal` is a single pure-stdlib module (`zonal.py`) exposed as a console script
via `pyproject.toml`. It carries **no** dependencies of its own — each zone's
Flask/SQLAlchemy/etc. live in that zone's `.venv`, created by `zonal setup`.
