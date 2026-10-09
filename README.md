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
```

## Tests

```bash
python tests/test_keyhole.py                  # offline, 16 tests
KEYHOLE_NET_TESTS=1 python tests/test_keyhole.py   # + live network checks
```

## Status

`0.1.1`. The four cases in the table above are verified against live sites.
Next: an MCP server wrapper so any agent can use it as a tool, and a
`--batch` mode reading URLs from stdin.
