# zone

A small, bench-style development CLI for ZT POS and any application built on it.

Create isolated **zones**, add applications to them, and drive the full
development lifecycle — set up, run, migrate, back up, build, and release — from
a single command.

![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)
![Dependencies](https://img.shields.io/badge/dependencies-none%20(stdlib)-success)

---

## Overview

- **Zones** — each is a workspace with its own shared `.venv` and an `apps/` folder.
- **One-command setup** — `zone init` scaffolds a runnable starter app instantly.
- **Native development window** — `zone start` runs the app in a desktop window with live logs (no browser).
- **Live reload** — `zone start --reload` picks up code and template edits automatically.
- **Self-contained zones** — like a frappe bench, `zone init` installs the CLI into the zone's own `.venv`, pinning each zone to the version it was created with.
- **Develop the framework** — `zone init --dev` clones this CLI into the zone (`framework/`, installed editable) so you can hack on `zone` itself, with edits live.
- **No dependencies of its own** — `zone` is pure stdlib; each app's packages live in its zone's `.venv`.

---

## Prerequisites

| Requirement | Purpose | Source |
|-------------|---------|--------|
| **Python 3.9+** (with pip) | Runs the CLI and builds each zone's `.venv` | [python.org](https://python.org) — enable *Add to PATH* |
| **Git** | Required for `pip install git+…` and `zone get` | [git-scm.com](https://git-scm.com) |
| **MariaDB / MySQL** | Only for applications that use a database (e.g. ZT POS) | [mariadb.org](https://mariadb.org) |

> `zone` installs no Python packages of its own. Each application's dependencies
> are installed into its zone's `.venv` automatically by `zone setup`.

---

## Installation

Install the CLI **globally**, once, from GitHub (no clone needed):

```bat
py -m pip install "git+https://github.com/ZonalTech/Zone.git"
py -m zone --version
```

The one-time `py -m zone --version` registers `zone` on your `PATH`. After that,
use plain `zone` commands from any directory.

This global install is the bootstrapper — much like `pip install frappe-bench`.
From there, `zone init <name>` installs the CLI into that zone's own `.venv`, so
each zone is self-contained and pinned to the version it was created with
(pass `--no-cli` to opt out and use the global CLI for a zone instead).

---

## Quick start

```bat
zone init mystore        :: create a zone and a runnable starter app
cd mystore
zone start mystore       :: open it in a native window with live logs
```

To use an existing application instead of the starter:

```bat
zone get https://github.com/ZonalTech/<your-app>.git
zone setup <your-app> --seed
zone start <your-app>
```

---

## Developing the framework

To work on the CLI itself, create a **dev zone**. `--dev` clones this framework
into `framework/` and installs it **editable**, so the in-zone `zone` runs from
that checkout and your edits to `framework/zone.py` take effect immediately — no
starter template; add real apps afterwards with `zone get`.

```bat
zone init zonedev --dev                              :: clone framework/ (editable)
cd zonedev
zone get https://github.com/ZonalTech/zt-pos.git     :: add an app to test against
zone start zt-pos --reload                            :: run it; edits to the CLI are live
```

A dev zone's layout:

```
zonedev/
|- .venv/                <- framework installed editable (-e framework)
|- .zone/zone.json       <- {"dev": true, ...}
|- framework/            <- git checkout of this CLI (edit me)
`- apps/                 <- empty until `zone get`
```

---

## Build and release an app

Run from inside an app, or from anywhere in the zone with `zone --app <name> …`.
These wrap the app's own build/release scripts:

```bat
zone build                 :: build the app payload (e.g. POS.exe + release zip + manifest)
zone build setup           :: build the installer
zone build all             :: both

zone bump                  :: bump the patch version + changelog (also: minor | major | X.Y.Z)
zone update                :: bump version + rebuild app payload + rebuild installer
zone update minor          :: same, bumping the minor version
zone update --no-bump      :: rebuild at the current version
zone update --no-setup     :: skip rebuilding the installer

zone release               :: publish a GitHub release
```

Typical ship flow:  `zone update`  →  `zone release`.

---

## Zones and applications

A **zone** is a workspace; **applications** live inside it and share the zone's `.venv`:

```
mystore/                 <- the zone (zone init mystore)
|- .venv/                <- one shared environment
|- .zone/zone.json       <- zone marker
`- apps/
   |- mystore/           <- the starter app
   `- zt-pos/            <- zone get <repo>
```

Every command (except `init`, `get`, `version`, `upgrade`, and `help`) operates
on the zone containing the current directory. It selects the target application
by:

1. the name you pass — `zone start zt-pos`;
2. the application folder you are in; otherwise
3. the zone's only application; otherwise
4. `zone --app <name> <command>` when several are present.

---

## Commands

### Zones and applications

| Command | Description |
|---------|-------------|
| `zone init [NAME] [--app-name N] [--no-app] [--no-cli] [--dev]` | Create a zone (`.venv` with the zone CLI installed into it, plus a starter app). `--no-cli` skips installing the CLI into the `.venv`; `--no-app` skips the starter app; `--dev` clones the framework into `framework/` and installs it editable (no starter app) for working on the CLI itself. |
| `zone new NAME` | Scaffold another minimal application into `apps/`. |
| `zone get REPO [NAME] [--branch B]` | Clone an application from GitHub into `apps/`. |
| `zone setup [APP] [--seed] [--skip-install]` | `.env`, dependencies, database, and optional sample data. |
| `zone install [--build]` | Install the application's dependencies into the zone `.venv`. |

### Run and develop

| Command | Description |
|---------|-------------|
| `zone start [APP] [--reload] [--port] [--host] [--no-window]` | Native window with live logs; `--reload` for live edits. |
| `zone serve [--port] [--host] [--reload] [--prod]` | Headless development server (logs only). |
| `zone launch` | Run the application's desktop entry point via `launcher.py`. |
| `zone restart` / `zone refresh` | Restart, or run dependencies, migration, assets, and restart. |
| `zone shell` / `zone routes` / `zone config` | Application REPL, list routes, print configuration. |

### Database

| Command | Description |
|---------|-------------|
| `zone initdb` / `zone migrate [APP]` / `zone seed` | Create schema; upgrade and refresh assets (application must be running); sample data. |
| `zone set-db-password ["pw"] [--user root]` | Set the MariaDB password in the application's `.env`. |
| `zone set-admin-password ["pw"] [--user admin] [--require-change]` | Reset an application login user's password. |
| `zone db` / `zone backup [-o FILE]` / `zone restore FILE` / `zone reset-db` | Database client, dump, restore, and drop-and-recreate. |

### Build, release, and the CLI

| Command | Description |
|---------|-------------|
| `zone bump [part]` / `zone build [app\|setup\|all]` / `zone update` / `zone release` | Version, build artifacts, one-shot update, and GitHub release. |
| `zone doctor` | Check Python, `.venv`, dependencies, database, and `.env`. |
| `zone version` / `zone upgrade [--force]` | Show versions; update the CLI itself. |
| `zone help [command]` | Detailed help. |

---

## Update and uninstall

Update the CLI to the latest version:

```bat
zone upgrade
```

Uninstall:

```bat
py -m pip uninstall zone
```

---

Built by Zonal Tech. Run `zone --help` for the complete command reference.
