# Keyhole

**Fetch the pages other tools can't.**

Most fetchers fail in one of two ways. They get blocked by a bot wall and hand
back a `403` the caller has to decode, or they succeed and return 9,000
characters of nav, cookie banner, and footer soup. Keyhole does neither.

```bash
./keyhole.py fetch https://example.com                 # status + title + summary
./keyhole.py fetch https://example.com --md            # clean markdown
./keyhole.py fetch https://example.com --json          # everything, structured
./keyhole.py fetch https://example.com --links         # links, absolutised
./keyhole.py fetch https://example.com --render        # escalate to a real browser
cat urls.txt | ./keyhole.py batch --jobs 8             # survey many at once
```

No install, no dependencies — Python 3.8+ stdlib only.

## Why this exists

Three failures observed in a single working session, all of them the same
underlying problem:

| Target | Naive client | Keyhole |
|---|---|---|
| `api.abund.ai` | `403 error code: 1010` | `200`, content extracted |
| `en.wikipedia.org` | `200`, but 0 links / 0 markdown | `200`, 21,892 chars, 60 links |
| `larecompensa.online` | `200`, 18 chars (React shell) | `4,024,515` DOM, 17,521 chars via `--render` |
| `www.npmjs.com` | Cloudflare interstitial | `200`, 6,187 chars |

The `1010` case is the common one: Cloudflare rejects a request whose
`User-Agent` says `Python-urllib`. A realistic header set fixes it outright.

## Design

**Walls are named, never returned.** When a response is a bot wall, Keyhole says
which one — `cloudflare_1010`, `cloudflare_challenge`, `datadome`,
`perimeterx`, `consent_gate`, … — and why, plus the way out. A wall is a fact,
not a 403 to guess at.

**The parser tolerates malformed HTML structurally.** It keeps an explicit tag
stack instead of depth counters. Depth counters desynchronise the moment a
document has an unbalanced or void tag, and then silently drop the rest of the
page — which is exactly how a 320KB article once parsed down to zero characters
while reporting `200`. Two real bugs are frozen as tests in
`tests/test_keyhole.py`:

- `<html class="…main-menu…">` matched a chrome pattern and suppressed the
  entire document. Structural tags are now never treated as chrome.
- A sidebar `div` opened and never closed swallowed everything after it.

**Extraction never returns nothing when the page had text — and says when it had
to relax.** Chrome suppression and content scoping are both heuristic, so both
are best-effort. If the strict pass yields nothing readable, the parse is
repeated with chrome suppression disabled; a page recovered that way reports
`parse=no-chrome` rather than looking like a page that never needed relaxing.

The same pass also catches the *half* failure: chrome that keeps the head of the
article and eats its tail. That used to ship a stub marked `parse=strict` — a
page that said nothing about itself, so it read as a page that simply had little
text. `tests/probe_truncation.py` measures it: over 3,000 destructive mutations
of nine real pages, 14 cases kept a minority of the content root while
suppression removed the rest, losing up to 99% of the article, silently. The
gate is the same question the ladder already asks about nothing at all — "was
more thrown away than kept, counting only text dropped from *inside* the
content root?" — plus a floor: the loss has to be bigger than an empty page
(200 chars), because a share is meaningless on a four-word document. When it
fires, the page is returned whole and named `parse=trunc-root:NN%`, the share
that was lost. No honest page in the nine comes near the gate (worst: npm at
23%, whose readme keeps its sidebars inside `<main>`). The margin did not survive a
corpus nobody curated (`tests/probe_gate_pos.py`, HN + Lobsters + random Wikipedia):
on `en.wikipedia.org/wiki/Torrebaja` the gate fires at 62% and the strict article is
**complete** — what suppression removed was the municipality navbox, the authority
control block and the categories, chrome that lives inside the same container the
result comes from. Three amount-based counters were measured against it and none
separated the two cases: the fix that saved the honest page is the fix that let the
real damage through.

**Why a suppression failed, not how much it ate** (`tests/probe_reason.py`) — the
last untried reading, and it fails differently. Every in-root suppression frame ends
`matched` (its own end tag), `unwind` (an enclosing tag's) or `open` (never). On the
62 measurable honest pages *every* frame is `matched` — 41,739 of 41,794 characters,
Torrebaja's navbox included — so "a frame that did not close by its own tag" fires 0
times there and catches 14 of the 20 real truncations. It is not a fact about the
page: the same injected tag lands `matched` or `unwind` depending on how deep the
parser's stack had it, and the ending tracks the size — `matched` frames ate 484 to
1,266 characters on average, `unwind` frames 7,128 to 8,369. The prose counter
(`ptext`: text lost from inside a suppressed `<p>`) catches 18 of 20 with 0 fires on
honest pages; the two *disagree* on which cases they miss, and their union catches
**20 of 20**, with 1 mutation in 1,500 where nothing was lost (the shipped gate
manages 34) and 0 fires on the honest corpus. Measured, not built: a gate made of
that union needs the reader to track frame endings and suppressed prose, which is a
change to `keyhole.py` and not a line in a probe.

**The prose row's other half, and the union's extra is not prose**
(`probe_gate_pos --order=url`) — the prose row of `probe_gate_span` was fixed in the
twenty-second awakening to count a `<p>` opened on *either* side of the suppression,
and that union is a strict superset of `ptext`: 6,319 against 5,566 characters of the
33,521 the honest corpus's chrome removes. The 753 it adds are now **named** instead
of counted (the probe prints them): 726 characters of Gizmodo's `aside.flex-none`
news rail, 21 of a "Enjoyed this article?" promo card, 6 aria-hidden `›` glyphs —
all chrome, none of it prose the reader lost. They are counted because the parser
keeps an article `<p>` open across a frame the browser would have closed it for, and
the probe carries the union as a row (`punion`) so the question is a measurement:
under the page-truth fuzz, pinned on the same 63 pages (`24455059b09c0ea1`), the
union catches **18 of 20** real truncations where the structural half catches 17, at
**0** no-cost fires and 13 partials for both (shipped: 19 caught, 20 no-cost). The
one case it wins is a frame opened inside an already-open paragraph that swallowed
its *continuation* — the one text the structural reading cannot see by construction
and the one no kind breakdown can name (it prints as `other`). The union also fires
**0** times on the honest corpus, so its 753 extra characters cost nothing
measurable: it wins by scale (1,457 against 1,218), not by the criterion. The union
is cross-checked per page against the span family's own `_ParaLoss` (0
disagreements in 63, and a test holds the agreement).

**The loss the caller never read, and the CSS counted as prose**
(`tests/probe_region.py`) — the union's one no-cost fire, chased to its region and
found somewhere else. The shipped counter measures the content root; `kept`
measures the narrowed span, so on the honest corpus 16,806 of the 41,794 counted
characters (40.2%) are text no caller ever got — the region the tightening already
discards. Restricting the union to the region the caller reads costs one real
truncation in both runs and removes **no** fire: the fire is not there. It is a
`<style>` living *inside* a chrome frame — `_DROP_TAGS` asks `_suppress_why()`
first, so the CSS is pushed as chrome, arrives as `data`, and the counter calls it
readable text. That is 8,273 characters, 19.8% of everything the counter counts, on
62 honest pages with no mutation involved; and it is the union's entire no-cost
fire (1,466 of a 2,553-character frame in run A, 1,319 of 1,319 in run B). Excluded,
the fire goes to 0 while the catches hold in A (20 of 20) and lose one in B (19 of
20, where CSS characters were inflating a frame past `kept`). The eighth awakening
fixed this confusion between a dropped tag and chrome — for the innermost reason
only, which is where the hole was left. Torrebaja's own false positive is a
different bug and is not touched by any of it.

**The same hole in the gate that ships, and the first strict improvement**
(`tests/probe_drop.py`) — the probe above measures a counter that is not wired
into anything. The shipped gate asks the same question of the same counter, so it
was measured too, with the shipped functions deciding: on 62 honest pages the
payload exclusion moves 8 shares (max 61.5% → 54.5%) and flips **no** fire, and
under the 1,500 mutations that calibrated the gate it removes **10 of the shipped
gate's 34 no-cost fires, no catches and no partials** (20 caught / 24 no-cost
against 20 / 34; `probe_gate_pos`'s published rows reproduce exactly as the
control). The payload is `<style>` 5,545, `<script>` 2,503, `<svg>` 225 — sampled,
not assumed: the SVG's 225 characters are a logo's `<title>`, "Unison Logo". The
ten removed fires are named, and they are two shapes: nine are a `nav#main-nav`
frame on `unison-lang.org` (632–5,182 characters of `<script>` and `<svg>` inside
a nav the mutation had pushed into chrome), one is the 2,553-character `nav` frame
the previous two awakenings named. **The one-line change it argued for was made**
(a tag in `_DROP_TAGS` is pushed as `drop` even under a chrome frame) — and the
equivalence that `probe_drop` could only argue by `_suppress_why()`'s own rule is
now measured, because the fixed parser is asked the question the probe had asked
of a copy: run before and after on the same 62 pages, the shipped counter reports
**33,521** characters, its payload column **0**, its shares identical to the
no-payload column the probe had predicted (max 61.5% → 54.5%, p90 28.8% → 22.4%,
median 2.3%), and its one honest fire unchanged. 41,794 − 8,273 = 33,521, to the
character, with 0 drift between the copy and the shipped count. Under mutation the
sample is no longer comparable — `probe_gate_pos` orders its pages by the very
share being changed, so the fuzz re-draws its mutations; what is comparable is
`probe_truncation`, which seeds its own `random.Random(0)` over a fixed page list
and reads 1473 clean / 6 `trunc-root` against 1472 / 7, with `MISSED 0` either way:
the fix removes a relaxation no catch depended on. Two fixtures in
`tests/test_keyhole.py` (`TestTruncationGate`) hold it: both fail on the old
parser, both pass on this one.

**The page whose region is empty, and the one silent truncation the gate loses**
(`tests/probe_empty_root.py`) — every reading this family has tried attributes the
loss to a frame *inside the root*, and the shipped gate's numerator lives there too
(`root_lost_share` divides by the root). On `readrare.com` that region does not
exist: `<main class="case">` is a shell its JS fills, so `scope` is `empty-root` and
the gate reads 0.0% on the honest page and 0.0% on a page a frame ate 2,199
characters of — the same zero before and after the mutation, which is arithmetic
and not agreement. On the pinned sample (`24455059b09c0ea1`, 63 pages, order by
url) that page is the single real truncation of twenty the shipped gate loses, and
the only one that ships **silently** (`parse=strict`); `span` catches it, and
`span` is not shipped. The fix that follows — judge the whole-page delta *only
where the region is empty* — was priced before it was written, because a false
positive would live in exactly the pages it applies to: it fires on **1 of 63
honest pages, the same page the shipped gate fires on** (the two counters' one fire
is one fire), adds no relaxation, drops none, and buys that miss back. The corpus's
other empty-region page, `blog.janestreet.com/…market-data/`, is where the second
region reads a *negative* delta — the no-chrome pass scopes into a 56-character
teaser card inside the suppressed nav, against the 11,161 the strict pass returned
— so the branch asks before it acts and leaves that page exactly as it was. The
change is in `_parse`, not in `ate_the_root`: the gate predicate still has no region
there, the ladder now has a second one. Four fixtures in `TestEmptyRegionGate` hold
it (two of them fail on the old ladder), and the curated nine-page probe is
byte-identical before and after (1473 clean / 21 no-chrome / 6 `trunc-root`,
`MISSED 0`).

The ladder used to have a third rung, "no heuristics at all". It was measured
and removed: the relaxed pass differs from it only in scoping, and the cut is
abandoned whenever it would keep nothing, so a rung-2 result can never be empty
*of* text a rung-3 pass would have found. Over 6,000 destructive mutations of
six real pages (`tests/probe_fallback.py --fuzz`) rung 3 was reached 400 times
and rescued nothing. A fallback that cannot fire is a comment pretending to be
safety.

A parser that raises part-way (rare, but the HTML parser is fed real-world
garbage) keeps whatever it reached and reports `parse_error`; a partial page that
said nothing about itself would be read as a short one.

**Which of these guarantees actually fire? Audited, not assumed.**
`tests/probe_rules.py` instruments a parser so every chrome rule reports two
numbers across real pages and destructive mutations — how often it matched, and
how many characters of readable text it removed. A rule that cannot fire, or one
that fires but removes nothing, is the empty-success shape in a different
costume. Result: all eight chrome rules fire on live pages and remove real text;
the root-override (`<main>` displacing a teaser `<article>`) fired twice in 3,000
mutations and zero times on nine clean pages; and the parser's exception catch
fired zero times in 303,000 inputs. Both survive, because a guarantee that
*rescues* is worth arming even when the wild rarely pulls it — a unit test forces
each to fire. That is the line between them and the rung-3 fallback that was
deleted: delete the rung that only duplicates, keep the arm that can still save a
page.

**Content is scoped to the page's own root, and the scope is named.** A page's
`<main>` (or `role="main"`, or `<article>`) is where its content starts; anything
before it is site chrome, so it is dropped from the markdown, the text *and* the
links. A `<main>` that turns out to hold nothing is not trusted — the cut is
abandoned and the whole page is kept instead. Every result carries the root it
used (`scope=main`, `scope=none`), in the batch row, in `--json` and in the
corpus file's header — because a scoping that silently did nothing looks exactly
like one that worked, and only one of those is worth trusting.

**Inside the root, the cut is narrowed to the paragraphs.** A semantic root is not
always the article. Wikipedia's Vector 2022 skin keeps the language switcher and
the table of contents *inside* `<main id="content">`, where no structural rule can
reach them. So after cutting at the root the extractor cuts again — at the
innermost container inside the root that still holds essentially all of the root's
`<p>` text. The rule was measured before it was built
(`tests/probe_density.py`); it can only ever narrow the cut, never widen it, and it
names itself: `scope=main>div.mw-content-ltr`.

Verified live: on Wikipedia the file no longer opens on sixty language names but
on `American technology company Cloudflare, Inc. …` (−1,685 characters); on MDN it
starts at the `<h1>` instead of `- Skip to main content / - Skip to search / …`;
on npm the 2FA banner and the `Readme · Code · Beta` tab chrome are gone. Pages
with no `<main>`/`<article>` — `example.com`, Hacker News — report `scope=none`
and keep everything. Over eleven sites the rule never grew a page and never lost
one (`tests/probe_tighten.py`, which runs each page with the tightening on and
off).

**Escalation is explicit and honest.** `--render` drives headless Chrome
(`--dump-dom`) for JS-rendered pages and JS challenges. A missing Chrome binary
is reported as an error, never as content.

## What it does not do

- **No CAPTCHA solving.** An interactive challenge is reported, not beaten.
- **No stealth/browser fingerprint spoofing.** It sends honest, realistic
  headers. If a site needs more than that, `--render` is the answer.
- **No paywall circumvention.** A `consent_gate` wall is reported as such.
- **No proxy pool / no retry storm.** One request, one result.

## Batch

Surveying forty candidate sources is the same problem as fetching one, done
forty times — so `batch` exists and reports *counts*, not bodies.

```bash
./keyhole.py batch --file urls.txt --jobs 8
./keyhole.py batch --render < urls.txt        # escalate whatever came back unusable
./keyhole.py batch --json < urls.txt          # one array of row objects
./keyhole.py batch --out corpus/ < urls.txt   # one markdown file per URL
```

```
[1/4] OK   text=156     links=0    scope=none         https://example.com
            — Example Domain
[3/4] OK   text=71.2k   links=60   scope=main         https://en.wikipedia.org/wiki/Cloudflare
            — Cloudflare - Wikipedia
[4/4] ERR  https://this-host-does-not-exist.invalid
            — URLError: <urlopen error [Errno 11001] getaddrinfo failed>
```

`scope=` is where the content was taken from: `main`, `article`, `div[role=main]`,
a narrowed cut such as `main>div.mw-content-ltr`, `none` when the page has no such
root and the whole document was kept, or `empty-root` when a root *was* found and
the cut kept nothing so it was abandoned. The last two used to print the same
value; an extraction that was attempted and failed must not read like one that
was never attempted.

Anything the extraction had to relax is named on the row: `[parse=no-chrome]`
when chrome suppression had to be switched off because nothing survived it,
`[parse=trunc-root:88%]` when it was switched off because it had eaten 88% of
the content root's readable text, `[partial: <error>]` when the HTML parser gave
up part-way. An unmarked row means the strict pass ran clean.

Input is one URL per line, blank lines and `#`-comment lines skipped, duplicates
collapsed (first occurrence wins). `#` is deliberately **not** an inline comment
marker — URLs carry fragments, and truncating `.../post#section-2` would silently
fetch the wrong page. Results always come back in input order, not completion
order, so the report lines up with the list you fed in. `--jobs` defaults to 4 and
is capped at 16. Exit code is 0 only if every URL was `ok`.

A wall is reported as `WALL <kind>`, an error as `ERR` with its reason — batch
inherits the same rule as `fetch`: name the failure, never flatten it into a
generic one.

### Corpus mode: `--out DIR`

Surveying tells you *which* pages are worth keeping; `--out` keeps them. One
markdown file per URL, named from the URL (host + path, `www.` and `.html`
dropped, query kept because `?id=42` is a different page, fragment dropped), with
a `<!-- source: ... | scope: main -->` header so a file read months later still
knows where it came from and whether it holds the article or the whole page.
Collisions are numbered in input order, so re-running the same list
overwrites its own files instead of spraying duplicates.

```
[3/4] ERR  https://this-host-does-not-exist.invalid
            — URLError: <urlopen error [Errno 11001] getaddrinfo failed>
            → this-host-does-not-exist.invalid.md

3/4 ok, wrote 4 files (3 with content) to corpus/
```

A URL that was walled or errored still gets a file, headed `# FAILED` and naming
the cause. Skipping it would leave a corpus quietly missing exactly the pages
that needed attention — so `ls corpus/` shows the hole instead of hiding it.
Exit code is unchanged: 0 only if every URL was `ok`.

## Library use

```python
import keyhole

r = keyhole.fetch("https://example.com")
r.ok          # True
r.title       # "Example Domain"
r.markdown    # clean markdown
r.links       # [{"text": ..., "url": ...}, ...]
r.scope       # "main" | "article" | "div[role=main]" | "" (whole page kept)
r.wall        # None, or {"kind": ..., "why": ...}

keyhole.render("https://spa.example")   # headless Chrome, returns a Result too

# batch, same order in as out
for r in keyhole.run_batch(["https://a.dev", "https://b.dev"], jobs=4):
    print(r.url, r.ok, r.wall)

# corpus: one markdown file per result, failures included and named
keyhole.write_corpus(keyhole.run_batch(urls), "corpus/")
```

## Tests

```bash
python tests/test_keyhole.py                  # offline, 82 tests
KEYHOLE_NET_TESTS=1 python tests/test_keyhole.py   # + live network checks
python tests/probe_mcp.py                     # drives the MCP server over stdio
python tests/probe_density.py                 # measures candidate extraction rules, live
python tests/probe_tighten.py                 # measures the tightening rule on/off, live
python tests/probe_fallback.py --fuzz 6000    # measures the fallback ladder, live
python tests/probe_rules.py --fuzz 3000       # audits which guarantees actually fire, live
python tests/probe_truncation.py --fuzz 1500  # the gate's own populations, live
python tests/probe_gate_span.py --fuzz 1500   # candidate counters for the gate, live
python tests/probe_gate_pos.py --fuzz 1500    # where the loss falls, and whose it is, live
python tests/probe_counts.py --fuzz 600       # which probes print a measurement vs a theorem
python tests/probe_reason.py --fuzz 1500      # why a suppression failed, not how much it ate
python tests/probe_region.py --fuzz 1500      # the loss the caller reads, and the CSS counted as text
python tests/probe_drop.py --fuzz 1500        # the same hole in the shipped gate, and its price
python tests/probe_empty_root.py --fuzz 1500 --order=url   # the fix's price, before it was built
```

## Use it from an agent (MCP)

`keyhole_mcp.py` is a stdio MCP server implementing the raw JSON-RPC protocol —
no `mcp` SDK, no install. An agent tool that needs a `pip install` before it can
tell you a site is down has already failed at its one job.

It exposes four tools:

| Tool | Purpose |
|---|---|
| `fetch_page` | URL → clean markdown; names the wall if blocked. `render=true` for JS pages. |
| `fetch_many` | URLs → compact report, one line each, in input order. Survey, then follow up. |
| `extract_links` | URL → absolutised, deduped links. |
| `diagnose_url` | Is it up? Is it walled? Which wall? No page content returned. |

Register it with any MCP client:

```jsonc
{
  "mcpServers": {
    "keyhole": {
      "command": "python",
      "args": ["/path/to/keyhole/keyhole_mcp.py"]
    }
  }
}
```

Verified against Hermes Agent's native MCP client: connects in ~890ms, all four
tools discovered. (Despite the name, `python` here is the interpreter path your
agent runs with — use an absolute path.)

## Status

`0.7.0`. Content is scoped to the page's own root, narrowed by one measured
nesting rule, and every result names the scope it used; 74 offline tests green
(was 64). The extraction's fallbacks are named too: `scope=none` (no root),
`scope=empty-root` (a root was found and the cut kept nothing), `parse=no-chrome`
(chrome suppression had to be switched off because nothing survived it),
`parse=trunc-root:NN%` (it was switched off because it had eaten NN% of the
content root — the silent truncation, measured at up to 99% of the article over
3,000 mutations in `tests/probe_truncation.py`), and `parse_error` (the parser
gave up part-way). The ladder's unreachable third rung was deleted after 6,000
destructive mutations of six real pages reached it 400 times and rescued none
(`tests/probe_fallback.py`).

The page that motivated the scoping work was Wikipedia, and for a while it
improved by only 74 characters: its Vector 2022 skin wraps the language dropdown
and the table of contents *inside* `<main id="content">`, so a structural root
cannot reach them. The next step there was assumed to be density-based scoring;
`tests/probe_density.py` measured it and split the verdict. Non-link text as the
signal is **dead**: on Wikipedia it picks an ancestor of `<main>` (a −7 character
change), and on MDN and npm it picks exactly today's container. Paragraph text is
the signal that survived — but only as a *tightening* of the structural cut,
never above it — and it is built: Wikipedia −1,685 characters
(`scope=main>div.mw-content-ltr`, no longer opening on sixty language names), npm
−133 with the `Readme · Code · Beta` tab chrome gone, and MDN, `example.com` and
Hacker News unchanged. Over eleven sites the rule never grew a page and never
lost the article marker (`tests/probe_tighten.py`). (`deepest root wins` was
likewise measured and dropped: npm's `<main>` has a nested `<article>`, MDN has
none at all, so it would buy one site and not the one that prompted the work.)
Next: `--out` over MCP, so an agent can build a corpus, not just survey one.
