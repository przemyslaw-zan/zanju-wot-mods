# -*- coding: utf-8 -*-
"""Which hangar view this mod attaches to, when other mods want one too.

`net.openwg.gameface` carries a mod into a Gameface document by way of a `ModInjectModel`
attached to one of that document's sub-views. It always writes to that one fixed field name,
so a sub-view holds at most one mod: two mods that pick the same one silently clobber each
other, last writer wins.

Every mod therefore keeps a list of candidate sub-views and takes one that is still free. The
trap is in the word *one*. A mod that patches all its candidates and injects into each free
one does not take a view -- it takes every view that is left, and the next mod along finds
nothing. That is not hypothetical: two mods in this repository did exactly that, and the one
whose loader sorted first silently stopped the other from appearing at all. Patch order alone
decided it, because the loader files are read in name order.

So: attach to the first free candidate, remember it, and leave the rest alone. The candidate
order stays a preference rather than a guarantee, since the order the views are built in is
the client's business, not ours -- but which of them we end up on does not matter. What
matters is that we take one, and only one.

This module holds no client imports, so the rule can be tested outside the game.
"""
from __future__ import absolute_import, print_function, unicode_literals


def decide(model_class, is_claimed, claimed_class):
    """Whether to attach to this view, and which class this mod calls home afterwards.

    Returns `(claim, claimed_class)`. `claimed_class` is carried between calls: None until
    this mod has attached to something, then the class it attached to.
    """
    if is_claimed:
        # Another mod got here first. If it took the view we normally use, drop that
        # preference so the next free candidate can adopt us instead of going without.
        if claimed_class is model_class:
            return False, None
        return False, claimed_class

    if claimed_class is not None and claimed_class is not model_class:
        # Already attached elsewhere. Taking a second view would leave nothing for the next
        # mod along, which is the bug this module exists to prevent.
        return False, claimed_class

    return True, model_class
