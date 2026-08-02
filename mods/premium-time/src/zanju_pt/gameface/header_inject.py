"""Live remaining-time counters on the lobby header's subscription buttons.

The lobby top bar is a Gameface (HTML/JS) view: the Premium Account button
labels are rendered client-side by the header's JS bundle from localization strings and
`expiryTime` on `UserAccountModel.subscriptions`, so neither the Python presenter nor the
view model exposes the text itself. To change those labels we inject JS into the header
document via `net.openwg.gameface`: its bootstrap runs in every Gameface view and loads
the modules listed in a `ModInjectModel` attached to any sub-view's view model.

We attach that marker by wrapping `UserAccountModel._initialize` (the model behind the
header's account panel, which contains both subscription buttons), together with a small
data model (`zanjuPtHeader`) carrying what the JS side cannot know by itself: localized
unit labels and the client-to-server clock offset. The injected JS (header_patch.js)
computes and renders the countdowns from the game's own `expiryTime`. If the OpenWG
library is not installed the mod keeps working without the header counters.
"""
from __future__ import print_function, unicode_literals

from frameworks.wulf import ViewModel

from ..formatting import build_header_payload

_MODULE_URL = 'coui://gui/gameface/mods/zanju_premiumtime/header_patch.js'
_INJECT_NAME = 'zanju_pt_header'
_DATA_PROPERTY = 'zanjuPtHeader'

_original_initialize = None


class _HeaderDataModel(ViewModel):
    """Formatting data consumed by header_patch.js (payload built in formatting.py)."""

    def __init__(self, payload):
        self._payload = payload
        # `properties` must match the number added below, or wulf drops the extras.
        super(_HeaderDataModel, self).__init__(properties=5, commands=0)

    def _initialize(self):
        super(_HeaderDataModel, self)._initialize()
        self._addNumberProperty('timeOffset', self._payload['timeOffset'])
        self._addStringProperty('dayUnit', self._payload['dayUnit'])
        self._addStringProperty('hourUnit', self._payload['hourUnit'])
        self._addStringProperty('minuteUnit', self._payload['minuteUnit'])
        self._addStringProperty('secondUnit', self._payload['secondUnit'])


def install(logger):
    """Patch UserAccountModel to carry our inject marker and data. Returns True when active."""
    global _original_initialize

    if _original_initialize is not None:
        return True

    try:
        from openwg_gameface import gf_mod_inject
    except ImportError:
        logger.info(
            'net.openwg.gameface not found; lobby header integration disabled '
            '(install the OpenWG Gameface library to enable it)'
        )
        return False

    try:
        from gui.impl.gen.view_models.views.lobby.page.header.user_account_model import (
            UserAccountModel,
        )
    except ImportError:
        logger.exception('Lobby header model not found; header integration disabled')
        return False

    original = UserAccountModel._initialize

    def _initialize_with_inject(self):
        original(self)
        try:
            gf_mod_inject(self, str(_INJECT_NAME), modules=[str(_MODULE_URL)])
            self._addViewModelProperty(str(_DATA_PROPERTY), _HeaderDataModel(build_header_payload()))
        except Exception:
            logger.exception('Failed to attach header inject model')

    UserAccountModel._initialize = _initialize_with_inject
    _original_initialize = original
    logger.info('Lobby header integration installed (%s)', _MODULE_URL)
    return True


def uninstall(logger):
    global _original_initialize

    if _original_initialize is None:
        return
    try:
        from gui.impl.gen.view_models.views.lobby.page.header.user_account_model import (
            UserAccountModel,
        )
        UserAccountModel._initialize = _original_initialize
    except Exception:
        logger.exception('Failed to restore UserAccountModel._initialize')
    _original_initialize = None
