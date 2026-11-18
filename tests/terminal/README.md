# Tests of the terminal page (hterm + app/terminal/term.js) outside the app

These load the page the app shows in its web view into a real WebKit engine with Playwright
and stub the messages to the app, so the page's behavior can be checked on any host.

Setup, once:

    pip install playwright && playwright install webkit
    (cd deps/libapps && ./hterm/bin/mkdist)        # builds hterm/dist/js/hterm_all.js
    mkdir /tmp/termtest && cp app/terminal/term.{html,css,js} deps/libapps/hterm/dist/js/hterm_all.js tests/terminal/*.py /tmp/termtest/

- `python3 /tmp/termtest/subrow.py`: the terminal must stay at the end of the buffer, and keep
  following output, when the view's height changes by less than one row; it must stay put
  when the user has scrolled back.
