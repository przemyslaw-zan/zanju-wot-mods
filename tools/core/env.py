"""Resolve repo tooling configuration from the environment, overlaid on .env.

`os.environ` takes precedence over the repo-root `.env` file, so the Dev
Container's container environment (e.g. `WOT_GAME_DIR=/game`) is authoritative
without a hand-written `.env`, while a local `.env` still works outside
containers.
"""

import io
import os

from .paths import ENV_PATH


def _read_env_file(path):
    env = {}
    if not path or not os.path.isfile(path):
        return env
    with io.open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def load_env(path=ENV_PATH):
    env = _read_env_file(path)
    env.update(os.environ)
    return env


def subprocess_env(extra=None):
    """Environment for a child process, with bytecode writing disabled.

    Python 2.7 writes `foo.pyc` beside `foo.py`, so every test or lint run used to leave
    bytecode scattered through `mods/*/src/` and `tools/`. Those files are gitignored, which
    is what let them go unnoticed -- and a stale one shadows the source it was built from,
    producing test results that do not match the code on disk. Worse, a `.pyc` whose `.py` has
    since moved stays importable under Python 2, so dead modules keep resolving.

    Set on the child rather than globally: the parent's own `__pycache__` is wanted.
    """
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra:
        env.update(extra)
    return env
