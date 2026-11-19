# Force the situation where the page can never quite reach the end (a gap that stays open) and
# count how much work the page does while nothing is happening.
import pathlib, sys
from playwright.sync_api import sync_playwright
here = pathlib.Path(__file__).parent.resolve()
html = sys.argv[1] if len(sys.argv) > 1 else 'term.html'
STUB = "window.__msgs=[]; window.webkit={messageHandlers:new Proxy({},{get:(o,n)=>({postMessage:(b)=>window.__msgs.push([n,b])})})};"
bad = 0
with sync_playwright() as p:
    b = p.webkit.launch(); page = b.new_page(viewport={'width': 820, 'height': 709})
    page.add_init_script(STUB); page.goto((here/html).as_uri())
    page.wait_for_function("window.__msgs.some(m => m[0] == 'load')")
    page.evaluate("exports.updateStyle({foregroundColor:'#fff', backgroundColor:'#000', fontFamily:'Menlo, monospace', fontSize: 13, colorPaletteOverrides: {}, blinkCursor: false, cursorShape: 'BLOCK'})")
    page.wait_for_timeout(300)
    page.evaluate("for (let i=0;i<200;i++) exports.write('n='+i+'\\r\\n')"); page.wait_for_timeout(300)
    for short in (1, 3, 20):
        # the screen refuses to scroll closer than `short` px to the end
        page.evaluate("""(short) => {
            const s = term.scrollPort_.screen_;
            const d = Object.getOwnPropertyDescriptor(Element.prototype, 'scrollTop');
            Object.defineProperty(s, 'scrollTop', {configurable: true,
                get() { return d.get.call(this); },
                set(v) { d.set.call(this, Math.min(v, this.scrollHeight - this.clientHeight - short)); }});
            window.__n = 0;
            if (!window.__w) { window.__w = 1; const o = term.scrollEnd.bind(term); term.scrollEnd = () => { window.__n++; return o(); }; }
            s.scrollTop = 1e9;
        }""", short)
        page.evaluate("exports.write('x\\r\\n'); window.dispatchEvent(new Event('resize'))")
        page.wait_for_timeout(500)
        page.evaluate("window.__n = 0; window.__msgs = []")
        page.wait_for_timeout(2000)
        n = page.evaluate("window.__n"); m = page.evaluate("window.__msgs.length")
        ok = n <= 2 and m <= 4
        if not ok: bad += 1
        print(f"{'PASS' if ok else 'FAIL'}  gap that stays open at {short:2d} px: {n} scrollEnd calls and {m} messages to the app in 2 idle seconds")
    # still stuck 20 px short: output must keep being followed (as closely as it can), at a bounded cost
    page.evaluate("window.__n = 0")
    t0 = page.evaluate("term.scrollPort_.screen_.scrollTop")
    for i in range(10):
        page.evaluate("exports.write('more\\r\\n')"); page.wait_for_timeout(100)
    page.wait_for_timeout(500)
    t1 = page.evaluate("term.scrollPort_.screen_.scrollTop"); n = page.evaluate("window.__n")
    ok = t1 - t0 > 100 and n <= 40
    if not ok: bad += 1
    print(f"{'PASS' if ok else 'FAIL'}  with the gap still open, 10 lines of output moved the view {t1 - t0:.0f} px with {n} scrollEnd calls")
    # a burst of 2000 writes must not cost 2000 follow-ups
    page.evaluate("window.__n = 0; for (let i = 0; i < 2000; i++) exports.write('burst ' + i + '\\r\\n')")
    page.wait_for_timeout(1500)
    n = page.evaluate("window.__n"); ok = n <= 40
    if not ok: bad += 1
    print(f"{'PASS' if ok else 'FAIL'}  2000 writes in a burst: {n} scrollEnd calls")
    b.close()
print('failed:', bad); sys.exit(1 if bad else 0)
