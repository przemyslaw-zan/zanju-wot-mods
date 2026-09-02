from __future__ import print_function, unicode_literals

import logging

from CurrentVehicle import g_currentPreviewVehicle, g_currentVehicle
from frameworks.wulf import WindowLayer
from gui.Scaleform.framework import ScopeTemplates, ViewSettings, g_entitiesFactories
from gui.Scaleform.framework.entities.View import View
from helpers import dependency
from skeletons.gui.shared import IItemsCache

from ..constants import TOOLTIP_FILE_NAME, TOOLTIP_VIEW_ALIAS

_logger = logging.getLogger('zanju.researchprogressbar')

# The live tooltip view, or None while it is not loaded. Held here rather than passed around:
# the bar's hover reports arrive on the bar's view, and the tooltip is a different view entirely.
_tooltip_view = None

# Set once the display-tree report has been logged for the current view, so a diagnostic that
# answers the same question every frame does not fill game.log.
_display_tree_reported = False

_on_scaleform_view_populated = None
_on_scaleform_view_disposed = None
_on_lobby_route_log = None
_on_scaleform_marker_click = None


def _configure_scaleform_runtime_callbacks(on_view_populated, on_view_disposed, on_lobby_route_log, on_marker_click):
    global _on_lobby_route_log, _on_scaleform_marker_click, _on_scaleform_view_disposed, _on_scaleform_view_populated

    _on_scaleform_view_populated = on_view_populated
    _on_scaleform_view_disposed = on_view_disposed
    _on_lobby_route_log = on_lobby_route_log
    _on_scaleform_marker_click = on_marker_click


# The marker list of the context the bar was last given, flattened across modes and keyed by the
# index stamped on each marker. The bar names markers by that index; this is what turns a name
# back into the data the tooltip renders.
_tooltip_markers_by_index = {}


def _remember_tooltip_context(data):
    global _tooltip_markers_by_index
    markers = {}
    try:
        for mode in (data or {}).get('modes') or []:
            for marker in mode.get('markers') or []:
                key = marker.get('tooltipIndex')
                if key is not None:
                    markers[int(key)] = marker
    except Exception:
        _logger.exception('Failed to read the context for the tooltip')
        return
    _tooltip_markers_by_index = markers


def _show_tooltip(indices, cursor_x, cursor_y):
    """Draw the tooltip for the markers the bar says the cursor is over, or hide it."""
    view = _tooltip_view
    if view is None:
        return
    entries = []
    for part in str(indices or '').split(','):
        part = part.strip()
        if not part:
            continue
        try:
            marker = _tooltip_markers_by_index.get(int(part))
        except ValueError:
            continue
        if marker is None:
            continue
        # The shape the tooltip renderer reads. Built here rather than sent from the bar,
        # because the bar would be handing back data Python gave it in the first place.
        entries.append({
            'marker': marker,
            'costXp': marker.get('costXp'),
            'combatXp': marker.get('tooltipCombatXp') or 0,
            'freeXp': marker.get('tooltipFreeXp') or 0,
        })
    if not entries:
        view.as_hideTooltipS()
        return
    view.as_showTooltipS(entries, cursor_x, cursor_y)


class _ScaleformTooltipView(View):
    """The tooltip's own view, on a band of its own. It renders; it decides nothing."""

    def as_showTooltipS(self, entries, cursor_x, cursor_y):
        if self._isDAAPIInited():
            return self.flashObject.as_showTooltip(entries, cursor_x, cursor_y)
        return None

    def as_hideTooltipS(self):
        if self._isDAAPIInited():
            return self.flashObject.as_hideTooltip()
        return None

    def _populate(self):
        global _tooltip_view
        super(_ScaleformTooltipView, self)._populate()
        _tooltip_view = self
        _logger.info('Tooltip view populated on layer %s', TOOLTIP_LAYER)

    def _dispose(self):
        global _tooltip_view
        if _tooltip_view is self:
            _tooltip_view = None
        super(_ScaleformTooltipView, self)._dispose()


class _ScaleformGarageView(View):
    def as_setContextS(self, data):
        if not self._isDAAPIInited():
            return None
        # The tooltip resolves a hover against the same context the bar renders, so it is kept
        # here rather than rebuilt: the two must never describe a marker differently.
        _remember_tooltip_context(data)
        return self.flashObject.as_setContext(data)

    def as_getSelectedModeIdS(self):
        if self._isDAAPIInited():
            return self.flashObject.as_getSelectedModeId()
        return None

    def as_setVisibleS(self, is_visible):
        if not self._isDAAPIInited():
            return None
        result = self.flashObject.as_setVisible(is_visible)
        if is_visible:
            self._report_display_tree_once()
        return result

    def _report_display_tree_once(self):
        """Log the view's display tree the first time it is shown.

        Waits for the view to be visible rather than merely populated: the parents that decide
        how the bar is composited are the ones it is attached to on screen.
        """
        global _display_tree_reported
        if _display_tree_reported:
            return
        _display_tree_reported = True
        try:
            self.as_reportDisplayTreeS()
        except Exception:
            _logger.exception('Failed to request the display-tree report')

    def as_pingS(self):
        if self._isDAAPIInited():
            return self.flashObject.as_ping()
        return None

    def as_refreshLayoutS(self):
        if self._isDAAPIInited():
            return self.flashObject.as_refreshLayout()
        return None

    def as_reportDisplayTreeS(self):
        if self._isDAAPIInited():
            return self.flashObject.as_reportDisplayTree()
        return None

    def onDisplayTreeReport(self, report):
        # Reverse DAAPI channel, as onMarkerClickAction below. Answers one question: is the bar
        # dimmed by something in its own display tree, or by how the engine composites the band
        # it sits on? A concatenated transform of 1,1,1,1 with zero offsets rules out the tree.
        _logger.info('Display tree on layer %s: %s', VIEW_LAYER, report)

    def onTooltipHover(self, indices, cursor_x, cursor_y):
        # Reverse DAAPI channel. The bar says which markers the cursor is over, by the index
        # Python stamped on each one, and where the cursor is in stage pixels. An empty string
        # means it left them all.
        try:
            _show_tooltip(indices, cursor_x, cursor_y)
        except Exception:
            _logger.exception('Failed to update the tooltip view')

    def onMarkerClickAction(self, action_kind, action_id, action_extra=None):
        # Reverse DAAPI channel: when _populate binds flashObject.script = self,
        # GFx injects this method into the SWF's declared
        # `public var onMarkerClickAction:Function` slot, so marker clicks in
        # ActionScript land here. `action_extra` is the pick action's chosen
        # modification id; other kinds omit it (GFx calls with two args, the
        # default fills in).
        if callable(_on_scaleform_marker_click):
            _on_scaleform_marker_click(action_kind, action_id, action_extra)

    def _populate(self):
        super(_ScaleformGarageView, self)._populate()
        if callable(_on_scaleform_view_populated):
            _on_scaleform_view_populated(self)

    def _dispose(self):
        # A new view gets a fresh report: it may be attached somewhere else.
        global _display_tree_reported
        _display_tree_reported = False
        if callable(_on_scaleform_view_disposed):
            _on_scaleform_view_disposed(self)
        super(_ScaleformGarageView, self)._dispose()


class _LobbyStateRouteLogHandler(logging.Handler):
    def emit(self, record):
        if not callable(_on_lobby_route_log):
            return
        try:
            message = record.getMessage()
        except Exception:
            return
        _on_lobby_route_log(message)


def _refresh_vehicle_change_hooks(on_vehicle_changed, on_preview_vehicle_changed, reason, logger):
    try:
        try:
            g_currentVehicle.onChanged -= on_vehicle_changed
        except Exception:
            pass
        g_currentVehicle.onChanged += on_vehicle_changed
    except Exception:
        logger.exception('Failed to refresh current vehicle hook (%s)', reason)

    try:
        try:
            g_currentPreviewVehicle.onChanged -= on_preview_vehicle_changed
        except Exception:
            pass
        g_currentPreviewVehicle.onChanged += on_preview_vehicle_changed
    except Exception:
        logger.exception('Failed to refresh preview vehicle hook (%s)', reason)


def _detach_vehicle_change_hooks(on_vehicle_changed, on_preview_vehicle_changed):
    try:
        g_currentPreviewVehicle.onChanged -= on_preview_vehicle_changed
    except Exception:
        pass

    try:
        g_currentVehicle.onChanged -= on_vehicle_changed
    except Exception:
        pass


def _refresh_items_cache_hooks(on_items_cache_synced, reason, logger):
    """Subscribes to the items-cache sync so the bar follows server-side changes.

    g_currentVehicle.onChanged only fires when the selected vehicle changes, so
    without this the bar kept showing an item as researchable after WG confirmed the
    unlock -- the new state only landed on the next vehicle switch. onSyncCompleted
    carries every stats/inventory diff (including stats.unlocks), and the update it
    schedules is coalesced to the next tick, so a burst of syncs costs one rebuild.
    """
    try:
        items_cache = dependency.instance(IItemsCache)
        try:
            items_cache.onSyncCompleted -= on_items_cache_synced
        except Exception:
            pass
        items_cache.onSyncCompleted += on_items_cache_synced
    except Exception:
        logger.exception('Failed to refresh items cache hook (%s)', reason)


def _detach_items_cache_hooks(on_items_cache_synced):
    try:
        dependency.instance(IItemsCache).onSyncCompleted -= on_items_cache_synced
    except Exception:
        pass


def _get_lobby_app(app_loader):
    app = None
    if hasattr(app_loader, 'getDefLobbyApp'):
        app = app_loader.getDefLobbyApp()
    if app is None and hasattr(app_loader, 'getApp'):
        app = app_loader.getApp()
    return app


def _attach_lobby_route_log_handler(current_handler, handler_class, lobby_state_logger, logger):
    if current_handler is not None:
        return current_handler

    try:
        handler = handler_class()
        handler.setLevel(logging.INFO)
        lobby_state_logger.addHandler(handler)
        return handler
    except Exception:
        logger.exception('Failed to attach lobby route log handler')
        return None


def _detach_lobby_route_log_handler(current_handler, lobby_state_logger, logger):
    if current_handler is None:
        return None

    try:
        lobby_state_logger.removeHandler(current_handler)
    except Exception:
        logger.exception('Failed to detach lobby route log handler')
    return None


def _attach_scaleform_container_hooks(current_container_manager, app_loader, on_view_added_to_container, logger):
    app = _get_lobby_app(app_loader)
    container_manager = getattr(app, 'containerManager', None) if app is not None else None
    if container_manager is current_container_manager:
        return current_container_manager

    current_container_manager = _detach_scaleform_container_hooks(
        current_container_manager,
        on_view_added_to_container,
        logger,
    )
    if container_manager is None:
        return None

    try:
        container_manager.onViewAddedToContainer += on_view_added_to_container
        return container_manager
    except Exception:
        logger.exception('Failed to attach scaleform container hooks')
        return None


def _detach_scaleform_container_hooks(current_container_manager, on_view_added_to_container, logger):
    if current_container_manager is None:
        return None

    try:
        current_container_manager.onViewAddedToContainer -= on_view_added_to_container
    except Exception:
        logger.exception('Failed to detach scaleform container hooks')
    return None


def _start_scaleform_view_runtime(
    current_settings_registered,
    current_hooks_registered,
    current_container_manager,
    app_loader,
    view_alias,
    view_class,
    swf_name,
    on_gui_space_entered,
    on_gui_space_left,
    on_view_added_to_container,
    sync_scaleform_view,
    logger,
):
    try:
        current_settings_registered = _register_scaleform_view_settings(
            current_settings_registered,
            view_alias,
            view_class,
            swf_name,
        )
        current_hooks_registered = _attach_scaleform_space_hooks(
            current_hooks_registered,
            app_loader,
            on_gui_space_entered,
            on_gui_space_left,
        )
        current_container_manager = _attach_scaleform_container_hooks(
            current_container_manager,
            app_loader,
            on_view_added_to_container,
            logger,
        )
        sync_scaleform_view('start')
    except Exception:
        logger.exception('Failed to start scaleform garage view')

    return current_settings_registered, current_hooks_registered, current_container_manager


def _stop_scaleform_view_runtime(
    current_container_manager,
    current_scaleform_view,
    current_scaleform_view_visible,
    current_hooks_registered,
    current_settings_registered,
    app_loader,
    on_view_added_to_container,
    on_gui_space_entered,
    on_gui_space_left,
    view_alias,
    logger,
):
    current_container_manager = _detach_scaleform_container_hooks(
        current_container_manager,
        on_view_added_to_container,
        logger,
    )

    if current_scaleform_view is not None:
        try:
            current_scaleform_view.destroy()
        except Exception:
            logger.exception('Failed to destroy scaleform garage view')
        finally:
            current_scaleform_view = None
            current_scaleform_view_visible = None

    current_hooks_registered = _detach_scaleform_space_hooks(
        current_hooks_registered,
        app_loader,
        on_gui_space_entered,
        on_gui_space_left,
        logger,
    )
    current_settings_registered = _unregister_scaleform_view_settings(
        current_settings_registered,
        view_alias,
        logger,
    )

    return (
        current_container_manager,
        current_scaleform_view,
        current_scaleform_view_visible,
        current_hooks_registered,
        current_settings_registered,
    )


# The band the bar draws in. This is the only place it is named; change it and rebuild to try
# another one.
#
# `WINDOW` (7) is the ordinary choice for a mod view: above the garage document on band 5, and
# therefore above every Gameface mod injected into it.
#
# `MARKER` (3) is under the garage document instead, which is what puts the bar beneath another
# mod's tooltip when that tooltip is drawn inside a garage document -- the x5 counter draws in
# `mono/hangar/header`, for one. The band is not reserved: the client runs `lobbyVehicleMarkerView`
# there as a Scaleform view and `PetHouseMarkerView` there as a Gameface one.
#
# Two things it costs, and the second is the one that decides whether this is usable:
#
# * the bar goes under ALL garage UI, not only the tooltip it was meant to duck beneath;
# * the bar's markers are clickable, and whether a band below a full-screen document still
#   receives the clicks that document declined is UNVERIFIED. Input passthrough is known to work
#   within the garage document, at the DOM level, which is a different question.
#
# Measured on 2.3.1.3, and no band below `WINDOW` (7) turned out to be usable.
#
# `MARKER` (3) draws under the garage document, and the ordering works, but the whole view comes
# out DIMMED there -- and the dimming is the band, not anything the view does. Sampled pixels put
# it beyond doubt: the bar's own green (#789E4E) read back as #5A773D, and a marker's green
# (#9CCB68) read back as #5A773D as well. One overlay drawn over the band cannot do that. Two
# different source colours landing on the same result means each was blended with something
# different behind it, so the band composites with the scene rather than over the finished image
# -- which is what the band is for, since the client puts hangar-space markers on it. It cannot
# be tuned away either: undoing a blend against an unknown, position-dependent background needs a
# per-pixel correction, and a view has one colour transform for the whole of it.
#
# `TOP_SUB_VIEW` (6) is not dimmed, but it belongs to the legacy Scaleform lobby. A view there
# goes into the old `LobbyPage` sub-view container, the page sees an old-style view in it and
# calls `setRequiresOldStyle`, and the legacy header and footer come back -- so the garage grows
# a top bar with a background, and the container insets its contents below it, which drags the
# bar down the screen. That is the client's own chrome reacting correctly to what looks to it
# like a legacy screen, so there is nothing to fix on this end. Suppressing it would mean
# overriding a flag the crew and customization screens rely on.
#
# So `WINDOW` (7) it is. The cost is that the bar draws over other mods' widgets on the same
# band; the tooltip is what actually needed to move, and it has its own band below.
VIEW_LAYER = WindowLayer.WINDOW

# The tooltip's band. `TOP_WINDOW` (10) clears the platoon window and everything else on band 7,
# which is the whole reason the tooltip is a separate view. It is also where `lobbyMenu` and the
# client's dialogs live, so the tooltip ties with those on activation -- acceptable for something
# only up while the cursor rests on a marker. `OVERLAY` (11) would sit above the lobby menu and
# is reported upstream to stop the second Escape press from closing it.
TOOLTIP_LAYER = WindowLayer.TOP_WINDOW


def _register_tooltip_view_settings():
    """Register the tooltip's view once, on its own band."""
    g_entitiesFactories.addSettings(
        ViewSettings(
            TOOLTIP_VIEW_ALIAS,
            _ScaleformTooltipView,
            TOOLTIP_FILE_NAME,
            TOOLTIP_LAYER,
            None,
            ScopeTemplates.GLOBAL_SCOPE,
        )
    )


def _register_scaleform_view_settings(current_registered, view_alias, view_class, swf_name):
    if current_registered:
        return current_registered

    g_entitiesFactories.addSettings(
        ViewSettings(
            view_alias,
            view_class,
            swf_name,
            VIEW_LAYER,
            None,
            ScopeTemplates.GLOBAL_SCOPE,
        )
    )
    _register_tooltip_view_settings()
    return True


def _attach_scaleform_space_hooks(current_registered, app_loader, on_gui_space_entered, on_gui_space_left):
    if current_registered:
        return current_registered

    app_loader.onGUISpaceEntered += on_gui_space_entered
    app_loader.onGUISpaceLeft += on_gui_space_left
    return True


def _detach_scaleform_space_hooks(current_registered, app_loader, on_gui_space_entered, on_gui_space_left, logger):
    if not current_registered:
        return False

    try:
        app_loader.onGUISpaceEntered -= on_gui_space_entered
        app_loader.onGUISpaceLeft -= on_gui_space_left
    except Exception:
        logger.exception('Failed to detach scaleform garage view hooks')
    return False


def _unregister_scaleform_view_settings(current_registered, view_alias, logger):
    if not current_registered:
        return False

    try:
        g_entitiesFactories.removeSettings(view_alias)
    except Exception:
        logger.exception('Failed to unregister scaleform garage view settings')
    return False
