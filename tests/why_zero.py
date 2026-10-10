"""Why can no region reading see the readrare.com case? Ask the parser, not the log.

The twenty-fourth awakening named the case (round 1082 of the pinned fuzz):
`hn https://readrare.com/`, clean 2,513 kept 314, lost 2,199, and *every*
frame-attributing reading returns exactly 0 — `in_root` 0, `ptext` 0, `inline`
0, `li` 0, `frames` 0 — while `span` fires. This script answers where the loss
fell, on both the honest page and the mutated one, and whether the root region
even exists after the mutation.

Usage: python why_zero.py CASE.html  https://readrare.com/
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
sys.path.insert(0, HERE)

import keyhole  # noqa: E402
from keyhole import _NoChromeReader, _Reader  # noqa: E402
import probe_gate_pos as pg  # noqa: E402


def show(tag, html):
    print(f"\n===== {tag}  ({len(html):,} bytes of html)")
    m = pg._pg.measure(html)
    for k in ("kept", "ratio", "rung", "scope", "drop_in_root", "ate", "by_label"):
        print(f"   {k:<14} {m[k]!r}")
    nc = keyhole._reader(html, _NoChromeReader)
    kept_nc = len(keyhole._text_of(nc))
    print(f"   no-chrome kept {kept_nc:,}")
    pos = keyhole._reader(html, pg._PosReader)
    print(f"   pos: sup_in_root {pos.sup_in_root:,}  sup_ptext {pos.sup_ptext:,}  "
          f"sup_pinline {pos.sup_pinline:,}  _para {pos._para:,}  "
          f"kinds {pos.kinds()}")
    print(f"   frames recorded: {len(pos.frames)}")
    for f in pos.frames:
        print(f"     {f['chars']:>8,}  {f['label']:<28} ended {f['how']:<8} {f['kinds']}")
    # How much text does each pass return, and where does the difference live?
    strict = keyhole._text_of(keyhole._reader(html, _Reader))
    print(f"   strict kept {len(strict):,}  |  no-chrome {kept_nc:,}  "
          f"|  difference {kept_nc - len(strict):,}")
    return m, pos


def main():
    path = sys.argv[1]
    with open(path, encoding="utf-8", errors="replace") as fh:
        html = fh.read()
    from probe_gate import cached_download
    url = sys.argv[2]
    clean = cached_download(url)
    show("HONEST", clean)
    show("MUTATED", html)


if __name__ == "__main__":
    main()
