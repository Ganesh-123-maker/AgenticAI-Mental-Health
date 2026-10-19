#!/usr/bin/env python3
"""Dump raw visit messages to diagnose the turn-1 reply.
Run from the repo root with the backend running:
    python scripts/dump_visit.py
"""
import httpx

c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0)
tok = c.post("/auth/login",
             json={"username": "smoke_1792402973",
                   "password": "smoke-test-pass"}).json()["token"]
v = c.get("/visits/5bbd871c-dfc9-4c50-a2e0-dfd5db6d8b40",
          headers={"Authorization": f"Bearer {tok}"}).json()
print(f"visit has {len(v['messages'])} messages\n")
for i, m in enumerate(v["messages"]):
    print(f"===== msg {i} role={m['role']} id={m.get('id')} =====")
    print(m["text"])
    print()
