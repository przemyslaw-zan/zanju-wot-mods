"""Shared on-disk storage helpers: AppData path resolution and atomic writes.

The window state (config.py) lives under a shared AppData parent so the modpack never
wipes it on reinstall:

    %APPDATA%/zanju_wot_mods_cache/directives-helper/window.json
"""
from __future__ import print_function, unicode_literals

import io
import os

from .constants import MOD_CONFIG_DIR_NAME

try:
    _text_type = unicode
except NameError:
    _text_type = str

# Shared parent for every Zanju WoT mod's AppData data; the per-mod subfolder keeps
# this mod's files separate from any future mod that reuses the same parent.
_DATA_ROOT_DIR_NAME = 'zanju_wot_mods_cache'


def resolve_mod_data_dir():
    base_dir = resolve_appdata_base_dir()
    if not base_dir:
        return None

    return os.path.join(base_dir, _DATA_ROOT_DIR_NAME, MOD_CONFIG_DIR_NAME)


def resolve_appdata_base_dir():
    for env_name in ('APPDATA', 'LOCALAPPDATA'):
        value = _normalize_path(os.environ.get(env_name))
        if value:
            return value

    user_profile = _normalize_path(os.environ.get('USERPROFILE'))
    if not user_profile:
        return None

    return os.path.join(user_profile, 'AppData', 'Roaming')


def atomic_write_text(path, text, logger):
    # Atomic write: serialise to a temp file (flush+fsync), then replace the target in one
    # step, so a crash mid-write can never leave a truncated/corrupt file. os.rename is atomic
    # on POSIX; on Windows Py2.7 it cannot overwrite, so fall back to remove-then-rename - the
    # live file is still never partially written, since the full content lands in the temp file
    # first.
    tmp = path + '.tmp'
    try:
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        with io.open(tmp, 'w', encoding='utf-8') as fh:
            fh.write(text)
            try:
                fh.flush()
                os.fsync(fh.fileno())
            except Exception:
                pass
        try:
            os.rename(tmp, path)
        except OSError:
            if os.path.exists(path):
                os.remove(path)
            os.rename(tmp, path)
        return True
    except Exception:
        logger.exception('Failed to write %s', path)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


def _normalize_path(value):
    text = _normalize_text(value)
    if text is None:
        return None
    return os.path.normpath(text)


def _normalize_text(value):
    if value is None:
        return None

    try:
        text = value if isinstance(value, _text_type) else _text_type(value)
    except Exception:
        return None

    text = text.strip()
    if not text:
        return None
    return text
