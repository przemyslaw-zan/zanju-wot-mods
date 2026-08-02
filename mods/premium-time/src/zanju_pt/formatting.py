# -*- coding: utf-8 -*-
"""Time helpers shared by the header and tooltip integrations.

Pure-ish helpers: the only WoT imports are done lazily so failures degrade to
sensible fallbacks instead of breaking the caller.
"""
from __future__ import print_function, unicode_literals

import time

from .localization import get_text as _loc


def server_now():
    """Current time as epoch seconds, server-synced when the client exposes it."""
    try:
        from helpers import time_utils
        timestamp = time_utils.getCurrentTimestamp()
        if timestamp:
            return float(timestamp)
    except Exception:
        pass
    return time.time()


def server_time_offset():
    """Seconds to add to the client clock to approximate server time (constant per session)."""
    return server_now() - time.time()


def format_end_datetime(timestamp):
    """Format an epoch timestamp as a localized "date time" string, seconds included."""
    try:
        from gui.impl import backport
        date_str = backport.getLongDateFormat(timestamp)
        # The regional long time format includes seconds; the short one does not.
        time_str = backport.getLongTimeFormat(timestamp)
        if date_str and time_str:
            return '{0} {1}'.format(date_str, time_str)
    except Exception:
        pass
    try:
        return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
    except Exception:
        return ''


def utc_offset_label(timestamp):
    """UTC offset designation (e.g. 'UTC+2') of the local zone at the given timestamp.

    An offset is used instead of a zone name: Python 2.7 on Windows reports zone names
    localized in the OS language and codepage, which is both unwieldy in a tooltip and
    prone to mojibake.
    """
    try:
        is_dst = time.localtime(timestamp).tm_isdst > 0
        offset_seconds = -(time.altzone if is_dst else time.timezone)
    except Exception:
        return ''
    total_minutes = int(offset_seconds) // 60
    sign = '+' if total_minutes >= 0 else '-'
    hours, minutes = divmod(abs(total_minutes), 60)
    if minutes:
        return 'UTC{0}{1}:{2:02d}'.format(sign, hours, minutes)
    return 'UTC{0}{1}'.format(sign, hours)


def end_datetime_text(expiry_timestamp):
    """'<date> <time> UTC+X' display value for an end timestamp, or ''."""
    formatted = format_end_datetime(expiry_timestamp)
    if not formatted:
        return ''
    offset = utc_offset_label(expiry_timestamp)
    if offset:
        return '{0} {1}'.format(formatted, offset)
    return formatted


def ends_on_label():
    """Localized "Ends on:" label preceding the end-time value in tooltips."""
    return _loc('TOOLTIP_ENDS_ON')


def end_text_if_running(expiry, now, is_active=True):
    """End-time text for a subscription that is still running, or '' when it is not.

    The single rule behind both tooltips: a subscription counts as running only while the
    client reports it active *and* its expiry is still ahead. An expiry that has already
    passed reads as not running even though the client may still advertise the
    subscription, because the server confirming the end can lag by seconds — the same
    reasoning the header countdown applies (see header_patch.js).
    """
    if not is_active:
        return ''
    try:
        expiry = int(expiry or 0)
    except (TypeError, ValueError):
        return ''
    if expiry <= now:
        return ''
    return end_datetime_text(expiry)


def build_header_payload():
    """Values header_patch.js cannot work out on its own: clock offset and unit labels.

    The offset is rounded to whole seconds because wulf number properties are integer
    only — handing `addNumberField` a float raises TypeError and the whole model fails
    to attach, which shows up in-game as the button silently keeping its default label.
    """
    return {
        'timeOffset': int(round(server_time_offset())),
        'dayUnit': _loc('UNIT_DAY_SHORT'),
        'hourUnit': _loc('UNIT_HOUR_SHORT'),
        'minuteUnit': _loc('UNIT_MINUTE_SHORT'),
        'secondUnit': _loc('UNIT_SECOND_SHORT'),
    }
