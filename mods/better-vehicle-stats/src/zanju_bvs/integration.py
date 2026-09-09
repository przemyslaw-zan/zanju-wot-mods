# -*- coding: utf-8 -*-
"""Register the added stats with the client, so every stat surface draws them.

Four surfaces show these lists, and they do not share a renderer:

* the crew screen, the equipment loadout and the vehicle characteristics tab are Gameface,
  and each is a different bundle;
* the field modifications screen is Scaleform.

They do share their data. Both the Gameface presenter
(``_VehicleParamsPresenterBase._prepareData``) and the Scaleform generator
(``VehParamsBaseGenerator.getFormattedParams``) walk ``params_helper.PARAMS_GROUPS`` and
``params_helper.EXTRA_PARAMS_GROUP``, then ask the comparator for each name. So one set of
registrations reaches all four, and no renderer needs a patch.

What each step buys (verified against client 2.4.0.0):

1. A ``property`` on ``VehicleParams`` makes the stat a real parameter.
   ``ParamsDictProxy.__loadAllValues`` enumerates properties by reflection, so the value
   then flows into the comparator, the group lists and the tooltip extractor by itself.
2. A name in ``EXTRA_PARAMS_GROUP`` puts a row in a group on every surface.
3. A name removed from ``EXTRA_PARAMS_GROUP`` takes the modifier row away.
4. A ``BACKWARD_QUALITY_PARAMS`` entry tells the comparator that less is better here.
5. A ``getBonuses()`` entry gives the tooltip its list of everything that can move the
   value. The client computes each contribution by removing that bonus and re-reading the
   property, so nothing else is needed for a full tooltip.
6. The Scaleform screen asks Python for the row label and the row icon, so a wrapper on
   two formatter functions finishes that surface. The Gameface surfaces resolve both in
   the frontend and are not finished by this module.

BigWorld scripting uses Python 2.7. Avoid Python-3-only syntax.
"""
from __future__ import print_function, unicode_literals

from .stats import BACKWARD_STATS, HIDDEN_PARAMS, STATS, describe, describe_bonuses

_installed = False
_originalGroups = {}
_originalBackward = None
_originalFormatName = None
_originalIconPath = None
_originalLocalizedName = None
_originalTooltipFill = None
_originalPrepareData = None
_describedVehicles = set()
_formatKeys = []

_STATS_BY_NAME = {stat.name: stat for stat in STATS}


def _install_properties(logger):
    """Add one property per stat to VehicleParams."""
    from gui.shared.items_parameters.params import VehicleParams

    for stat in STATS:
        if hasattr(VehicleParams, stat.name):
            logger.warning('%s already exists on VehicleParams; skipped', stat.name)
            continue
        setattr(VehicleParams, stat.name, property(stat.read))

    return


def _remove_properties():
    from gui.shared.items_parameters.params import VehicleParams

    for stat in STATS:
        if stat.name in vars(VehicleParams):
            delattr(VehicleParams, stat.name)

    return


def _install_groups(logger):
    """Add the new names to the main lists and take the replaced names out of the extras.

    The main list is the right home for two reasons. It draws every row whether or not a
    modifier exists, which is the point of showing a value. It also reaches the Scaleform
    screen through ``_makeAdvancedParamVO``, which asks Python for the label, while the
    extras list there builds its label from a string resource we cannot supply.
    """
    from gui.shared.items_parameters import params_helper

    main = params_helper.PARAMS_GROUPS
    extra = params_helper.EXTRA_PARAMS_GROUP
    _originalGroups['main'] = dict(main)
    _originalGroups['extra'] = dict(extra)

    added = {}
    for stat in STATS:
        added.setdefault(stat.group, []).append(stat.name)

    for groupName in list(main.keys()):
        main[groupName] = tuple(main[groupName]) + tuple(added.get(groupName, ()))

    for groupName in list(extra.keys()):
        extra[groupName] = tuple(name for name in extra[groupName] if name not in HIDDEN_PARAMS)

    logger.info('main groups: %s', {k: len(v) for k, v in main.items()})
    logger.info('extra groups: %s', {k: len(v) for k, v in extra.items()})
    return


def _restore_groups():
    from gui.shared.items_parameters import params_helper

    for groupName, names in _originalGroups.get('main', {}).items():
        params_helper.PARAMS_GROUPS[groupName] = names

    for groupName, names in _originalGroups.get('extra', {}).items():
        params_helper.EXTRA_PARAMS_GROUP[groupName] = names

    _originalGroups.clear()
    return


def _install_backward_quality():
    """Tell the comparator that a smaller number is an improvement for these stats."""
    global _originalBackward
    from gui.shared.items_parameters import comparator

    _originalBackward = comparator.BACKWARD_QUALITY_PARAMS
    comparator.BACKWARD_QUALITY_PARAMS = frozenset(_originalBackward) | BACKWARD_STATS
    return


def _restore_backward_quality():
    global _originalBackward
    if _originalBackward is None:
        return
    from gui.shared.items_parameters import comparator

    comparator.BACKWARD_QUALITY_PARAMS = _originalBackward
    _originalBackward = None
    return


def _install_bonuses(logger):
    """Copy the bonus lists of the replaced rows onto the new names."""
    from gui.shared.items_parameters import params_cache

    bonuses = params_cache.g_paramsCache.getBonuses()
    for stat in STATS:
        collected = []
        for source in stat.bonusesFrom:
            for entry in bonuses.get(source, ()):
                if entry not in collected:
                    collected.append(entry)

        bonuses[stat.name] = tuple(collected)
        logger.info('bonuses for %s: %s copied from %s', stat.name, len(collected), list(stat.bonusesFrom))

    return


def _remove_bonuses():
    from gui.shared.items_parameters import params_cache

    bonuses = params_cache.g_paramsCache.getBonuses()
    for stat in STATS:
        bonuses.pop(stat.name, None)

    return


def _install_format_settings():
    """Give each stat a rounder that keeps its decimals.

    An unregistered parameter falls back to a list format whose rounder is ``int``, which
    turns 0.24 into 0. ``veh_param_helpers`` imports this table by name, so the dict has
    to be changed in place rather than replaced.
    """
    from gui.impl import backport
    from gui.shared.items_parameters import formatters

    def makeRounder(digits):
        return lambda value: backport.getNiceNumberFormat(round(value, digits))

    for stat in STATS:
        setting = {'rounder': makeRounder(stat.digits)}
        formatters.FORMAT_SETTINGS[stat.name] = setting
        deltaSetting = setting.copy()
        deltaSetting['rounder'] = formatters._deltaWrapper(setting['rounder'])
        formatters.DELTA_PARAMS_SETTING[stat.name] = deltaSetting
        _formatKeys.append(stat.name)

    return


def _restore_format_settings():
    from gui.shared.items_parameters import formatters

    for name in _formatKeys:
        formatters.FORMAT_SETTINGS.pop(name, None)
        formatters.DELTA_PARAMS_SETTING.pop(name, None)

    del _formatKeys[:]
    return


def _install_gameface_names():
    """Give the crew screen the label for each stat.

    That screen prints the ``name`` field as it stands, and the client builds it from a
    string resource keyed by parameter name, which no added stat owns. The other two
    Gameface screens resolve the label in the frontend and ignore this field, so they
    still show nothing.
    """
    global _originalLocalizedName
    from gui.impl.lobby.hangar.sub_views import vehicle_params_view

    base = vehicle_params_view._VehicleParamsPresenterBase
    _originalLocalizedName = base._getLocalizedName

    def _getLocalizedName(presenter, param, applyFormatting=True):
        stat = _STATS_BY_NAME.get(param.name)
        if stat is not None:
            return stat.label if applyFormatting else ''
        return _originalLocalizedName(presenter, param, applyFormatting)

    base._getLocalizedName = _getLocalizedName
    return


def _restore_gameface_names():
    global _originalLocalizedName
    if _originalLocalizedName is None:
        return
    from gui.impl.lobby.hangar.sub_views import vehicle_params_view

    vehicle_params_view._VehicleParamsPresenterBase._getLocalizedName = _originalLocalizedName
    _originalLocalizedName = None
    return


def _install_tooltip_text():
    """Give the tooltip a title, a description and an icon for each stat.

    The tooltip reads all three from Python, so the mod supplies them directly. The icon
    takes any resource id the client already holds, so each stat borrows the large icon of
    the row it replaces.
    """
    global _originalTooltipFill
    from gui.impl.gen import R
    from gui.impl.lobby.crew.tooltips import vehicle_params_tooltip_view

    base = vehicle_params_tooltip_view.BaseVehicleAdvancedParamsTooltipView
    _originalTooltipFill = base._fillModel

    def _fillModel(view, model):
        _originalTooltipFill(view, model)
        stat = _STATS_BY_NAME.get(view._paramName)
        if stat is None:
            return
        model.setTitle(stat.title)
        model.setDescription(stat.description)
        icon = R.images.gui.maps.icons.vehParams.big.dyn(stat.iconFrom)
        if icon.isValid():
            model.setIcon(icon())
        return

    base._fillModel = _fillModel
    return


def _restore_tooltip_text():
    global _originalTooltipFill
    if _originalTooltipFill is None:
        return
    from gui.impl.lobby.crew.tooltips import vehicle_params_tooltip_view

    vehicle_params_tooltip_view.BaseVehicleAdvancedParamsTooltipView._fillModel = _originalTooltipFill
    _originalTooltipFill = None
    return


def _install_scaleform_formatters():
    """Give the Scaleform field modifications screen a label and an icon for each stat."""
    global _originalFormatName, _originalIconPath
    from gui.shared.items_parameters import formatters

    _originalFormatName = formatters.formatVehicleParamName
    _originalIconPath = formatters.getParameterSmallIconPath

    def formatVehicleParamName(paramName, *args, **kwargs):
        stat = _STATS_BY_NAME.get(paramName)
        if stat is not None:
            # The client's own labels come back wrapped in a text style. A bare string
            # renders in the default face, which reads bolder than every row beside it.
            from gui.shared.formatters import text_styles

            return text_styles.main(stat.label)
        return _originalFormatName(paramName, *args, **kwargs)

    def getParameterSmallIconPath(paramName, *args, **kwargs):
        stat = _STATS_BY_NAME.get(paramName)
        if stat is not None:
            return _originalIconPath(stat.iconFrom, *args, **kwargs)
        return _originalIconPath(paramName, *args, **kwargs)

    formatters.formatVehicleParamName = formatVehicleParamName
    formatters.getParameterSmallIconPath = getParameterSmallIconPath
    return


def _restore_scaleform_formatters():
    global _originalFormatName, _originalIconPath
    if _originalFormatName is None:
        return
    from gui.shared.items_parameters import formatters

    formatters.formatVehicleParamName = _originalFormatName
    formatters.getParameterSmallIconPath = _originalIconPath
    _originalFormatName = None
    _originalIconPath = None
    return


def _install_diagnostics(logger):
    """Log every input channel once per vehicle, so the numbers can be audited."""
    global _originalPrepareData
    from gui.impl.lobby.hangar.sub_views import vehicle_params_view

    base = vehicle_params_view._VehicleParamsPresenterBase
    _originalPrepareData = base._prepareData

    def _prepareData(presenter, diffParams=None, concreteGroup=None):
        _originalPrepareData(presenter, diffParams, concreteGroup)
        try:
            vehicle = presenter._getVehicle()
            if vehicle is None or vehicle.intCD in _describedVehicles:
                return
            _describedVehicles.add(vehicle.intCD)
            logger.info('channels for %s: %s', vehicle.userName, describe(vehicle))
            for statName in ('zanjuTerrainSoft', 'zanjuDispMovement'):
                try:
                    logger.info('extractor for %s: %s', vehicle.userName, describe_bonuses(vehicle, statName))
                except Exception:
                    logger.exception('Extractor dump failed for %s', statName)
        except Exception:
            logger.exception('Diagnostic dump failed')

    base._prepareData = _prepareData
    return


def _restore_diagnostics():
    global _originalPrepareData
    if _originalPrepareData is None:
        return
    from gui.impl.lobby.hangar.sub_views import vehicle_params_view

    vehicle_params_view._VehicleParamsPresenterBase._prepareData = _originalPrepareData
    _originalPrepareData = None
    _describedVehicles.clear()
    return


def install(logger):
    """Register everything. Returns True when the stats are active."""
    global _installed

    if _installed:
        return True

    try:
        _install_properties(logger)
        _install_groups(logger)
        _install_backward_quality()
        _install_bonuses(logger)
        _install_format_settings()
        _install_scaleform_formatters()
        _install_gameface_names()
        _install_tooltip_text()
        _install_diagnostics(logger)
    except Exception:
        logger.exception('Registration failed; rolling back')
        uninstall(logger)
        return False

    _installed = True
    logger.info('registered %s stats, hid %s rows', len(STATS), len(HIDDEN_PARAMS))
    return True


def uninstall(logger):
    """Undo every registration, in the reverse order."""
    global _installed

    for step in (
        _restore_diagnostics,
        _restore_tooltip_text,
        _restore_gameface_names,
        _restore_scaleform_formatters,
        _restore_format_settings,
        _remove_bonuses,
        _restore_backward_quality,
        _restore_groups,
        _remove_properties,
    ):
        try:
            step()
        except Exception:
            logger.exception('Failed to undo %s', step.__name__)

    _installed = False
    return
