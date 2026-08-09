package {
    import flash.display.Shape;
    import flash.display.Sprite;
    import flash.events.KeyboardEvent;
    import flash.events.MouseEvent;
    import flash.text.TextField;
    import flash.text.TextFieldAutoSize;
    import flash.text.TextFormat;
    import flash.ui.Keyboard;
    import net.wg.infrastructure.base.AbstractView;

    /**
     * Mod-owned root for the customization screen.
     *
     * This is the spike build: it draws a probe panel rather than an interface. One thing it
     * does is not throwaway, because the real UI will need it -- it leaves the 3D scene
     * interactive, taking mouse input on the button alone, so the tank still rotates while
     * the panel is up.
     *
     * The panel is anchored top-left at fixed offsets and never reads the stage size, which
     * sidesteps rather than solves WoT's interface scale. Anything that stretches to the
     * viewport needs the logical-size treatment described in docs/reference/ui-and-scaleform.md.
     */
    [SWF(width="1920", height="1080", frameRate="30", backgroundColor="#000000")]
    public class ZanjuCustomizationView extends AbstractView {
        private static const PANEL_X:Number = 48;
        private static const PANEL_Y:Number = 120;
        private static const PANEL_WIDTH:Number = 560;
        private static const PANEL_PADDING:Number = 24;
        private static const BUTTON_HEIGHT:Number = 40;
        private static const TITLE_COLOR:uint = 0xF6F1E7;
        private static const BODY_COLOR:uint = 0xB8AC97;
        private static const PANEL_COLOR:uint = 0x0F1216;
        private static const BUTTON_COLOR:uint = 0x2A3138;
        private static const BUTTON_HOVER_COLOR:uint = 0x3C464F;

        // Reverse DAAPI channel: when the Python view binds flashObject.script, GFx injects
        // the same-named Python methods into these declared slots. They stay null until
        // DAAPI init completes, so every call site checks first.
        public var onSpikeViewReady:Function;
        public var leaveCustomization:Function;

        private var _panel:Sprite;
        private var _panelBackground:Shape;
        private var _titleField:TextField;
        private var _bodyField:TextField;
        private var _button:Sprite;
        private var _buttonBackground:Shape;
        private var _buttonLabel:TextField;
        private var _listeningForKeys:Boolean = false;

        public function ZanjuCustomizationView() {
            super();
        }

        override protected function configUI():void {
            super.configUI();

            // The view covers the whole screen but must not swallow input: the hangar reads
            // drag-to-rotate off the 3D scene behind us. Only the button opts back in.
            mouseEnabled = false;
            mouseChildren = true;

            _panel = new Sprite();
            _panel.mouseEnabled = false;
            addChild(_panel);

            _panelBackground = new Shape();
            _panel.addChild(_panelBackground);

            _titleField = createField(20, TITLE_COLOR, true);
            _panel.addChild(_titleField);

            _bodyField = createField(14, BODY_COLOR, false);
            _panel.addChild(_bodyField);

            _button = new Sprite();
            _button.buttonMode = true;
            _button.useHandCursor = true;
            _button.addEventListener(MouseEvent.CLICK, onButtonClick);
            _button.addEventListener(MouseEvent.ROLL_OVER, onButtonRollOver);
            _button.addEventListener(MouseEvent.ROLL_OUT, onButtonRollOut);
            _panel.addChild(_button);

            _buttonBackground = new Shape();
            _button.addChild(_buttonBackground);

            _buttonLabel = createField(14, TITLE_COLOR, true);
            _buttonLabel.mouseEnabled = false;
            _button.addChild(_buttonLabel);

            setReportText("Zanju's Customization UI", "waiting for the probe report...");
        }

        override protected function nextFrameAfterPopulateHandler():void {
            super.nextFrameAfterPopulateHandler();

            // stage is not reliably available in configUI, so the key listener is attached
            // here instead. Weak reference, matching the research progress bar's listeners.
            if (stage != null && !_listeningForKeys) {
                stage.addEventListener(KeyboardEvent.KEY_DOWN, onKeyDown, false, 0, true);
                _listeningForKeys = true;
            }

            if (onSpikeViewReady != null) {
                onSpikeViewReady();
            }
        }

        override protected function onDispose():void {
            if (_listeningForKeys && stage != null) {
                stage.removeEventListener(KeyboardEvent.KEY_DOWN, onKeyDown);
            }
            _listeningForKeys = false;

            if (_button != null) {
                _button.removeEventListener(MouseEvent.CLICK, onButtonClick);
                _button.removeEventListener(MouseEvent.ROLL_OVER, onButtonRollOver);
                _button.removeEventListener(MouseEvent.ROLL_OUT, onButtonRollOut);
            }

            onSpikeViewReady = null;
            leaveCustomization = null;
            _panel = null;
            _panelBackground = null;
            _titleField = null;
            _bodyField = null;
            _button = null;
            _buttonBackground = null;
            _buttonLabel = null;

            super.onDispose();
        }

        // -- inbound DAAPI (Python -> Flash) ---------------------------------

        public function as_setReport(title:String, body:String):void {
            setReportText(title, body);
        }

        // -- drawing ---------------------------------------------------------

        private function setReportText(title:String, body:String):void {
            if (_titleField == null || _bodyField == null) {
                return;
            }

            _titleField.text = title;
            _bodyField.text = body;
            _buttonLabel.text = "LEAVE CUSTOMIZATION";
            layout();
        }

        private function layout():void {
            if (_panel == null) {
                return;
            }

            _panel.x = PANEL_X;
            _panel.y = PANEL_Y;

            var contentWidth:Number = PANEL_WIDTH - PANEL_PADDING * 2;
            _titleField.width = contentWidth;
            _titleField.x = PANEL_PADDING;
            _titleField.y = PANEL_PADDING;

            _bodyField.width = contentWidth;
            _bodyField.x = PANEL_PADDING;
            _bodyField.y = _titleField.y + _titleField.height + 12;

            var buttonY:Number = _bodyField.y + _bodyField.height + 20;
            _button.x = PANEL_PADDING;
            _button.y = buttonY;
            drawButton(BUTTON_COLOR, contentWidth);

            _buttonLabel.width = contentWidth;
            _buttonLabel.x = 0;
            _buttonLabel.y = (BUTTON_HEIGHT - _buttonLabel.height) / 2;

            drawPanelBackground(buttonY + BUTTON_HEIGHT + PANEL_PADDING);
        }

        private function drawPanelBackground(height:Number):void {
            _panelBackground.graphics.clear();
            _panelBackground.graphics.beginFill(PANEL_COLOR, 0.82);
            _panelBackground.graphics.drawRoundRect(0, 0, PANEL_WIDTH, height, 6, 6);
            _panelBackground.graphics.endFill();
        }

        private function drawButton(color:uint, width:Number):void {
            _buttonBackground.graphics.clear();
            _buttonBackground.graphics.beginFill(color, 1);
            _buttonBackground.graphics.drawRoundRect(0, 0, width, BUTTON_HEIGHT, 4, 4);
            _buttonBackground.graphics.endFill();
        }

        private function createField(size:int, color:uint, bold:Boolean):TextField {
            var field:TextField = new TextField();
            var format:TextFormat = new TextFormat();

            // Device font: this build carries no embedded face, and the probe text is ASCII.
            // A real UI needs the font-fallback treatment the research progress bar uses.
            format.font = "Arial";
            format.size = size;
            format.color = color;
            format.bold = bold;
            if (bold) {
                format.align = "center";
            }

            field.defaultTextFormat = format;
            field.embedFonts = false;
            field.multiline = true;
            field.wordWrap = true;
            field.selectable = false;
            field.mouseEnabled = false;
            field.autoSize = TextFieldAutoSize.NONE;
            return field;
        }

        // -- interaction -----------------------------------------------------

        private function onKeyDown(event:KeyboardEvent):void {
            if (event.keyCode == Keyboard.ESCAPE) {
                requestLeave();
            }
        }

        private function onButtonClick(event:MouseEvent):void {
            requestLeave();
        }

        private function onButtonRollOver(event:MouseEvent):void {
            drawButton(BUTTON_HOVER_COLOR, PANEL_WIDTH - PANEL_PADDING * 2);
        }

        private function onButtonRollOut(event:MouseEvent):void {
            drawButton(BUTTON_COLOR, PANEL_WIDTH - PANEL_PADDING * 2);
        }

        private function requestLeave():void {
            if (leaveCustomization != null) {
                leaveCustomization();
            }
        }
    }
}
