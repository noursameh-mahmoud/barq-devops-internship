# Security and production-readiness review

Record at least 8 concrete risks or improvements relevant to your final solution.
This is a review requirement, not the number of hidden faults.

For each finding:
- Risk and evidence:
- Impact:
- Implemented fix / commit:
- Production follow-up:
- How to verify:

Cover secrets, ports, container user, image selection, networks, persistence/backup,
logging/monitoring and availability. Separate completed work from planned improvements.

## 1. Real database credentials committed to git history and baked into Docker image
- Risk and evidence: config/app.env, containing real (synthetic lab) database credentials, was tracked in git due to a .gitignore pattern mismatch (.env.* did not match app.env), and was also copied directly into the Docker image via the Dockerfile, permanently embedding secrets in the image layer.
- Impact: anyone with access to the git history or a copy of the built image could extract the database password, even after it is later rotated in the live environment.
- Implemented fix / commit: added config/app.env to .gitignore, untracked it with git rm --cached, created a safe config/app.env.example with placeholder values, and removed the COPY config/app.env line from the Dockerfile so secrets are only supplied at runtime via docker-compose's env_file. See troubleshooting.md Entry 10.
- Production follow-up: earlier commits in this repo's history still contain the real (synthetic) credentials; in a real production incident this would require credential rotation and, ideally, git history rewriting or treating the old credentials as permanently compromised. A proper secrets manager (Docker secrets, AWS Secrets Manager, HashiCorp Vault) should replace plain environment files entirely.
- How to verify: docker history <app-image> to confirm app.env is no longer a layer; git log -p config/app.env to see it is no longer modified after the fix commit.

## 2. Application containers ran as root
- Risk and evidence: the Dockerfile created a dedicated low-privilege user (app, uid 10001) but then explicitly switched back to USER root before starting the application process.
- Impact: if the Flask application or one of its dependencies were compromised (e.g. via a future vulnerability), an attacker would have root privileges inside the container, increasing the potential for container breakout or broader damage within that container's filesystem.
- Implemented fix / commit: changed the final USER instruction from root to app. See troubleshooting.md Entry 6.
- Production follow-up: consider also setting a read-only root filesystem (read_only: true in Compose) where the application does not need to write to disk, further reducing what a compromised process could modify.
- How to verify: docker compose exec app-01 whoami and id both confirm the process runs as uid 10001 (app), not root.

## 3. NGINX had unnecessary direct network access to PostgreSQL and Redis
- Risk and evidence: nginx's service definition included both frontend and backend networks, meaning it could resolve and connect directly to postgres and redis, despite never needing to.
- Impact: if NGINX itself were compromised (e.g. via a misconfiguration or vulnerability), an attacker would have a direct network path to the database and cache, bypassing the application layer entirely.
- Implemented fix / commit: removed nginx from the backend network, leaving it only on frontend. See troubleshooting.md Entry 9.
- Production follow-up: consider additional network policies (e.g. firewall rules or a service mesh) for defense in depth, rather than relying solely on Docker's network segmentation.
- How to verify: docker compose exec nginx nc -zv postgres 5432 and redis 6379 both fail with a DNS resolution error, confirming no path exists.

## 4. PostgreSQL data did not actually persist across container recreation
- Risk and evidence: the named volume postgres-data was mounted at /var/lib/postgresql/backup, an unused path, while PostgreSQL's real data directory (/var/lib/postgresql/data) was originally set as tmpfs (memory-only, wiped on restart).
- Impact: any data written to the database would be permanently lost on every container restart or recreation, a critical data-loss risk for any real workload.
- Implemented fix / commit: removed the tmpfs setting and corrected the volume mount to point at /var/lib/postgresql/data. Proved persistence by creating a record, destroying and recreating the postgres and app containers, and confirming the record survived. See troubleshooting.md Entry 7.
- Production follow-up: backup.sh/restore.sh should be run on a schedule (e.g. via cron or a backup sidecar container) in production, with backups stored off-host, not just relying on the named volume surviving on the same machine.
- How to verify: run backup.sh, then restore.sh against a fresh volume, and confirm records are present (documented separately in README.md).

## 5. No restart policy meant containers would not recover from crashes automatically
- Risk and evidence: all services were configured with restart: "no".
- Impact: if any container crashed (e.g. the app due to an unhandled exception, or postgres due to a transient issue), it would remain stopped indefinitely with no automatic recovery, causing an avoidable outage.
- Implemented fix / commit: changed restart policy to unless-stopped for all services. See troubleshooting.md Entry 8.
- Production follow-up: in a real production environment running under an orchestrator (Kubernetes, Docker Swarm, ECS), restart behavior would be managed by the orchestrator's own health-based rescheduling rather than Compose's restart policy alone.
- How to verify: docker inspect <container> --format='{{.HostConfig.RestartPolicy.Name}}' returns unless-stopped for each service.

## 6. No CPU or memory limits meant one container could starve the others
- Risk and evidence: no resource constraints were defined for any service; a memory leak or runaway process in one container could consume all host resources, affecting every other container on the same machine.
- Impact: a bug or attack against a single service (e.g. the app under heavy load) could cause a full outage of the entire stack, not just that one service, due to host resource exhaustion.
- Implemented fix / commit: added mem_limit and cpus to all services (256MB/0.5 CPU per app instance, 512MB/1.0 CPU for postgres, 256MB/0.5 CPU for redis). Note: initially attempted using the deploy.resources.limits syntax, which is silently ignored outside Docker Swarm mode; switched to the classic mem_limit/cpus properties, which are correctly enforced by plain docker compose. See troubleshooting.md Entry 8.
- Production follow-up: these limits were chosen as reasonable defaults for a small assessment workload, not derived from load testing; a real production deployment should size limits based on actual observed usage under load.
- How to verify: docker inspect app-01 --format='{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}' returns non-zero values matching the configured limits.

## 7. Confirm no unintended ports are exposed to the host
- Risk and evidence: postgres and redis both bind to 127.0.0.1-only host ports (15432 and 16379 respectively) for local developer convenience, and only NGINX is reachable on the assessment's required public port.
- Impact: binding to 127.0.0.1 rather than 0.0.0.0 means these ports are not reachable from outside the host machine itself, but they are still technically accessible to any other process running locally on the same machine, which is broader access than strictly necessary.
- Implemented fix / commit: not changed, since the brief's local assessment context requires being able to reach postgres/redis directly for testing/debugging purposes; documented here as an accepted trade-off rather than a fixed issue.
- Production follow-up: in production, postgres and redis should not expose any host port at all; only application containers within the same private network should reach them, with a bastion host or SSH tunnel used for any necessary manual access.
- How to verify: docker compose ps confirms only nginx's port is bound to a non-127.0.0.1 interface (or the assessment's required 0.0.0.0 equivalent); postgres/redis ports remain 127.0.0.1-only.

## 8. No centralized logging or monitoring/alerting exists
- Risk and evidence: application, NGINX, and database logs are only accessible via docker compose logs on the local machine; there is no log aggregation, retention policy, or alerting on error rates or container health changes.
- Impact: in a real incident, logs would be lost when containers are removed, and nobody would be automatically notified of elevated error rates, dependency failures, or a container repeatedly restarting.
- Implemented fix / commit: not implemented, out of scope for this local assessment; the application does emit structured JSON logs (see app/server.py's log_event function) which would be straightforward to forward to a log aggregator.
- Production follow-up: forward container logs to a centralized system (e.g. an ELK stack, Loki, or a managed service like CloudWatch/Datadog); add alerting on health check failures, elevated 5xx rates, and container restart loops.
- How to verify: not applicable yet; would be verified by confirming logs appear in the aggregator and test alerts fire correctly once implemented.


