package {
    import flash.display.Shape;
    import flash.display.Sprite;
    import flash.events.Event;
    import flash.geom.Point;
    import net.wg.infrastructure.base.AbstractView;

    /**
     * The bar's marker tooltip, as a view of its own.
     *
     * A window band applies to a whole view, not to an element inside it, so a tooltip drawn
     * inside the bar's SWF is stuck on the bar's band. The bar wants a low band -- under the
     * garage document, so other mods' widgets can cover it -- and the tooltip wants a high one,
     * above the native windows. One view cannot have both.
     *
     * So the tooltip is a second view, registered on its own band. It renders with the same
     * `ResearchProgressBarTooltipContent` the bar used, unchanged: the tooltip that appears
     * after the move is the same tooltip, drawn by the same code, in a different window.
     *
     * Python drives the content. The bar reports which markers the cursor is over, Python
     * resolves those to the entries it built, and `as_showTooltip` draws them. Nothing crosses
     * directly between the two SWFs -- they are separate views with no reference to each other.
     *
     * Position is not driven that way. The cursor moves every frame and the content only
     * changes when it crosses onto a different set of markers, so this view follows the cursor
     * itself and Python hears about it only when there is something new to draw.
     */
    public class ResearchProgressBarTooltipLobby extends AbstractView {

        private var tooltipContainer:Sprite;
        private var tooltipBackground:Shape;
        private var tooltipContent:Sprite;

        // Where the cursor was when the tooltip was last moved, in this view's own space.
        // A still cursor then costs one comparison a frame and nothing else.
        private var lastCursorX:Number = NaN;
        private var lastCursorY:Number = NaN;

        public function ResearchProgressBarTooltipLobby() {
            super();
        }

        override protected function configUI():void {
            super.configUI();
            mouseEnabled = false;
            mouseChildren = false;

            // The same three-part shape the bar built for its own tooltip: a container that
            // takes no input, a background shape, and the content above it.
            tooltipContainer = new Sprite();
            tooltipContainer.mouseEnabled = false;
            tooltipContainer.mouseChildren = false;
            tooltipContainer.visible = false;

            tooltipBackground = new Shape();
            tooltipContainer.addChild(tooltipBackground);

            tooltipContent = new Sprite();
            tooltipContent.mouseEnabled = false;
            tooltipContent.mouseChildren = false;
            tooltipContainer.addChild(tooltipContent);

            addChild(tooltipContainer);

            removeEventListener(Event.ENTER_FRAME, onEnterFrame);
            addEventListener(Event.ENTER_FRAME, onEnterFrame, false, 0, true);
        }

        override protected function onDispose():void {
            removeEventListener(Event.ENTER_FRAME, onEnterFrame);
            if (tooltipContainer != null) {
                ResearchProgressBarTooltipView.hideTooltip(tooltipContainer);
                if (tooltipContainer.parent == this) {
                    removeChild(tooltipContainer);
                }
            }
            tooltipContent = null;
            tooltipBackground = null;
            tooltipContainer = null;
            super.onDispose();
        }

        /**
         * Draw the tooltip for the entries under the cursor.
         *
         * `entries` is the array Python built for the bar, so every field the content renderer
         * reads is the one the bar would have read. `stageX`/`stageY` are global pixels, which
         * `globalToLocal` converts into this view's own space -- the stage is scaled by the
         * interface scale, and the tooltip is laid out unscaled inside it.
         *
         * The point given here is where the cursor was when the bar reported the hover, which
         * is a round trip old by the time it arrives. It anchors the first frame only; the
         * follow below corrects it on the next one.
         */
        public function as_showTooltip(entries:Array, stageX:Number, stageY:Number):void {
            var localPoint:Point;
            var localExtent:Point;

            if (tooltipContainer == null || entries == null || entries.length == 0) {
                as_hideTooltip();
                return;
            }

            localPoint = globalToLocal(new Point(stageX, stageY));
            localExtent = stageExtent();

            ResearchProgressBarTooltipView.showEntries(
                tooltipContainer,
                tooltipBackground,
                tooltipContent,
                entries,
                localPoint.x,
                localPoint.y,
                localExtent.x,
                localExtent.y
            );

            // Forget where the cursor was for the tooltip that just went away, so the first
            // frame under the new content moves it to where the cursor actually is now.
            lastCursorX = NaN;
            lastCursorY = NaN;
        }

        public function as_hideTooltip():void {
            if (tooltipContainer != null) {
                ResearchProgressBarTooltipView.hideTooltip(tooltipContainer);
            }
        }

        /**
         * Keep the drawn tooltip under the cursor.
         *
         * `mouseX`/`mouseY` are the cursor in this view's own coordinates, which the player
         * keeps current whether or not the view takes mouse input -- and this one takes none.
         * Reading them costs nothing, so the tooltip can follow at the frame rate without
         * anything crossing into Python.
         *
         * Only the position is refreshed here. What the tooltip says still comes from Python,
         * which sends it again whenever the cursor crosses onto a different set of markers --
         * so an overlapping stack re-renders as the cursor moves through it, from this same
         * per-frame motion, one send per change rather than one per frame.
         */
        private function onEnterFrame(event:Event):void {
            var localExtent:Point;

            if (tooltipContainer == null || !tooltipContainer.visible) {
                return;
            }
            if (mouseX == lastCursorX && mouseY == lastCursorY) {
                return;
            }

            lastCursorX = mouseX;
            lastCursorY = mouseY;
            localExtent = stageExtent();
            ResearchProgressBarTooltipView.repositionAtPoint(
                tooltipContainer,
                mouseX,
                mouseY,
                localExtent.x,
                localExtent.y
            );
        }

        // The far corner of the stage in this view's space, which is what the tooltip clamps
        // itself against so it never runs off the screen.
        private function stageExtent():Point {
            return stage != null
                ? globalToLocal(new Point(stage.stageWidth, stage.stageHeight))
                : new Point(NaN, NaN);
        }

        public function as_ping():String {
            return "tooltip-ok";
        }
    }
}
