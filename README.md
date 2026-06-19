# zonal — a bench-style dev CLI

## Install

```bat
py -m pip install "git+https://github.com/ZonalTech/Zonal.git"
zonal --version
```

## New machine, start to finish

```bat
py -m pip install "git+https://github.com/ZonalTech/Zonal.git"
zonal init mystore
cd mystore
zonal get https://github.com/ZonalTech/<your-app>.git
zonal setup --seed
zonal start
```

## Create a zone

```bat
zonal init mystore
cd mystore
```

## Get an app

```bat
zonal get https://github.com/ZonalTech/<your-app>.git
zonal get https://github.com/ZonalTech/<your-app>.git pos
zonal get https://github.com/ZonalTech/<your-app>.git --branch dev
```

## Set up and run (from the zone — name the app)

```bat
zonal setup zt-pos --seed
zonal start zt-pos
```

## Commands

```
zonal init [NAME]
zonal get REPO [NAME] [--branch B]
zonal setup [APP] [--seed] [--skip-install]
zonal install [--build]
zonal initdb
zonal migrate
zonal seed
zonal start [APP] [--port] [--host] [--no-window]
zonal serve [--port] [--host] [--reload] [--prod]
zonal launch
zonal restart
zonal refresh [--no-deps] [--no-migrate] [--no-restart]
zonal shell
zonal db
zonal backup [-o FILE]
zonal restore FILE [--yes]
zonal reset-db [--seed] [--yes]
zonal doctor
zonal config
zonal routes
zonal bump [part]
zonal build [app|setup|all]
zonal update [part] [--no-bump] [--no-setup]
zonal release
zonal version
zonal --app NAME <command>
zonal help [command]
```

## Build & update

```bat
zonal refresh
zonal update
zonal update minor
zonal update --no-setup
zonal build app|setup|all
```

## Update or uninstall zonal

```bat
py -m pip install --user --upgrade "git+https://github.com/ZonalTech/Zonal.git"
py -m pip uninstall zonal
```
