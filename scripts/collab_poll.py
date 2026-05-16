"""Background poller for the collab server.

Continuously polls /messages and prints new ones to stdout.
Claude Code's Monitor tool watches stdout and fires a notification
each time a new message lands.

Usage:
    python3 scripts/collab_poll.py [--interval 5] [--url http://localhost:8765]
"""

import argparse
import json
import time
import urllib.request
import urllib.error


def poll(url: str, interval: int) -> None:
    last_id = 0
    while True:
        try:
            with urllib.request.urlopen(f"{url}/messages?since={last_id}", timeout=5) as r:
                msgs = json.loads(r.read())
            for m in msgs:
                print(f"[{m['at']}] {m['from']}: {m['message']}", flush=True)
                last_id = max(last_id, m["id"])
        except urllib.error.URLError:
            print("[poller] server not reachable, retrying...", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=5)
    parser.add_argument("--url", default="http://localhost:8765")
    args = parser.parse_args()
    poll(args.url, args.interval)
