#!/usr/bin/env python
"""Drive keyhole_mcp.py over stdio: initialize, list tools, call the new one."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
reqs = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
     "params": {"protocolVersion": "2025-03-26", "clientInfo": {"name": "probe", "version": "0"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
     "params": {"name": "fetch_many", "arguments": {
         "urls": ["https://example.com", "https://this-host-does-not-exist-9x8y.invalid"],
         "jobs": 2}}},
    {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
     "params": {"name": "fetch_many", "arguments": {"urls": []}}},
]
stdin = "".join(json.dumps(r) + "\n" for r in reqs)

p = subprocess.run([sys.executable, f"{HERE}/keyhole_mcp.py"], input=stdin,
                   capture_output=True, text=True, timeout=180)
print("exit:", p.returncode)
print("stderr:", p.stderr.strip()[:400])
responses = [json.loads(l) for l in p.stdout.splitlines() if l.strip()]
print("responses:", len(responses), "(4 requests, 1 is a notification)")

for r in responses:
    rid = r.get("id")
    if rid == 1:
        info = r["result"]["serverInfo"]
        print(f"[1] initialize ok: {info['name']} {info['version']} "
              f"proto={r['result']['protocolVersion']}")
    elif rid == 2:
        names = [t["name"] for t in r["result"]["tools"]]
        print(f"[2] tools: {names}")
        assert "fetch_many" in names
        schema = [t for t in r["result"]["tools"] if t["name"] == "fetch_many"][0]["inputSchema"]
        print(f"    fetch_many required={schema['required']} "
              f"props={sorted(schema['properties'])}")
    elif rid == 3:
        res = r["result"]
        print(f"[3] isError={res.get('isError')}")
        print("    " + res["content"][0]["text"].replace("\n", "\n    "))
    elif rid == 4:
        res = r["result"]
        print(f"[4] empty urls -> isError={res.get('isError')}: "
              f"{res['content'][0]['text']}")
