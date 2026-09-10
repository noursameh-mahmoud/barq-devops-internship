import json
import re
from collections import Counter

ACCESS_LOG = "logs/access.log"
ERROR_LOG = "logs/error.log"
APP_LOG = "logs/application.log"


def parse_json_log(path):
    valid, malformed = [], []
    with open(path) as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                valid.append(json.loads(line))
            except json.JSONDecodeError:
                malformed.append((i, line))
    return valid, malformed


ERROR_LINE_RE = re.compile(
    r'^(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}) \[(?P<level>\w+)\] '
    r'(?P<pid>\d+)#(?P<tid>\d+): \*(?P<conn>\d+) (?P<message>.*)$'
)


def parse_error_log(path):
    valid, malformed = [], []
    with open(path) as f:
        for i, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            m = ERROR_LINE_RE.match(line)
            if m:
                d = m.groupdict()
                rid_match = re.search(r'request_id=([\w-]+)', d['message'])
                d['request_id'] = rid_match.group(1) if rid_match else None
                valid.append(d)
            else:
                malformed.append((i, line))
    return valid, malformed


def dedupe_by_request_id(records):
    seen, duplicates = {}, []
    for r in records:
        rid = r.get("request_id")
        if rid in seen:
            duplicates.append(r)
        else:
            seen[rid] = r
    return list(seen.values()), duplicates


def percentile(sorted_data, p):
    if not sorted_data:
        return None
    k = (len(sorted_data) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(sorted_data) - 1)
    if f == c:
        return sorted_data[f]
    return sorted_data[f] + (sorted_data[c] - sorted_data[f]) * (k - f)


def main():
    access_valid, access_malformed = parse_json_log(ACCESS_LOG)
    app_valid, app_malformed = parse_json_log(APP_LOG)
    error_valid, error_malformed = parse_error_log(ERROR_LOG)

    print("=== Q1: Coverage and line counts ===")
    for name, valid, malformed in [
        ("access.log", access_valid, access_malformed),
        ("error.log", error_valid, error_malformed),
        ("application.log", app_valid, app_malformed),
    ]:
        print(f"{name}: valid={len(valid)} malformed={len(malformed)}")

    access_deduped, access_dupes = dedupe_by_request_id(access_valid)
    print(f"\naccess.log duplicate request_id lines removed: {len(access_dupes)}")
    for d in access_dupes:
        print("  duplicate request_id:", d.get("request_id"))

    all_access_ts = sorted(r["timestamp"] for r in access_deduped if "timestamp" in r)
    if all_access_ts:
        print(f"\naccess.log covers: {all_access_ts[0]} to {all_access_ts[-1]}")

    print("\n=== Q2: Distinct client requests ===")
    print(f"Distinct request_ids (after removing duplicate lines): {len(access_deduped)}")
    retried = [r for r in access_deduped if "," in r.get("upstream", "")]
    print(f"Requests that retried against a second upstream: {len(retried)}")

    print("\n=== Q3: Final client status counts and error rate ===")
    status_counts = Counter(r["status"] for r in access_deduped)
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")
    total = len(access_deduped)
    errors_5xx = sum(c for s, c in status_counts.items() if s >= 500)
    errors_4xx = sum(c for s, c in status_counts.items() if 400 <= s < 500)
    print(f"Denominator (total distinct client requests): {total}")
    print(f"5xx count: {errors_5xx}  5xx error rate: {errors_5xx/total:.4f}")
    print(f"4xx count: {errors_4xx}")

    print("\n=== Q4: Failures by path / time / backend ===")
    fail_records = [r for r in access_deduped if r["status"] >= 400]
    print("By path:", dict(Counter(r["path"] for r in fail_records)))
    print("By backend:", dict(Counter(r["upstream"] for r in fail_records)))
    if fail_records:
        fail_ts = sorted(r["timestamp"] for r in fail_records)
        print(f"Failure time window: {fail_ts[0]} to {fail_ts[-1]}")

    print("\n=== Q5: Latency percentiles (client-facing, from access.log) ===")
    latencies_ms = sorted(r["request_time"] * 1000 for r in access_deduped)
    median = percentile(latencies_ms, 50)
    p95 = percentile(latencies_ms, 95)
    print(f"Median: {median:.2f} ms   P95: {p95:.2f} ms")
    print("(linear interpolation between closest ranks, over all deduped client requests)")

    print("\n=== Q6: Retried requests - outcome ===")
    retried_success = [r for r in retried if r["status"] < 400]
    print(f"Total retried: {len(retried)}  Succeeded after retry: {len(retried_success)}")
    for r in retried[:10]:
        print(f"  {r['request_id']}: upstream=[{r['upstream']}] final_status={r['status']}")

    print("\n=== Q7/Q8: Correlated examples ===")
    app_by_id = {r["request_id"]: r for r in app_valid if "request_id" in r}
    if fail_records:
        example_fail = fail_records[0]
        rid = example_fail["request_id"]
        print("FAILED example - request_id:", rid)
        print("  access :", example_fail)
        print("  app    :", app_by_id.get(rid))
        print("  error  :", [e for e in error_valid if e.get("request_id") == rid])

    success_example = next((r for r in access_deduped if r["status"] == 200), None)
    if success_example:
        rid = success_example["request_id"]
        print("SUCCESS example - request_id:", rid)
        print("  access :", success_example)
        print("  app    :", app_by_id.get(rid))

    print("\n=== Q9: Proxy/connectivity vs dependency/app issues ===")
    connectivity_errors = [e for e in error_valid if "connect() failed" in e.get("message", "")]
    print(f"error.log 'connect() failed' (proxy/connectivity) entries: {len(connectivity_errors)}")
    app_errors = [r for r in app_valid if r.get("level") == "ERROR"]
    print(f"application.log ERROR-level (dependency/app) entries: {len(app_errors)}")
    print("application.log ERROR event types:", dict(Counter(r.get("event") for r in app_errors)))


if __name__ == "__main__":
    main()