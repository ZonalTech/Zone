# zone — a dev CLI

## Install

```bat
py -m pip install "git+https://github.com/ZonalTech/Zone.git"
zone --version
```

## New machine, start to finish

```bat
py -m pip install "git+https://github.com/ZonalTech/Zone.git"
zone init mystore
cd mystore
zone get https://github.com/ZonalTech/<your-app>.git
zone setup --seed
zone start
```

## Create a zone

```bat
zone init mystore
cd mystore
```

## Get an app

```bat
zone get https://github.com/ZonalTech/<your-app>.git
zone get https://github.com/ZonalTech/<your-app>.git pos
zone get https://github.com/ZonalTech/<your-app>.git --branch dev
```

## Set up and run (from the zone — name the app)

```bat
zone setup zt-pos --seed
zone start zt-pos
```

## Commands

```
zone init [NAME]
zone get REPO [NAME] [--branch B]
zone setup [APP] [--seed] [--skip-install]
zone install [--build]
zone initdb
zone migrate
zone seed
zone start [APP] [--port] [--host] [--no-window]
zone serve [--port] [--host] [--reload] [--prod]
zone launch
zone restart
zone refresh [--no-deps] [--no-migrate] [--no-restart]
zone shell
zone db
zone backup [-o FILE]
zone restore FILE [--yes]
zone reset-db [--seed] [--yes]
zone doctor
zone config
zone routes
zone bump [part]
zone build [app|setup|all]
zone update [part] [--no-bump] [--no-setup]
zone release
zone version
zone --app NAME <command>
zone help [command]
```

## Build & update

```bat
zone refresh
zone update
zone update minor
zone update --no-setup
zone build app|setup|all
```

## Update or uninstall zone

```bat
py -m pip install --user --upgrade "git+https://github.com/ZonalTech/Zone.git"
py -m pip uninstall zone
```
