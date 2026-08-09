"""Stable constants for the customization UI mod."""
from __future__ import print_function, unicode_literals

from gui.Scaleform.daapi.settings.views import VIEW_ALIAS

# MOD_ID / MOD_NAME come from meta.xml via the build-generated _mod_meta module
# (see tools/commands/build.py). meta.xml is the single authored source of these values.
from ._mod_meta import MOD_ID, MOD_NAME  # noqa: F401

MOD_CONFIG_DIR_NAME = 'customization-ui'
LOGGER_NAME = 'zanju.customizationui'

# The view alias the customization screen loads. _MainState (in
# gui.Scaleform.daapi.view.lobby.customization.states) is an SFViewLobbyState keyed to
# ViewKey(VIEW_ALIAS.LOBBY_CUSTOMIZATION), so whatever class is registered under this
# alias is the screen. The client registers its own view here in
# gui/Scaleform/daapi/view/lobby/__init__.py; the extension override strips that entry.
CUSTOMIZATION_VIEW_ALIAS = VIEW_ALIAS.LOBBY_CUSTOMIZATION

# Absolute import path of our GUI package, as PackageImporter/_OverrideScaleFormViewsManager
# hand it to importlib. The build lands src/zanju_cui/*.py at
# res/scripts/client/gui/mods/zanju_cui/*.pyc, so the package is gui.mods.zanju_cui.
VIEW_PACKAGE_PATH = 'gui.mods.zanju_cui.view_package'

# Identifies us in the client's extension registry; only used in its duplicate-alias error.
EXTENSION_NAME = 'zanju_customization_ui'

# Resolved by the client relative to gui/flash/, which is where the build stages it.
SCALEFORM_FILE_NAME = 'zanju-customization-view.swf'
