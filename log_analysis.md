# Log analysis

# Log analysis

## Commands / scripts
All analysis was performed using scripts/log_analysis.py, run via:
    python3 scripts/log_analysis.py
Source of truth for all counts below is this script's output; commands used to verify specific
findings (e.g. individual request correlation) are noted inline.

## Results

### 1. UTC interval and line validity
- Interval covered (access.log): 2026-08-20T11:00:00.015Z to 2026-08-20T11:29:57.578Z (approx. 30 minutes).
- access.log: 725 valid JSON lines, 1 malformed line.
- error.log: 67 valid lines (matching the NGINX error format), 1 malformed line.
- application.log: 729 valid JSON lines, 1 malformed line.
- Malformed lines were identified by attempting to parse each line as JSON (access.log, application.log) or against the expected NGINX error line pattern (error.log); lines that failed parsing were counted as malformed and excluded from all further analysis, not repaired or guessed at.

### 2. Distinct client requests and deduplication
- 5 duplicate request_id values were found in access.log (lab-000121, lab-000241, lab-000361, lab-000481, lab-000601), each appearing as an exact repeated line.
- Deduplication method: grouped access.log records by request_id, keeping the first occurrence of each and discarding subsequent duplicates, since request_id uniquely identifies a single client request per the logs README.
- After deduplication: 720 distinct client requests.
- Retries were not counted as separate client requests: 19 requests had a comma-separated upstream field (e.g. "172.23.0.12:8080, 172.23.0.11:8080"), representing NGINX retrying a single client request against a second backend after the first failed. These remain a single request_id/single row in access.log, so no special handling was needed to avoid double-counting them as two requests; the risk would have been double-counting if retries had been logged as separate rows, which they were not.

### 3. Final client status counts and error rate
Denominator: 720 (distinct, deduplicated client requests).
- 200: 615
- 404: 10
- 502: 40
- 503: 47
- 504: 8
- 5xx count: 95, 5xx error rate: 95/720 = 13.19%
- 4xx count: 10 (all /missing, an intentionally nonexistent endpoint, not part of the incident)

### 4. Failures by path, time window, and backend
- By path: /records 26, /counter 26, /ready 23, /health 10, /missing 10, / 10.
- By backend: 172.23.0.12:8080 accounted for 73 of the failing requests; 172.23.0.11:8080 accounted for 32.
- Failure time window: 2026-08-20T11:00:00.015Z to 2026-08-20T11:29:37.522Z, but the 502/503/504 failures (excluding the unrelated /missing 404s) cluster specifically starting at 11:05:02Z, indicating a distinct incident window rather than failures spread evenly across the full 30 minutes.

### 5. Latency percentiles
- Median (p50): 54.00 ms
- P95: 2001.00 ms
- Method: linear interpolation between closest ranks over all 720 deduplicated client requests' request_time values (converted from seconds to milliseconds). The large gap between median and p95 reflects the incident: most requests during normal operation are fast (tens of ms), while requests hitting timeouts during the incident take up to ~2 seconds.

### 6. Retried requests
- 19 requests show a comma-separated upstream (retry against a second backend).
- All 19 succeeded after retrying (final status 200), confirmed by cross-referencing each retried request_id's final status field.
- Example: lab-000124, upstream=[172.23.0.12:8080, 172.23.0.11:8080], final_status=200 - NGINX's first attempt against .12 failed, it retried against .11, and that succeeded.

### 7. Incident timeline (cross-referencing access, error, and application logs)
- 11:00:00Z - 11:05:00Z: normal operation, all requests return 200, evenly split across both backends.
- 11:05:02Z: first failure - lab-000122 (GET /health) fails with 502; error.log shows a matching "connect() failed (111: Connection refused)" entry against 172.23.0.12:8080 at the same timestamp; application.log has no corresponding entry for lab-000122 at all, confirming the request never reached the Flask app.
- 11:05:02Z - ~11:07:xxZ: repeated connect() failed errors specifically against 172.23.0.12:8080 in error.log, at regular ~5s intervals, matching a pattern of one backend (app-02, based on IP-to-instance correlation elsewhere in the logs) being completely unreachable during this window.
- Some requests during this window succeed via retry (upstream shows both .12 then .11), while some fail outright with 502/503/504, suggesting NGINX's retry behavior was inconsistent or limited during the incident.
- 11:29:37Z: last failing request recorded.
- No application.log ERROR entries correlate with the "connect() failed" (502) errors, since those never reached the app; the 47 application.log ERROR entries (event: dependency_error) instead correlate with 503 responses, representing a separate failure mode where the app itself was reachable but its dependency check (postgres or redis) failed - documented separately from the connectivity outage above.

### 8. Correlated examples
FAILED example - request_id lab-000122:
- access.log: {"timestamp":"2026-08-20T11:05:02.503Z","request_id":"lab-000122","method":"GET","path":"/health","status":502,"upstream":"172.23.0.12:8080","upstream_status":"502","request_time":0.003,"client":"192.0.2.24"}
- error.log: 2026/08/20 11:05:02 [error] 31#31: *122 connect() failed (111: Connection refused) while connecting to upstream, request_id=lab-000122, request: "GET /health HTTP/1.1", upstream: "http://172.23.0.12:8080/health"
- application.log: no entry - the request never reached the app process, confirming this is a connectivity-layer failure, not an application error.

SUCCESSFUL example - request_id lab-000002:
- access.log: {"timestamp":"2026-08-20T11:00:02.532Z","request_id":"lab-000002","method":"GET","path":"/health","status":200,"upstream":"172.23.0.12:8080","upstream_status":"200","request_time":0.032,"client":"192.0.2.24"}
- application.log: {"timestamp":"2026-08-20T11:00:02.532Z","level":"INFO","event":"http_request","request_id":"lab-000002","instance_id":"app-02","method":"GET","path":"/health","status":200,"duration_ms":32.0}
- Matching timestamps and request_id confirm this request was received by NGINX, forwarded to app-02, and successfully processed.

### 9. Proxy/connectivity vs dependency/application issues
- error.log contains 59 "connect() failed (111: Connection refused)" entries - these are proxy/connectivity issues: NGINX could not even establish a TCP connection to the backend, meaning the backend process was not listening at all (e.g. the container was down or not yet started). Proof: these request_ids have no corresponding entry in application.log at all.
- application.log contains 47 ERROR-level entries, all with event=dependency_error - these are application-level issues: the Flask app was running and reachable, but its own check of PostgreSQL or Redis failed internally, and the app correctly returned a 503 to the client itself (matching the app/server.py code's unavailable() error handler). Proof: these request_ids DO have a corresponding access.log entry with status 503, AND a matching application.log entry showing the app's own error handling, unlike the connectivity failures which have no application.log entry at all.

### 10. What the logs don't prove, and what to check next in a running environment
- The logs prove that 172.23.0.12:8080 was unreachable for a period and that dependency checks failed for another period, but they don't prove the root cause of either (e.g. whether app-02 crashed, was restarting, or was resource-starved; whether postgres/redis were themselves down or just slow to respond).
- The logs don't include resource usage (CPU/memory) at the time of the incident, so it's not possible to confirm from these logs alone whether resource limits (or their prior absence) played a role.
- In a running environment, the next steps would be: check docker compose ps / container restart counts and exit codes for app-02 around 11:05Z; check postgres/redis's own logs for the same window to see if they show connection refusals or crashes on their side; check host-level metrics (CPU, memory, disk) for resource exhaustion; and confirm whether this historical incident matches conditions similar to any of the bugs found and fixed during this project's own investigation (e.g. the APP_HOST or healthcheck issues),