package {
    import flash.display.Bitmap;
    import flash.display.BlendMode;
    import flash.display.DisplayObject;
    import flash.display.Shape;
    import flash.display.Sprite;
    import flash.events.Event;
    import flash.events.KeyboardEvent;
    import flash.events.MouseEvent;
    import flash.geom.ColorTransform;
    import flash.geom.Matrix;
    import flash.text.TextField;
    import flash.utils.Dictionary;
    import flash.utils.getQualifiedClassName;
    import net.wg.infrastructure.base.AbstractView;

    [SWF(width="1920", height="220", frameRate="30", backgroundColor="#000000")]
    public class ResearchProgressBarLobby extends AbstractView {
        [Embed(source="assets/progress_bar_base.png")]
        private static const ProgressBarBaseAsset:Class;

        [Embed(source="assets/progress_bar_green.png")]
        private static const ProgressBarGreenAsset:Class;

        [Embed(source="assets/progress_bar_white.png")]
        private static const ProgressBarWhiteAsset:Class;

        [Embed(source="assets/progress_bar_yellow.png")]
        private static const ProgressBarYellowAsset:Class;

        private static const LABEL_COLOR:uint = 0xE6DDC8;
        private static const COUNTER_FONT_SIZE:int = 15;
        private static const COUNTER_FIELD_HEIGHT:Number = 18;
        private static const MARKER_VALUE_COLOR:uint = 0xB8AC97;
        private static const BAR_FILL_MODE_COMPLETED_ONLY:String = "completed_only";
        private static const SEPARATE_STATUS_VERTICAL_GAP:Number = 4;
        private var combatPercentLabel:TextField;
        private var combatPercentCaption:TextField;
        private var totalPercentLabel:TextField;
        private var totalPercentCaption:TextField;
        private var sideCounterLabel:TextField;
        private var sideCounterCaption:TextField;
        private var separateStatusLabel:TextField;
        private var baseBar:Bitmap;
        private var completedBar:Bitmap;
        private var combatBar:Bitmap;
        private var freeBar:Bitmap;
        private var completedMaskShape:Shape;
        private var combatMaskShape:Shape;
        private var freeMaskShape:Shape;
        private var markersContainer:Sprite;
        private var modeButtonsContainer:Sprite;
        private var tooltipContainer:Sprite;
        private var tooltipBackground:Shape;
        private var tooltipContent:Sprite;
        // Reverse DAAPI channel: when the Python view binds flashObject.script,
        // GFx injects the same-named Python method into this declared slot (the
        // same pattern WG's own meta classes use, e.g. ServerStatsMeta.relogin).
        public var onMarkerClickAction:Function;
        // Second reverse slot, for the display-tree report below. Declared for the same reason
        // as the one above: AVM2 classes are sealed, so GFx can only inject into a declared var.
        public var onDisplayTreeReport:Function;
        // Third reverse slot: which markers the cursor is over, for the tooltip window Python
        // owns. See EXTERNAL_TOOLTIP below.
        public var onTooltipHover:Function;
        // The marker sprite currently under the cursor (for keyboard picking).
        private var _hoveredMarkerDisplay:Sprite = null;
        // The keyboard-pickable entries of the tooltip stack under the cursor, in the
        // order the tooltip numbers them. Two or more means a plain click is
        // ambiguous, so it is suppressed and 1..N keys drive the choice instead.
        private var _hoveredStackEntries:Array = [];
        private var _context:Object;
        // Draw the tooltip here, or hand it to Python to draw in a window of its own?
        //
        // The bar sits on one window band and its tooltip, drawn inside this SWF, is stuck on
        // that same band -- a band applies to a whole view, not to an element in it. Handing
        // the tooltip to Python lets it live in a second view on a higher band, above the
        // native windows this bar cannot clear. Set false to go back to drawing it here.
        private static const EXTERNAL_TOOLTIP:Boolean = true;
        // The last hover reported, so a mouse move that changes nothing sends nothing.
        private var _lastHoverKey:String = "";
        private var _selectedModeId:String;
        private var _selectedVehicleIntCD:String;
        private var _barX:Number = 0;
        private var _barY:Number = 0;
        private var _barWidth:Number = 0;
        private var _isReady:Boolean = false;
        private var _markerTooltipDataByDisplay:Dictionary = new Dictionary(true);
        private var _modeIdByButton:Dictionary = new Dictionary(true);
        private var _activeCounterLayout:String = "";
        private var _lastStageWidth:Number = -1;
        private var _lastStageHeight:Number = -1;
        private var _lastEffectiveScale:Number = -1;

        public function ResearchProgressBarLobby() {
            super();
        }

        override protected function configUI():void {
            super.configUI();
            visible = false;
            mouseEnabled = false;
            mouseChildren = true;
            build();
            removeEventListener(Event.ENTER_FRAME, onEnterFrame);
            addEventListener(Event.ENTER_FRAME, onEnterFrame, false, 0, true);
            ResearchProgressBarStageSupport.attachListeners(
                stage,
                onStageResize,
                onStageMouseMove,
                onStageMouseLeave
            );
            attachKeyListener();
        }

        override protected function onDispose():void {
            ResearchProgressBarTooltipView.hideTooltip(tooltipContainer);
            clearModeButtons();
            removeEventListener(Event.ENTER_FRAME, onEnterFrame);
            ResearchProgressBarStageSupport.detachListeners(
                stage,
                onStageResize,
                onStageMouseMove,
                onStageMouseLeave
            );
            detachKeyListener();
            _hoveredMarkerDisplay = null;
            _hoveredStackEntries = [];
            super.onDispose();
        }

        private function attachKeyListener():void {
            if (stage != null) {
                stage.addEventListener(KeyboardEvent.KEY_DOWN, onStageKeyDown, false, 0, true);
            }
        }

        private function detachKeyListener():void {
            if (stage != null) {
                stage.removeEventListener(KeyboardEvent.KEY_DOWN, onStageKeyDown);
            }
        }

        override protected function nextFrameAfterPopulateHandler():void {
            var stageState:Object;

            super.nextFrameAfterPopulateHandler();
            _isReady = true;
            ResearchProgressBarStageSupport.attachListeners(
                stage,
                onStageResize,
                onStageMouseMove,
                onStageMouseLeave
            );
            attachKeyListener();
            layoutFromStage();
            stageState = ResearchProgressBarStageSupport.updateTrackedStageSize(stage, _lastStageWidth, _lastStageHeight);
            _lastStageWidth = Number(stageState.stageWidth);
            _lastStageHeight = Number(stageState.stageHeight);
            _lastEffectiveScale = resolveEffectiveScale();
            updateBarFromContext(false);
        }

        private function onEnterFrame(event:Event):void {
            var stageState:Object;
            var scale:Number;

            if (!_isReady || stage == null) {
                return;
            }

            stageState = ResearchProgressBarStageSupport.updateTrackedStageSize(stage, _lastStageWidth, _lastStageHeight);
            scale = resolveEffectiveScale();
            // Interface-scale changes (e.g. x1 -> x2) keep stageWidth/stageHeight
            // constant and only change the inherited scale, so track it explicitly.
            if (!Boolean(stageState.changed) && scale == _lastEffectiveScale) {
                return;
            }

            _lastStageWidth = Number(stageState.stageWidth);
            _lastStageHeight = Number(stageState.stageHeight);
            _lastEffectiveScale = scale;
            layoutFromStage();
            updateBarFromContext(false);
        }

        private function build():void {
            var parts:Object = ResearchProgressBarViewFactory.build(
                this,
                ProgressBarBaseAsset,
                ProgressBarWhiteAsset,
                ProgressBarGreenAsset,
                ProgressBarYellowAsset,
                LABEL_COLOR,
                MARKER_VALUE_COLOR,
                COUNTER_FONT_SIZE,
                COUNTER_FIELD_HEIGHT
            );

            combatPercentLabel = parts.combatPercentLabel as TextField;
            combatPercentCaption = parts.combatPercentCaption as TextField;
            totalPercentLabel = parts.totalPercentLabel as TextField;
            totalPercentCaption = parts.totalPercentCaption as TextField;
            sideCounterLabel = parts.sideCounterLabel as TextField;
            sideCounterCaption = parts.sideCounterCaption as TextField;
            separateStatusLabel = parts.separateStatusLabel as TextField;
            baseBar = parts.baseBar as Bitmap;
            completedBar = parts.completedBar as Bitmap;
            combatBar = parts.combatBar as Bitmap;
            freeBar = parts.freeBar as Bitmap;
            completedMaskShape = parts.completedMaskShape as Shape;
            combatMaskShape = parts.combatMaskShape as Shape;
            freeMaskShape = parts.freeMaskShape as Shape;
            markersContainer = parts.markersContainer as Sprite;
            modeButtonsContainer = parts.modeButtonsContainer as Sprite;
            tooltipContainer = parts.tooltipContainer as Sprite;
            tooltipBackground = parts.tooltipBackground as Shape;
            tooltipContent = parts.tooltipContent as Sprite;
        }

        private function onStageResize(event:Event):void {
            layoutFromStage();
            updateBarFromContext(false);
        }

        private function onStageMouseMove(event:MouseEvent):void {
            // Mouse-move keeps the tooltip live as the cursor crosses the stack, so it
            // must keep the keyboard-pick stack live too -- route through the shared
            // helper rather than refreshing the tooltip alone.
            refreshTooltipAndStack(event.stageX, event.stageY);
        }

        private function onStageMouseLeave(event:Event):void {
            if (EXTERNAL_TOOLTIP) {
                // The tooltip belongs to another view, so the only way to take it down is to
                // tell Python the cursor is over nothing. Hiding the local container would
                // hide something that was never drawn.
                reportTooltipHover([], 0, 0);
            }
            else {
                ResearchProgressBarTooltipView.hideTooltip(tooltipContainer);
            }
            _hoveredStackEntries = [];
        }

        public function as_setContext(data:Object):void {
            applyContext(data);
        }

        public function as_ping():String {
            return "research-progress-bar-lobby-ready";
        }

        public function as_getSelectedModeId():String {
            return _selectedModeId;
        }

        public function as_setVisible(value:Boolean):void {
            visible = value;
            if (!value) {
                ResearchProgressBarTooltipView.hideTooltip(tooltipContainer);
            }
        }

        // Diagnostic: describe this view's place in the display tree, so Python can log why the
        // bar looks different on one window band than on another.
        //
        // `concatenatedColorTransform` is the answer on its own: it composes every ancestor's
        // transform, so if its multipliers are 1 and its offsets 0, nothing in the display tree
        // is tinting the view and the difference is in how the engine composites the band. The
        // per-ancestor walk that follows says which ancestor to blame when they are not.
        public function as_reportDisplayTree():void {
            if (onDisplayTreeReport == null) {
                return;
            }
            var lines:Array = [];
            var ct:ColorTransform;
            try {
                ct = this.transform.concatenatedColorTransform;
                lines.push("concatenated: mult=" + fmt(ct.redMultiplier) + "," + fmt(ct.greenMultiplier)
                    + "," + fmt(ct.blueMultiplier) + "," + fmt(ct.alphaMultiplier)
                    + " offset=" + ct.redOffset + "," + ct.greenOffset + "," + ct.blueOffset
                    + "," + ct.alphaOffset);
            } catch (ctError:Error) {
                lines.push("concatenated: unreadable (" + ctError.message + ")");
            }

            var node:DisplayObject = this as DisplayObject;
            var depth:int = 0;
            while (node != null && depth < 24) {
                lines.push(describeNode(node, depth));
                try {
                    node = node.parent;
                } catch (parentError:Error) {
                    break;
                }
                depth++;
            }
            onDisplayTreeReport(lines.join(" | "));
        }

        private static function fmt(value:Number):String {
            return String(Math.round(value * 1000) / 1000);
        }

        private static function describeNode(node:DisplayObject, depth:int):String {
            var text:String = depth + ":" + getQualifiedClassName(node).split("::").pop();
            try {
                text += " alpha=" + fmt(node.alpha) + " visible=" + node.visible;
                if (node.blendMode != BlendMode.NORMAL) {
                    text += " blend=" + node.blendMode;
                }
                if (node.filters != null && node.filters.length > 0) {
                    text += " filters=" + node.filters.length;
                }
                var own:ColorTransform = node.transform.colorTransform;
                if (own.redMultiplier != 1 || own.greenMultiplier != 1 || own.blueMultiplier != 1
                    || own.alphaMultiplier != 1 || own.redOffset != 0 || own.greenOffset != 0
                    || own.blueOffset != 0 || own.alphaOffset != 0) {
                    text += " ct=" + fmt(own.redMultiplier) + "," + fmt(own.greenMultiplier) + ","
                        + fmt(own.blueMultiplier) + "," + fmt(own.alphaMultiplier)
                        + "/" + own.redOffset + "," + own.greenOffset + "," + own.blueOffset;
                }
            } catch (nodeError:Error) {
                text += " unreadable";
            }
            return text;
        }

        public function as_refreshLayout():void {
            var stageState:Object;

            if (!_isReady) {
                return;
            }

            ResearchProgressBarStageSupport.attachListeners(
                stage,
                onStageResize,
                onStageMouseMove,
                onStageMouseLeave
            );
            layoutFromStage();
            stageState = ResearchProgressBarStageSupport.updateTrackedStageSize(stage, _lastStageWidth, _lastStageHeight);
            _lastStageWidth = Number(stageState.stageWidth);
            _lastStageHeight = Number(stageState.stageHeight);
            _lastEffectiveScale = resolveEffectiveScale();
            updateBarFromContext(false);
        }

        private function applyContext(data:Object):void {
            var nextVehicleIntCD:String = data != null && data.vehicleIntCD !== undefined && data.vehicleIntCD != null
                ? String(data.vehicleIntCD)
                : null;

            if (data == null) {
                return;
            }

            if (_selectedVehicleIntCD != nextVehicleIntCD) {
                _selectedModeId = null;
                _selectedVehicleIntCD = nextVehicleIntCD;
            }

            _context = data;

            if (!_isReady) {
                return;
            }

            updateBarFromContext(false);
        }

        private function updateBarFromContext(relayout:Boolean = true):void {
            var viewState:Object;
            var activeMode:Object;
            var fillState:Object;
            var completedOnly:Boolean;

            if (!_isReady || _context == null) {
                return;
            }

            if (baseBar == null || completedBar == null || combatBar == null || freeBar == null || markersContainer == null || modeButtonsContainer == null) {
                return;
            }

            if (relayout) {
                layoutFromStage();
            }

            viewState = ResearchProgressBarViewState.resolve(
                _context,
                _selectedModeId,
                modeButtonsContainer,
                _barX,
                _barY,
                _barWidth,
                onModeButtonClick,
                BAR_FILL_MODE_COMPLETED_ONLY
            );
            _selectedModeId = viewState.selectedModeId != null
                ? String(viewState.selectedModeId)
                : null;
            _modeIdByButton = viewState.modeIdByButton;

            updateSeparateStatusLabel();

            activeMode = viewState.activeMode;
            if (activeMode == null) {
                clearBarPresentation();
                return;
            }

            _activeCounterLayout = String(viewState.counterState.counterLayout);
            completedOnly = Boolean(viewState.completedOnly);
            fillState = viewState.fillState;

            ResearchProgressBarCounterFields.apply(
                activeMode,
                int(fillState.defaultPrimaryPercent),
                int(fillState.defaultTotalPercent),
                combatPercentLabel,
                combatPercentCaption,
                totalPercentLabel,
                totalPercentCaption,
                sideCounterLabel,
                sideCounterCaption
            );

            markersContainer.visible = true;
            ResearchProgressBarBars.render(
                baseBar,
                completedBar,
                combatBar,
                freeBar,
                completedMaskShape,
                combatMaskShape,
                freeMaskShape,
                _barX,
                _barY,
                _barWidth,
                ResearchProgressBarLayout.BAR_HEIGHT,
                fillState,
                completedOnly
            );

            rebuildMarkers(
                activeMode,
                Number(fillState.barMaxValue),
                Number(fillState.markerPrimaryValue),
                Number(fillState.markerSecondaryValue)
            );
            positionLabels();
        }

        private function clearBarPresentation():void {
            clearMarkers();
            ResearchProgressBarBars.clear(
                baseBar,
                completedBar,
                combatBar,
                freeBar,
                completedMaskShape,
                combatMaskShape,
                freeMaskShape,
                _barX,
                _barY,
                ResearchProgressBarLayout.BAR_HEIGHT
            );
            markersContainer.visible = false;
            combatPercentLabel.text = "";
            combatPercentCaption.text = "";
            totalPercentLabel.text = "";
            totalPercentCaption.text = "";
            sideCounterLabel.text = "";
            sideCounterCaption.text = "";
            _activeCounterLayout = "";
        }

        private function clearModeButtons():void {
            _modeIdByButton = ResearchProgressBarInteractions.clearModeButtons(
                modeButtonsContainer,
                onModeButtonClick
            );
        }

        private function onModeButtonClick(event:MouseEvent):void {
            var modeId:String = ResearchProgressBarInteractions.resolveClickedModeId(
                event,
                _modeIdByButton,
                _selectedModeId
            );

            if (modeId == null) {
                return;
            }

            _selectedModeId = modeId;
            ResearchProgressBarTooltipView.hideTooltip(tooltipContainer);
            updateBarFromContext(false);
        }

        private function rebuildMarkers(activeMode:Object, maxRequirementXp:Number, combatXp:Number, freeXp:Number):void {
            _markerTooltipDataByDisplay = ResearchProgressBarInteractions.rebuildMarkers(
                markersContainer,
                tooltipContainer,
                activeMode,
                maxRequirementXp,
                combatXp,
                freeXp,
                _barWidth,
                _barX,
                _barY,
                onMarkerMouseOver,
                onMarkerMouseOut,
                onMarkerClick
            );
        }

        private function clearMarkers():void {
            _markerTooltipDataByDisplay = ResearchProgressBarInteractions.clearMarkers(
                markersContainer,
                tooltipContainer
            );
            // The rebuilt markers create fresh entry objects; drop references to the
            // old ones so a key press cannot act on a destroyed marker.
            _hoveredMarkerDisplay = null;
            _hoveredStackEntries = [];
            // The markers the last hover named are gone, and the ones replacing them can carry
            // the same indices with different numbers on them. Forget the hover so the next
            // move sends the tooltip again instead of matching it away as unchanged.
            _lastHoverKey = "";
        }

        private function onMarkerMouseOver(event:MouseEvent):void {
            _hoveredMarkerDisplay = event != null ? event.currentTarget as Sprite : null;
            refreshTooltipAndStack(event.stageX, event.stageY);
        }

        private function onMarkerMouseOut(event:MouseEvent):void {
            if (_hoveredMarkerDisplay == (event != null ? event.currentTarget as Sprite : null)) {
                _hoveredMarkerDisplay = null;
            }
            refreshTooltipAndStack(event.stageX, event.stageY);
        }

        // Refresh the tooltip and, from the same entries it renders, the ordered
        // keyboard-pick stack -- so the numbers the tooltip shows and the keys that
        // act always agree (both derive from keyboardStackEntries).
        private function refreshTooltipAndStack(stageX:Number, stageY:Number):void {
            var entries:Array;
            if (EXTERNAL_TOOLTIP) {
                entries = ResearchProgressBarTooltipView.resolveEntriesAtStagePoint(
                    visible,
                    markersContainer,
                    _markerTooltipDataByDisplay,
                    stageX,
                    stageY
                );
                reportTooltipHover(entries, stageX, stageY);
            }
            else {
                entries = ResearchProgressBarTooltipView.refreshAtStagePoint(
                    visible,
                    markersContainer,
                    _markerTooltipDataByDisplay,
                    tooltipContainer,
                    tooltipBackground,
                    tooltipContent,
                    stage,
                    stageX,
                    stageY
                );
            }
            _hoveredStackEntries = ResearchProgressBarInteractions.keyboardStackEntries(entries);
        }

        // Tell Python which markers are under the cursor, by the index Python itself put on
        // each one, plus where the cursor is in stage pixels.
        private function reportTooltipHover(entries:Array, stageX:Number, stageY:Number):void {
            var indices:Array = [];
            var entry:Object;
            var idx:int;
            var key:String;

            for (idx = 0; idx < entries.length; idx++) {
                entry = entries[idx];
                if (entry != null && entry.marker != null && entry.marker.tooltipIndex !== undefined) {
                    indices.push(int(entry.marker.tooltipIndex));
                }
            }
            key = indices.join(",");
            if (key.length == 0) {
                if (_lastHoverKey.length == 0) {
                    return;
                }
                _lastHoverKey = "";
                if (onTooltipHover != null) {
                    onTooltipHover("", 0, 0);
                }
                return;
            }
            if (key == _lastHoverKey) {
                return;
            }
            // Only a change of stack is sent, not every mouse move: a move across one marker
            // fires continuously, and each send would cross into Python and redraw every
            // section of the tooltip to move it a few pixels. The tooltip view follows the
            // cursor on its own between sends, so what crosses here is content, never
            // position -- and an overlapping stack still re-renders the moment the cursor
            // steps onto a different set of markers.
            _lastHoverKey = key;
            if (onTooltipHover != null) {
                onTooltipHover(key, Math.round(stageX), Math.round(stageY));
            }
        }

        // Keyboard picking. Two cases share the number keys:
        //  - An ambiguous overlapping stack (two or more clickable markers under the
        //    cursor): 1..N run the action of the item the tooltip numbers the same.
        //  - A single hovered dual marker: WoT's hangar GFx exposes no usable
        //    right-click, so 1 (or A) picks Option A and 2 (or B) picks Option B.
        // The stack takes precedence, since it is the ambiguous one that disabled the
        // plain click.
        private function onStageKeyDown(event:KeyboardEvent):void {
            var entry:Object;
            var clickAction:Object;
            var code:int;
            var modId:Number;
            var digit:int;

            if (event == null || onMarkerClickAction == null) {
                return;
            }

            code = event.keyCode;

            if (_hoveredStackEntries.length >= 2) {
                digit = keyCodeToDigit(code);
                if (digit >= 1 && digit <= _hoveredStackEntries.length) {
                    entry = _hoveredStackEntries[digit - 1];
                    if (entry != null && entry.marker != null && entry.marker.clickAction != null) {
                        clickAction = entry.marker.clickAction;
                        moveFocusToSelf();
                        if (clickAction.extra !== undefined) {
                            onMarkerClickAction(String(clickAction.kind), Number(clickAction.id), Number(clickAction.extra));
                        }
                        else {
                            onMarkerClickAction(String(clickAction.kind), Number(clickAction.id));
                        }
                    }
                }
                return;
            }

            if (_hoveredMarkerDisplay == null) {
                return;
            }
            entry = _markerTooltipDataByDisplay[_hoveredMarkerDisplay];
            if (entry == null || entry.marker == null) {
                return;
            }
            clickAction = entry.marker.clickAction;
            if (clickAction == null || clickAction.leftId === undefined || clickAction.rightId === undefined) {
                return;
            }

            modId = Number.NaN;
            if (code == 49 || code == 97 || code == 65) {
                modId = Number(clickAction.leftId);
            }
            else if (code == 50 || code == 98 || code == 66) {
                modId = Number(clickAction.rightId);
            }
            if (!isNaN(modId)) {
                moveFocusToSelf();
                onMarkerClickAction(String(clickAction.kind), Number(clickAction.id), modId);
            }
        }

        // Digit 1..9 from a top-row (49..57) or numpad (97..105) key, else 0.
        private function keyCodeToDigit(code:int):int {
            if (code >= 49 && code <= 57) {
                return code - 48;
            }
            if (code >= 97 && code <= 105) {
                return code - 96;
            }
            return 0;
        }

        // Move focus off any marker to the (persistent) view before an action's
        // modal dialog opens. WG's AbstractView remembers the focused element to
        // restore focus to when the modal resolves; our bar destroys the clicked
        // marker on the post-action sync, so a marker left as the focused element
        // makes AbstractView.onSetModalFocus assert ("Last focused element is not
        // on display list") and corrupts modal focus, taking the hangar's loadout
        // bar down with it. Focusing the view (what AbstractView.draw does itself)
        // keeps _lastFocusedElement valid across the rebuild.
        private function moveFocusToSelf():void {
            try {
                setFocus(this);
            }
            catch (error:Error) {
            }
        }

        private function onMarkerClick(event:MouseEvent):void {
            var markerDisplay:Sprite = event != null ? event.currentTarget as Sprite : null;
            var entry:Object = markerDisplay != null ? _markerTooltipDataByDisplay[markerDisplay] : null;
            var clickAction:Object;

            if (entry == null || entry.marker == null || onMarkerClickAction == null) {
                return;
            }
            // With two or more clickable markers overlapping here a single click can
            // only ever hit the topmost, which is ambiguous. Suppress it and let the
            // player press the number the tooltip shows against the item they mean.
            if (_hoveredStackEntries.length >= 2) {
                return;
            }
            if (!ResearchProgressBarInteractions.isMarkerClickable(
                entry.marker,
                Number(entry.combatXp),
                Number(entry.freeXp)
            )) {
                return;
            }

            clickAction = entry.marker.clickAction;
            moveFocusToSelf();
            // Some single-click actions carry a second id (e.g. the modification to
            // switch a picked dual level to); pass it through when present.
            if (clickAction.extra !== undefined) {
                onMarkerClickAction(String(clickAction.kind), Number(clickAction.id), Number(clickAction.extra));
            }
            else {
                onMarkerClickAction(String(clickAction.kind), Number(clickAction.id));
            }
        }

        private function layoutFromStage():void {
            var layout:Object = ResearchProgressBarStageSupport.resolveBarLayout(stage, resolveEffectiveScale());

            x = 0;
            y = 0;
            _barX = Number(layout.barX);
            _barY = Number(layout.barY);
            _barWidth = Number(layout.barWidth);
        }

        // At interface scale x2 the GFx stage is scaled x2 (stage.scaleX == 2) while
        // stage.stageWidth still reports full client pixels, so laying out against the
        // raw stage size doubled the bar's on-screen width and pushed it off both
        // edges. We size against the logical (pre-scale) space instead, derived from
        // this view's own concatenated scale so any scale factor is handled.
        private function resolveEffectiveScale():Number {
            var concat:Matrix = transform.concatenatedMatrix;
            var scale:Number = concat.a;

            if (isNaN(scale) || scale <= 0) {
                return 1;
            }
            return scale;
        }

        private function positionLabels():void {
            ResearchProgressBarCounterLayout.positionLabels(
                _activeCounterLayout,
                _barX,
                _barY,
                _barWidth,
                ResearchProgressBarLayout.BAR_HEIGHT,
                combatPercentLabel,
                combatPercentCaption,
                totalPercentLabel,
                totalPercentCaption,
                sideCounterLabel,
                sideCounterCaption
            );
        }

        private function updateSeparateStatusLabel():void {
            var modes:Array;
            var layout:Object;
            var nextText:String = "";

            if (separateStatusLabel == null || _context == null) {
                return;
            }

            if (_context.separateStatusText !== undefined && _context.separateStatusText != null) {
                nextText = String(_context.separateStatusText);
            }

            ResearchProgressBarFonts.setText(separateStatusLabel, nextText);
            separateStatusLabel.visible = nextText.length > 0;
            if (!separateStatusLabel.visible) {
                return;
            }

            modes = ResearchProgressBarModes.resolveModes(_context);
            layout = ResearchProgressBarModes.resolveModeButtonsLayout(
                modes,
                _barX,
                _barY,
                ResearchProgressBarLayout.BAR_HEIGHT,
                ResearchProgressBarLayout.BAR_MIN_STAGE_SIDE_MARGIN
            );

            separateStatusLabel.visible = true;
            separateStatusLabel.x = Number(layout.x) + Number(layout.width) - separateStatusLabel.width;
            separateStatusLabel.y = Number(layout.y) - separateStatusLabel.height - SEPARATE_STATUS_VERTICAL_GAP;
        }

    }
}
