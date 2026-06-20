# Changelog

## v1.1.0

Self-contained zones, modelled on `frappe bench`. `zone init` now installs the
`zone` CLI into the new zone's `.venv`, and all commands that run app code
re-exec through that venv-local copy (`python -m zone`) instead of the global
`zone.py` file. Each zone is pinned to the CLI version it was created with and
no longer breaks if the global install moves or is removed.

- `zone init` installs the CLI into the zone `.venv` (skip with `--no-cli`); the
  install source — a local source checkout or `git+https://github.com/ZonalTech/Zone.git`
  — is recorded in `.zone/zone.json` as `cli_source`.
- `zone setup` / `zone install` backfill the venv-local CLI for zones created
  before this release.
- `zone upgrade` also refreshes the current zone's venv-local CLI so it stays in
  sync with the global install.

## v1.0.0

Initial release of the **zone** CLI.

The patch version is bumped automatically on **every commit** by the
`.githooks/pre-commit` hook (enable with `git config core.hooksPath .githooks`).
