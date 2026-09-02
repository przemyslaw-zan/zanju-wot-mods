# -*- coding: utf-8 -*-
"""The hover card, in a Wulf window the mod owns.

The banners stay injected in the garage document, because only a widget inside that document can
measure the element they anchor to. The card does not need an anchor -- it needs to draw over
native windows, which nothing inside the garage document can do: an injected widget inherits the
host document's window band (`SUB_VIEW`, 5), and every native window is above that.

So the card gets a window of its own:

    _CardModel  ->  _CardView(ViewImpl)  ->  _CardWindow(WindowImpl, layer=...)  ->  main window

Positioning crosses Python. `widgets.js` reports which banner the pointer is on and where that
banner sits, this module places the window under it, and the card's own JavaScript reports back
how big it turned out so the placement can use the real size. That round trip was measured at
about 2 ms, which is why the seam is affordable.

The window is shown before it is placed, and the card inside it stays transparent until it is.
That ordering is forced: `requestAnimationFrame` does not run in a hidden Wulf window, and the
card cannot measure itself without a frame. Waiting for a size before showing the window
deadlocks -- eleven hovers produced no measurement at all until an unrelated route change
happened to render the view. So the window is shown first, at whatever size and position it
last had, with nothing painted in it, and the card is revealed once Python has moved it.

Band choice, from measurements on 2.3.1.3:

* `WINDOW` (7) is shared with the platoon window and ordered by activation, so a card there is
  covered the moment the player clicks the platoon window. That is the bug this module exists to
  fix, so 7 is not an option.
* `TOP_WINDOW` (10) draws over the platoon window at all times. It is also where `lobbyMenu`,
  `settingsWindow` and the client's dialogs live, so the card ties with those on activation --
  acceptable for a card that is only up while the pointer rests on a banner.
* `OVERLAY` (11) is above the lobby menu. The upstream guide reports that a panel there stops
  the second Escape press from closing that menu, so it is deliberately not used.

The window is rebuilt rather than kept. The client destroys it along with the lobby's main
window, and the Python object survives that: it keeps answering attribute access and raises only
when a call reaches through to `proxy`. So a stored reference is not evidence that a window
exists, and `install` checks liveness rather than checking for None. Without that the card
worked until the first lobby rebuild and then failed for the rest of the session, once per hover,
with `AttributeError: 'NoneType' object has no attribute 'show'`.

See docs/reference/ui-and-scaleform.md#window-layers.
"""
from __future__ import print_function, unicode_literals

import json

# Rebuilt on every hover so a stale measurement can be told from a current one.
_token = 0

_state = {
    'window': None,
    'model': None,
    'view': None,
    'generation': 0,
    'retry_id': None,
    'branch': '',
    'rect': None,
    'size': None,
    'shown': False,
    # The payload as a dictionary, so a re-push for one changed field does not rebuild it.
    'payload': None,
}

# How far below the banner the card hangs, in client pixels at scale 1. The banner's own tail
# occupies the space above this.
_GAP_PX = 6

_MAX_PARENT_RETRIES = 60
_PARENT_RETRY_DELAY = 0.1

# The stable key the resource map entry declares; see res/mods/configs/res_map/.
LAYOUT_KEY = 'mods/zanju/CampaignTracker/cardLayoutID'


def _layer():
    """The band to build on. Imported late so this module stays importable under the tests."""
    from frameworks.wulf import WindowLayer
    return WindowLayer.TOP_WINDOW


def build_model_class():
    """Define the model against the live client, so this file imports outside the game.

    A hand-written view model gets no generated setters. `_addStringProperty` registers the
    storage; the setter has to be written by hand against the same property index.
    """
    from frameworks.wulf import ViewModel

    class _CardModel(ViewModel):
        """One JSON payload out to the card, one size report back from it."""

        def __init__(self, payload, on_sized):
            self._payload = payload
            self._on_sized = on_sized
            super(_CardModel, self).__init__(properties=1, commands=1)

        def _initialize(self):
            super(_CardModel, self)._initialize()
            self._addStringProperty('payload', self._payload)
            self.onSized = self._addCommand('onSized')
            self.onSized += self._on_sized

        def setPayload(self, payload):
            self._payload = payload
            self._setString(0, payload)

    return _CardModel


def build_view_class():
    from frameworks.wulf import ViewFlags, ViewSettings
    from gui.impl.pub import ViewImpl

    class _CardView(ViewImpl):

        def __init__(self, layout_id, model):
            self._model = model
            super(_CardView, self).__init__(
                ViewSettings(layoutID=layout_id, flags=ViewFlags.VIEW, model=model))

        @property
        def viewModel(self):
            return self._model

    return _CardView


def build_window_class(layer):
    from frameworks.wulf import WindowFlags
    from gui.impl.pub import WindowImpl

    class _CardWindow(WindowImpl):

        def __init__(self, content, parent):
            super(_CardWindow, self).__init__(
                WindowFlags.WINDOW,
                content=content,
                layer=layer,
                name=str('ZanjuCampaignCard'),
                parent=parent,
            )

        def _onReady(self):
            # `show(False)` on the window, not on the view: the argument means "do not take
            # focus". The card is never interactive, so it must never take focus from the
            # garage, and it starts hidden until a banner is hovered anyway.
            self.show(False)
            self.hide()

    return _CardWindow


def is_alive():
    """Whether the native side of the card window still exists.

    The Python wrapper outlives it. A destroyed window answers `windowStatus` and everything
    else quite happily, and only raises when a call reaches `proxy`, which is None by then.
    """
    window = _state['window']
    if window is None:
        return False
    try:
        if window.proxy is None:
            return False
        from frameworks.wulf import WindowStatus
        return window.windowStatus not in (WindowStatus.DESTROYING, WindowStatus.DESTROYED)
    except Exception:
        return False


def _discard():
    """Drop a window the client already destroyed, without reaching into the dead native side."""
    _state['window'] = None
    _state['view'] = None
    _state['model'] = None
    _state['branch'] = ''
    _state['rect'] = None
    _state['size'] = None
    _state['shown'] = False
    _state['payload'] = None


def install(logger):
    """Build the card window once the resource map, the lobby and the main window are ready.

    Called on every hangar build. It returns at once while the window is alive, and rebuilds
    after the client has destroyed it with the lobby it was parented to.
    """
    if is_alive():
        return
    if _state['window'] is not None:
        logger.info('The hover card window was destroyed with the lobby; rebuilding')
        _discard()
    _state['generation'] += 1
    generation = _state['generation']
    try:
        from openwg_gameface import manager, on_ready
    except ImportError:
        logger.info('net.openwg.gameface is not installed; the hover card is disabled')
        return
    if manager.isResMapValidated:
        _wait_for_parent(logger, generation, 0)
    else:
        on_ready(lambda: _wait_for_parent(logger, generation, 0))


def _wait_for_parent(logger, generation, attempt):
    """Retry until the current main window is loaded, then build against that exact window."""
    _state['retry_id'] = None
    if generation != _state['generation'] or _state['window'] is not None:
        return

    import BigWorld
    from frameworks.wulf import WindowStatus
    from helpers import dependency
    from skeletons.gui.impl import IGuiLoader

    # Re-resolved on every attempt: a window reference kept across a lobby teardown names an
    # object the client already destroyed.
    parent = dependency.instance(IGuiLoader).windowsManager.getMainWindow()
    if parent is None or parent.proxy is None or parent.windowStatus != WindowStatus.LOADED:
        if attempt < _MAX_PARENT_RETRIES:
            _state['retry_id'] = BigWorld.callback(
                _PARENT_RETRY_DELAY,
                lambda: _wait_for_parent(logger, generation, attempt + 1))
        else:
            logger.warning('The main window never loaded; the hover card is disabled')
        return
    _build(logger, parent)


def _build(logger, parent):
    from openwg_gameface import res_id_by_key

    layout_id = res_id_by_key(LAYOUT_KEY)
    if not layout_id or layout_id < 0:
        logger.warning(
            'The resource map has no entry for %s; the hover card is disabled. '
            'The client restarts once after this mod is installed, which is when the map is '
            'rebuilt.', LAYOUT_KEY)
        return

    model = build_model_class()(_empty_payload(), lambda *args: _on_sized(logger, *args))
    view = build_view_class()(layout_id, model)
    window = build_window_class(_layer())(view, parent)
    _state['model'] = model
    _state['view'] = view
    _state['window'] = window
    window.load()
    logger.info('Hover card window built on layer %s', _layer())


def _empty_payload():
    return json.dumps({'entry': None, 'labels': {}, 'heldKeys': '', 'token': '', 'reveal': False})


def _push(payload, logger):
    """Send the payload the card renders from. Kept in one place: three callers change one
    field each, and each needs the rest of it left alone."""
    _state['payload'] = payload
    model = _state['model']
    if model is None:
        return
    try:
        with model.transaction() as live:
            live.setPayload(json.dumps(payload))
    except Exception:
        logger.exception('Failed to push the hover card payload')


def show(branch, rect, entry, labels, held, logger):
    """Point the card at one banner. `rect` is (x, y, w, h) in the garage document's pixels."""
    global _token
    if not is_alive():
        # The lobby was rebuilt under us. Put the window back now rather than waiting for the
        # next hangar build, so the card returns within the session it was lost in.
        _discard()
        install(logger)
        if not is_alive():
            # The parent is not loaded yet, so `install` left a retry running. The next hover
            # finds the window and this one is dropped, which is the right trade for a hover.
            return
    _token += 1
    _state['branch'] = branch
    _state['rect'] = rect
    # The size belongs to the card that is about to be built, not the one on screen. Cleared so
    # a stale measurement cannot place the new card.
    _state['size'] = None
    _push({
        'entry': entry,
        'labels': labels,
        'heldKeys': held,
        'token': str(_token),
        # Painted only once the window has been moved. Until then the window is on screen and
        # empty, which is what lets the card's own frames run at all.
        'reveal': False,
    }, logger)
    _show_window(logger)


def _show_window(logger):
    """Put the window on screen so the card inside it starts receiving frames.

    Nothing is painted yet: the card is transparent until `_place` reveals it. The window does
    sit over its old position for the frame or two this takes, so it is kept as short as
    possible rather than being made conditional on anything.
    """
    if _state['shown'] or not is_alive():
        return
    try:
        _state['window'].show(False)
        _state['shown'] = True
    except Exception:
        logger.exception('Failed to show the hover card')


def hide(logger):
    """Take the card off screen. Cheap enough to call when nothing is showing."""
    _state['branch'] = ''
    _state['rect'] = None
    _state['size'] = None
    if not _state['shown']:
        return
    _state['shown'] = False
    if not is_alive():
        # Destroyed with the lobby. Nothing to hide, and the next hover rebuilds it.
        _discard()
        return
    try:
        _state['window'].hide()
    except Exception:
        logger.exception('Failed to hide the hover card')


def set_held_keys(text, logger):
    """Re-push the current card with new modifier keys, so its hint lines light in step."""
    payload = _state['payload']
    if not _state['branch'] or not payload:
        return
    payload = dict(payload)
    payload['heldKeys'] = text
    _push(payload, logger)


def _on_sized(logger, *args):
    """The card measured itself. Place the window and only then show it."""
    arg = args[0] if args else None
    token = _read(arg, 'token')
    if token != str(_token):
        # A measurement for a card the pointer has already left.
        return
    width = _read(arg, 'width')
    height = _read(arg, 'height')
    if not width or not height:
        return
    _state['size'] = (int(width), int(height))
    _place(logger)


def _place(logger):
    rect = _state['rect']
    size = _state['size']
    if rect is None or size is None or not is_alive():
        return
    window = _state['window']
    try:
        parent = window.parent
        screen_w, screen_h = parent.size if parent is not None else (0, 0)
        if screen_w <= 0:
            return
        width, height = size
        banner_x, banner_y, banner_w, banner_h = rect
        # Centred on the banner, hanging below it, and clamped so a card near an edge stays
        # wholly on screen rather than being cut.
        left = banner_x + (banner_w // 2) - (width // 2)
        top = banner_y + banner_h + _GAP_PX
        left = max(0, min(screen_w - width, left))
        top = max(0, min(screen_h - height, top))
        window.move(int(left), int(top))
    except Exception:
        logger.exception('Failed to place the hover card')
        return

    # Placed, so it is safe to paint. One more push rather than a flag the card could have
    # guessed: the card cannot know when the window moved, and revealing itself a frame early
    # shows it at the position the previous card had.
    payload = _state['payload']
    if payload and not payload.get('reveal'):
        payload = dict(payload)
        payload['reveal'] = True
        _push(payload, logger)


def _read(arg, key):
    """Read one key from the single map argument a wulf command carries."""
    if isinstance(arg, dict):
        return arg.get(key)
    getter = getattr(arg, 'get', None)
    if callable(getter):
        try:
            return arg.get(key)
        except Exception:
            return None
    return None


def uninstall(logger):
    """Destroy the window and make any callback still in flight a no-op."""
    _state['generation'] += 1
    retry_id = _state['retry_id']
    if retry_id is not None:
        try:
            import BigWorld
            BigWorld.cancelCallback(retry_id)
        except Exception:
            pass
        _state['retry_id'] = None

    window = _state['window'] if is_alive() else None
    _discard()
    if window is not None:
        try:
            window.destroy()
        except Exception:
            logger.exception('Failed to destroy the hover card window')
