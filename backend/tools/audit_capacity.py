"""Bounded, loopback-only HTTP benchmark. Run against an isolated copy of KickPick.

Example: .venv/bin/python tools/audit_capacity.py --base http://127.0.0.1:18080 \
    --output /tmp/kickpick-capacity.json
Closed-loop results describe this workload and machine, not a production SLA.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
from urllib.parse import urlencode, urlsplit

import httpx


WEEK = "/matches?" + urlencode({"from": "2026-08-15T00:00:00Z", "to": "2026-08-22T00:00:00Z"})
ENDPOINTS = {
    "health": "/health",
    "competitions": "/competitions",
    "matches_week": WEEK,
    "season_matches": "/competitions/premier-league/matches",
    "match": "/matches/5795369",
    "team": "/teams/8634",
    "player": "/players/1467236",
    "search_normal": "/search?" + urlencode({"q": "barcelona"}),
    "search_short": "/search?" + urlencode({"q": "li"}),
    "search_many_words": "/search?" + urlencode({"q": "x " * 24 + "x"}),
    "status": "/status",
}
# Synthetic browse mix; it is deliberately explicit and is not user analytics.
MIX = ["matches_week"] * 4 + ["match"] * 3 + ["team", "player", "search_normal"]


def percentile(values, fraction):
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * fraction) - 1)] * 1000, 2) if ordered else None


async def measure(client, name, duration, concurrency, conditional=False, rate=None):
    paths = [ENDPOINTS[key] for key in MIX] if name == "mixed" else [ENDPOINTS[name]]
    tags = {}
    for path in dict.fromkeys(paths):
        warm = await client.get(path)
        warm.raise_for_status()
        if conditional:
            tags[path] = {"If-None-Match": warm.headers["etag"]}
    records = []
    start = time.perf_counter()
    deadline = start + duration
    sequence = 0

    async def request(index, scheduled=None):
        path = paths[index % len(paths)]
        began = time.perf_counter()
        try:
            response = await client.get(path, headers=tags.get(path, {}))
            code, size = str(response.status_code), len(response.content)
        except httpx.HTTPError as exc:
            code, size = type(exc).__name__, 0
        completed = time.perf_counter()
        records.append((completed - (scheduled if scheduled is not None else began), code, size))

    async def worker():
        nonlocal sequence
        while time.perf_counter() < deadline:
            index = sequence
            sequence += 1
            await request(index)

    dropped = 0
    if rate is None:
        await asyncio.gather(*(worker() for _ in range(concurrency)))
    else:
        active = set()
        for index in range(int(duration * rate)):
            scheduled = start + index / rate
            await asyncio.sleep(max(0, scheduled - time.perf_counter()))
            if len(active) >= concurrency:
                dropped += 1
                continue
            task = asyncio.create_task(request(index, scheduled))
            active.add(task)
            task.add_done_callback(active.discard)
        await asyncio.gather(*active)
    elapsed = time.perf_counter() - start
    codes = Counter(row[1] for row in records)
    latencies = [row[0] for row in records]
    successful = sum(row[1] in ("200", "304") for row in records)
    return {
        "name": name, "mode": "scheduled" if rate else "closed_loop", "conditional": conditional,
        "duration_requested_s": duration, "elapsed_s": round(elapsed, 3), "concurrency": concurrency,
        "offered_rps": rate, "dropped": dropped, "requests": len(records), "codes": dict(codes),
        "successful_rps": round(successful / elapsed, 2),
        "p50_ms": percentile(latencies, .5), "p95_ms": percentile(latencies, .95),
        "p99_ms": percentile(latencies, .99), "max_ms": percentile(latencies, 1),
        "mean_body_bytes": round(sum(row[2] for row in records) / len(records)) if records else 0,
    }


async def main(args):
    target = urlsplit(args.base)
    if target.scheme != "http" or target.hostname not in ("127.0.0.1", "::1", "localhost"):
        raise SystemExit("Only a local HTTP target is allowed; use an isolated test deployment.")
    if not 1 <= args.concurrency <= 32 or not 1 <= args.duration <= 30:
        raise SystemExit("Concurrency must be 1..32 and sample duration 1..30 seconds.")
    document = {"created_at": datetime.now(timezone.utc).isoformat(), "base": args.base,
                "endpoints": ENDPOINTS, "mix": MIX, "results": []}
    limits = httpx.Limits(max_connections=32, max_keepalive_connections=32)
    async with httpx.AsyncClient(base_url=args.base, timeout=10, limits=limits, trust_env=False,
                                 headers={"Accept-Encoding": "gzip"}, follow_redirects=False) as client:
        for name in args.names:
            result = await measure(client, name, args.duration, args.concurrency, args.conditional, args.rate)
            document["results"].append(result)
            Path(args.output).write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:18080")
    parser.add_argument("--output", required=True)
    parser.add_argument("--duration", type=float, default=8)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--conditional", action="store_true")
    parser.add_argument("--rate", type=float, default=None, help="Optional scheduled RPS, bounded to 200.")
    parser.add_argument("--names", nargs="+", choices=[*ENDPOINTS, "mixed"], default=list(ENDPOINTS))
    arguments = parser.parse_args()
    if arguments.rate is not None and not 0 < arguments.rate <= 200:
        parser.error("--rate must be greater than 0 and at most 200")
    asyncio.run(main(arguments))
