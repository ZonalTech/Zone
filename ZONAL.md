# zonal — a bench-style dev CLI for ZT POS

`zonal` is a small command-line tool you install **once** on your machine. You
then use it to create and drive any number of independent ZT POS **zones** — one
cloned project each, with its own virtualenv and database — through their whole
dev lifecycle (set up, serve, migrate, seed, back up, build, release). Think of
it as a lightweight `bench` for ZT POS.

## 1. Install the CLI (once per machine)

From this `zonal/` folder, on Windows:

```bat
install.bat
```

This installs `zonal` with **pipx** (isolated, recommended) or falls back to
`pip install --user`. Open a **new** terminal so `PATH` refreshes, then check:

```bat
zonal --version
```

> Don't have pipx? `py -m pip install --user pipx && py -m pipx ensurepath`,
> then re-run `install.bat`. Or install manually: `pipx install path\to\zonal`.

## 2. Create a zone and start developing

```bat
zonal get https://github.com/<org>/zt-pos.git   :: clone a new zone
cd zt-pos
zonal setup --seed                               :: .env + .venv + deps + DB + samples
zonal start                                      :: dev server: live logs + reload + browser
```

First login: **admin / admin** (you'll be forced to change it).

`zonal start` runs in the foreground, streams the server log live, reloads on
code changes, and opens the POS in your browser. Press **Ctrl+C** to stop.

## How zonal finds a zone

Every command except `get` / `version` / `help` operates on the zone that
contains your **current directory** — zonal walks up from the CWD looking for a
ZT POS project (an `app.py` + `config.py` pair), exactly like `bench` finds its
bench root. You can keep as many zones as you like side by side:

```
C:\dev\
  store-a\      :: zonal get … store-a   (its own .venv + DB)
  store-b\      :: zonal get … store-b   (its own .venv + DB)
```

Commands that run POS code automatically re-exec inside that zone's `.venv`, so
zones stay isolated and you never have to activate a virtualenv by hand.

## Commands

| Command | What it does |
|---|---|
| `get REPO [DIR] [--branch B]` | Clone a ZT POS repo into a new zone (git clone wrapper). |
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
| `db` | Open the MariaDB client connected to the POS database. |
| `backup [-o FILE]` | Dump the database to `backups/<db>-<timestamp>.sql`. |
| `restore FILE [--yes]` | Restore the database from a `.sql` dump (**destructive**). |
| `reset-db [--seed] [--yes]` | Drop and recreate the database (**destructive**). |
| `doctor` | Check the zone: Python, `.venv`, deps, MariaDB, `.env`. |
| `config` | Print the effective configuration (password masked). |
| `routes` | List all registered URL routes. |
| `bump [part]` | Bump the version (`major`/`minor`/`patch`/`X.Y.Z`) and roll the changelog. |
| `build [app\|setup\|all]` | Build the **app payload** (`app`, default: POS.exe + release zip/manifest via `build-setup.bat`), the **setup file** (`setup`: installer via `build-online-setup.bat`), or `all`. |
| `update [part] [--no-bump] [--no-setup]` | **One-shot local update**: bump version → rebuild app payload → rebuild setup file. |
| `release` | Cut a GitHub release (delegates to `release-github.bat`). |
| `version` | Show zonal / Python / zone versions. |

Run `zonal help` or `zonal help <command>` for details.

## Build & update workflows

There are two distinct build outputs:

- **App payload** — `release/ZTPOS-<ver>.zip` + `manifest.json` (the compiled
  `POS.exe`). This is what the in-app updater and installer download.
- **Setup file** — `setup/ZTPOS-Online-Setup.exe`, the shippable installer.

```bat
:: Local development (fast, no PyInstaller) — after editing code/templates:
zonal refresh                :: deps + migrate + cache-bust static + restart server

:: Cut a new local build of everything, with a fresh version number:
zonal update                 :: bump patch → rebuild payload → rebuild setup file
zonal update minor           :: bump minor instead
zonal update --no-setup      :: only rebuild the app payload

:: Or run the raw builds individually:
zonal build app              :: POS.exe + release zip/manifest
zonal build setup            :: the installer only
zonal build all              :: both
```

`refresh` is for the **inner dev loop** — it never runs PyInstaller, so it's
fast. `update`/`build` are for producing **distributable artifacts**.

## How it relates to the existing scripts

`zonal` is a thin orchestrator — it reuses the project's existing modules
rather than reimplementing them:

- `initdb` → `init_db.py`   • `migrate` → `migrate.py`   • `seed` → `seed.py`
- `launch` → `launcher.serve()`   • `bump` → `bump_version.py`
- `build` / `release` → the existing `.bat` files
- DB connection + config come from `config.py` (`.env`)

Those scripts still work standalone; `zonal` just gives them one consistent
front door, and adds zone management (`get`/`setup`) and an isolated `.venv`
per zone on top.

## How the CLI is packaged

`zonal` is a single pure-stdlib module (`zonal.py`) exposed as a console script
via `pyproject.toml`. It carries **no** dependencies of its own — each zone's
Flask/SQLAlchemy/etc. live in that zone's `.venv`, created by `zonal setup`.
