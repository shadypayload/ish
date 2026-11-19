hterm.defaultStorage = new lib.Storage.Memory();
window.onload = async function() {
    await lib.init();
    window.term = new hterm.Terminal();

    // make everything invisible so as to not be embarrassing
    term.getPrefs().set('background-color', 'transparent');
    term.getPrefs().set('foreground-color', 'transparent');
    term.getPrefs().set('cursor-color', 'transparent');

    term.getPrefs().set('terminal-encoding', 'iso-2022');
    term.getPrefs().set('enable-resize-status', false);
    term.getPrefs().set('copy-on-select', false);
    term.getPrefs().set('enable-clipboard-notice', false);
    term.getPrefs().set('user-css-text', termCss);
    term.getPrefs().set('screen-padding-size', 4);
    // Creating and preloading the <audio> element for this sometimes hangs WebKit on iOS 16 for some reason. Can be most easily reproduced by resetting a simulator and starting the app. System logs show Fig hanging while trying to do work.
    term.getPrefs().set('audible-bell-sound', '');

    term.onTerminalReady = onTerminalReady;
    term.decorate(document.getElementById('terminal'));
};

var termCss = `
x-screen {
    background: transparent !important;
    overflow: hidden !important;
    -webkit-tap-highlight-color: transparent;
}
x-row {
  text-rendering: optimizeLegibility;
  font-variant-ligatures: normal;
}
.uri-node {
  text-decoration: underline;
}
`;

function onTerminalReady() {

// Shorthand for JS -> native IPC
const native = new Proxy({}, {
    get(obj, prop) {
        return (...args) => {
            if (args.length == 0)
                args = null;
            else if (args.length == 1)
                args = args[0];
            webkit.messageHandlers[prop].postMessage(args);
        };
    },
});

// Functions for native -> JS
window.exports = {};

term.io.push();
term.reset();

let oldProps = {};
function syncProp(name, value) {
    if (oldProps[name] !== value)
        native.propUpdate(name, value);
}
let decoder = new TextDecoder();
exports.write = (data) => {
    term.io.writeUTF16(decoder.decode(lib.codec.stringToCodeUnitArray(data)));
    syncProp('applicationCursor', term.keyboard.applicationCursor);
    scheduleFollow(true);
};
term.io.sendString = term.io.onVTKeyStroke = (data) => {
    native.sendInput(data);
};

// hterm size updates native size
term.io.onTerminalResize = () => native.resize();
exports.getSize = () => [term.screenSize.width, term.screenSize.height];

// selection, copying
term.scrollPort_.screen_.contentEditable = false;
term.blur();
term.focus();
exports.copy = () => term.copySelectionToClipboard();

// focus
// This listener blocks blur events that come in because the webview has lost first responder
term.scrollPort_.screen_.addEventListener('blur', (e) => {
    if (e.target.ownerDocument.activeElement == e.target) {
        e.stopPropagation();
    }
}, {capture: true});
term.scrollPort_.screen_.addEventListener('mousedown', (e) => {
    // Taps while there is a selection should be left to the selection view
    if ((document.getSelection().rangeCount != 0) &&
        (!document.getSelection().isCollapsed)) return;
    native.focus();
});
exports.setFocused = (focus) => {
    if (focus)
        term.focus();
    else
        term.blur();
};
term.scrollPort_.screen_.addEventListener('focus', (e) => native.syncFocus());

// scrolling
// Disable hterm builtin touch scrolling
term.scrollPort_.onTouch = (e) => {
    // Convince hterm that we called preventDefault() and that it shouldn't do more handling, but don't actually call it because that would break text selection
    Object.defineProperty(e, 'defaultPrevented', {value: true});
};
// Scroll to bottom wrapper
exports.scrollToBottom = () => {
    following = true;
    stuckGap = null;
    term.scrollEnd();
    scheduleFollow();
};
// Set scroll position
exports.newScrollTop = (y) => {
    // two lines instead of one because the value you read out of scrollTop can be different from the value you write into it
    term.scrollPort_.screen_.scrollTop = y;
    lastScrollTop = term.scrollPort_.screen_.scrollTop;
    // the user scrolled: back from the end, or back to it
    following = gapToEnd() < Math.max(term.scrollPort_.characterSize.height, END_SLACK);
    stuckGap = null;
};

// Send scroll height and position to native code
let lastScrollHeight, lastScrollTop;
function syncScroll() {
    const scrollHeight = parseFloat(term.scrollPort_.scrollArea_.style.height);
    if (scrollHeight != lastScrollHeight)
        native.newScrollHeight(scrollHeight);
    lastScrollHeight = scrollHeight;

    const scrollTop = term.scrollPort_.screen_.scrollTop;
    if (scrollTop != lastScrollTop)
        native.newScrollTop(scrollTop);
    lastScrollTop = scrollTop;
}

const realSyncScrollHeight = hterm.ScrollPort.prototype.syncScrollHeight;
hterm.ScrollPort.prototype.syncScrollHeight = function() {
    realSyncScrollHeight.call(this);
    const before = lastScrollHeight;
    syncScroll();
    // (redraws come through here too; only a height that really changed counts)
    if (lastScrollHeight !== before)
        scheduleFollow(true);
};
term.scrollPort_.screen_.addEventListener('scroll', syncScroll);

// Following the end of the buffer.
//
// hterm follows new output only while it believes it is scrolled to the end,
// and it loses that belief on its own when the view changes size: a change
// smaller than a row moves the end without any resize handling, and when the
// view shrinks in two steps (rotating with the keyboard up) a redraw between
// the steps measures the new height against the old row count and concludes
// the page is scrolled back. The screen then stayed on old rows, or on the
// blank ones below the text, until the next typed key scrolled down.
//
// So this file keeps the answer itself. `following` is true until the user
// scrolls back (newScrollTop from the app, which sends only the user's own
// scrolling) and true again when they return to the end or type. While it is
// true, any size change or new output that leaves a gap is closed.
let following = true;
// Being this close counts as being at the end: scroll offsets are rounded to
// device pixels, so the last fraction of a point is not always reachable.
const END_SLACK = 2;
function gapToEnd() {
    const screen = term.scrollPort_.screen_;
    return screen.scrollHeight - screen.clientHeight - screen.scrollTop;
}
// follow() must not be able to keep itself going. hterm redraws after every
// scroll and each redraw recomputes the scroll height, so anything that
// reacted to those would run again for as long as a gap stayed open (an
// earlier version did, 125 times a second). So:
// - it runs only for something from outside: a resize, output, a real change
//   of the scroll height, a typed key (never for a redraw or a scroll);
// - it gives up for good on a gap it could not close, until the gap or the
//   view's size is different;
// - and it is capped per second whatever happens.
let stuckGap = null, stuckHeight = null;
let followBudget = 12;
setInterval(() => { followBudget = 12; }, 1000);
function follow() {
    if (!following)
        return;
    const screen = term.scrollPort_.screen_;
    let gap = gapToEnd();
    if (gap <= END_SLACK) {
        stuckGap = null;
        return;
    }
    if (stuckGap !== null && Math.abs(gap - stuckGap) < 0.5 && stuckHeight === screen.clientHeight)
        return;
    if (followBudget <= 0)
        return;
    followBudget--;
    term.scrollEnd();
    gap = gapToEnd();
    if (gap > END_SLACK) {
        // hterm's row count can be behind the page's real height for a moment
        screen.scrollTop = screen.scrollHeight - screen.clientHeight;
        gap = gapToEnd();
    }
    if (gap > END_SLACK) {
        stuckGap = gap;
        stuckHeight = screen.clientHeight;
    } else {
        stuckGap = null;
    }
}
let followScheduled = false;
function scheduleFollow(fresh) {
    // new output or a new size is worth one more try at a gap given up on
    if (fresh === true)
        stuckGap = null;
    if (followScheduled)
        return;
    followScheduled = true;
    setTimeout(() => {
        followScheduled = false;
        follow();
    }, 0);
}
term.scrollPort_.subscribe('resize', () => scheduleFollow(true));
window.addEventListener('resize', () => scheduleFollow(true));

exports.updateStyle = ({foregroundColor, backgroundColor, fontFamily, fontSize, colorPaletteOverrides, blinkCursor, cursorShape}) => {
    term.getPrefs().set('background-color', backgroundColor);
    term.getPrefs().set('foreground-color', foregroundColor);
    term.getPrefs().set('cursor-color', foregroundColor);
    term.getPrefs().set('font-family', fontFamily);
    term.getPrefs().set('font-size', fontSize);
    term.getPrefs().set('color-palette-overrides', colorPaletteOverrides);
    term.getPrefs().set('cursor-blink', blinkCursor);
    term.getPrefs().set('cursor-shape', cursorShape);
};

exports.getCharacterSize = () => {
    return [term.scrollPort_.characterSize.width, term.scrollPort_.characterSize.height];
};

exports.clearScrollback = () => {
    following = true;
    term.clearScrollback();
};
exports.setUserGesture = () => term.accessibilityReader_.hasUserGesture = true;

hterm.openUrl = (url) => native.openLink(url);

native.load();
native.syncFocus();

}
