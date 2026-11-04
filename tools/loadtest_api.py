#!/usr/bin/env python3
"""Load test for the tracking API.

Logs in once, then fires N authenticated requests at an endpoint with a bounded
concurrency and reports throughput and latency percentiles. Requires httpx
(installed in the API venv).

Example:
  python tools/loadtest_api.py --url http://127.0.0.1:8080 \
      --email admin@example.com --password admin12345 \
      --endpoint /api/devices --requests 2000 --concurrency 50
"""
import argparse
import asyncio
import time

import httpx


async def worker(client, url, headers, queue, latencies, errors):
    while True:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        t0 = time.perf_counter()
        try:
            r = await client.get(url, headers=headers)
            latencies.append((time.perf_counter() - t0) * 1000.0)
            if r.status_code >= 400:
                errors.append(r.status_code)
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))


def pct(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    i = min(len(sorted_vals) - 1, int(round(p / 100.0 * (len(sorted_vals) - 1))))
    return sorted_vals[i]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--email", default="admin@example.com")
    ap.add_argument("--password", default="admin12345")
    ap.add_argument("--endpoint", default="/api/devices")
    ap.add_argument("--requests", type=int, default=1000)
    ap.add_argument("--concurrency", type=int, default=50)
    args = ap.parse_args()

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(args.url + "/api/auth/login",
                              json={"email": args.email, "password": args.password})
        r.raise_for_status()
        token = r.json()["access_token"]
        headers = {"Authorization": "Bearer " + token}

        queue = asyncio.Queue()
        for _ in range(args.requests):
            queue.put_nowait(1)
        latencies, errors = [], []

        print(f"load test: {args.requests} reqs, concurrency {args.concurrency}, GET {args.endpoint}")
        start = time.perf_counter()
        await asyncio.gather(*[
            worker(client, args.url + args.endpoint, headers, queue, latencies, errors)
            for _ in range(args.concurrency)
        ])
        elapsed = time.perf_counter() - start

    latencies.sort()
    ok = len(latencies)
    print(f"completed {ok} ok / {len(errors)} errors in {elapsed:.2f}s")
    if ok:
        print(f"throughput: {ok / elapsed:,.0f} req/s")
        print(f"latency ms  p50={pct(latencies,50):.1f}  p95={pct(latencies,95):.1f}  "
              f"p99={pct(latencies,99):.1f}  max={latencies[-1]:.1f}")
    if errors:
        print(f"first errors: {errors[:5]}")


if __name__ == "__main__":
    asyncio.run(main())
