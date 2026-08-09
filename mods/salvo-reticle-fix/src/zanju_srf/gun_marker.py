# -*- coding: utf-8 -*-
"""Drop the fixed shell-spread term from the gun marker while Salvo Fire mode is on.

Every vehicle's reticle is sized from two numbers produced by
``VehicleGunRotator.__getGunMarkerInfo`` (verified against client 2.3.1.1):

    doubleDistance = 2.0 * <distance to the aim point>
    diameter       = doubleDistance * dispersionAngles[0]     -> GunMarkerInfo.size
    diameterOffset = 2.0 * gun.twinGun.gunMarkerOffset        -> GunMarkerInfo.sizeOffset

``_DefaultGunMarkerController.update`` then converts both from world units to screen
units through ``BigWorld.markerHelperScale``, which is a perspective projection and so
divides by the distance to the aim point. That makes the two terms behave differently:

* ``size`` is proportional to distance before projection, so distance cancels and what
  is left on screen is the dispersion angle alone -- the accuracy signal the player
  wants, and all a normal vehicle ever contributes.
* ``sizeOffset`` is a *constant* world-space length, so after projection it survives as
  a term proportional to 1 / distance. It swamps the accuracy signal at close range and
  fades at long range.

``gunMarkerOffset`` defaults to 0.0 for every gun in the game
(``component_constants.DEFAULT_GUN_TWINGUN``) and is set only in the
``<vehicle>_siege_mode.xml`` definitions of the British twin-gun line -- FV224 Chopper,
FV225 Collector, FV226 Contradictious, FV229 Contender, FV230 Canopener, FV227 Conceiver
and FV4025 Contriver -- all of them at 0.213 m. Because it lives in the siege-mode
descriptor overlay, it applies only while Salvo Fire mode is engaged, and it models the
fixed gap between where the two barrels put their shells. It is *not* the ``dualGun``
"double-barrelled" mechanic of the Object 703 II or E 65 Zwilling: those vehicles have no
``gunMarkerOffset`` and are untouched by this mod.

Both terms are divided by the same camera distance on the way to the screen, so it cancels
out of their ratio and the inflation depends only on the aim distance and the dispersion
angle:

    stock circle / true circle  =  1 + 0.213 / (dGun * dispersionAngle)

Measured in game against that formula (client 2.3.1.1, FV229 Contender, 94 ticks in Salvo
Fire): predicted 4.00x at 7.0 m against 3.98x observed, and 7.20x at 3.4 m against 7.1x.
Salvo Fire also pins the dispersion factors near their 0.01 floor, so the term that should
move is frozen while the one that should not is doing all the moving. At that floor the
stock circle runs ~3.1x true size at 10 m, ~1.8x at 25 m and ~1.2x at 100 m -- which is
exactly the range band these heavies fight in. Zeroing ``sizeOffset`` restores a reticle
that means the same thing it means on every other vehicle.

The patch is deliberately placed on the marker *controller* rather than on
``VehicleGunRotator``: the rotator's value is also handed to ``BattleReplay`` and to the
shot pipeline, whereas the controller is the last step before the circle is drawn.
Nothing but the rendered size changes -- ``GunMarkerState`` never carried ``sizeOffset``
in the first place.

BigWorld scripting uses Python 2.7. Avoid Python-3-only syntax.
"""
from __future__ import print_function, unicode_literals

_original_update = None


def strip_size_offset(gun_marker_info):
    """Return marker info whose ``sizeOffset`` is 0.0, or the original when it already is.

    Returning the very same object in the common case matters: this runs on every marker
    update tick, and every vehicle without a twin gun -- which is nearly all of them --
    already reports 0.0.
    """
    if not getattr(gun_marker_info, 'sizeOffset', 0.0):
        return gun_marker_info

    # GunMarkerInfo is a namedtuple; _replace keeps every other field as-is.
    replace = getattr(gun_marker_info, '_replace', None)
    if replace is None:
        return gun_marker_info
    return replace(sizeOffset=0.0)


def install(logger):
    """Patch the default gun marker controller. Returns True when the patch is active."""
    global _original_update

    if _original_update is not None:
        return True

    try:
        from AvatarInputHandler.gun_marker_ctrl import _DefaultGunMarkerController
    except ImportError:
        logger.exception('Gun marker controller not found; salvo reticle fix disabled')
        return False

    original = _DefaultGunMarkerController.update

    def _update_without_size_offset(self, markerType, gunMarkerInfo, *args, **kwargs):
        try:
            gunMarkerInfo = strip_size_offset(gunMarkerInfo)
        except Exception:
            # Never let a marker update fail: a broken reticle is worse than a fat one.
            logger.exception('Failed to strip the salvo gun marker offset')
        return original(self, markerType, gunMarkerInfo, *args, **kwargs)

    # _DualAccMarkerController inherits update() from this class, so the dual-accuracy
    # marker is covered too. _SPGGunMarkerController is a sibling and is left alone: no
    # SPG has a twin gun, so its sizeOffset is always 0.0 anyway.
    _DefaultGunMarkerController.update = _update_without_size_offset
    _original_update = original
    logger.info('Salvo gun marker offset removal installed')
    return True


def uninstall(logger):
    global _original_update

    if _original_update is None:
        return
    try:
        from AvatarInputHandler.gun_marker_ctrl import _DefaultGunMarkerController
        _DefaultGunMarkerController.update = _original_update
    except Exception:
        logger.exception('Failed to restore _DefaultGunMarkerController.update')
    _original_update = None
