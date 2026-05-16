"""One-shot collab client — for the side that can't background-monitor (Codex).

Claude Code's side runs scripts/collab_poll.py under the Monitor tool and gets
auto-notified. The Codex side has no equivalent, so it runs this by hand (or on
a cron / every-5-min nudge) to pull new messages and reply.

A cursor file (.collab_cursor_<name>, gitignored) tracks the last id you've
seen so `inbox` only ever shows what's new.

Usage:
    python3 scripts/collab.py inbox                 # new messages addressed to you
    python3 scripts/collab.py send "your message"   # reply on the channel
    python3 scripts/collab.py log [N]               # last N messages (no cursor move)
    python3 scripts/collab.py wait [--timeout 600]  # block until a new non-self msg

Identity defaults to "arnav"; override with --as <name> or COLLAB_AS env var.
Server defaults to http://localhost:8765; override with --url or COLLAB_URL.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URL = os.environ.get("COLLAB_URL", "http://localhost:8765")
DEFAULT_AS = os.environ.get("COLLAB_AS", "arnav")


def _cursor_path(name: str) -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, f".collab_cursor_{name}")


def _read_cursor(name: str) -> int:
    try:
        with open(_cursor_path(name)) as f:
            return int(f.read().strip() or 0)
    except (FileNotFoundError, ValueError):
        return 0


def _write_cursor(name: str, value: int) -> None:
    with open(_cursor_path(name), "w") as f:
        f.write(str(value))


def _get(url: str, since: int) -> list:
    try:
        with urllib.request.urlopen(f"{url}/messages?since={since}", timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.URLError as e:
        print(f"[collab] server unreachable at {url}: {e}", file=sys.stderr)
        sys.exit(2)


def _fmt(m: dict) -> str:
    at = m.get("at", "")
    return f"#{m['id']} [{at}] {m['from']}: {m['message']}"


def cmd_inbox(url: str, me: str) -> None:
    since = _read_cursor(me)
    msgs = _get(url, since)
    incoming = [m for m in msgs if m["from"] != me]
    if msgs:
        _write_cursor(me, max(m["id"] for m in msgs))
    if not incoming:
        print(f"[collab] no new messages for {me} (cursor at {since})")
        return
    for m in incoming:
        print(_fmt(m))


def cmd_send(url: str, me: str, message: str) -> None:
    body = json.dumps({"from": me, "message": message}).encode()
    req = urllib.request.Request(
        f"{url}/send", data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            sent = json.loads(r.read())
        print(f"[collab] sent #{sent.get('id', '?')} as {me}")
    except urllib.error.URLError as e:
        print(f"[collab] send failed: {e}", file=sys.stderr)
        sys.exit(2)


def cmd_log(url: str, n: int) -> None:
    msgs = _get(url, 0)
    for m in msgs[-n:]:
        print(_fmt(m))


def cmd_wait(url: str, me: str, timeout: int, interval: int) -> None:
    since = _read_cursor(me)
    deadline = time.time() + timeout
    while time.time() < deadline:
        msgs = _get(url, since)
        incoming = [m for m in msgs if m["from"] != me]
        if incoming:
            if msgs:
                _write_cursor(me, max(m["id"] for m in msgs))
            for m in incoming:
                print(_fmt(m))
            return
        time.sleep(interval)
    print(f"[collab] no new messages after {timeout}s", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    p = argparse.ArgumentParser(description="One-shot collab client")
    p.add_argument("command", choices=["inbox", "send", "log", "wait"])
    p.add_argument("text", nargs="?", help="message body (send) or count (log)")
    p.add_argument("--as", dest="me", default=DEFAULT_AS)
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--interval", type=int, default=5)
    args = p.parse_args()

    if args.command == "inbox":
        cmd_inbox(args.url, args.me)
    elif args.command == "send":
        if not args.text:
            p.error("send requires a message")
        cmd_send(args.url, args.me, args.text)
    elif args.command == "log":
        cmd_log(args.url, int(args.text) if args.text else 10)
    elif args.command == "wait":
        cmd_wait(args.url, args.me, args.timeout, args.interval)


if __name__ == "__main__":
    main()
