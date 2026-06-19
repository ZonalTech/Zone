# Installing zonal & running an app on it

`zonal` is a small, **bench**-style CLI. You install it **once** on your
machine, then use `zonal get` to clone any app built on it (like **ZT POS**)
into an isolated *zone* and drive its whole dev lifecycle.

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

> No pipx yet? Install it once:
> ```bat
> py -m pip install --user pipx
> py -m pipx ensurepath
> ```
> Then **open a new terminal** so `PATH` picks up pipx.

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

Useful while developing:

```bat
zonal doctor        :: check Python, .venv, deps, DB, .env for this zone
zonal refresh       :: deps + migrate + cache-bust static + restart the server
zonal config        :: print effective config (password masked)
zonal help          :: full command list
```

---

## 5. Many zones on one machine

Because every command targets the zone containing your **current directory**
(zonal walks up looking for the app's `app.py` + `config.py`), you can run as
many side-by-side as you like — each with its own `.venv` and database:

```
C:\dev\
  store-a\     :: zonal get <repo> store-a   →  cd store-a   →  zonal setup  →  zonal start
  store-b\     :: zonal get <repo> store-b   →  cd store-b   →  zonal setup  →  zonal start
```

There is nothing to "switch" — just `cd` into the zone you want to work on.

---

## 6. Update or uninstall zonal

```bat
pipx upgrade zonal              :: after pulling new CLI source: pipx reinstall zonal
pipx uninstall zonal            :: remove the CLI (zones on disk are untouched)
```

(With a `pip --user` install, use `py -m pip install --user --upgrade path\to\zonal`
and `py -m pip uninstall zonal`.)

---

## 7. What makes an app "built on zonal"?

`zonal get` can clone **any** app, but the lifecycle commands expect a small
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
still gets `get` / `setup` (deps only) / `install` / `start` / `serve` /
`doctor` / `config` / `routes`.

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `zonal` not found after install | Reopen the terminal; run `pipx ensurepath`; or add the Scripts dir to `PATH`. |
| `Not inside a ZT POS zone` | `cd` into a cloned zone, or create one with `zonal get`. |
| `This zone has no virtual environment yet` | Run `zonal setup` (or `zonal install`) in that zone first. |
| `git was not found on PATH` | Install Git for Windows, reopen the terminal. |
| DB errors on `setup`/`start` | Ensure the app's database service (MariaDB for ZT POS) is running and the credentials in `.env` are correct — `zonal doctor` reports specifics. |
| Port already in use | `zonal start --port 5050` (or pick another free port). |

See [ZONAL.md](ZONAL.md) for the full command reference.
