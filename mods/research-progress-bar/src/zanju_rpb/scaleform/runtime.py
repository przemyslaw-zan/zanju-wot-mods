from __future__ import print_function, unicode_literals

from gui.Scaleform.framework.managers.loaders import SFViewLoadParams

from ..constants import SCALEFORM_VIEW_ALIAS, TOOLTIP_VIEW_ALIAS


def _refresh_scaleform_layout(scaleform_view, reason, logger):
    if scaleform_view is None:
        return False

    try:
        scaleform_view.as_refreshLayoutS()
        logger.info('Scaleform garage view layout refresh (%s)', reason)
        return True
    except Exception:
        logger.exception('Failed to refresh scaleform garage view layout (%s)', reason)
        return False


def _set_scaleform_view_visible(scaleform_view, current_visible, is_visible, reason, logger):
    if scaleform_view is None:
        return current_visible
    if current_visible is is_visible:
        return current_visible

    try:
        scaleform_view.as_setVisibleS(is_visible)
        logger.info('Scaleform garage view visibility -> %s (%s)', is_visible, reason)
        if is_visible:
            _refresh_scaleform_layout(scaleform_view, 'visible:{0}'.format(reason), logger)
        return is_visible
    except Exception:
        logger.exception('Failed to set scaleform garage view visibility=%s (%s)', is_visible, reason)
        return current_visible


def _hide_scaleform_view(scaleform_view, current_visible, reason, logger):
    return _set_scaleform_view_visible(scaleform_view, current_visible, False, reason, logger)


def _dispose_scaleform_view(scaleform_view, reason, logger):
    if scaleform_view is None:
        return False

    try:
        scaleform_view.destroy()
        logger.info('Disposed scaleform garage view (%s)', reason)
        return True
    except Exception:
        logger.exception('Failed to dispose scaleform garage view (%s)', reason)
        return False


def _push_scaleform_payload(scaleform_view, scaleform_payload, logger):
    if scaleform_view is None or scaleform_payload is None:
        return False

    try:
        scaleform_view.as_setContextS(scaleform_payload)
        return True
    except Exception:
        logger.exception('Failed to push data to scaleform garage view')
        return False


def _show_scaleform_view(scaleform_view, current_visible, scaleform_payload, reason, logger):
    if scaleform_view is None or scaleform_payload is None:
        return current_visible

    _push_scaleform_payload(scaleform_view, scaleform_payload, logger)
    return _set_scaleform_view_visible(scaleform_view, current_visible, True, reason, logger)


def _handle_populated_scaleform_view(scaleform_view, current_visible, scaleform_payload, logger):
    if scaleform_payload is None:
        return _hide_scaleform_view(scaleform_view, current_visible, 'populated_no_modes', logger)

    try:
        ping_value = scaleform_view.as_pingS()
        logger.info('Scaleform garage view populated (%s)', ping_value)
    except Exception:
        logger.exception('Scaleform garage view ping failed')

    return _show_scaleform_view(scaleform_view, current_visible, scaleform_payload, 'populated', logger)


def _request_scaleform_view_load(
    is_active,
    scaleform_enabled,
    scaleform_view,
    scaleform_view_requested,
    app,
    reason,
    logger,
):
    if not is_active or not scaleform_enabled:
        return scaleform_view_requested
    if scaleform_view is not None or scaleform_view_requested:
        return scaleform_view_requested
    if app is None:
        return scaleform_view_requested

    try:
        app.loadView(SFViewLoadParams(SCALEFORM_VIEW_ALIAS))
        # The tooltip is a second view on its own band, loaded with the bar and torn down with
        # it. Loading it here keeps the two in step: a bar without its tooltip shows nothing on
        # hover, and a tooltip without a bar has nothing to report one.
        app.loadView(SFViewLoadParams(TOOLTIP_VIEW_ALIAS))
        logger.info('Requested scaleform garage and tooltip view load (%s)', reason)
        return True
    except Exception:
        logger.exception('Failed to request scaleform garage view load (%s)', reason)
        return False
