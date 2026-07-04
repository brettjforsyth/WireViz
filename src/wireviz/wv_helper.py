# -*- coding: utf-8 -*-

import html as _html
import re
from pathlib import Path
from typing import Dict, List

# Largest range expand() will materialise, e.g. "1-100000". A range beyond this
# is almost certainly a typo or an attempt to exhaust memory (a tiny YAML like
# "pins: [1-999999999]" would otherwise allocate a billion-element list).
MAX_EXPAND = 100_000

awg_equiv_table = {
    "0.09": "28",
    "0.14": "26",
    "0.25": "24",
    "0.34": "22",
    "0.5": "21",
    "0.75": "20",
    "1": "18",
    "1.5": "16",
    "2.5": "14",
    "4": "12",
    "6": "10",
    "10": "8",
    "16": "6",
    "25": "4",
    "35": "2",
    "50": "1",
}

mm2_equiv_table = {v: k for k, v in awg_equiv_table.items()}


def awg_equiv(mm2):
    return awg_equiv_table.get(str(mm2), "Unknown")


def mm2_equiv(awg):
    return mm2_equiv_table.get(str(awg), "Unknown")


def expand(yaml_data):
    # yaml_data can be:
    # - a singleton (normally str or int)
    # - a list of str or int
    # if str is of the format '#-#', it is treated as a range (inclusive) and expanded
    output = []
    if not isinstance(yaml_data, list):
        yaml_data = [yaml_data]
    for e in yaml_data:
        e = str(e)
        if "-" in e:
            a, b = e.split("-", 1)
            try:
                a = int(a)
                b = int(b)
            except ValueError:
                # '-' was not a delimiter between two ints, pass e through unchanged
                output.append(e)
                continue
            if abs(b - a) + 1 > MAX_EXPAND:
                raise ValueError(
                    f"Refusing to expand the range '{e}': "
                    f"{abs(b - a) + 1} items exceeds the {MAX_EXPAND} limit."
                )
            if a < b:
                for x in range(a, b + 1):
                    output.append(x)  # ascending range
            elif a > b:
                for x in range(a, b - 1, -1):
                    output.append(x)  # descending range
            else:  # a == b
                output.append(a)  # range of length 1
        else:
            try:
                x = int(e)  # single int
            except Exception:
                x = e  # string
            output.append(x)
    return output


def get_single_key_and_value(d: dict):
    k = list(d.keys())[0]
    v = d[k]
    return (k, v)


def int2tuple(inp):
    if isinstance(inp, tuple):
        output = inp
    else:
        output = (inp,)
    return output


def flatten2d(inp):
    return [
        [str(item) if not isinstance(item, List) else ", ".join(item) for item in row]
        for row in inp
    ]


def tuplelist2tsv(inp, header=None):
    output = ""
    if header is not None:
        inp.insert(0, header)
    inp = flatten2d(inp)
    for row in inp:
        output = output + "\t".join(str(remove_links(item)) for item in row) + "\n"
    return output


def remove_links(inp):
    return (
        re.sub(r"<[aA] [^>]*>([^<]*)</[aA]>", r"\1", inp)
        if isinstance(inp, str)
        else inp
    )


# --- HTML sanitisation -----------------------------------------------------
# WireViz intentionally lets a few fields (part numbers, notes) carry hyperlinks
# and line breaks into the HTML output, but everything is user-supplied YAML, so
# raw <script>, <img onerror=...>, event handlers etc. must not survive into the
# generated .html. sanitize_html escapes the whole string, then restores only a
# safe allow-list: <br> and <a href="SAFE_URL">...</a>.

_ESC_BR = re.compile(r"&lt;br\s*/?&gt;", re.IGNORECASE)
_ESC_A_OPEN = re.compile(r"&lt;a\s+href=&quot;(?P<url>.*?)&quot;&gt;", re.IGNORECASE | re.DOTALL)
_ESC_A_CLOSE = re.compile(r"&lt;/a&gt;", re.IGNORECASE)
_SCHEME = re.compile(r"^([a-z][a-z0-9+.\-]*):", re.IGNORECASE)
_SAFE_SCHEMES = {"http", "https", "mailto", "ftp"}


def _safe_url(url: str) -> bool:
    """Allow relative URLs and http/https/mailto/ftp; block javascript:, data:,
    etc. Whitespace/control chars (used to obfuscate schemes) are stripped first.
    """
    u = re.sub(r"[\s\x00-\x1f]+", "", _html.unescape(url)).lower()
    m = _SCHEME.match(u)
    return not m or m.group(1) in _SAFE_SCHEMES


def sanitize_html(inp):
    """Escape user text for safe HTML embedding, keeping only <br> and safe
    <a href> links. Non-strings pass through unchanged."""
    if not isinstance(inp, str):
        return inp
    esc = _html.escape(inp, quote=True)
    esc = _ESC_BR.sub("<br/>", esc)

    def _restore_a(match: re.Match) -> str:
        url = match.group("url")
        return f'<a href="{url}">' if _safe_url(url) else match.group(0)

    esc = _ESC_A_OPEN.sub(_restore_a, esc)
    esc = _ESC_A_CLOSE.sub("</a>", esc)
    return esc


def html_text(inp):
    """Escape user text for a Graphviz HTML-like label cell.

    Strips any `<a>` links (as remove_links does for GV output) then escapes
    `&`, `<`, `>` so user-supplied names/labels/part numbers can't inject markup
    into the generated .gv label (and, via the embedded SVG, into the HTML page).
    Non-string values pass through unchanged (e.g. integer pin numbers).
    """
    if not isinstance(inp, str):
        return inp
    return _html.escape(remove_links(inp), quote=False)


def _within_any(path: Path, bases: List[Path]) -> bool:
    """True if `path` is one of `bases` or lives inside one of them."""
    path = path.resolve()
    for base in bases:
        base = base.resolve()
        if path == base or base in path.parents:
            return True
    return False


def clean_whitespace(inp):
    return " ".join(inp.split()).replace(" ,", ",") if isinstance(inp, str) else inp


def open_file_read(filename):
    """Open utf-8 encoded text file for reading - remember closing it when finished"""
    # TODO: Intelligently determine encoding
    return open(filename, "r", encoding="UTF-8")


def open_file_write(filename):
    """Open utf-8 encoded text file for writing - remember closing it when finished"""
    return open(filename, "w", encoding="UTF-8")


def open_file_append(filename):
    """Open utf-8 encoded text file for appending - remember closing it when finished"""
    return open(filename, "a", encoding="UTF-8")


def file_read_text(filename: str) -> str:
    """Read utf-8 encoded text file, close it, and return the text"""
    return Path(filename).read_text(encoding="utf-8")


def file_write_text(filename: str, text: str) -> int:
    """Write utf-8 encoded text file, close it, and return the number of characters written"""
    return Path(filename).write_text(text, encoding="utf-8")


def is_arrow(inp):
    """
    Matches strings of one or multiple `-` or `=` (but not mixed)
    optionally starting with `<` and/or ending with `>`.

    Examples:
      <-, --, ->, <->
      <==, ==, ==>, <=>
    """
    # regex by @shiraneyo
    return bool(
        re.match(r"^\s*(?P<leftHead><?)(?P<body>-+|=+)(?P<rightHead>>?)\s*$", inp)
    )


def aspect_ratio(image_src):
    try:
        from PIL import Image

        with Image.open(image_src) as image:
            if image.width > 0 and image.height > 0:
                return image.width / image.height
            print(f"aspect_ratio(): Invalid image size {image.width} x {image.height}")
    # ModuleNotFoundError and FileNotFoundError are the most expected, but all are handled equally.
    except Exception as error:
        print(f"aspect_ratio(): {type(error).__name__}: {error}")
    return 1  # Assume 1:1 when unable to read actual image size


def smart_file_resolve(
    filename: str, possible_paths: (str, List[str]), restrict: bool = True
) -> Path:
    """Resolve `filename` against `possible_paths`.

    When `restrict` is True (the default), the resolved file must live inside
    one of `possible_paths`; absolute paths and ``../`` escapes that land
    outside every permitted directory are rejected. This prevents a malicious
    YAML file (image src or template name) from reading arbitrary files such as
    ``../../../../etc/passwd``.
    """
    if not isinstance(possible_paths, List):
        possible_paths = [possible_paths]
    bases = [Path(path).resolve() for path in possible_paths if path is not None]
    filename = Path(filename)

    if filename.is_absolute():
        candidates = [filename.resolve()]
    else:  # search all possible paths in decreasing order of precedence
        candidates = [(base / filename).resolve() for base in bases]

    for candidate in candidates:
        if candidate.exists():
            if restrict and not _within_any(candidate, bases):
                raise Exception(
                    f"Refusing to resolve '{filename}': it points outside the "
                    f"permitted directories."
                )
            return candidate
    raise Exception(
        f"{filename} was not found in any of the following locations: \n"
        + "\n".join([str(x) for x in bases])
    )
