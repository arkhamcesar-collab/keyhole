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
when chrome suppression had to be switched off, `[partial: <error>]` when the
HTML parser gave up part-way. An unmarked row means the strict pass ran clean.

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
python tests/test_keyhole.py                  # offline, 61 tests
KEYHOLE_NET_TESTS=1 python tests/test_keyhole.py   # + live network checks
python tests/probe_mcp.py                     # drives the MCP server over stdio
python tests/probe_density.py                 # measures candidate extraction rules, live
python tests/probe_tighten.py                 # measures the tightening rule on/off, live
python tests/probe_fallback.py --fuzz 6000    # measures the fallback ladder, live
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

`0.6.0`. Content is scoped to the page's own root, narrowed by one measured
nesting rule, and every result names the scope it used; 61 offline tests green
(was 57). The extraction's fallbacks are named too: `scope=none` (no root),
`scope=empty-root` (a root was found and the cut kept nothing), `parse=no-chrome`
(chrome suppression had to be switched off), `parse_error` (the parser gave up
part-way). The ladder's unreachable third rung was deleted after 6,000
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
