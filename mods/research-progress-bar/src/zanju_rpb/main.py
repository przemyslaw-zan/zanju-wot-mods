"""
zanju_rpb.main

Displays research progress for the currently selected vehicle in the hangar:
  - Module / next vehicle unlock progress  (tech tree XP)
  - Elite status progress                  (modules unlocked / total needed)
    - Field modification tree progress       (post-progression / "field mods")

BigWorld scripting uses Python 2.7. Avoid Python-3-only syntax.
"""
from __future__ import print_function, unicode_literals

import logging

from CurrentVehicle import g_currentVehicle
from helpers import dependency
from . import actions as _actions_api
from . import collector as _collector_api
from . import panel_watch as _panel_watch_api
from . import mode_state as _mode_state_api
from . import runtime_lifecycle as _runtime_lifecycle_api
from .scaleform import sync as _scaleform_sync_api
from .scaleform import callbacks as _scaleform_callbacks_api
from . import runtime_updates as _runtime_updates_api
from . import t11_action_metadata as _t11_action_metadata_api
from .constants import (
    MOD_ID,
)
from . import config as _config_api
from skeletons.gui.shared import IItemsCache

_logger = logging.getLogger('zanju.researchprogressbar')
_lobby_state_logger = logging.getLogger('gui.lobby_state_machine.lobby_state_machine')

_config = _config_api._config
_collect_research_progress_data = _collector_api._collect_research_progress_data
_execute_marker_click_action = _actions_api._execute_marker_click_action
_cancel_callback = _scaleform_callbacks_api._cancel_callback
_cancel_pending_update_runtime = _runtime_updates_api._cancel_pending_update
_cancel_visibility_probe_runtime = _runtime_updates_api._cancel_visibility_probe
_finalize_runtime = _runtime_lifecycle_api._finalize_runtime
_handle_registered_mod_settings_change = _runtime_lifecycle_api._handle_registered_mod_settings_change
_handle_runtime_config_change = _runtime_lifecycle_api._handle_runtime_config_change
_handle_lobby_route_log_runtime = _runtime_updates_api._handle_lobby_route_log
_handle_preview_vehicle_changed_runtime = _runtime_updates_api._handle_preview_vehicle_changed
_handle_vehicle_changed_runtime = _runtime_updates_api._handle_vehicle_changed
_initialize_runtime = _runtime_lifecycle_api._initialize_runtime
_run_deferred_update_runtime = _runtime_updates_api._run_deferred_update
_run_visibility_probe_runtime = _runtime_updates_api._run_visibility_probe
_schedule_update_runtime = _runtime_updates_api._schedule_update
_schedule_visibility_probe_runtime = _runtime_updates_api._schedule_visibility_probe
_start_runtime_lifecycle = _runtime_lifecycle_api._start_runtime_lifecycle
_stop_runtime_lifecycle = _runtime_lifecycle_api._stop_runtime_lifecycle
_evaluate_scaleform_view_visibility = _scaleform_sync_api._evaluate_scaleform_visibility
_handle_gui_space_entered = _scaleform_sync_api._handle_gui_space_entered
_handle_gui_space_left = _scaleform_sync_api._handle_gui_space_left
_handle_view_added_to_container_runtime = _scaleform_sync_api._handle_view_added_to_container
_handle_scaleform_view_disposed_runtime = _scaleform_sync_api._handle_scaleform_view_disposed
_handle_scaleform_view_populated_runtime = _scaleform_sync_api._handle_scaleform_view_populated
_render_scaleform_view_runtime = _scaleform_sync_api._render_scaleform_view
_reschedule_callback = _scaleform_callbacks_api._reschedule_callback
_start_scaleform_view_runtime = _scaleform_sync_api._start_scaleform_view
_stop_scaleform_view_runtime = _scaleform_sync_api._stop_scaleform_view
_should_show_scaleform_view_runtime = _scaleform_sync_api._should_show_scaleform_view
_sync_scaleform_view_runtime = _scaleform_sync_api._sync_scaleform_view
_extract_t11_action_marker_meta = _t11_action_metadata_api._extract_t11_action_marker_meta
_ModeSelectionState = _mode_state_api.ModeSelectionState

_MODE_STATE_SAVE_DELAY = 1.0


def _on_registered_mod_settings_changed(reason):
    _handle_registered_mod_settings_change(_mod, reason)


# ---------------------------------------------------------------------------
# Core mod class
# ---------------------------------------------------------------------------

class ResearchProgressBar(object):
    itemsCache = dependency.descriptor(IItemsCache)

    def __init__(self):
        self._active = False
        self._mode_state = _ModeSelectionState()
        self._mode_state_capture_error_logged = False
        self._mode_state_save_callback = None
        self._pending_update_callback = None
        self._visibility_probe_callback = None
        self._update_in_progress = False
        self._scaleform_view = None
        self._scaleform_payload = None
        self._scaleform_view_requested = False
        self._scaleform_settings_registered = False
        self._scaleform_hooks_registered = False
        self._scaleform_container_manager = None
        self._scaleform_view_visible = None
        self._lobby_route_log_handler = None
        self._current_lobby_route_path = None
        self._last_context_log_key = None
        self._last_rendered_vehicle_int_cd = None
        self._last_scaleform_payload_log_key = None
        self._last_seen_sub_view_alias = None

    # -- lifecycle -----------------------------------------------------------

    def start(self):
        _start_runtime_lifecycle(self, _logger, _lobby_state_logger)
        # Avoid running heavy collection during early login/loading phase.
        # First update is triggered by onChanged once hangar vehicle selection settles.

    def stop(self):
        self._capture_current_view_mode_selection()
        self._flush_mode_state()
        _stop_runtime_lifecycle(self, _logger, _lobby_state_logger)

    def on_external_config_changed(self, reason):
        _handle_runtime_config_change(self, reason, _logger)

    def _load_mode_state(self, logger):
        self._mode_state.load(logger)

    def _start_scaleform_view(self):
        _start_scaleform_view_runtime(self, _logger)

    def _stop_scaleform_view(self):
        _stop_scaleform_view_runtime(self, _logger)

    def _on_lobby_route_log(self, message):
        _handle_lobby_route_log_runtime(self, message, _logger)

    def _evaluate_scaleform_visibility(self, reason=None, incoming_view=None):
        return _evaluate_scaleform_view_visibility(self, _logger, reason, incoming_view)

    def _should_show_scaleform_view(self, reason=None, incoming_view=None):
        return _should_show_scaleform_view_runtime(self, _logger, reason, incoming_view)

    def _sync_scaleform_view(self, reason, incoming_view=None):
        return _sync_scaleform_view_runtime(self, reason, _logger, incoming_view)

    def _on_gui_space_entered(self, space_id):
        _handle_gui_space_entered(self, space_id, _logger)

    def _on_gui_space_left(self, space_id):
        _handle_gui_space_left(self, space_id, _logger)

    def _on_scaleform_view_populated(self, view):
        _handle_scaleform_view_populated_runtime(self, view, _logger)

    def _on_scaleform_view_disposed(self, view):
        _handle_scaleform_view_disposed_runtime(self, view, _logger)

    def _render_scaleform_view(self, vehicle, data, preferred_mode_id=None):
        _render_scaleform_view_runtime(self, vehicle, data, preferred_mode_id, _logger)

    def _cancel_pending_update(self):
        _cancel_pending_update_runtime(self)

    def _cancel_visibility_probe(self):
        _cancel_visibility_probe_runtime(self)

    def _schedule_visibility_probe(self, reason):
        _schedule_visibility_probe_runtime(self, reason)

    def _run_visibility_probe(self):
        _run_visibility_probe_runtime(self, _logger)

    def _schedule_update(self, reason):
        _schedule_update_runtime(self, reason)

    def _schedule_mode_state_save(self):
        self._mode_state_save_callback = _reschedule_callback(
            self._active,
            self._mode_state_save_callback,
            _MODE_STATE_SAVE_DELAY,
            self._save_mode_state,
        )

    def _save_mode_state(self):
        self._mode_state_save_callback = None
        self._mode_state.save(_logger)

    def _flush_mode_state(self):
        self._mode_state_save_callback = _cancel_callback(self._mode_state_save_callback)
        self._mode_state.save(_logger)

    def _remember_mode_selection(self, vehicle_int_cd, mode_id):
        if self._mode_state.set_mode(vehicle_int_cd, mode_id):
            self._schedule_mode_state_save()

    def _resolve_preferred_mode_id(self, vehicle):
        return self._mode_state.get_mode(getattr(vehicle, 'intCD', None))

    def _capture_current_view_mode_selection(self):
        if self._last_rendered_vehicle_int_cd is None or self._scaleform_view is None:
            return

        try:
            mode_id = self._scaleform_view.as_getSelectedModeIdS()
        except Exception:
            if not self._mode_state_capture_error_logged:
                _logger.exception('Failed to capture selected mode from Scaleform view')
                self._mode_state_capture_error_logged = True
            return

        self._mode_state_capture_error_logged = False
        self._remember_mode_selection(self._last_rendered_vehicle_int_cd, mode_id)

    def _remember_rendered_payload_selection(self, vehicle):
        vehicle_int_cd = getattr(vehicle, 'intCD', None) if vehicle is not None else None
        payload = self._scaleform_payload or {}
        selected_mode_id = payload.get('selectedModeId')
        if vehicle_int_cd is None or selected_mode_id is None:
            self._last_rendered_vehicle_int_cd = None
            return

        self._last_rendered_vehicle_int_cd = vehicle_int_cd
        self._remember_mode_selection(vehicle_int_cd, selected_mode_id)

    # -- event handlers ------------------------------------------------------

    def _on_vehicle_changed(self):
        _handle_vehicle_changed_runtime(self)

    def _on_preview_vehicle_changed(self):
        _handle_preview_vehicle_changed_runtime(self)

    def _on_items_cache_synced(self, _reason, _invalid_items):
        # Every server-confirmed stats/inventory change lands here, which is how the
        # bar picks up a research/purchase without a vehicle switch. Deliberately
        # unfiltered: the scheduled update is coalesced to the next tick and exits
        # early when the bar is hidden, so a burst of syncs costs one rebuild.
        if self._active:
            self._schedule_update('items_cache_synced')

    def _on_view_added_to_container(self, _container, view):
        _handle_view_added_to_container_runtime(self, view, _logger)

    def _on_marker_click(self, action_kind, action_id, action_extra=None):
        if not self._active or not _config.get('enabled'):
            return
        _execute_marker_click_action(
            action_kind,
            action_id,
            action_extra,
            on_state_changed=self._on_marker_action_state_changed,
        )

    def _on_marker_action_state_changed(self):
        if self._active:
            self._schedule_update('marker_action_state_changed')

    def _deferred_update(self):
        _run_deferred_update_runtime(self, _logger)

    # -- data collection -----------------------------------------------------

    def _update(self):
        if not _config.get('enabled'):
            return
        if not self._sync_scaleform_view('update_precheck'):
            return
        if self._update_in_progress:
            return

        self._update_in_progress = True
        try:
            self._capture_current_view_mode_selection()

            vehicle = g_currentVehicle.item
            if vehicle is None:
                return

            try:
                stats = self.itemsCache.items.stats
            except Exception:
                _logger.exception('itemsCache not ready')
                return

            data = self._collect(vehicle, stats)
            preferred_mode_id = self._resolve_preferred_mode_id(vehicle)
            self._render(vehicle, data, preferred_mode_id)
        finally:
            self._update_in_progress = False

    def _collect(self, vehicle, stats):
        return _collect_research_progress_data(
            vehicle,
            stats,
            self.itemsCache.items,
            _extract_t11_action_marker_meta,
            include_hypothetical_t11=(_config.get('researchMode', 'hypothetical_t11') == 'hypothetical_t11'),
        )

    # -- rendering -----------------------------------------------------------

    def _render(self, vehicle, data, preferred_mode_id=None):
        self._render_scaleform_view(vehicle, data, preferred_mode_id)
        self._remember_rendered_payload_selection(vehicle)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

_mod = None


def init():
    global _mod
    _mod = _initialize_runtime(
        _mod,
        ResearchProgressBar,
        MOD_ID,
        _on_registered_mod_settings_changed,
        _logger,
    )
    # Diagnostic only; see panel_watch for what it watches and how to switch it off.
    _panel_watch_api.start(_logger)


def fini():
    global _mod
    _panel_watch_api.stop()
    _mod = _finalize_runtime(_mod, MOD_ID, _logger)
