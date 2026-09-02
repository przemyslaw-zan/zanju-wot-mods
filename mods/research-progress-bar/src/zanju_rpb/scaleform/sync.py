from __future__ import print_function, unicode_literals

from gui.shared.personality import ServicesLocator
from skeletons.gui.app_loader import GuiGlobalSpaceID as SPACE_ID

from .. import config as _config_api
from . import callbacks as _scaleform_callbacks_api
from . import context as _scaleform_context_api
from . import gate as _scaleform_gate_api
from . import hooks as _scaleform_hooks_api
from . import payload as _scaleform_payload_api
from . import runtime as _scaleform_runtime_api
from ..constants import SCALEFORM_FILE_NAME, SCALEFORM_VIEW_ALIAS

_config = _config_api._config
_handle_view_added_to_container_callback = _scaleform_callbacks_api._handle_view_added_to_container_callback
_build_scaleform_context = _scaleform_context_api._build_scaleform_context
_log_scaleform_context = _scaleform_context_api._log_scaleform_context
_ScaleformGarageView = _scaleform_hooks_api._ScaleformGarageView
_dispose_tooltip_view = _scaleform_hooks_api._dispose_tooltip_view
_attach_scaleform_container_hooks = _scaleform_hooks_api._attach_scaleform_container_hooks
_detach_scaleform_container_hooks = _scaleform_hooks_api._detach_scaleform_container_hooks
_get_lobby_app = _scaleform_hooks_api._get_lobby_app
_start_scaleform_view_runtime = _scaleform_hooks_api._start_scaleform_view_runtime
_stop_scaleform_view_runtime = _scaleform_hooks_api._stop_scaleform_view_runtime
_build_scaleform_payload = _scaleform_payload_api._build_scaleform_payload
_log_scaleform_payload_summary = _scaleform_payload_api._log_scaleform_payload_summary
_get_scaleform_block_reason = _scaleform_gate_api._get_scaleform_block_reason
_needs_visibility_probe = _scaleform_gate_api._needs_visibility_probe
_should_dispose_scaleform_view_for_block = _scaleform_gate_api._should_dispose_scaleform_view_for_block
_dispose_scaleform_view = _scaleform_runtime_api._dispose_scaleform_view
_handle_populated_scaleform_view = _scaleform_runtime_api._handle_populated_scaleform_view
_hide_scaleform_view = _scaleform_runtime_api._hide_scaleform_view
_push_scaleform_payload = _scaleform_runtime_api._push_scaleform_payload
_request_scaleform_view_load = _scaleform_runtime_api._request_scaleform_view_load
_show_scaleform_view = _scaleform_runtime_api._show_scaleform_view

_LAYOUT_REFRESH_VIEW_ALIASES = frozenset((
    'lobbyMenu',
    'settingsWindow',
    'simpleDialog',
))
_SCALEFORM_DISPOSE_SUB_VIEW_ALIASES = frozenset((
    'vehicleHub',
))
_SCALEFORM_DISPOSE_ROUTE_PREFIXES = (
    'subScope/subLayer/vehicleHub',
)


def _start_scaleform_view(mod, logger):
    if not _config.get('scaleformPrototypeEnabled', True):
        return

    (
        mod._scaleform_settings_registered,
        mod._scaleform_hooks_registered,
        mod._scaleform_container_manager,
    ) = _start_scaleform_view_runtime(
        mod._scaleform_settings_registered,
        mod._scaleform_hooks_registered,
        mod._scaleform_container_manager,
        ServicesLocator.appLoader,
        SCALEFORM_VIEW_ALIAS,
        _ScaleformGarageView,
        SCALEFORM_FILE_NAME,
        mod._on_gui_space_entered,
        mod._on_gui_space_left,
        mod._on_view_added_to_container,
        mod._sync_scaleform_view,
        logger,
    )


def _stop_scaleform_view(mod, logger):
    mod._scaleform_view_requested = False
    mod._scaleform_payload = None
    mod._current_lobby_route_path = None
    mod._last_seen_sub_view_alias = None
    mod._cancel_visibility_probe()

    (
        mod._scaleform_container_manager,
        mod._scaleform_view,
        mod._scaleform_view_visible,
        mod._scaleform_hooks_registered,
        mod._scaleform_settings_registered,
    ) = _stop_scaleform_view_runtime(
        mod._scaleform_container_manager,
        mod._scaleform_view,
        mod._scaleform_view_visible,
        mod._scaleform_hooks_registered,
        mod._scaleform_settings_registered,
        ServicesLocator.appLoader,
        mod._on_view_added_to_container,
        mod._on_gui_space_entered,
        mod._on_gui_space_left,
        SCALEFORM_VIEW_ALIAS,
        logger,
    )


def _evaluate_scaleform_visibility(mod, logger, reason=None, incoming_view=None):
    container_manager = mod._scaleform_container_manager
    if container_manager is None:
        app = _get_lobby_app(ServicesLocator.appLoader)
        container_manager = getattr(app, 'containerManager', None) if app is not None else None

    context = _build_scaleform_context(
        container_manager,
        mod._last_seen_sub_view_alias,
        incoming_view,
        logger,
    )
    block_reason = _get_scaleform_block_reason(
        context,
        mod._active,
        _config.get('scaleformPrototypeEnabled', True),
        mod._current_lobby_route_path,
        mod._scaleform_view is not None,
    )
    if reason is not None:
        mod._last_context_log_key = _log_scaleform_context(
            reason,
            context,
            block_reason,
            mod._current_lobby_route_path,
            mod._last_context_log_key,
            logger,
        )
    return context, block_reason


def _should_show_scaleform_view(mod, logger, reason=None, incoming_view=None):
    _, block_reason = _evaluate_scaleform_visibility(mod, logger, reason, incoming_view)
    return block_reason is None


def _sync_scaleform_view(mod, reason, logger, incoming_view=None):
    context, block_reason = _evaluate_scaleform_visibility(mod, logger, reason, incoming_view)
    if block_reason is None:
        mod._cancel_visibility_probe()
        mod._scaleform_view_requested = _request_scaleform_view_load(
            mod._active,
            _config.get('scaleformPrototypeEnabled', True),
            mod._scaleform_view,
            mod._scaleform_view_requested,
            _get_lobby_app(ServicesLocator.appLoader)
            if mod._scaleform_view is None and not mod._scaleform_view_requested
            else None,
            reason,
            logger,
        )
        if mod._scaleform_view is not None and mod._scaleform_payload is not None:
            mod._scaleform_view_visible = _show_scaleform_view(
                mod._scaleform_view,
                mod._scaleform_view_visible,
                mod._scaleform_payload,
                reason,
                logger,
            )
        return True

    if _needs_visibility_probe(context, block_reason):
        mod._schedule_visibility_probe(reason)
    else:
        mod._cancel_visibility_probe()

    if mod._scaleform_view is not None:
        if _should_dispose_scaleform_view_for_block(
            mod._current_lobby_route_path,
            context,
            _SCALEFORM_DISPOSE_ROUTE_PREFIXES,
            _SCALEFORM_DISPOSE_SUB_VIEW_ALIASES,
        ):
            view = mod._scaleform_view
            mod._scaleform_view = None
            mod._scaleform_view_visible = None
            mod._scaleform_view_requested = False
            _dispose_scaleform_view(view, 'blocked:{0}'.format(reason), logger)
            # The tooltip goes with it. Leaving it standing does not keep it working: the pair
            # is only ever reloaded together, and the reload skips a view the client still
            # holds, so the tooltip would survive the teardown and then never be rebuilt.
            _dispose_tooltip_view('blocked:{0}'.format(reason), logger)
        else:
            mod._scaleform_view_visible = _hide_scaleform_view(
                mod._scaleform_view,
                mod._scaleform_view_visible,
                reason,
                logger,
            )

    return False


def _handle_gui_space_entered(mod, space_id, logger):
    if not mod._active:
        return
    if space_id == SPACE_ID.LOBBY:
        mod._scaleform_container_manager = _attach_scaleform_container_hooks(
            mod._scaleform_container_manager,
            ServicesLocator.appLoader,
            mod._on_view_added_to_container,
            logger,
        )
        _sync_scaleform_view(mod, 'lobby_entered', logger)


def _handle_gui_space_left(mod, space_id, logger):
    if space_id != SPACE_ID.LOBBY:
        return

    mod._scaleform_container_manager = _detach_scaleform_container_hooks(
        mod._scaleform_container_manager,
        mod._on_view_added_to_container,
        logger,
    )
    mod._scaleform_view_requested = False
    view = mod._scaleform_view
    mod._scaleform_view = None
    mod._scaleform_view_visible = None
    _dispose_scaleform_view(view, 'lobby_exit', logger)


def _handle_scaleform_view_populated(mod, view, logger):
    mod._scaleform_view_requested = False
    mod._scaleform_view = view
    mod._scaleform_view_visible = None
    if not _should_show_scaleform_view(mod, logger, 'populated', view):
        _sync_scaleform_view(mod, 'populated_outside_hangar', logger, view)
        return
    mod._scaleform_view_visible = _handle_populated_scaleform_view(
        mod._scaleform_view,
        mod._scaleform_view_visible,
        mod._scaleform_payload,
        logger,
    )


def _handle_scaleform_view_disposed(mod, view, logger):
    if mod._scaleform_view is view:
        mod._scaleform_view = None
        mod._scaleform_view_visible = None
    mod._scaleform_view_requested = False
    logger.info('Scaleform garage view disposed')


def _render_scaleform_view(mod, vehicle, data, preferred_mode_id, logger):
    if not _config.get('scaleformPrototypeEnabled', True):
        return
    mod._scaleform_payload = _build_scaleform_payload(vehicle, data, preferred_mode_id)
    mod._last_scaleform_payload_log_key = _log_scaleform_payload_summary(
        mod._scaleform_payload,
        vehicle,
        mod._last_scaleform_payload_log_key,
        logger,
    )
    if mod._scaleform_payload is None:
        if mod._scaleform_view is not None:
            mod._scaleform_view_visible = _hide_scaleform_view(
                mod._scaleform_view,
                mod._scaleform_view_visible,
                'no_available_modes',
                logger,
            )
        return
    if _sync_scaleform_view(mod, 'data_update', logger):
        _push_scaleform_payload(mod._scaleform_view, mod._scaleform_payload, logger)


def _handle_view_added_to_container(mod, view, logger):
    mod._last_seen_sub_view_alias = _handle_view_added_to_container_callback(
        mod._active,
        view,
        mod._last_seen_sub_view_alias,
        SCALEFORM_VIEW_ALIAS,
        _LAYOUT_REFRESH_VIEW_ALIASES,
        mod._scaleform_view,
        mod._should_show_scaleform_view,
        mod._schedule_update,
        mod._sync_scaleform_view,
        logger,
    )
