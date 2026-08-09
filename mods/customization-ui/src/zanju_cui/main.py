"""
zanju_cui.main

Claims the customization screen's view alias for this mod.

The client supports this directly. gui/Scaleform/framework/package_layout.py drops a base
package's ViewSettings when an extension has registered the same alias
(PackageImporter._getHandlesWithoutExtensionOverride), and gui/Scaleform/app_factory.py
loads base lobby packages first, then extension packages:

    self.__importer.load(lobby.proxy, sf_config.COMMON_PACKAGES + lobbyPackages)
    self.__importer.load(lobby.proxy, g_overrideScaleFormViewsConfig.lobbyPackages, None, True)

Nothing in the shipped client calls initExtensionLobbyPackages, so the registry starts empty
and the seam is free. Registration has to happen before the lobby is created; mod init runs
at client start-up, which is comfortably early.

The registration is not atomic in the client: initExtensionLobbyPackages appends to its
package list *before* validating the aliases, so a failure halfway through leaves the client
in a state where the base customization view is suppressed and ours never loads -- a screen
that opens to nothing. Hence the pre-check and the rollback below: if we cannot register
cleanly, we leave no trace and the player keeps the stock screen.

BigWorld scripting uses Python 2.7. Avoid Python-3-only syntax.
"""
from __future__ import print_function, unicode_literals

import logging

from .constants import CUSTOMIZATION_VIEW_ALIAS, EXTENSION_NAME, MOD_ID, VIEW_PACKAGE_PATH

_logger = logging.getLogger('zanju.customizationui')

# Lobby packages register under this key; see _OverrideScaleFormViewsManager.__initHandlers,
# which defaults guiType to None, and app_factory.createLobby, which loads them with no
# arena type. Battle packages use their ARENA_GUI_TYPE instead.
_LOBBY_GUI_TYPE = None


def init():
    _logger.info('%s initializing', MOD_ID)
    try:
        if _register_view_override():
            _logger.info('%s initialized; customization view alias claimed', MOD_ID)
    except Exception:
        _logger.exception('%s failed to claim the customization view alias', MOD_ID)
        _rollback_registration()


def fini():
    # The client tears the lobby down at shutdown; there is no supported way to hand the
    # alias back mid-session, and nothing would consume it afterwards.
    _logger.info('%s shutting down', MOD_ID)


def _register_view_override():
    from gui.override_scaleform_views_manager import g_overrideScaleFormViewsConfig

    claimed = g_overrideScaleFormViewsConfig.activeExtensionsViewAliases.get(_LOBBY_GUI_TYPE) or {}
    owner = claimed.get(CUSTOMIZATION_VIEW_ALIAS)
    if owner is not None:
        # Registering anyway would raise inside the client and strand the alias.
        _logger.warning(
            'customization view alias "%s" is already claimed by "%s"; standing down',
            CUSTOMIZATION_VIEW_ALIAS,
            owner,
        )
        return False

    g_overrideScaleFormViewsConfig.initExtensionLobbyPackages(EXTENSION_NAME, [VIEW_PACKAGE_PATH])
    return True


def _rollback_registration():
    """Undo a partial registration so the client falls back to its own screen."""
    try:
        from gui.override_scaleform_views_manager import g_overrideScaleFormViewsConfig

        packages = g_overrideScaleFormViewsConfig.lobbyPackages
        while VIEW_PACKAGE_PATH in packages:
            packages.remove(VIEW_PACKAGE_PATH)

        for registry in (
            g_overrideScaleFormViewsConfig.activeExtensionsViewAliases,
            g_overrideScaleFormViewsConfig.activeExtensionsCMAliases,
        ):
            aliases = registry.get(_LOBBY_GUI_TYPE)
            if not aliases:
                continue
            for alias in [a for a, owner in aliases.items() if owner == EXTENSION_NAME]:
                del aliases[alias]

        _logger.info('rolled back the partial view override registration')
    except Exception:
        _logger.exception('failed to roll back the view override registration')
