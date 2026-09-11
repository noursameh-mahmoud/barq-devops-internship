#!/usr/bin/env python3
"""Stop one backend, measure traffic/errors, restore it, verify recovery."""
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8080"
REQUESTS_DURING_FAILURE = 10
REQUESTS_AFTER_RECOVERY = 6
MAX_WAIT_RECOVERY = 90


def http_get(path, timeout=3):
    try:
        with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return None, {"error": str(e)}


def run(cmd):
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main():
    print("=== Baseline: confirm both backends respond ===")
    instances = set()
    for _ in range(6):
        status, body = http_get("/instance")
        if status == 200:
            instances.add(body.get("instance_id"))
    print(f"Instances seen before failure: {instances}")
    if len(instances) < 2:
        print("FAIL: did not see both backends before starting the test.")
        sys.exit(1)

    print("\n=== Stopping app-01 ===")
    run(["docker", "compose", "stop", "app-01"])
    time.sleep(2)

    print(f"\n=== Sending {REQUESTS_DURING_FAILURE} requests during failure ===")
    success_during, errors_during, seen_during = 0, 0, set()
    for i in range(REQUESTS_DURING_FAILURE):
        status, body = http_get("/instance")
        if status == 200:
            success_during += 1
            seen_during.add(body.get("instance_id"))
        else:
            errors_during += 1
        print(f"  request {i+1}: status={status} body={body}")
    print(f"During failure: {success_during} succeeded, {errors_during} failed, instances seen: {seen_during}")

    if success_during == 0:
        print("FAIL: no requests succeeded during failure; app-02 should have kept serving traffic.")
        run(["docker", "compose", "start", "app-01"])
        sys.exit(1)

    print("\n=== Restoring app-01 ===")
    run(["docker", "compose", "start", "app-01"])

    print(f"\n=== Waiting up to {MAX_WAIT_RECOVERY}s for app-01 to recover ===")
    deadline = time.time() + MAX_WAIT_RECOVERY
    recovered = False
    while time.time() < deadline:
        status, body = http_get("/instance")
        if status == 200 and body.get("instance_id") == "app-01":
            recovered = True
            break
        time.sleep(2)

    if not recovered:
        print("FAIL: app-01 did not recover within the timeout window.")
        sys.exit(1)

    print(f"\n=== Sending {REQUESTS_AFTER_RECOVERY} requests after recovery ===")
    seen_after = set()
    for i in range(REQUESTS_AFTER_RECOVERY):
        status, body = http_get("/instance")
        if status == 200:
            seen_after.add(body.get("instance_id"))
        print(f"  request {i+1}: status={status} body={body}")

    if "app-01" not in seen_after:
        print("FAIL: app-01 did not serve any requests after being restored.")
        sys.exit(1)

    print(f"\nRESULT: PASS - app-02 kept serving during failure, app-01 recovered and served again ({seen_after}).")
    sys.exit(0)


if __name__ == "__main__":
    main()