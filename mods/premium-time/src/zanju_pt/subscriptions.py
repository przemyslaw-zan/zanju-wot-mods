# -*- coding: utf-8 -*-
"""Current subscription end times, read from the running client.

The Premium Account end time comes from the account stats cache, the same fields the game's
own header presenter uses. The reader hands the rule in `formatting.end_text_if_running`
the values it needs.

Every client import happens lazily inside a try/except, so the reader degrades to '' rather
than breaking the tooltip it feeds: outside the game (tests), before the client is ready, or
on a client version that moved the API. Keeping it here rather than next to the code that
hooks the game also keeps this module importable on its own.

WoT Plus was covered here too; see docs/reference/wot-plus-subscriptions.md for the data
model and what a re-implementation would need.
"""
from __future__ import print_function, unicode_literals

from .formatting import end_text_if_running, server_now


def premium_ends_on(logger):
    """'<date> <time> UTC+X' end time for the active Premium Account, or ''."""
    try:
        from helpers import dependency
        from skeletons.gui.shared import IItemsCache
        stats = dependency.instance(IItemsCache).items.stats
        if not stats.isPremium:
            return ''
        expiry = stats.activePremiumExpiryTime
    except Exception:
        logger.exception('Failed to read premium account expiry time')
        return ''
    return end_text_if_running(expiry, server_now())
