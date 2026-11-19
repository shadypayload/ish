# Does the page keep working with nothing happening? Counts scrollEnd calls and messages to the app while idle.
import pathlib, sys
from playwright.sync_api import sync_playwright
here = pathlib.Path(__file__).parent.resolve()
html = sys.argv[1] if len(sys.argv) > 1 else 'term.html'
STUB = "window.__msgs=[]; window.webkit={messageHandlers:new Proxy({},{get:(o,n)=>({postMessage:(b)=>window.__msgs.push([n,b])})})};"
worst = 0
with sync_playwright() as p:
    b = p.webkit.launch()
    for dsf in (2, 1):
        page = b.new_page(viewport={'width': 820, 'height': 709}, device_scale_factor=dsf)
        page.add_init_script(STUB); page.goto((here/html).as_uri())
        page.wait_for_function("window.__msgs.some(m => m[0] == 'load')")
        for fs in (13, 12.5, 14, 11):
            page.evaluate(f"exports.updateStyle({{foregroundColor:'#fff', backgroundColor:'#000', fontFamily:'Menlo, monospace', fontSize: {fs}, colorPaletteOverrides: {{}}, blinkCursor: false, cursorShape: 'BLOCK'}})")
            page.wait_for_timeout(300)
            page.evaluate("window.__n=0; if(!window.__w){window.__w=1; const o=term.scrollEnd.bind(term); term.scrollEnd=()=>{window.__n++; return o();};}")
            page.evaluate("for (let i=0;i<200;i++) exports.write('n='+i+'\\r\\n')")
            for h in ('709px', '709.5px', '703.3px', '361.7px', '450.25px', '1069.5px', '699.75px'):
                page.evaluate(f"for (const e of [document.documentElement, document.body, document.getElementById('terminal')]) e.style.height='{h}'; window.dispatchEvent(new Event('resize'))")
                page.evaluate("exports.write('x\\r\\n')")
                page.wait_for_timeout(400)
                page.evaluate("window.__n=0; window.__msgs=[]")
                page.wait_for_timeout(1000)
                n = page.evaluate("window.__n"); m = page.evaluate("window.__msgs.length")
                st = page.evaluate("(() => { const s=term.scrollPort_.screen_; return [s.scrollTop, s.scrollHeight, s.clientHeight, s.scrollHeight-s.clientHeight-s.scrollTop, term.scrollPort_.characterSize.height].map(x=>Math.round(x*100)/100).join(' ') })()")
                worst = max(worst, n, m)
                if n > 2 or m > 2:
                    print(f"SPIN  dsf={dsf} font={fs} height={h}: {n} scrollEnd calls and {m} messages in 1 idle second  [top height client gap rowH] = {st}")
        page.close()
    b.close()
print('worst idle activity per second:', worst)
sys.exit(1 if worst > 2 else 0)
