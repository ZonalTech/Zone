#!/usr/bin/env python3
"""Bump the PATCH version in pyproject.toml and zone.py (no git operations).

Called by the pre-commit hook so every commit carries a new version
(1.0.0 -> 1.0.1 -> 1.0.2 ...). Keeps ZONE_VERSION and pyproject in sync.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_version():
    text = open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8").read()
    m = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else None


def bump_patch(version):
    parts = (version.split(".") + ["0", "0", "0"])[:3]
    nums = [int(re.sub(r"\D", "", p) or "0") for p in parts]
    nums[2] += 1
    return ".".join(str(n) for n in nums)


def replace_in_file(rel, pattern, repl):
    path = os.path.join(ROOT, rel)
    text = open(path, encoding="utf-8").read()
    new, n = re.subn(pattern, repl, text, count=1)
    if n:
        open(path, "w", encoding="utf-8").write(new)
    return n


def main():
    current = read_version()
    if not current:
        sys.exit("bump_patch: version not found in pyproject.toml")
    new = bump_patch(current)
    replace_in_file("pyproject.toml",
                    r'(?m)^(\s*version\s*=\s*")[^"]+(")', rf"\g<1>{new}\g<2>")
    replace_in_file("zone.py",
                    r'(?m)^(ZONE_VERSION\s*=\s*")[^"]+(")', rf"\g<1>{new}\g<2>")
    print(f"version bumped {current} -> {new}")


if __name__ == "__main__":
    main()
