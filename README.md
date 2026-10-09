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

**Extraction never returns nothing when the page had text.** Chrome suppression
is heuristic, so it is best-effort: if the strict pass yields nothing at all,
the parse is repeated with suppression disabled. Keeping a cookie banner is a
much smaller failure than returning an empty page.

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
```

```
[1/4] OK   text=156     links=0    https://example.com
            — Example Domain
[3/4] OK   text=71.2k   links=60   https://en.wikipedia.org/wiki/Cloudflare
            — Cloudflare - Wikipedia
[4/4] ERR  https://this-host-does-not-exist.invalid
            — URLError: <urlopen error [Errno 11001] getaddrinfo failed>
```

Input is one URL per line, blank lines and `#`-comment lines skipped, duplicates
collapsed (first occurrence wins). `#` is deliberately **not** an inline comment
marker — URLs carry fragments, and truncating `.../post#section-2` would silently
fetch the wrong page. Results always come back in input order, not completion
order, so the report lines up with the list you fed in. `--jobs` defaults to 4 and
is capped at 16. Exit code is 0 only if every URL was `ok`.

A wall is reported as `WALL <kind>`, an error as `ERR` with its reason — batch
inherits the same rule as `fetch`: name the failure, never flatten it into a
generic one.

## Library use

```python
import keyhole

r = keyhole.fetch("https://example.com")
r.ok          # True
r.title       # "Example Domain"
r.markdown    # clean markdown
r.links       # [{"text": ..., "url": ...}, ...]
r.wall        # None, or {"kind": ..., "why": ...}

keyhole.render("https://spa.example")   # headless Chrome, returns a Result too

# batch, same order in as out
for r in keyhole.run_batch(["https://a.dev", "https://b.dev"], jobs=4):
    print(r.url, r.ok, r.wall)
```

## Tests

```bash
python tests/test_keyhole.py                  # offline, 28 tests
KEYHOLE_NET_TESTS=1 python tests/test_keyhole.py   # + live network checks
```

## Use it from an agent (MCP)

`keyhole_mcp.py` is a stdio MCP server implementing the raw JSON-RPC protocol —
no `mcp` SDK, no install. An agent tool that needs a `pip install` before it can
tell you a site is down has already failed at its one job.

It exposes three tools:

| Tool | Purpose |
|---|---|
| `fetch_page` | URL → clean markdown; names the wall if blocked. `render=true` for JS pages. |
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

Verified against Hermes Agent's native MCP client: connects in ~890ms, all three
tools discovered. (Despite the name, `python` here is the interpreter path your
agent runs with — use an absolute path.)

## Status

`0.2.0`. Four live sites verified (table above); 28 offline tests green; MCP
server exercised over the wire; `batch` verified live over 4 URLs. Next:
`main`-scoped content selection, so language switchers and sidebars stop reaching
the top of the output, and a `--out DIR` for batch that writes one markdown file
per URL instead of only counting them.
