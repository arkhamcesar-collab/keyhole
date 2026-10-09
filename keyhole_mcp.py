#!/usr/bin/env python
"""Keyhole as an MCP server — stdio JSON-RPC 2.0, no SDK, no dependencies.

Any MCP-speaking agent (Hermes, Claude Code, Cursor, ...) can install this and
get four tools:

    fetch_page     URL -> clean markdown, wall named if blocked
    fetch_many     URLs -> compact report, one line each, input order
    extract_links  URL -> absolutised, deduped links
    diagnose_url   URL -> is it up? is it walled? which wall?

Deliberately implemented against the raw wire protocol instead of the `mcp`
package: an agent tool that needs a pip install before it can tell you a site is
down has already failed at its one job.

stdout carries JSON-RPC and nothing else. All diagnostics go to stderr.
"""
from __future__ import annotations

import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import keyhole  # noqa: E402

SERVER_NAME = "keyhole"
SERVER_VERSION = keyhole.__version__
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_PROTOCOL = "2025-03-26"

MAX_CHARS_DEFAULT = 20000

TOOLS = [
    {
        "name": "fetch_page",
        "description": (
            "Fetch a URL and return its readable content as clean markdown. "
            "Use this when a normal fetch fails, returns a 403, or comes back as "
            "mostly navigation and cookie-banner noise. Bot walls (Cloudflare, "
            "DataDome, PerimeterX, CAPTCHA) are named explicitly rather than "
            "returned as HTML. Set render=true for JavaScript-rendered pages, "
            "which requires a local Chrome install."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Absolute URL, or a bare host to default to https."},
                "render": {"type": "boolean", "description": "Escalate to headless Chrome for JS-rendered pages. Slower (a few seconds).", "default": False},
                "format": {"type": "string", "enum": ["markdown", "text", "json"], "default": "markdown", "description": "markdown: readable content. text: single-line plain text. json: full structured result."},
                "max_chars": {"type": "integer", "default": MAX_CHARS_DEFAULT, "description": "Truncate the returned content to this many characters."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "extract_links",
        "description": (
            "Extract the links from a page, absolutised against the final URL and "
            "deduplicated. Useful for discovery and crawl seeding. Navigational "
            "chrome is skipped."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Absolute URL to scan."},
                "limit": {"type": "integer", "default": 40, "description": "Maximum links to return."},
                "render": {"type": "boolean", "default": False, "description": "Render with headless Chrome first, for JS-built links."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "fetch_many",
        "description": (
            "Fetch many URLs in one call and return a compact report: one line per "
            "URL with status, text length, link count, and the wall kind if blocked. "
            "Use this to survey a list of candidate sources without pulling every "
            "page's full text into context — follow up on the interesting ones with "
            "fetch_page. Results come back in the order the URLs were given."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "urls": {"type": "array", "items": {"type": "string"},
                         "description": "URLs to fetch. A single newline-separated string is also accepted."},
                "render": {"type": "boolean", "default": False, "description": "Escalate walls and JS shells to headless Chrome. Slow: it costs a browser launch per URL."},
                "jobs": {"type": "integer", "default": 4, "description": "Parallel fetches, capped at 16."},
            },
            "required": ["urls"],
        },
    },
    {
        "name": "diagnose_url",
        "description": (
            "Check whether a URL is reachable, and whether it sits behind a bot "
            "wall. Returns status, wall kind, and a plain-language explanation, "
            "WITHOUT returning page content. Use this to decide whether fetching "
            "is worth attempting, or to debug why a fetch failed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "Absolute URL to diagnose."}},
            "required": ["url"],
        },
    },
]


def _text(payload, is_error=False):
    return {"content": [{"type": "text", "text": payload}], "isError": is_error}


def _truncate(s: str, n: int) -> str:
    if n and len(s) > n:
        return s[:n] + f"\n\n[truncated: {len(s) - n} more characters]"
    return s


def tool_fetch_page(args: dict) -> dict:
    url = (args.get("url") or "").strip()
    if not url:
        return _text("fetch_page requires a 'url' argument.", True)
    render = bool(args.get("render"))
    fmt = args.get("format") or "markdown"
    max_chars = int(args.get("max_chars") or MAX_CHARS_DEFAULT)

    res = keyhole.fetch_maybe_render(url, do_render=render)
    used_browser = res.method == "browser"

    if res.wall and not res.ok:
        return _text(
            f"BLOCKED by a bot wall: {res.wall['kind']}\n"
            f"{res.wall['why']}\n\n"
            f"No content available. Retry with render=true if this is a JS "
            f"challenge and a local Chrome exists.", True)

    if res.error and not res.text:
        return _text(f"ERROR: {res.error}", True)

    if fmt == "json":
        payload = {
            "url": res.url, "final_url": res.final_url, "status": res.status,
            "method": res.method, "title": res.title, "description": res.description,
            "links": res.links[:40], "text_length": len(res.text or ""),
            "wall": res.wall, "error": res.error,
            "markdown": _truncate(res.markdown or "", max_chars),
        }
        return _text(json.dumps(payload, indent=2, ensure_ascii=False))

    body = res.text if fmt == "text" else res.markdown
    header = [f"# {res.title}" if res.title else "", res.final_url or res.url]
    if used_browser:
        header.append("(rendered with headless Chrome)")
    if res.wall:
        header.append(f"(note: {res.wall['kind']} present, content recovered)")
    return _text("\n".join(x for x in header if x) + "\n\n" + _truncate(body or "", max_chars))


def tool_extract_links(args: dict) -> dict:
    url = (args.get("url") or "").strip()
    if not url:
        return _text("extract_links requires a 'url' argument.", True)
    limit = int(args.get("limit") or 40)
    res = keyhole.fetch(url)
    if args.get("render") and (res.wall or not res.ok):
        ren = keyhole.render(res.final_url or res.url)
        if ren.status == 200 and not ren.error:
            res = ren
    links = res.links[:limit]
    if not links:
        note = f" (wall: {res.wall['kind']})" if res.wall else ""
        return _text(f"No links found at {res.final_url or url} "
                     f"[HTTP {res.status}]{note}. Try render=true if the page is JS-built.")
    lines = [f"{len(links)} links from {res.final_url or url}:"]
    lines += [f"- {l['text'][:90]} | {l['url']}" for l in links]
    return _text("\n".join(lines))


def tool_diagnose_url(args: dict) -> dict:
    url = (args.get("url") or "").strip()
    if not url:
        return _text("diagnose_url requires a 'url' argument.", True)
    res = keyhole.fetch(url)
    out = [f"url:     {res.final_url or res.url}",
           f"status:  {res.status}",
           f"bytes:   {res.bytes_in}",
           f"title:   {res.title or '(none)'}",
           f"reachable: {'yes' if res.status == 200 else 'no'}"]
    if res.wall:
        out += [f"WALL:    {res.wall['kind']}",
                f"reason:  {res.wall['why']}",
                "advice:  retry with render=true, or use a browser session"]
    elif res.error:
        out += [f"ERROR:   {res.error}"]
    else:
        out += ["wall:    none detected"]
    return _text("\n".join(out))


def tool_fetch_many(args: dict) -> dict:
    urls = args.get("urls") or []
    if isinstance(urls, str):
        # Agents sometimes paste a newline-separated list into a string field;
        # accepting it costs nothing and avoids a pointless round trip.
        urls = keyhole.parse_url_list(urls)
    urls = [u.strip() for u in urls if isinstance(u, str) and u.strip()]
    if not urls:
        return _text("fetch_many requires a non-empty 'urls' array.", True)

    do_render = bool(args.get("render"))
    results = keyhole.run_batch(urls, do_render=do_render, jobs=int(args.get("jobs") or 4))

    lines = []
    for i, r in enumerate(results, 1):
        lines += keyhole.format_batch_row(i, len(results), r).splitlines()
    ok = sum(1 for r in results if r.ok)
    walled = sum(1 for r in results if r.wall)
    lines.append("")
    lines.append(f"{ok}/{len(results)} ok" + (f", {walled} walled" if walled else ""))
    if walled and not do_render:
        lines.append("hint: render=true to escalate the walled ones.")
    if ok:
        lines.append("Use fetch_page on the ones worth reading.")
    # isError only when nothing came back at all: a partial survey is still a
    # useful answer, and flagging it as an error would invite a pointless retry.
    return _text("\n".join(lines), is_error=(ok == 0))


HANDLERS = {
    "fetch_page": tool_fetch_page,
    "fetch_many": tool_fetch_many,
    "extract_links": tool_extract_links,
    "diagnose_url": tool_diagnose_url,
}


def handle(req: dict):
    """Return a response dict, or None for notifications."""
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        want = params.get("protocolVersion")
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": want if want in PROTOCOL_VERSIONS else DEFAULT_PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": (
                "Fetch web pages that resist ordinary clients. Bot walls are "
                "named, not returned as HTML. Use render=true for JS-rendered pages."
            ),
        }}

    if method in ("notifications/initialized", "initialized"):
        return None

    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method == "tools/call":
        name = params.get("name")
        fn = HANDLERS.get(name)
        if not fn:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32602, "message": f"unknown tool: {name}"}}
        try:
            return {"jsonrpc": "2.0", "id": rid, "result": fn(params.get("arguments") or {})}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": rid, "result": _text(
                f"tool {name} failed: {type(e).__name__}: {e}", True)}

    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def main() -> int:
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"[keyhole-mcp] bad JSON on stdin: {e}", file=sys.stderr)
            continue
        try:
            resp = handle(req)
        except Exception:
            print(f"[keyhole-mcp] handler crashed:\n{traceback.format_exc()}", file=sys.stderr)
            resp = {"jsonrpc": "2.0", "id": req.get("id"),
                    "error": {"code": -32603, "message": "internal error"}}
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
