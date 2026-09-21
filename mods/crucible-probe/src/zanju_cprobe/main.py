"""
zanju_cprobe.main

A throwaway probe. It answers one question: can Python hold the Crucible
tracker's widget on screen for the whole battle?

What the earlier runs settled:

- Run 1. The GFx value proxy is real. Reads return true values, and a method
  call runs inside ActionScript. The tracker component holds no children.
- Run 2. The widget is a child of the client's own TabScreen. The tracker adds
  it there with tabScreen.addChild(_challenges).
- Run 4. page.flashObject.addChild(widget) raises nothing, but the child count
  of both containers stays the same. The call is a silent no-op, so the bridge
  drops a DisplayObject argument. The widget cannot change parent from Python.
- Run 4. A property write does take effect. The widget read back visible=True
  after a write, against the value the tracker had set.
- Run 4. The tab screen is one child of the battle page, and one visible flag
  is all that hides it.

So this run stops trying to move the widget. It shows the tab screen and hides
every child of that screen except the widget. Only property writes are needed,
which is the one operation the earlier runs proved.

The tab screen is a modal surface, so the probe also stops it from taking
input. If the aim breaks in battle, that write is the first thing to blame.

Each step runs on its own and logs its own result. A probe that stops at the
first failure teaches the least.

BigWorld scripting uses Python 2.7. Avoid Python-3-only syntax.
"""
from __future__ import print_function, unicode_literals

import logging

import BigWorld
from frameworks.wulf import WindowLayer
from gui.shared.personality import ServicesLocator
from skeletons.gui.app_loader import GuiGlobalSpaceID

_logger = logging.getLogger('zanju.crucibleprobe')

MOD_ID = 'zanju.crucibleprobe'

# The tracker registers its own component under this alias. Kept as a control.
COMPONENT_ALIAS = 'ChallengesTrackerUI'

# Members that the tracker's widget carries. They are timeline instances inside the
# ChallengesTrackerView symbol, so they are public. Index and name are not safe
# identifiers: the name reads 'title', which looks incidental.
WIDGET_MARKERS = ('titleTF', 'shields', 'condition')

# The one marker that crosses the bridge, measured in run 6. Only this one decides.
REQUIRED_MARKER = 'titleTF'

# Members worth logging for every child of a container.
CHILD_MEMBERS = ('name', 'visible', 'x', 'y', 'width', 'height', 'alpha', 'scaleX')

# Seconds after battle entry to try. The tracker builds its widget during the battle page
# population, and we do not control when that finishes.
ATTEMPT_DELAYS = (6.0, 14.0, 28.0, 45.0)

# Measured geometry, from the battle page children in run 4. The battle page is a plain
# top-left space of 1920 by 1200. The tab screen is one of its children, at x = 960, so
# the children of the tab screen use a centered space. The widget sits at local x = -460
# and y = 307, which puts it at global x = 500 and y = 307. Leave it there for this run:
# it is easy to see, and a position needs no guess now that the space is known.

# Seconds between re-asserts. The client shows the tab screen children again on every Tab
# press, and the tracker hides its own widget again with them.
REAPPLY_PERIOD = 0.5


def _read(owner, name, indent='    '):
    """Read one member and log the result. Return a (value, ok) pair."""
    try:
        value = getattr(owner, name)
    except Exception as error:
        _logger.info('%sread  %-12s FAILED %s: %s', indent, name, type(error).__name__, error)
        return None, False
    _logger.info('%sread  %-12s %r', indent, name, value)
    return value, True


def _quiet_read(owner, name):
    """Read one member without logging. Return a (value, ok) pair."""
    try:
        return getattr(owner, name), True
    except Exception:
        return None, False


def _write(owner, name, value, indent='    '):
    """Write one member, then read it back. Return True only if the value took.

    A write through this bridge can raise nothing and still do nothing. Runs 1 to 5 all
    treated "no exception" as success, and run 4 proved that wrong for addChild. So a
    write is not a result here. The read-back is the result.
    """
    try:
        setattr(owner, name, value)
    except Exception as error:
        _logger.info('%swrite %-12s FAILED %s: %s', indent, name, type(error).__name__, error)
        return False
    read_back, ok = _quiet_read(owner, name)
    if not ok:
        _logger.info('%swrite %-12s %r sent, READ BACK FAILED', indent, name, value)
        return False
    if read_back != value:
        _logger.info('%swrite %-12s %r sent, READ BACK %r -- DID NOT TAKE',
                     indent, name, value, read_back)
        return False
    _logger.info('%swrite %-12s %r confirmed', indent, name, value)
    return True


def _markers_on(child):
    """Return the list of tracker markers the child exposes."""
    found = []
    for member in WIDGET_MARKERS:
        value, ok = _quiet_read(child, member)
        if ok and value is not None:
            found.append(member)
    return found


def _marker_of(child):
    """Return a marker label if the child is the tracker widget, or None.

    Run 6 asked for two markers of three and matched nothing. The widget exposes only
    titleTF: shields is a custom class instance and condition is a sprite, and neither
    crosses the bridge. So the required marker is titleTF alone, and every marker hit
    gets logged to keep this honest.
    """
    found = _markers_on(child)
    if REQUIRED_MARKER not in found:
        return None
    return '+'.join(found)


class _Probe(object):
    """Holds the probe state for one battle."""

    def __init__(self):
        self._callbacks = []
        self._reapply_id = None
        self._moved = False
        self._verdict_logged = False

    # -- lifecycle ---------------------------------------------------------------

    def start(self):
        loader = ServicesLocator.appLoader
        loader.onGUISpaceEntered += self._on_space_entered
        loader.onGUISpaceLeft += self._on_space_left
        _logger.info('%s armed, waiting for battle', MOD_ID)

    def stop(self):
        loader = ServicesLocator.appLoader
        try:
            loader.onGUISpaceEntered -= self._on_space_entered
            loader.onGUISpaceLeft -= self._on_space_left
        except Exception:
            _logger.exception('failed to unsubscribe the space handlers')
        self._cancel_all()

    def _on_space_entered(self, space_id):
        if space_id != GuiGlobalSpaceID.BATTLE:
            return
        self._cancel_all()
        self._moved = False
        self._verdict_logged = False
        _logger.info('=== battle entered, %s attempts scheduled ===', len(ATTEMPT_DELAYS))
        for index, delay in enumerate(ATTEMPT_DELAYS):
            self._schedule(delay, self._attempt, index, delay)

    def _on_space_left(self, space_id):
        if space_id != GuiGlobalSpaceID.BATTLE:
            return
        _logger.info('=== battle left, probe stopped ===')
        self._cancel_all()

    # -- scheduling --------------------------------------------------------------

    def _schedule(self, delay, method, *args):
        try:
            callback_id = BigWorld.callback(delay, lambda: self._run(method, *args))
        except Exception:
            _logger.exception('failed to schedule a probe callback')
            return
        self._callbacks.append(callback_id)

    def _run(self, method, *args):
        """Run a scheduled step. A probe must never raise into the client."""
        try:
            method(*args)
        except Exception:
            _logger.exception('probe step raised')

    def _cancel_all(self):
        for callback_id in self._callbacks:
            try:
                BigWorld.cancelCallback(callback_id)
            except Exception:
                pass
        self._callbacks = []
        if self._reapply_id is not None:
            try:
                BigWorld.cancelCallback(self._reapply_id)
            except Exception:
                pass
            self._reapply_id = None

    # -- surfaces ----------------------------------------------------------------

    def _battle_page(self):
        app = ServicesLocator.appLoader.getDefBattleApp()
        if app is None:
            return None
        container = app.containerManager.getContainer(WindowLayer.VIEW)
        if container is None:
            return None
        return container.getView()

    def _tab_screen_flash(self, page):
        """Return the ActionScript TabScreen behind the full-stats component."""
        alias = getattr(page, '_fullStatsAlias', None)
        if alias is None:
            _logger.info('  the battle page carries no _fullStatsAlias')
            return None
        try:
            component = page.getComponent(alias)
        except Exception as error:
            _logger.info('  getComponent(%r) FAILED %s: %s', alias, type(error).__name__, error)
            return None
        if component is None:
            _logger.info('  the full stats component is not registered yet')
            return None
        return getattr(component, 'flashObject', None)

    # -- enumeration -------------------------------------------------------------

    def _enumerate(self, flash, label):
        """Log every child of a container. Return a (children, marked_child) pair."""
        count, ok = _read(flash, 'numChildren', indent='  %s ' % label)
        if not ok or not count:
            return [], None
        children = []
        marked = None
        for child_index in range(int(count)):
            try:
                child = flash.getChildAt(child_index)
            except Exception as error:
                _logger.info('  %s child %s getChildAt FAILED %s: %s',
                             label, child_index, type(error).__name__, error)
                continue
            children.append(child)
            marker = _marker_of(child)
            values = []
            for member in CHILD_MEMBERS:
                value, member_ok = _quiet_read(child, member)
                values.append('%s=%r' % (member, value) if member_ok else '%s=?' % member)
            # Log every marker hit, not only a match. A near miss is the thing that
            # explains a wrong identification, and run 6 had no way to show one.
            markers = _markers_on(child)
            if markers:
                values.append('markers=%s' % '+'.join(markers))
            _logger.info('  %s child %s %s%s', label, child_index, ' '.join(values),
                         ' <-- TRACKER WIDGET (%s)' % marker if marker else '')
            if marker and marked is None:
                marked = child
        return children, marked

    # -- the probe ---------------------------------------------------------------

    def _attempt(self, index, delay):
        is_last = index == len(ATTEMPT_DELAYS) - 1
        _logger.info('--- attempt %s at +%ss ---', index + 1, delay)
        page = self._battle_page()
        if page is None:
            _logger.info('  no battle page yet')
            return
        _logger.info('  battle page %s', type(page).__name__)

        page_flash = getattr(page, 'flashObject', None)
        if page_flash is None:
            _logger.info('  the battle page has no flashObject')
            return

        tab_flash = self._tab_screen_flash(page)
        if tab_flash is None:
            return
        _, widget = self._enumerate(tab_flash, 'tabScreen')

        # The battle page is where the widget has to end up, so its own children give the
        # coordinate space, the scale and a set of known-visible reference rectangles.
        self._enumerate(page_flash, 'battlePage')

        if widget is None:
            _logger.info('  no child of the tab screen carries a tracker marker')
            return

        if not (is_last and not self._moved):
            return
        self._try_unveil(tab_flash)
        if self._moved and self._reapply_id is None:
            _logger.info('  re-asserting every %ss so the screen can be checked', REAPPLY_PERIOD)
            self._start_reapply()
        self._log_verdict()

    def _try_unveil(self, tab_flash):
        """Show the tab screen with every child hidden except the tracker widget.

        Run 4 proved that addChild is a silent no-op across the bridge, so the widget
        cannot change parent from Python. It also proved that a property write does take
        effect. The tab screen is one child of the battle page, and a visible flag is all
        that hides it, so a set of writes can leave the widget alone on screen.
        """
        _logger.info('  unveil attempt:')
        if not _write(tab_flash, 'visible', True):
            return

        # The tab screen is a modal surface. An invisible child still takes part in hit
        # testing, so the container has to stop taking input or it can eat the aim.
        _write(tab_flash, 'mouseEnabled', False)
        _write(tab_flash, 'mouseChildren', False)

        hidden = self._hide_siblings(tab_flash)
        _logger.info('    hid %s sibling children', hidden)

        # Read the whole screen back. The per-write read-back proves each value landed on
        # the object. This proves the screen as a whole is in the state we asked for.
        _logger.info('  tab screen after the writes:')
        _, widget = self._enumerate(tab_flash, 'tabScreen')
        if widget is None:
            _logger.info('    the widget is no longer identifiable')
            return
        widget_visible, _ = _read(widget, 'visible')
        self._moved = hidden > 0 and widget_visible is True

    def _hide_siblings(self, tab_flash):
        """Hide every child of the tab screen that carries no tracker marker.

        Absence of a marker is the test, not a name or an index, so a change in the
        client's own child order does not matter.
        """
        count, ok = _quiet_read(tab_flash, 'numChildren')
        if not ok or not count:
            return 0
        hidden = 0
        for child_index in range(int(count)):
            try:
                child = tab_flash.getChildAt(child_index)
            except Exception:
                continue
            name, _ = _quiet_read(child, 'name')
            if _marker_of(child):
                _write(child, 'visible', True, indent='      widget %r ' % name)
                continue
            if _write(child, 'visible', False, indent='      %r ' % name):
                hidden += 1
        return hidden

    def _log_verdict(self):
        if self._verdict_logged:
            return
        self._verdict_logged = True
        if self._moved:
            _logger.info('VERDICT: the tab screen is visible with only the tracker widget in it.')
            _logger.info('VERDICT: look near x=500 y=307 on screen, and test that the aim still works.')
            return
        _logger.info('VERDICT: the unveil writes did not land. Read the write lines above.')

    def _start_reapply(self):
        self._reapply_id = BigWorld.callback(REAPPLY_PERIOD, lambda: self._run(self._reapply))

    def _reapply(self):
        """Hold the unveiled state. Log only a change, so the log stays readable."""
        self._reapply_id = None
        page = self._battle_page()
        if page is None:
            return
        try:
            tab_flash = self._tab_screen_flash(page)
            if tab_flash is not None and not tab_flash.visible:
                _logger.info('re-assert: the tab screen was hidden again, restoring')
                tab_flash.visible = True
                self._quiet_hide_siblings(tab_flash)
        except Exception as error:
            _logger.info('re-assert FAILED %s: %s', type(error).__name__, error)
            return
        self._start_reapply()

    def _quiet_hide_siblings(self, tab_flash):
        """Re-apply the sibling state without logging every write."""
        count, ok = _quiet_read(tab_flash, 'numChildren')
        if not ok or not count:
            return
        for child_index in range(int(count)):
            try:
                child = tab_flash.getChildAt(child_index)
                child.visible = bool(_marker_of(child))
            except Exception:
                continue

    def _find_marked(self, flash):
        """Return the marked child of a container without logging every child."""
        count, ok = _quiet_read(flash, 'numChildren')
        if not ok or not count:
            return None
        for child_index in range(int(count)):
            try:
                child = flash.getChildAt(child_index)
            except Exception:
                continue
            if _marker_of(child):
                return child
        return None


_probe = _Probe()


def init():
    # A failure inside init() raising AttributeError disappears with no log line at all,
    # so this mod logs its own traceback. See docs/debugging.md.
    _logger.info('%s initializing', MOD_ID)
    try:
        _probe.start()
        _logger.info('%s initialized', MOD_ID)
    except Exception:
        _logger.exception('%s failed to initialize', MOD_ID)


def fini():
    try:
        _probe.stop()
    except Exception:
        _logger.exception('%s error in fini', MOD_ID)
