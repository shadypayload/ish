# Reproduce the stale screen: a change of the view's height by less than one row while at the bottom.
import pathlib, sys
from playwright.sync_api import sync_playwright
here = pathlib.Path(__file__).parent.resolve()
html = sys.argv[1] if len(sys.argv) > 1 else 'term.html'
STUB = "window.__msgs=[]; window.webkit={messageHandlers:new Proxy({},{get:(o,n)=>({postMessage:(b)=>window.__msgs.push([n,b])})})};"
fails = 0
with sync_playwright() as p:
    b = p.webkit.launch(); page = b.new_page(viewport={'width': 820, 'height': 709})
    page.add_init_script(STUB); page.goto((here/html).as_uri())
    page.wait_for_function("window.__msgs.some(m => m[0] == 'load')")
    page.evaluate("exports.updateStyle({foregroundColor:'#fff', backgroundColor:'#000', fontFamily:'Menlo, monospace', fontSize: 13, colorPaletteOverrides: {}, blinkCursor: false, cursorShape: 'BLOCK'})")
    page.wait_for_timeout(300)
    n = [0]
    def out(k):
        page.evaluate(f"for (let i={n[0]};i<{n[0]+k};i++) exports.write('n='+i+'\\r\\n')"); n[0] += k
    def st(label, expect_bottom=True):
        global fails
        page.wait_for_timeout(250)
        v = [float(x) for x in page.evaluate("(() => { const s = term.scrollPort_.screen_; return [s.scrollTop, parseFloat(term.scrollPort_.scrollArea_.style.height), s.clientHeight, term.screenSize.height, term.getRowCount(), term.scrollPort_.characterSize.height].join(' '); })()").split()]
        gap = v[1] - v[2] - v[0]
        atb = abs(gap) < 1.5
        tag = 'PASS' if atb == expect_bottom else 'FAIL'
        if atb != expect_bottom: fails += 1
        print(f"{tag}  {label:46s} top={v[0]:.0f} height={v[1]:.0f} client={v[2]:.0f} rows={v[3]:.0f} rowCount={v[4]:.0f} -> {'at the bottom' if atb else '%.0f px above the bottom' % gap}")
    out(120); st('120 lines')
    for h, name in ((699, 'height -10 px (less than a row)'), (709, 'height +10 px'), (719, 'height +10 px again'), (709, 'height -10 px')):
        page.set_viewport_size({'width': 820, 'height': h}); st(name); out(8); st('  8 more lines of output')
    page.set_viewport_size({'width': 1100, 'height': 400}); st('rotate (real resize)'); out(8); st('  8 more lines')
    page.set_viewport_size({'width': 820, 'height': 709}); st('rotate back'); out(8); st('  8 more lines')
    # scrolled up by the user: must stay where it is through a sub-row change and through output
    top = float(page.evaluate("term.scrollPort_.screen_.scrollTop"))
    page.evaluate(f"exports.newScrollTop({top - 300})"); st('user scrolls up 300 px', expect_bottom=False)
    page.set_viewport_size({'width': 820, 'height': 699}); st('height -10 px while scrolled up', expect_bottom=False)
    out(8); st('  output while scrolled up', expect_bottom=False)
    page.evaluate("exports.scrollToBottom()"); st('key typed')
    b.close()
print('failed:', fails); sys.exit(1 if fails else 0)
