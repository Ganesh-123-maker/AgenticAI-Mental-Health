#!/usr/bin/env python3
"""Live conversation smoke test through the real PsychAgent pipeline.

Exercises: /health -> register/login -> /schools -> create course
(auto-starts first visit) -> send 2 synthetic user messages ->
assistant replies via the real pipeline (Gemini LLM + Gemini-vector
skill retrieval). Bounded: exactly 2 user turns, then stops.

Run from the repo root with the backend already running:
    python scripts/smoke_live_conversation.py

Requires the backend at http://127.0.0.1:8000 (override with --base-url).
"""

import argparse
import re
import sys
import time

import httpx

MESSAGES = [
    "I've been feeling anxious about my final exams and I can't sleep at night.",
    "I tried the breathing exercise. What else can I do to calm down before the exam?",
]


def fail(msg: str):
    print(f"SMOKE FAIL: {msg}")
    raise SystemExit(1)


def extract_response(text: str) -> str:
    m = re.search(r"<response>(.*?)</response>", text or "", re.S | re.I)
    return (m.group(1) if m else (text or "")).strip()


def main() -> None:
    ap = argparse.ArgumentParser(description="Live conversation smoke test")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    client = httpx.Client(base_url=base, timeout=300.0)

    r = client.get("/health")
    if r.status_code != 200:
        fail(f"/health returned {r.status_code}")
    print(f"/health: {r.json()}")

    username = f"smoke_{int(time.time())}"
    password = "smoke-test-pass"
    r = client.post("/auth/register", json={"username": username, "password": password})
    if r.status_code == 200:
        token = r.json()["token"]
        print(f"registered user {username}")
    else:
        r = client.post("/auth/login", json={"username": username, "password": password})
        if r.status_code != 200:
            fail(f"register ({r.status_code}) and login ({r.status_code}) both failed")
        token = r.json()["token"]
        print(f"logged in as {username}")
    headers = {"Authorization": f"Bearer {token}"}

    schools = client.get("/schools").json()
    if not schools:
        fail("no schools returned")
    school = schools[0]
    print(f"school: {school['id']} ({school['name']})")

    r = client.post("/courses", json={
        "school_id": school["id"],
        "auto_start_first_visit": True,
        "title": "smoke test course",
    }, headers=headers)
    if r.status_code != 200:
        fail(f"create course: {r.status_code} {r.text[:200]}")
    course = r.json()["course"]
    print(f"course: {course['course_id']} status={course['status']}")

    visits = client.get(f"/courses/{course['course_id']}/visits", headers=headers).json()
    open_visits = [v for v in visits if v.get("status") == "open"]
    if not open_visits:
        fail("no open visit after auto-start")
    visit_id = open_visits[0]["visit_id"]
    print(f"visit: {visit_id} (open)")

    for i, text in enumerate(MESSAGES, 1):
        print(f"\n--- turn {i} (user) ---\n{text}")
        r = client.post(f"/visits/{visit_id}/messages", json={"text": text}, headers=headers)
        if r.status_code != 200:
            fail(f"send message turn {i}: {r.status_code} {r.text[:300]}")
        visit = r.json()["visit"]
        assistant_msgs = [m for m in visit.get("messages", []) if m.get("role") == "assistant"]
        if not assistant_msgs:
            fail(f"turn {i}: no assistant reply in visit messages")
        reply = extract_response(assistant_msgs[-1]["text"])
        if not reply:
            fail(f"turn {i}: empty assistant reply")
        stage = (visit.get("stage") or {}).get("label", "?")
        print(f"--- turn {i} (assistant, stage: {stage}) ---\n{reply[:600]}")
        if len(reply) > 600:
            print(f"... [truncated, full length {len(reply)} chars]")

    print("\nSMOKE TEST: LIVE CONVERSATION PASSED "
          f"({len(MESSAGES)} turns, replies non-empty, pipeline responsive)")


if __name__ == "__main__":
    try:
        main()
    except httpx.ConnectError:
        fail("cannot reach backend at " + sys.argv[0] +
             " -- is uvicorn running on 127.0.0.1:8000?")
