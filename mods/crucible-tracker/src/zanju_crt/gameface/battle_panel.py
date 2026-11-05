# -*- coding: utf-8 -*-
"""The battle panel: a Wulf window of the mod's own over the battle page.

battle_session decides when the panel shows and what it shows. This module owns the window: it
builds it, places it, hides it while the full statistics are up, moves it when the player drags
it with Ctrl held, and tells the page when to show the full information (see show_full). The
probe of 14 October 2026 measured this route in seven battles. The window shows over the battle
page, the battle keeps the keyboard, also after a click on the panel, and the drag works. See
docs/reference/choosing-a-ui-approach.md.

* The window is on `WindowLayer.WINDOW`, and `_onReady` shows it with `show(False)`. The argument
  means "do not take the focus".
* JavaScript reports only the press and the release of a drag. Between the two, Python follows
  the cursor once per frame. Mouse events stop when the pointer leaves a small window, and a fast
  drag leaves it at once.
* `GUI.mcursor().position` is in clip space, from -1 to 1, with y up. The window moves in the
  pixels of its parent, the main window.
* The position is kept in config.json with the size of the parent it was dragged on, so a new
  resolution puts the panel at the same relative place. The panel is clamped to the parent, so a
  drag cannot take it off the screen.
* The full information can show only while the player holds the key of the extended vehicle
  markers, Alt by default. The client tells each battle panel of its own about that key with
  `GameEvent.SHOW_EXTENDED_INFO`: the players panel, the damage log, the minimap and the markers
  follow it. So the panel follows the key that the player set in the game settings.

Every client import stays inside a function, so this module is importable outside the game.
"""
from __future__ import absolute_import, print_function, unicode_literals

import json

from .. import card_window, config

LAYOUT_PATH = ('mods', 'zanju', 'crucibletracker', 'views', 'CruciblePanel')

# The parent window can still be loading when the battle page populates. It is asked again every
# 0.1 s, for at most 8 s.
_PARENT_RETRY_SECONDS = 0.1
_MAX_PARENT_RETRIES = 80
# The default position, in pixels of the parent at scale 1: right of the centre of the screen,
# below the team score.
_DEFAULT_OFFSET_X = 120
_DEFAULT_TOP = 96
# While the key of the extended markers is down, it is checked again every 0.2 s. The client sends
# no release when the game loses the keyboard with the key down, for example on Alt+Tab.
_EXTENDED_CHECK_SECONDS = 0.2

_classes = {}


def _build_classes():
    """Define the model, view and window classes against the live client, once."""
    if _classes:
        return _classes
    from frameworks.wulf import ViewFlags, ViewModel, ViewSettings, WindowFlags, WindowLayer
    from gui.impl.pub import ViewImpl, WindowImpl

    class _PanelModel(ViewModel):
        """One JSON payload out to the panel, a size and the drag phases back from it."""

        def __init__(self, payload, owner):
            self._payload = payload
            self._owner = owner
            super(_PanelModel, self).__init__(properties=1, commands=2)

        def _initialize(self):
            super(_PanelModel, self)._initialize()
            self._addStringProperty('payload', self._payload)
            self.onSized = self._addCommand('onSized')
            self.onSized += self.__onSized
            self.onDrag = self._addCommand('onDrag')
            self.onDrag += self.__onDrag

        def setPayload(self, payload):
            self._payload = payload
            self._setString(0, payload)

        def __onSized(self, *args):
            self._owner.guard('panel size', self._owner.on_sized, args[0] if args else None)

        def __onDrag(self, *args):
            self._owner.guard('panel drag', self._owner.on_drag, args[0] if args else None)

    class _PanelView(ViewImpl):

        def __init__(self, layout_id, model):
            self._model = model
            super(_PanelView, self).__init__(ViewSettings(layoutID=layout_id, flags=ViewFlags.VIEW, model=model))

        @property
        def viewModel(self):
            return self._model

    class _PanelWindow(WindowImpl):

        def __init__(self, content, parent, owner):
            self._owner = owner
            super(_PanelWindow, self).__init__(
                WindowFlags.WINDOW, content=content, layer=WindowLayer.WINDOW,
                name=str('ZanjuCruciblePanel'), parent=parent)

        def _onReady(self):
            # No super call: the upstream tutorial overrides _onReady the same way.
            self._owner.guard('panel ready', self._owner.on_window_ready)

    _classes.update(model=_PanelModel, view=_PanelView, window=_PanelWindow)
    return _classes


def to_parent(cursor, screen, parent):
    """A clip-space cursor position, y up, in the pixels of the parent window."""
    # Unpacked rather than indexed: the client unpacks these values the same way.
    cursor_x, cursor_y = cursor
    screen_w, screen_h = screen
    parent_w, parent_h = parent
    screen_w, screen_h = float(screen_w) or 1.0, float(screen_h) or 1.0
    x = (cursor_x + 1.0) * 0.5 * screen_w
    y = (1.0 - cursor_y) * 0.5 * screen_h
    return x * parent_w / screen_w, y * parent_h / screen_h


def clamp(x, y, size, parent):
    """The top left corner that keeps a panel of this size wholly inside the parent."""
    width, height = size or (0, 0)
    parent_w, parent_h = parent
    return (int(round(max(0, min(parent_w - width, x)))),
            int(round(max(0, min(parent_h - height, y)))))


def show_full(details, extended):
    """Whether the panel shows its full information: the head, and the text of each condition.

    `details` is the setting, `extended` whether the key of the extended markers is down.
    """
    if details == config.DETAILS_ALT:
        return bool(extended)
    return details != config.DETAILS_NEVER


def start_position(saved, parent):
    """Where the panel goes when it opens: the saved place, scaled to this parent, or the default.
    Returns (x, y, source)."""
    parent_w, parent_h = parent
    if saved:
        return (float(saved['x']) * parent_w / float(saved['parentWidth']),
                float(saved['y']) * parent_h / float(saved['parentHeight']), 'saved')
    return parent_w / 2.0 + _DEFAULT_OFFSET_X, _DEFAULT_TOP, 'default'


class Panel(object):
    """The panel window of one battle. `close` ends it, and a closed panel stays closed."""

    def __init__(self, logger):
        self.logger = logger
        self.window = None
        self.model = None
        self.content = {}
        self.payload = '{}'
        self.details = config.DETAILS_ALWAYS
        self.extended = False
        self.extended_id = None
        self.size = None
        self.placed = False
        # Where the panel belongs: the start position, then the end of each drag. A clamp starts
        # from here, so the panel goes back to its place after a larger form pushed it away.
        self.anchor = None
        self.ready = False
        self.closed = False
        self.hidden_by = set()
        self.retry_id = None
        self.drag = None
        self.drag_id = None
        self.listeners = []

    def guard(self, what, function, *args):
        """Run a callback from the client. Nothing may leave it, or it breaks the client's own
        dispatch."""
        try:
            return function(*args)
        except Exception:
            self.logger.exception('Failed in the %s', what)
            return None

    # -- life ---------------------------------------------------------------------------------

    def open(self, payload):
        self.details = config.panel_details()
        self.content = payload
        self.payload = self._serialize()
        self._bind()
        self._load_when_parent_ready(0)

    def update(self, payload):
        self.content = payload
        self._push()

    def _serialize(self):
        return json.dumps(dict(self.content, full=show_full(self.details, self.extended),
                               style=config.panel_style(), figures=config.panel_figures()))

    def _push(self):
        text = self._serialize()
        if text == self.payload:
            return
        self.payload = text
        model = self.model
        if model is None:
            return
        try:
            with model.transaction() as live:
                live.setPayload(text)
        except Exception:
            self.logger.exception('Failed to push the battle panel payload')

    def close(self):
        self.closed = True
        for name in ('retry_id', 'drag_id', 'extended_id'):
            self._cancel(name)
        self._unbind()
        window = self.window
        self.window = None
        self.model = None
        self.drag = None
        if window is not None:
            try:
                window.destroy()
            except Exception:
                self.logger.exception('Failed to destroy the battle panel')

    def _cancel(self, name):
        callback_id = getattr(self, name)
        if callback_id is None:
            return
        setattr(self, name, None)
        try:
            import BigWorld
            BigWorld.cancelCallback(callback_id)
        except Exception:
            pass

    def _load_when_parent_ready(self, retry):
        import BigWorld
        self.retry_id = None
        if self.closed or self.window is not None:
            return
        parent = card_window.main_window()
        if parent is None:
            if retry < _MAX_PARENT_RETRIES:
                self.retry_id = BigWorld.callback(
                    _PARENT_RETRY_SECONDS, lambda: self.guard('panel load', self._load_when_parent_ready, retry + 1))
            else:
                self.logger.error('The main window did not load in %d tries; no battle panel', _MAX_PARENT_RETRIES)
            return
        layout_id = card_window.layout_id(LAYOUT_PATH)
        if layout_id is None:
            self.logger.error('The client has no resource R.%s; no battle panel. The client reads it from '
                              'gui/gen_resources/zanju.crucibletracker.json in this mod at start.',
                              '.'.join(LAYOUT_PATH))
            return
        classes = _build_classes()
        self.model = classes['model'](self.payload, self)
        view = classes['view'](layout_id, self.model)
        self.window = classes['window'](view, parent, self)
        self.window.load()

    # -- window -------------------------------------------------------------------------------

    def on_window_ready(self):
        self.ready = True
        self._apply_visibility()

    def on_sized(self, arg):
        width = _int(card_window.read_arg(arg, 'width'))
        height = _int(card_window.read_arg(arg, 'height'))
        if not width or not height or self.window is None:
            return
        self.size = (width, height)
        if not self.placed:
            self._place()
        elif self.drag is None:
            # The panel grew or shrank. Clamp again from its place, so its new edge stays on the
            # screen, and a smaller form goes back to where the player put it.
            self._move(*clamp(self.anchor[0], self.anchor[1], self.size, self._parent_size()))

    def _parent_size(self):
        parent_w, parent_h = self.window.parent.size
        return float(parent_w), float(parent_h)

    def _place(self):
        parent = self._parent_size()
        x, y, source = start_position(config.panel_position(), parent)
        self.anchor = (x, y)
        x, y = clamp(x, y, self.size, parent)
        self._move(x, y)
        self.placed = True
        self.logger.info('Battle panel placed at %d,%d (%s position), size %dx%d', x, y, source, *self.size)

    def _move(self, x, y):
        self.window.move(x, y)

    # -- visibility ---------------------------------------------------------------------------

    def _bind(self):
        from gui.shared import EVENT_BUS_SCOPE, g_eventBus
        from gui.shared.events import GameEvent
        # Each screen that covers the battle with statistics hides the panel while it is up.
        for event_type in (GameEvent.FULL_STATS, GameEvent.FULL_STATS_QUEST_PROGRESS,
                           GameEvent.FULL_STATS_PERSONAL_RESERVES, GameEvent.EVENT_STATS):
            self._listen(g_eventBus, event_type, self._on_stats, EVENT_BUS_SCOPE.BATTLE)
        self._listen(g_eventBus, GameEvent.GUI_VISIBILITY, self._on_gui_visibility, EVENT_BUS_SCOPE.BATTLE)
        if self.details == config.DETAILS_ALT:
            self._listen(g_eventBus, GameEvent.SHOW_EXTENDED_INFO, self._on_extended_info, EVENT_BUS_SCOPE.BATTLE)

    def _listen(self, bus, event_type, handler, scope):
        bus.addListener(event_type, handler, scope=scope)
        self.listeners.append((event_type, handler, scope))

    def _unbind(self):
        if not self.listeners:
            return
        from gui.shared import g_eventBus
        while self.listeners:
            event_type, handler, scope = self.listeners.pop()
            try:
                g_eventBus.removeListener(event_type, handler, scope=scope)
            except Exception:
                self.logger.exception('Failed to remove the %s listener', event_type)

    def _on_stats(self, event):
        self.guard('statistics event', self._set_hidden, 'stats:%s' % event.eventType,
                   bool((event.ctx or {}).get('isDown')))

    def _on_gui_visibility(self, event):
        self.guard('interface visibility event', self._set_hidden, 'gui',
                   not (event.ctx or {}).get('visible', True))

    def _on_extended_info(self, event):
        self.guard('extended information event', self._set_extended, bool((event.ctx or {}).get('isDown')))

    def _set_extended(self, down):
        if down == self.extended:
            return
        self.extended = down
        self._cancel('extended_id')
        if down:
            self._schedule_extended_check()
        self._push()

    def _schedule_extended_check(self):
        import BigWorld
        self.extended_id = BigWorld.callback(
            _EXTENDED_CHECK_SECONDS, lambda: self.guard('extended key check', self._check_extended))

    def _check_extended(self):
        self.extended_id = None
        if self.closed or not self.extended:
            return
        import CommandMapping
        if CommandMapping.g_instance.isActive(CommandMapping.CMD_VEHICLE_MARKERS_SHOW_INFO):
            self._schedule_extended_check()
        else:
            self._set_extended(False)

    def _set_hidden(self, key, hidden):
        before = bool(self.hidden_by)
        if hidden:
            self.hidden_by.add(key)
        else:
            self.hidden_by.discard(key)
        if bool(self.hidden_by) != before:
            self._apply_visibility()

    def _apply_visibility(self):
        window = self.window
        if window is None or not self.ready:
            return
        try:
            if self.hidden_by:
                window.hide(False)
            else:
                window.show(False)
        except Exception:
            self.logger.exception('Failed to show or hide the battle panel')

    # -- drag ---------------------------------------------------------------------------------

    def on_drag(self, arg):
        phase = card_window.read_arg(arg, 'phase')
        if phase == 'start':
            self._drag_start()
        elif phase == 'end':
            self._drag_end()

    def _drag_start(self):
        window = self.window
        if window is None or self.drag is not None:
            return
        import GUI
        x, y = window.position
        point = to_parent(GUI.mcursor().position, GUI.screenResolution(), self._parent_size())
        self.drag = {'grab': (point[0] - x, point[1] - y), 'last': (int(x), int(y))}
        self._schedule_drag_step()

    def _schedule_drag_step(self):
        import BigWorld
        self.drag_id = BigWorld.callback(0.0, lambda: self.guard('panel drag step', self._drag_step))

    def _drag_step(self):
        self.drag_id = None
        drag = self.drag
        if drag is None or self.window is None:
            return
        import BigWorld
        import GUI
        import Keys
        cursor = GUI.mcursor()
        if not BigWorld.isKeyDown(Keys.KEY_LEFTMOUSE) or not cursor.visible:
            # The button is up, or Ctrl was let go and the cursor is gone: the drag ends there.
            self._drag_end()
            return
        parent = self._parent_size()
        point = to_parent(cursor.position, GUI.screenResolution(), parent)
        target = clamp(point[0] - drag['grab'][0], point[1] - drag['grab'][1], self.size, parent)
        if target != drag['last']:
            self._move(*target)
            drag['last'] = target
        self._schedule_drag_step()

    def _drag_end(self):
        if self.drag is None:
            return
        self.drag = None
        self._cancel('drag_id')
        if self.window is None:
            return
        x, y = self.window.position
        self.anchor = (x, y)
        parent_w, parent_h = self._parent_size()
        config.set_panel_position({'x': x, 'y': y, 'parentWidth': parent_w, 'parentHeight': parent_h}, self.logger)
        self.logger.info('Battle panel moved to %d,%d', x, y)


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
