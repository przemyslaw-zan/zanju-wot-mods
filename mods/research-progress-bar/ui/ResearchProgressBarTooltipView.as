package {
    import flash.display.Shape;
    import flash.display.Sprite;
    import flash.display.Stage;
    import flash.geom.Point;
    import flash.geom.Rectangle;
    import flash.utils.Dictionary;

    public final class ResearchProgressBarTooltipView {
        private static const TOOLTIP_BACKGROUND_COLOR:uint = 0x0B0B0B;
        private static const TOOLTIP_BACKGROUND_ALPHA:Number = 0.93;
        private static const TOOLTIP_BORDER_COLOR:uint = 0x7A6954;
        private static const TOOLTIP_PADDING_X:Number = 8;
        private static const TOOLTIP_PADDING_Y:Number = 6;
        private static const TOOLTIP_PADDING_BOTTOM:Number = 8;
        private static const TOOLTIP_OFFSET_Y:Number = 15;

        // The tooltip's size as last drawn, kept so the cursor can be followed without
        // rebuilding the content. One tooltip is on screen at a time in either SWF, so a
        // single pair of numbers covers it.
        private static var lastDrawnWidth:Number = NaN;
        private static var lastDrawnHeight:Number = NaN;

        public static function showEntries(
            tooltipContainer:Sprite,
            tooltipBackground:Shape,
            tooltipContent:Sprite,
            entries:Array,
            stageX:Number,
            stageY:Number,
            stageWidth:Number,
            stageHeight:Number
        ):void {
            var entry:Object;
            var section:Sprite;
            var sectionBounds:Rectangle;
            var contentBounds:Rectangle;
            var cursorY:Number = 0;
            var idx:int;
            var tooltipWidth:Number;
            var tooltipHeight:Number;
            var keyEntries:Array;
            var keyIndex:int;
            // Content-space Y of each divider drawn between stacked sections.
            var separatorYs:Array = [];

            if (tooltipContainer == null || tooltipBackground == null || tooltipContent == null) {
                return;
            }

            clearContent(tooltipContent);

            // Number the stack only when a plain click would be ambiguous -- two or
            // more keyboard-pickable markers overlapping here. A lone clickable
            // marker keeps its plain "Click to research." hint.
            keyEntries = ResearchProgressBarInteractions.keyboardStackEntries(entries);
            if (keyEntries.length < 2) {
                keyEntries = null;
            }

            for (idx = 0; idx < entries.length; idx++) {
                entry = entries[idx];
                keyIndex = keyEntries != null ? keyEntries.indexOf(entry) + 1 : 0;
                section = ResearchProgressBarTooltipContent.buildTooltipSection(entry, keyIndex);
                section.y = cursorY;
                tooltipContent.addChild(section);
                sectionBounds = section.getBounds(section);
                cursorY += sectionBounds.height;
                if (idx < entries.length - 1) {
                    separatorYs.push(cursorY + ResearchProgressBarTooltipContent.SECTION_GAP / 2);
                    cursorY += ResearchProgressBarTooltipContent.SECTION_GAP;
                }
            }

            contentBounds = tooltipContent.getBounds(tooltipContent);
            tooltipContent.x = TOOLTIP_PADDING_X - contentBounds.x;
            tooltipContent.y = TOOLTIP_PADDING_Y - contentBounds.y;

            tooltipWidth = contentBounds.width + TOOLTIP_PADDING_X * 2;
            tooltipHeight = contentBounds.height + TOOLTIP_PADDING_Y + TOOLTIP_PADDING_BOTTOM;
            drawBackground(tooltipBackground, tooltipWidth, tooltipHeight);
            // Divide stacked sections with a line in the tooltip's own border style.
            drawSectionSeparators(tooltipBackground, separatorYs, tooltipContent.y, tooltipWidth);

            lastDrawnWidth = tooltipWidth;
            lastDrawnHeight = tooltipHeight;
            tooltipContainer.visible = true;
            positionContainer(tooltipContainer, stageX, stageY, tooltipWidth, tooltipHeight, stageWidth, stageHeight);
        }

        public static function hideTooltip(tooltipContainer:Sprite):void {
            if (tooltipContainer != null) {
                tooltipContainer.visible = false;
            }
        }

        // Move the drawn tooltip to a new cursor point without rebuilding it.
        //
        // The content only changes when the set of markers under the cursor changes, but the
        // tooltip has to follow the cursor every frame in between, and rebuilding it for a
        // move would redraw every section for nothing. The size is the one measured when the
        // content was drawn, so the tooltip clamps against the screen edges exactly as it did
        // on the way in.
        public static function repositionAtPoint(
            tooltipContainer:Sprite,
            localX:Number,
            localY:Number,
            localWidthExtent:Number,
            localHeightExtent:Number
        ):void {
            if (tooltipContainer == null || !tooltipContainer.visible) {
                return;
            }
            if (isNaN(lastDrawnWidth) || isNaN(lastDrawnHeight)) {
                return;
            }

            positionContainer(
                tooltipContainer,
                localX,
                localY,
                lastDrawnWidth,
                lastDrawnHeight,
                localWidthExtent,
                localHeightExtent
            );
        }

        // The hit test on its own, without drawing anything: the ordered tooltip-stack entries
        // under the point, empty when there is nothing there.
        //
        // Used when the tooltip is drawn by a second view on a band of its own. The bar still
        // has to resolve what is under the cursor, because the keyboard-pick stack is built
        // from the same entries the tooltip shows and the two must not disagree.
        public static function resolveEntriesAtStagePoint(
            hostVisible:Boolean,
            markersContainer:Sprite,
            tooltipDataByDisplay:Dictionary,
            stageX:Number,
            stageY:Number
        ):Array {
            var localPoint:Point;

            if (!hostVisible || markersContainer == null) {
                return [];
            }
            // The mouse point arrives in global stage pixels; markers live in this view's local
            // space, which the GFx stage scales by the interface scale. globalToLocal inverts
            // that whole chain.
            localPoint = markersContainer.globalToLocal(new Point(stageX, stageY));
            return resolveEntriesAtLocalPoint(
                markersContainer,
                tooltipDataByDisplay,
                localPoint.x,
                localPoint.y
            );
        }

        public static function refreshAtStagePoint(
            hostVisible:Boolean,
            markersContainer:Sprite,
            tooltipDataByDisplay:Dictionary,
            tooltipContainer:Sprite,
            tooltipBackground:Shape,
            tooltipContent:Sprite,
            stageSpace:Stage,
            stageX:Number,
            stageY:Number
        ):Array {
            var tooltipEntries:Array;
            var localPoint:Point;
            var localExtent:Point;

            if (!hostVisible || markersContainer == null) {
                hideTooltip(tooltipContainer);
                return [];
            }

            // The mouse point arrives in global stage pixels, but markers and the
            // tooltip live in this view's local space, which the GFx stage scales by
            // the interface scale (x2 etc.). globalToLocal inverts that whole chain,
            // so we hit-test and position entirely in local coordinates.
            localPoint = markersContainer.globalToLocal(new Point(stageX, stageY));

            tooltipEntries = resolveEntriesAtLocalPoint(
                markersContainer,
                tooltipDataByDisplay,
                localPoint.x,
                localPoint.y
            );

            if (tooltipEntries.length == 0) {
                hideTooltip(tooltipContainer);
                return [];
            }

            localExtent = stageSpace != null
                ? markersContainer.globalToLocal(new Point(stageSpace.stageWidth, stageSpace.stageHeight))
                : new Point(NaN, NaN);

            showEntries(
                tooltipContainer,
                tooltipBackground,
                tooltipContent,
                tooltipEntries,
                localPoint.x,
                localPoint.y,
                localExtent.x,
                localExtent.y
            );
            return tooltipEntries;
        }

        public static function resolveEntriesAtLocalPoint(
            markersContainer:Sprite,
            tooltipDataByDisplay:Dictionary,
            localX:Number,
            localY:Number
        ):Array {
            var entries:Array = [];
            var candidate:Sprite;
            var candidateBounds:Rectangle;
            var candidateData:Object;
            var idx:int;

            if (markersContainer == null || tooltipDataByDisplay == null) {
                return entries;
            }

            for (idx = 0; idx < markersContainer.numChildren; idx++) {
                candidate = markersContainer.getChildAt(idx) as Sprite;
                if (candidate == null) {
                    continue;
                }

                candidateBounds = candidate.getBounds(markersContainer);
                if (candidateBounds == null || !candidateBounds.contains(localX, localY)) {
                    continue;
                }

                candidateData = tooltipDataByDisplay[candidate];
                if (candidateData != null) {
                    entries.push(candidateData);
                }
            }

            return entries;
        }

        private static function clearContent(tooltipContent:Sprite):void {
            if (tooltipContent == null) {
                return;
            }

            while (tooltipContent.numChildren > 0) {
                tooltipContent.removeChildAt(0);
            }
        }

        private static function positionContainer(
            tooltipContainer:Sprite,
            stageX:Number,
            stageY:Number,
            tooltipWidth:Number,
            tooltipHeight:Number,
            stageWidth:Number,
            stageHeight:Number
        ):void {
            var tooltipX:Number = stageX - Math.round(tooltipWidth / 2);
            var tooltipY:Number = stageY + TOOLTIP_OFFSET_Y;
            var minX:Number = 4;
            var maxX:Number;
            var minY:Number = 4;
            var maxY:Number;

            if (!isNaN(stageWidth) && !isNaN(stageHeight)) {
                maxX = stageWidth - tooltipWidth - 4;
                maxY = stageHeight - tooltipHeight - 4;
                if (tooltipX < minX) {
                    tooltipX = minX;
                }
                if (tooltipX > maxX) {
                    tooltipX = maxX;
                }

                if (tooltipY > maxY) {
                    tooltipY = stageY - tooltipHeight - TOOLTIP_OFFSET_Y;
                }

                if (tooltipY < minY) {
                    tooltipY = minY;
                }
                if (tooltipY > maxY) {
                    tooltipY = maxY;
                }
            }

            tooltipContainer.x = Math.round(tooltipX);
            tooltipContainer.y = Math.round(tooltipY);
        }

        private static function drawBackground(tooltipBackground:Shape, width:Number, height:Number):void {
            tooltipBackground.graphics.clear();
            tooltipBackground.graphics.lineStyle(1, TOOLTIP_BORDER_COLOR, 1.0);
            tooltipBackground.graphics.beginFill(TOOLTIP_BACKGROUND_COLOR, TOOLTIP_BACKGROUND_ALPHA);
            tooltipBackground.graphics.drawRoundRect(0, 0, width, height, 6, 6);
            tooltipBackground.graphics.endFill();
        }

        // Draws a horizontal divider between each pair of stacked sections, in the same
        // 1px border colour as the tooltip outline so it reads as part of the frame. The
        // separator Ys arrive in content space; contentOffsetY maps them into the
        // background's own coordinates (the two are siblings under the container). The
        // lines run edge to edge, meeting the side borders at their straight midsection.
        private static function drawSectionSeparators(tooltipBackground:Shape, separatorYs:Array, contentOffsetY:Number, width:Number):void {
            var i:int;
            var lineY:Number;

            if (separatorYs == null || separatorYs.length == 0) {
                return;
            }

            tooltipBackground.graphics.lineStyle(1, TOOLTIP_BORDER_COLOR, 1.0);
            for (i = 0; i < separatorYs.length; i++) {
                lineY = Math.round(Number(separatorYs[i]) + contentOffsetY);
                tooltipBackground.graphics.moveTo(0, lineY);
                tooltipBackground.graphics.lineTo(width, lineY);
            }
        }
    }
}