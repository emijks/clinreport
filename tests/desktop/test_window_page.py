"""The control window's page: one self-contained document that runs on the oldest supported WebKit (macOS 10.15)."""

import re

import pytest
from clinreport_desktop.__main__ import UI_DIR, window_page

# Newer than Safari 13.0 (macOS 10.15 as shipped) and not provided by the inline script in index.html.
TOO_NEW_JS = {
    r'\?\.[\w(\[]': 'optional chaining (Safari 13.1)',
    r'\?\?': 'nullish coalescing (Safari 13.1)',
    r'\.replaceAll\(': 'String.replaceAll (Safari 13.1)',
    r'(\|\||&&)=': 'logical assignment (Safari 14)',
    r'\.at\(': 'Array/String.at (Safari 15.4)',
    r'structuredClone|Object\.hasOwn|\.findLast|\.toSorted\(|\.toReversed\(': 'Safari 15.4+ API',
    r'\bthis\.#|(^|[{;])\s*#\w+|\bstatic\s+\w+\s*[=;]': 'private or static class fields (Safari 14.1)',
}


def test_window_page_is_self_contained():
    page = window_page()
    assert 'href="app.css"' not in page and 'src="app.js"' not in page
    assert '--accent' in page and 'function init()' in page  # app.css and app.js are inside
    assert not re.search(r'(src|href)="(?!#|https?:)[^"]+"', page), 'the page must not load files: there is no server'


@pytest.mark.parametrize('name', ['app.js', 'app.css'])
def test_inlined_files_do_not_close_their_tag(name):
    assert not re.search(r'</(script|style)', (UI_DIR / name).read_text(encoding='utf-8'), re.IGNORECASE)


def test_app_js_runs_on_safari_13():
    code = (UI_DIR / 'app.js').read_text(encoding='utf-8')
    code = re.sub(r"'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`|//[^\n]*", "''", code)  # strings and comments
    found = [f'{what}: {m.group().strip()!r}' for rx, what in TOO_NEW_JS.items() for m in re.finditer(rx, code, re.M)]
    assert not found, found


def test_inline_script_provides_replace_children():
    page = (UI_DIR / 'index.html').read_text(encoding='utf-8')
    head = page.split('</head>')[0]
    assert 'Element.prototype.replaceChildren = function' in head
    assert '=>' not in head and 'const ' not in head and 'let ' not in head  # stays ES5
