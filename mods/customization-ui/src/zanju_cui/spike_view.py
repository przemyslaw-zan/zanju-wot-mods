"""
zanju_cui.spike_view

The mod-owned replacement for the customization screen's view.

This is deliberately not an interface yet. It exists to settle four questions that decide
whether a full custom customization UI is worth building at all:

1. Does the extension override actually put our view on the screen, in place of the
   client's CustomizationMainView?
2. Is the customization context alive and readable from here? The context is created by
   _MainState._onEntered, not by the view, so replacing the view should leave the entire
   model layer -- modes, seasons, outfits, item data -- intact.
3. Does the 3D scene still set up? Camera, tank transform and turret angles are also
   _MainState's work, so the tank should render and rotate with no view involvement.
4. Can the player always get out? The client's view owns the Esc key and the close button,
   so a replacement that forgets them strands the player on the screen.

Everything the probe reads is logged before it is drawn, so a broken SWF still yields the
answers in python.log.

BigWorld scripting uses Python 2.7. Avoid Python-3-only syntax.
"""
from __future__ import print_function, unicode_literals

import logging

from gui.Scaleform.daapi import LobbySubView
from gui.shared import events
from gui.shared.event_bus import EVENT_BUS_SCOPE
from helpers import dependency
from skeletons.gui.customization import ICustomizationService

from .constants import CUSTOMIZATION_VIEW_ALIAS, MOD_NAME, SCALEFORM_FILE_NAME

_logger = logging.getLogger('zanju.customizationui')

_UNAVAILABLE = '<unavailable>'


class CustomizationSpikeView(LobbySubView):
    service = dependency.descriptor(ICustomizationService)

    def __init__(self, ctx=None):
        super(CustomizationSpikeView, self).__init__()
        # _MainState._getViewLoadCtx passes the navigation params through as 'ctx'; the
        # client's own view treats it the same way, as opaque view context.
        self._viewCtx = ctx or {}
        self._report = []

    # -- lifecycle -----------------------------------------------------------

    def _populate(self):
        super(CustomizationSpikeView, self)._populate()
        self._report = self._collectReport()
        for line in self._report:
            _logger.info('probe | %s', line)

    def _dispose(self):
        self._report = []
        self._viewCtx = {}
        _logger.info('spike view disposed')
        super(CustomizationSpikeView, self)._dispose()

    # -- inbound DAAPI (called by the SWF) -----------------------------------

    def onSpikeViewReady(self):
        """The SWF finished building its display tree and can accept a push."""
        if self.isDisposed() or self.flashObject is None:
            return
        try:
            # One joined string rather than a list: it keeps the marshalling assumptions at
            # the DAAPI boundary down to the one type we already know survives the trip.
            self.flashObject.as_setReport(MOD_NAME, '\n'.join(self._report))
        except Exception:
            _logger.exception('failed to push the probe report to the SWF')

    def leaveCustomization(self):
        """Exit to the hangar the same way the client's own close button does."""
        if self.isDisposed():
            return
        _logger.info('leaving customization on request from the spike view')
        try:
            self.fireEvent(
                events.CustomizationEvent(events.CustomizationEvent.CLOSE),
                scope=EVENT_BUS_SCOPE.LOBBY,
            )
        except Exception:
            _logger.exception('failed to fire the customization close event')

    # -- probe ---------------------------------------------------------------

    def _collectReport(self):
        lines = [
            'view: {0}'.format(type(self).__name__),
            'alias: {0}'.format(CUSTOMIZATION_VIEW_ALIAS),
            'swf: {0}'.format(SCALEFORM_FILE_NAME),
        ]
        lines.extend(self._describeContext())
        lines.extend(self._describeVehicle())
        return lines

    def _describeContext(self):
        try:
            ctx = self.service.getCtx()
        except Exception:
            _logger.exception('customization context lookup failed')
            return ['context: <lookup failed>']

        if ctx is None:
            # Would mean the model layer does depend on the client's view after all.
            return ['context: <missing>']

        return [
            'context: alive',
            'season: {0}'.format(self._safe(lambda: ctx.season)),
            'mode: {0}'.format(self._safe(lambda: ctx.modeId)),
            'tab: {0}'.format(self._safe(lambda: ctx.mode.tabId)),
            'outfits modified: {0}'.format(self._safe(ctx.isOutfitsModified)),
        ]

    def _describeVehicle(self):
        from CurrentVehicle import g_currentVehicle

        if not g_currentVehicle.isPresent():
            return ['vehicle: <none>']

        vehicle = g_currentVehicle.item
        return [
            'vehicle: {0}'.format(self._safe(lambda: vehicle.userName)),
            'styles for vehicle: {0}'.format(self._countItems(self.service.getStyles, vehicle)),
            'paints for vehicle: {0}'.format(self._countItems(self.service.getPaints, vehicle)),
            'camouflages for vehicle: {0}'.format(
                self._countItems(self.service.getCamouflages, vehicle)
            ),
        ]

    def _countItems(self, getter, vehicle):
        return self._safe(lambda: len(getter(vehicle)))

    @staticmethod
    def _safe(read):
        """A probe that raises is a finding, not a crash -- record it and keep going."""
        try:
            return read()
        except Exception:
            _logger.exception('probe read failed')
            return _UNAVAILABLE
