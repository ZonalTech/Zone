#!/usr/bin/env python3
"""Weekly version bump for the zone CLI.

Combines every commit since the last release tag into a CHANGELOG entry, bumps
the PATCH version (1.0.0 -> 1.0.1 -> ...) in pyproject.toml and zone.py, then
commits and tags `vX.Y.Z`. Run by the weekly GitHub Actions schedule; also
runnable locally. Pushing is left to the workflow.

Exits without changes (and sets bumped=false) when there are no new commits
since the last release, so an empty week never produces a release.
"""
import datetime
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, check=check).stdout.strip()


def gh_output(key, value):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")


def read_version():
    text = open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8").read()
    m = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', text)
    if not m:
        sys.exit("Could not find version in pyproject.toml")
    return m.group(1)


def bump_patch(version):
    parts = (version.split(".") + ["0", "0", "0"])[:3]
    major, minor, patch = (int(re.sub(r"\D", "", p) or 0) for p in parts)
    return f"{major}.{minor}.{patch + 1}"


def last_release_tag():
    try:
        return git("describe", "--tags", "--abbrev=0", "--match", "v*", check=True)
    except subprocess.CalledProcessError:
        return None


def commits_since(tag):
    rng = f"{tag}..HEAD" if tag else "HEAD"
    log = git("log", rng, "--no-merges", "--pretty=format:- %s (%h)", check=False)
    lines = [ln for ln in log.splitlines() if ln.strip()]
    # Ignore the automated release commits themselves.
    return [ln for ln in lines if "chore(release)" not in ln.lower()]


def replace_in_file(rel, pattern, repl):
    path = os.path.join(ROOT, rel)
    text = open(path, encoding="utf-8").read()
    new, n = re.subn(pattern, repl, text, count=1)
    if not n:
        sys.exit(f"Version pattern not found in {rel}")
    open(path, "w", encoding="utf-8").write(new)


def prepend_changelog(version, commits):
    date = os.environ.get("RELEASE_DATE") or datetime.date.today().isoformat()
    entry = f"## v{version} — {date}\n\n" + "\n".join(commits) + "\n\n"
    path = os.path.join(ROOT, "CHANGELOG.md")
    existing = open(path, encoding="utf-8").read() if os.path.exists(path) else "# Changelog\n\n"
    if existing.startswith("# "):
        head, _, rest = existing.partition("\n")
        existing = head + "\n\n" + entry + rest.lstrip("\n")
    else:
        existing = "# Changelog\n\n" + entry + existing
    open(path, "w", encoding="utf-8").write(existing)


def main():
    current = read_version()
    tag = last_release_tag()
    commits = commits_since(tag)
    if not commits:
        print(f"No new commits since {tag or 'the start'} — nothing to release.")
        gh_output("bumped", "false")
        return

    new = bump_patch(current)
    print(f"Releasing v{new} ({len(commits)} commit(s) since {tag or 'the start'}):")
    print("\n".join(commits))

    replace_in_file("pyproject.toml",
                    r'(?m)^(\s*version\s*=\s*")[^"]+(")', rf"\g<1>{new}\g<2>")
    replace_in_file("zone.py",
                    r'(?m)^(ZONE_VERSION\s*=\s*")[^"]+(")', rf"\g<1>{new}\g<2>")
    prepend_changelog(new, commits)

    git("add", "pyproject.toml", "zone.py", "CHANGELOG.md")
    subprocess.run(["git", "commit", "-m", f"chore(release): v{new} [skip ci]"],
                   cwd=ROOT, check=True)
    subprocess.run(["git", "tag", "-a", f"v{new}", "-m", f"Release v{new}"],
                   cwd=ROOT, check=True)
    print(f"Bumped {current} -> {new} and tagged v{new}.")
    gh_output("bumped", "true")
    gh_output("version", new)


if __name__ == "__main__":
    main()
