"""Security regression tests: HTML sanitisation, path containment, DoS cap."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_helper import expand, sanitize_html, smart_file_resolve  # noqa: E402
from wireviz.wv_html import generate_html_output  # noqa: E402


# --- HTML sanitisation -----------------------------------------------------


def test_script_is_neutralised():
    out = sanitize_html("<script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_img_onerror_is_neutralised():
    out = sanitize_html('<img src=x onerror="alert(1)">')
    assert "<img" not in out
    assert "onerror" not in out or "&lt;img" in out


def test_safe_link_preserved():
    out = sanitize_html('<a href="https://example.com">part</a>')
    assert '<a href="https://example.com">part</a>' == out


def test_line_break_preserved():
    assert sanitize_html("a<br>b") == "a<br/>b"


def test_javascript_url_neutralised():
    out = sanitize_html('<a href="javascript:alert(1)">x</a>')
    assert "<a href=" not in out  # link not restored
    assert "javascript" in out  # left inert/escaped, not executable markup


def test_ampersand_escaped():
    assert sanitize_html("A & B") == "A &amp; B"


# --- end-to-end XSS through the HTML generator -----------------------------


def _minimal_bom():
    return [["Id", "Description", "Qty"], ["1", "<script>alert('bom')</script>", "1"]]


def test_gv_labels_escape_user_text():
    # user names/pin labels/types must be escaped in the Graphviz label so
    # injected markup can't pass through into the embedded SVG
    yml = """
connectors:
  X1:
    pincount: 2
    pinlabels: ["<xss>", "A&B"]
    type: "t<i>t"
  X2: {pincount: 2}
cables:
  W1: {wirecount: 2}
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""
    gv = wireviz.parse(yml, return_types="harness").graph.source
    assert "<xss>" not in gv and "&lt;xss&gt;" in gv
    assert "A&B" not in gv and "A&amp;B" in gv
    assert "t<i>t" not in gv and "t&lt;i&gt;t" in gv


def test_html_output_escapes_metadata_and_bom(tmp_path):
    base = tmp_path / "out"
    (tmp_path / "out.tmp.svg").write_text("<svg></svg>")

    class Meta(dict):
        pass

    metadata = Meta(
        title="<script>alert('title')</script>",
        description="<img src=x onerror=alert('desc')>",
        notes="hi",
    )

    class Options:
        fontname = "arial"
        bgcolor = "WH"

    generate_html_output(str(base), _minimal_bom(), metadata, Options())
    html = (tmp_path / "out.html").read_text()
    # no live tags survive: the dangerous markup is escaped to inert text
    assert "<script>" not in html
    assert "<img" not in html
    assert "&lt;script&gt;" in html  # escaped form present instead


# --- path containment ------------------------------------------------------


def test_smart_file_resolve_blocks_traversal(tmp_path):
    (tmp_path / "ok.txt").write_text("fine")
    # a legit file inside the base resolves
    assert smart_file_resolve("ok.txt", [str(tmp_path)]).name == "ok.txt"
    # a traversal escaping the base is rejected
    with pytest.raises(Exception):
        smart_file_resolve("../../../../../../etc/hostname", [str(tmp_path)])


def test_smart_file_resolve_blocks_absolute_out_of_tree(tmp_path):
    # /etc/passwd exists on the test host but is outside the permitted base
    with pytest.raises(Exception):
        smart_file_resolve("/etc/passwd", [str(tmp_path)])


def test_image_absolute_path_out_of_tree_rejected(tmp_path):
    yml = """
connectors:
  X1:
    pincount: 1
    image:
      src: /etc/passwd
  X2: {pincount: 1}
cables:
  W1: {wirecount: 1}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
"""
    with pytest.raises(Exception):
        wireviz.parse(yml, return_types="harness", image_paths=[str(tmp_path)])


# --- DoS cap ---------------------------------------------------------------


def test_expand_small_range_ok():
    assert expand("1-5") == [1, 2, 3, 4, 5]


def test_expand_huge_range_rejected():
    with pytest.raises(ValueError):
        expand("1-100000000")


def test_expand_non_range_passes_through():
    assert expand("A-B") == ["A-B"]


if __name__ == "__main__":
    import traceback

    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for name, t in tests:
        try:
            import tempfile

            names = t.__code__.co_varnames[: t.__code__.co_argcount]
            kwargs = {"tmp_path": Path(tempfile.mkdtemp())} if "tmp_path" in names else {}
            t(**kwargs)
            passed += 1
            print(f"ok   {name}")
        except Exception:
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} security tests passed")
    sys.exit(0 if passed == len(tests) else 1)
