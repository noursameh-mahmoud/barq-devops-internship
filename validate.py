#!/usr/bin/env python3
"""Environment validation: bounded checks with PASS/FAIL output and non-zero exit on failure."""
import json
import socket
import sys
import time
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8080"
TIMEOUT_SECONDS = 2
MAX_WAIT_SECONDS = 30
POLL_INTERVAL = 2

# Ports that must NOT be reachable directly from outside (only NGINX's public port is allowed)
PROHIBITED_HOST_PORTS = [
    ("localhost", 8081),   # app-01's raw port must not be published
    ("localhost", 5432),   # postgres default port must not be published on the standard port
    ("localhost", 6379),   # redis default port must not be published on the standard port
]

results = []  # list of (name, passed: bool, detail: str)


def record(name, passed, detail=""):
    results.append((name, passed, detail))
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name} {detail}")


def http_get(path, timeout=TIMEOUT_SECONDS):
    try:
        with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=timeout) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body) if body else {}
        except json.JSONDecodeError:
            return e.code, {}
    except Exception as e:
        return None, {"error": str(e)}

def http_get_with_retry(path, max_attempts=3, delay=2):
    last_error = {}
    for attempt in range(max_attempts):
        status, body = http_get(path)
        if status is not None:
            return status, body
        last_error = body
        time.sleep(delay)
    return None, last_error


def wait_for_ready(max_wait=MAX_WAIT_SECONDS, interval=POLL_INTERVAL):
    """Bounded wait: poll /ready until it succeeds or the timeout is reached."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        status, body = http_get("/ready")
        if status == 200 and body.get("status") == "ready":
            return True, body
        time.sleep(interval)
    return False, {}


def check_endpoint(name, path, expected_status=200):
    status, body = http_get(path)
    passed = status == expected_status
    record(name, passed, f"status={status} body={body}")
    return passed, body


def check_public_access():
    status, body = http_get("/")
    record("Public access on port 8080", status == 200, f"status={status}")


def check_readiness_bounded():
    ok, body = wait_for_ready()
    record("PostgreSQL + Redis readiness (bounded wait)", ok, f"final_body={body}")
    return ok


def check_both_backends_respond(sample_size=10):
    seen_instances = set()
    for _ in range(sample_size):
        status, body = http_get("/instance")
        if status == 200:
            seen_instances.add(body.get("instance_id"))
    passed = len(seen_instances) >= 2
    record("Both backends respond via /instance", passed, f"seen={seen_instances}")
    return passed


def check_records_roundtrip():
    status, body = None, {}
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                f"{BASE_URL}/records",
                data=json.dumps({"title": "validate.py test record"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                status = resp.status
                body = json.loads(resp.read().decode())
            break
        except Exception as e:
            body = {"error": str(e)}
            time.sleep(2)
    created = status == 201 and "record" in body
    record("Create record via POST /records", created, f"status={status} body={body}")

    status2, body2 = http_get_with_retry("/records")
    listed = status2 == 200 and any(
        r.get("title") == "validate.py test record" for r in body2.get("records", [])
    )
    record("Newly created record appears in GET /records", listed, f"status={status2}")
    return created and listed

def check_counter_increments():
    status1, body1 = http_get_with_retry("/counter")
    status2, body2 = http_get_with_retry("/counter")
    passed = (
        status1 == 200 and status2 == 200
        and isinstance(body1.get("counter"), int)
        and body2.get("counter") == body1.get("counter") + 1
    )
    record("Redis-backed counter increments", passed, f"first={body1.get('counter')} second={body2.get('counter')}")
    return passed


def check_prohibited_ports_closed():
    all_closed = True
    for host, port in PROHIBITED_HOST_PORTS:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            sock.connect((host, port))
            reachable = True
        except (ConnectionRefusedError, socket.timeout, OSError):
            reachable = False
        finally:
            sock.close()
        if reachable:
            all_closed = False
        record(f"Port {port} not directly reachable", not reachable, f"host={host}")
    return all_closed


def main():
    print(f"=== Validation started at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} ===\n")

    check_public_access()
    ready_ok = check_readiness_bounded()
    check_endpoint("GET / returns 200", "/", 200)
    check_endpoint("GET /health returns 200", "/health", 200)
    check_both_backends_respond()
    check_records_roundtrip()
    check_counter_increments()
    check_prohibited_ports_closed()

    print("\n=== Summary ===")
    passed_count = sum(1 for _, p, _ in results if p)
    failed_count = sum(1 for _, p, _ in results if not p)
    print(f"Passed: {passed_count}  Failed: {failed_count}  Total: {len(results)}")

    if failed_count > 0:
        print("\nRESULT: FAIL")
        sys.exit(1)
    else:
        print("\nRESULT: PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
