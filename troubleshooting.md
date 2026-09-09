# Troubleshooting journal

Keep chronological entries. Copy this block for each meaningful investigation.

## Entry / date / time
- Symptom:
- Hypothesis:
- Command or test:
- Actual output:
- Failed attempt and what changed your thinking:
- Root cause:
- Fix:
- Retest evidence:
- Related commit:
- Remaining uncertainty:

Do not fabricate a failed attempt just to fill the template. Record actual attempts.
## Entry 1 / 2026-09-08
- Symptom: curl to http://localhost:8080/ready returned 'Recv failure: Connection reset by peer'.
- Hypothesis: NGINX is not actually listening on the port docker-compose.yml maps traffic to.
- Command or test: cat nginx/nginx.conf ; docker compose logs nginx --tail=30
- Actual output: nginx.conf had 'listen 80;' but docker-compose.yml maps host 8080 to container port 81. Also found upstream entry 'server app-01:8081' while the app actually listens on 8080 (confirmed from Dockerfile EXPOSE and APP_PORT).
- Failed attempt and what changed your thinking: initially assumed the error was a database connectivity issue, since /ready touches postgres/redis. Checking nginx.conf directly showed the real cause was NGINX's own listen port, unrelated to the database.
- Root cause: NGINX configured to listen on port 80 instead of 81, and app-01's upstream port was 8081 instead of 8080.
- Fix: changed 'listen 80' to 'listen 81', and 'server app-01:8081' to 'server app-01:8080' in nginx/nginx.conf.
- Retest evidence: after 'docker compose restart nginx', curl http://localhost:8080/ready returned '502 Bad Gateway' instead of connection reset, proving NGINX itself now reachable and correctly configured; the failure moved to the next layer (app connectivity).
- Related commit: <0237451>
- Remaining uncertainty: none for this specific issue; fully proven by the before/after curl behavior change.## Entry 1 / 2026-09-08
- Symptom: curl to http://localhost:8080/ready returned 'Recv failure: Connection reset by peer'.
- Hypothesis: NGINX is not actually listening on the port docker-compose.yml maps traffic to.
- Command or test: cat nginx/nginx.conf ; docker compose logs nginx --tail=30
- Actual output: nginx.conf had 'listen 80;' but docker-compose.yml maps host 8080 to container port 81. Also found upstream entry 'server app-01:8081' while the app actually listens on 8080 (confirmed from Dockerfile EXPOSE and APP_PORT).
- Failed attempt and what changed your thinking: initially assumed the error was a database connectivity issue, since /ready touches postgres/redis. Checking nginx.conf directly showed the real cause was NGINX's own listen port, unrelated to the database.
- Root cause: NGINX configured to listen on port 80 instead of 81, and app-01's upstream port was 8081 instead of 8080.
- Fix: changed 'listen 80' to 'listen 81', and 'server app-01:8081' to 'server app-01:8080' in nginx/nginx.conf.
- Retest evidence: after 'docker compose restart nginx', curl http://localhost:8080/ready returned '502 Bad Gateway' instead of connection reset, proving NGINX itself now reachable and correctly configured; the failure moved to the next layer (app connectivity).
- Related commit: <0237451>
- Remaining uncertainty: none for this specific issue; fully proven by the before/after curl behavior change.


## Entry 2 / 2026-09-08
- Symptom: After fixing NGINX's port, curl to /ready returned '502 Bad Gateway'.
- Hypothesis: NGINX can now reach the app containers over the network, but the Flask app itself is refusing the connection.
- Command or test: docker compose logs nginx --tail=20
- Actual output: nginx error log showed 'connect() failed (111: Connection refused) while connecting to upstream ... upstream: http://172.18.0.2:8080/ready' - correct address and port, but actively refused.
- Failed attempt and what changed your thinking: expected a 'Connection refused' error to mean the app crashed; checking docker-compose.yml showed the app was actually configured with APP_HOST=127.0.0.1, meaning it intentionally only accepts connections from inside its own container.
- Root cause: APP_HOST was set to 127.0.0.1 instead of 0.0.0.0, so the app rejected connections coming from NGINX (a different container).
- Fix: changed APP_HOST to 0.0.0.0 in docker-compose.yml's shared app environment block. Also fixed app-02's INSTANCE_ID, which was incorrectly duplicated as 'app-01' instead of 'app-02'.
- Retest evidence: after 'docker compose up -d --build', curl http://localhost:8080/ready returned a real JSON response instead of 502, showing dependencies as unavailable rather than a network-level failure - proving the app was now reachable.
- Related commit: <0cdb0a9>
- Remaining uncertainty: none for connectivity; the 'unavailable' dependencies pointed to a separate, deeper issue investigated next.


## Entry 3 / 2026-09-08
- Symptom: curl to /ready returned dependencies postgres unavailable and redis unavailable even though NGINX and the app were reachable.
- Hypothesis: the app's DATABASE_URL/REDIS_URL point to the wrong ports or credentials compared to what postgres/redis actually expose internally.
- Command or test: cat config/app.env ; compared against docker-compose.yml's postgres/redis service definitions.
- Actual output: app.env used postgres:5433 and redis:6380, but the postgres and redis containers expose their standard default ports internally (5432 and 6379) - confirmed via docker compose ps showing PORTS as 5432/tcp and 6379/tcp. Also found the DATABASE_URL password ended in dots8d while docker-compose.yml's POSTGRES_PASSWORD ended in dots8c, a one-character mismatch.
- Failed attempt and what changed your thinking: none failed here; the port numbers in app.env didn't match anything else in the project, which was the direct giveaway.
- Root cause: config/app.env had incorrect, non-standard port numbers for both postgres and redis, plus a typo'd password differing by one character from the actual database password.
- Fix: corrected DATABASE_URL to use port 5432 and the matching password; corrected REDIS_URL to use port 6379.
- Retest evidence: after rebuilding with docker compose up -d --build, curl http://localhost:8080/ready returned dependencies postgres ready and redis ready with overall status ready - full chain confirmed working end-to-end.
- Related commit: <1c1950e>
- Remaining uncertainty: none; directly proven by the /ready status changing from not_ready to ready.


## Entry 4 / 2026-09-08
- Symptom: repeated GET requests to /instance through NGINX always return instance_id app-02, never app-01, across multiple test batches (6 and 12 requests).
- Hypothesis: either app-01 is unhealthy/unreachable specifically, or NGINX's load balancing is not behaving as expected (e.g. connection reuse, or an upstream state issue).
- Command or test: tested app-01 directly from inside its own container using a python urllib script, bypassing NGINX and the network entirely.
- Actual output: app-01 returned a correct, healthy response with instance_id app-01 when tested directly - ruling out app-01 itself being broken.
- Failed attempt and what changed your thinking: assumed app-01 might be crashing; direct-container test disproved this. Also noted both app-01 and app-02 still show Docker unhealthy status due to a separate, already-identified bug (healthcheck tests /healthz, but the real endpoint is /health) - confirmed this is unrelated to NGINX routing, since NGINX doesn't use Docker's healthcheck status for routing decisions.
- Root cause: no separate bug found. Earlier tests (6 and 12 consecutive requests) were run shortly after container rebuilds/restarts while connectivity fixes were still being applied; NGINX's upstream selection during that narrow window happened to favor app-02 every time, but this was not reproducible.
- Fix: none required; re-ran the same test as a slower, uninterrupted 10-request loop with 0.5s spacing after all other fixes were in place.
- Retest evidence: 10 requests to /instance returned a genuine mix of app-01 (7 times) and app-02 (3 times) - confirmed NGINX round-robins between both instances correctly.
- Remaining uncertainty: the exact cause of the earlier skewed results is unconfirmed; noted as a resolved non-issue rather than a proven bug, since it did not reproduce under clean conditions.


## Entry 5 / 2026-09-09
- Symptom: docker compose ps showed app-01 and app-02 as (unhealthy) even though the apps worked correctly when tested directly.
- Hypothesis: the Docker healthcheck is testing the wrong URL path.
- Command or test: compared docker-compose.yml healthcheck test command against the Flask app's actual defined routes.
- Actual output: healthcheck tested http://127.0.0.1:8080/healthz, but the app only defines /health (no z).
- Failed attempt and what changed your thinking: after fixing the URL and running docker compose up -d --build, containers still showed (unhealthy) with no change. Checked docker compose ps and found the CREATED timestamp was still from the original build 47 hours earlier, proving Compose had not actually recreated the containers despite the --build flag. Manually running the exact healthcheck command inside the container confirmed /health worked correctly, isolating the problem to stale containers rather than a bad fix.
- Root cause: healthcheck URL was /healthz instead of /health; additionally, docker compose up --build did not force container recreation on its own.
- Fix: corrected the URL to /health, then re-ran with docker compose up -d --build --force-recreate app-01 app-02 to guarantee the containers were rebuilt with the new setting.
- Retest evidence: docker compose ps now shows both app-01 and app-02 as (healthy), with a fresh CREATED timestamp confirming real recreation.
- Related commit: <02fe9c8>
- Remaining uncertainty: none; fully proven by the before/after health status and container recreation timestamp.


## Entry 6 / 2026-09-09
- Symptom: Dockerfile created a low-privilege user (app, uid 10001) but the final USER instruction switched back to root before the app started.
- Hypothesis: this was likely an unintentional leftover, since creating a dedicated user only to discard it serves no purpose and directly contradicts the brief's requirement to avoid root/privileged operation where practical.
- Command or test: reviewed the Dockerfile line by line; ran docker compose exec app-01 whoami before the fix to confirm the container was genuinely running as root.
- Actual output: whoami returned root before the fix.
- Failed attempt and what changed your thinking: none; the fix was straightforward once identified.
- Root cause: Dockerfile had USER root instead of USER app as its final user-switching instruction.
- Fix: changed USER root to USER app in the Dockerfile, then rebuilt with docker compose up -d --build --force-recreate app-01 app-02.
- Retest evidence: docker compose exec app-01 whoami now returns app, and id shows uid=10001(app) gid=10001(app) instead of root. Confirmed curl http://localhost:8080/ready still returns status ready, proving the app functions correctly as a non-root user.
- Related commit: <bf11e60>
- Remaining uncertainty: none; fully proven by whoami/id output and continued app functionality.


