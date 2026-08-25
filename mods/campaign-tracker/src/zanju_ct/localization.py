"""Runtime localization loader for campaign-tracker.

Translations ship inside the `.wotmod` at `res/mods/<MOD_ID>/text/<lang>.yml`. The WoT
client mounts a package's `res/` at the root of its virtual resource filesystem, so the files
are read through `ResMgr` at the VFS path `mods/<MOD_ID>/text/<lang>.yml` (no `res/` prefix).
The client UI language selects the file, with English merged underneath as a fallback. There
is no loose on-disk localisation source and no per-mod language override.
"""
from __future__ import absolute_import, print_function, unicode_literals

import json
import logging

from .constants import MOD_ID

try:
    import ResMgr
except Exception:
    ResMgr = None

try:
    import helpers as _wg_helpers
except Exception:
    _wg_helpers = None

try:
    from helpers import i18n as _wg_i18n
except Exception:
    _wg_i18n = None


_logger = logging.getLogger('zanju.campaigntracker.i18n')
_DEFAULT_LANGUAGE = 'en'
_TEXT_DOMAIN = 'mods/{0}/text'.format(MOD_ID)
_bundle_cache = {}


def get_text(key, **format_kwargs):
    text = _get_active_bundle().get(key)
    if text is None:
        text = key

    if format_kwargs:
        try:
            text = text.format(**format_kwargs)
        except Exception:
            _logger.exception('Failed to format localized text for key %s', key)
    return text


def make_tooltip(header_key, body_key):
    return (
        '{HEADER}'
        + get_text(header_key)
        + '{/HEADER}{BODY}'
        + get_text(body_key)
        + '{/BODY}'
    )


def _get_active_bundle():
    languages = (_DEFAULT_LANGUAGE, _detect_client_language())
    bundle = _bundle_cache.get(languages)
    if bundle is not None:
        return bundle

    bundle = {}
    for language_code in languages:
        if language_code:
            bundle.update(_load_bundle(language_code))
    _bundle_cache[languages] = bundle
    return bundle


def _detect_client_language():
    # helpers.getClientLanguage() is the canonical client UI language code (e.g. 'en', 'pl').
    for source, attr in (
        (_wg_helpers, 'getClientLanguage'),
        (_wg_i18n, 'getLanguageCode'),
        (_wg_i18n, 'getCurrentLanguage'),
    ):
        getter = getattr(source, attr, None) if source is not None else None
        if not callable(getter):
            continue
        try:
            normalized = _normalize_language_code(getter())
        except Exception:
            continue
        if normalized:
            return normalized
    return _DEFAULT_LANGUAGE


def _normalize_language_code(value):
    if not value:
        return None
    try:
        text = '{0}'.format(value)
    except Exception:
        return None
    normalized = text.strip().lower().replace('-', '_')
    if '.' in normalized:
        normalized = normalized.split('.', 1)[0]
    return normalized or None


def _load_bundle(language_code):
    path = '{0}/{1}.yml'.format(_TEXT_DOMAIN, language_code)
    raw = _vfs_read_text(path)
    if not raw:
        return {}
    try:
        return _parse_flat_yaml(raw)
    except Exception:
        _logger.exception('Failed to parse localization resource %s', path)
        return {}


def _vfs_read_text(path):
    """Read a UTF-8 text resource from the mounted package VFS, or None if absent."""
    if ResMgr is None:
        return None

    try:
        section = ResMgr.openSection(path)
        if section is None or not ResMgr.isFile(path):
            return None
        raw = section.asBinary
    except Exception:
        _logger.exception('Failed to read localization resource %s', path)
        return None

    try:
        return bytes(raw).decode('utf-8').lstrip('\ufeff')
    except Exception:
        _logger.exception('Failed to decode localization resource %s', path)
        return None


def _parse_flat_yaml(text):
    data = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or ':' not in line:
            continue

        key, raw_value = line.split(':', 1)
        key = key.strip()
        value = raw_value.strip()
        if not key:
            continue
        if not value:
            # An empty value marks a key awaiting translation; skip it so the English
            # fallback (merged underneath) stays in effect.
            continue

        if value.startswith('"') and value.endswith('"'):
            try:
                decoded = json.loads(value)
            except Exception:
                pass
            else:
                if decoded:
                    data[key] = decoded
                continue

        if value.startswith("'") and value.endswith("'"):
            if value[1:-1]:
                data[key] = value[1:-1]
            continue

        data[key] = value
    return data
