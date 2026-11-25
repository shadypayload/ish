# A view height that changes and comes straight back must leave the screen exactly as it was
# (same rows, same cursor row, same scrollback) and report nothing to the app; a height that
# lasts must still be applied and reported. See RESIZE_SETTLE in app/terminal/term.js.
import pathlib, sys
from playwright.sync_api import sync_playwright
here = pathlib.Path(__file__).parent.resolve()
html = sys.argv[1] if len(sys.argv) > 1 else 'term.html'
STUB = "window.__msgs=[]; window.webkit={messageHandlers:new Proxy({},{get:(o,n)=>({postMessage:(b)=>window.__msgs.push([n,b])})})};"
fails = 0
def check(ok, label, detail=''):
    global fails
    fails += 0 if ok else 1
    print(('PASS  ' if ok else 'FAIL  ') + label + (('  ' + detail) if detail and not ok else ''))
with sync_playwright() as p:
    b = p.webkit.launch(); page = b.new_page(viewport={'width': 720, 'height': 500})
    page.add_init_script(STUB); page.goto((here/html).as_uri())
    page.wait_for_function("window.__msgs.some(m => m[0] == 'load')")
    page.evaluate("exports.updateStyle({foregroundColor:'#fff', backgroundColor:'#000', fontFamily:'Menlo, monospace', fontSize: 13, colorPaletteOverrides: {}, blinkCursor: false, cursorShape: 'BLOCK'})")
    page.wait_for_timeout(800)
    ch = page.evaluate("term.scrollPort_.characterSize.height")
    # a full screen with scrollback, a blank last row, and the cursor three rows above the end:
    # how a program with a status line at the bottom leaves the terminal
    page.evaluate("for (let i = 0; i < 80; i++) exports.write('line ' + i + '\\r\\n'); exports.write('\\x1b[3A> input')")
    page.wait_for_timeout(500)
    def state(): return page.evaluate("JSON.stringify([term.screen_.rowsArray.map(r => r.textContent), term.screen_.cursorPosition.row, term.scrollbackRows_.length, exports.getSize()])")
    def resizes(): return page.evaluate("(() => { const n = window.__msgs.filter(m => m[0] == 'resize').length; window.__msgs = []; return n; })()")
    resizes(); before = state()
    for name, dh, hold in (('one row shorter, at once', -ch, 0), ('one row taller, at once', ch, 0), ('one row shorter for 60 ms', -ch, 60),
                           ('one row taller for 60 ms', ch, 60), ('ten rows taller for 60 ms', 10 * ch, 60), ('wider for 60 ms', 0, 60)):
        page.set_viewport_size({'width': 720 + (200 if name.startswith('wider') else 0), 'height': int(500 + dh)})
        if hold: page.wait_for_timeout(hold)
        page.set_viewport_size({'width': 720, 'height': 500}); page.wait_for_timeout(900)
        after = state(); n = resizes()
        check(after == before, f'{name}, and back: the screen is as it was')
        check(n == 0, f'{name}, and back: nothing reported to the app', f'{n} resize messages')
        before = state()
    rows0 = page.evaluate("exports.getSize()")[1]
    page.set_viewport_size({'width': 720, 'height': int(500 - 3 * ch)}); page.wait_for_timeout(900)
    check(page.evaluate("exports.getSize()")[1] == rows0 - 3, 'a height that lasts is applied', str(page.evaluate("exports.getSize()")))
    check(resizes() >= 1, 'a height that lasts is reported to the app')
    page.set_viewport_size({'width': 720, 'height': 500}); page.wait_for_timeout(900)
    check(page.evaluate("exports.getSize()")[1] == rows0 and resizes() >= 1, 'and so is the way back')
    # a size that keeps changing is still applied within the maximum wait
    for i in range(12):
        page.set_viewport_size({'width': 720, 'height': int(500 - (i % 2) * ch - 5 * ch)}); page.wait_for_timeout(80)
    check(resizes() >= 1, 'a height that keeps changing is applied within the maximum wait')
    b.close()
print('failed:', fails); sys.exit(1 if fails else 0)
