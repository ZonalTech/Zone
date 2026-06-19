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

## Create a zone (also scaffolds a starter app)

```bat
zone init mystore        # creates mystore/.venv + apps/mystore (starter app)
cd mystore
zone start mystore       # runs the starter app immediately
zone init mystore --no-app   # ...or skip the starter app
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
zone init [NAME] [--app-name N] [--no-app]   # also scaffolds a starter app in apps/
zone new NAME                      # scaffold another minimal app in apps/
zone get REPO [NAME] [--branch B]
zone setup [APP] [--seed] [--skip-install]
zone install [--build]
zone initdb
zone migrate [APP] [--no-assets]   # app must be running (zone start)
zone seed
zone set-db-password ["password"] [--user root]
zone set-admin-password ["password"] [--user admin] [--require-change]
zone start [APP] [--reload] [--port] [--host] [--no-window] [--no-version-check]
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
zone upgrade [--force]
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
