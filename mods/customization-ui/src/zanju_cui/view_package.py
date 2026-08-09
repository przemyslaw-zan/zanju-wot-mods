"""
zanju_cui.view_package

The Scaleform GUI package that takes the customization screen's view alias away from the
client. It is loaded twice by the client, and must satisfy both callers:

- _OverrideScaleFormViewsManager.__initHandlers imports it at registration time and reads
  getViewSettings() to learn which aliases we claim.
- PackageImporter._loadPackage imports it again during lobby creation and additionally
  requires getContextMenuHandlers() and getBusinessHandlers(); a missing one raises
  SoftException and takes the whole lobby down with it.

Because the first of those runs at mod-init time -- long before the lobby exists -- module
scope here stays limited to framework imports. The view class is imported inside
getViewSettings() so it is only pulled in when the client asks for the settings.

BigWorld scripting uses Python 2.7. Avoid Python-3-only syntax.
"""
from __future__ import print_function, unicode_literals

from frameworks.wulf import WindowLayer
from gui.Scaleform.framework import ScopeTemplates, ViewSettings

from .constants import CUSTOMIZATION_VIEW_ALIAS, SCALEFORM_FILE_NAME


def getViewSettings():
    from .spike_view import CustomizationSpikeView

    # Mirrors the client's own registration for this alias, class and SWF aside.
    return (
        ViewSettings(
            CUSTOMIZATION_VIEW_ALIAS,
            CustomizationSpikeView,
            SCALEFORM_FILE_NAME,
            WindowLayer.SUB_VIEW,
            CUSTOMIZATION_VIEW_ALIAS,
            ScopeTemplates.LOBBY_SUB_SCOPE,
        ),
    )


def getContextMenuHandlers():
    return ()


def getBusinessHandlers():
    # The client's own lobby package keeps its LOAD_VIEW listener for this alias, and that
    # listener resolves the alias through the entities factory -- which now holds our
    # settings. So the screen reaches our view without a handler of our own.
    return ()
