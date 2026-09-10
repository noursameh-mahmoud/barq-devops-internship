# Technical decisions

Record at least 5 decisions. Include assumptions and limits.

## Decision
- Choice:
- Why:
- Alternative:
- Trade-off:
- Evidence / commit:
- Production improvement:

Cover your base image, health checks, networks, timeouts/retries, restart/resource settings,
storage and any other meaningful choices.


## Decision 1: Base image choice (python:3.12-slim-bookworm)
- Choice: kept the pre-selected python:3.12-slim-bookworm base image, pinned by digest (@sha256:...), rather than switching to a different variant.
- Why: slim images are significantly smaller than the full python image (fewer pre-installed packages, smaller attack surface) while still being Debian-based, which has good compatibility with psycopg (the PostgreSQL driver) without needing to compile from source, unlike alpine-based Python images which sometimes require extra build tooling for C-extension packages.
- Alternative: python:3.12-alpine would be even smaller, but alpine uses musl libc instead of glibc, which has historically caused compatibility issues with some Python packages that ship pre-compiled C extensions.
- Trade-off: slim-bookworm is larger than alpine would be, but avoids the risk of build failures or subtle runtime bugs from musl/glibc differences, which is a safer default for a time-limited assessment.
- Evidence / commit: unchanged from the starter pack; verified the image builds and runs correctly throughout this project.
- Production improvement: consider a multi-stage build to further reduce final image size, separating build-time dependencies from the runtime image.

## Decision 2: Resolving the DATABASE_URL password mismatch
- Choice: when config/app.env's password (ending in ...8d) did not match docker-compose.yml's POSTGRES_PASSWORD (ending in ...8c), changed app.env to match docker-compose.yml, rather than changing the database's actual password to match app.env.
- Why: docker-compose.yml's POSTGRES_PASSWORD is the source of truth that actually sets the database's real password when the container initializes; changing the consumer (app.env) to match the source was the more direct, lower-risk fix.
- Alternative: could have changed POSTGRES_PASSWORD instead, which would have worked equally well technically, since both files were simply out of sync.
- Trade-off: neither choice is more "correct" than the other technically; this was a judgment call to change the dependent file rather than the database's own configuration.
- Evidence / commit: see troubleshooting.md Entry 3.
- Production improvement: in production, credentials should not be manually duplicated across multiple files at all; a secrets manager would supply the same credential to both the database and its consumers from a single source, eliminating this class of mismatch entirely.

## Decision 3: Using Python's urllib for the app healthcheck instead of curl
- Choice: kept the existing healthcheck approach of using python -c "import urllib.request; ..." rather than installing curl or wget in the app image.
- Why: the python:3.12-slim-bookworm image already includes Python (obviously) but not curl by default; using a tool already present in the image avoids adding extra packages solely for health checking, keeping the image smaller and reducing the attack surface (fewer installed binaries).
- Alternative: could install curl via apt-get in the Dockerfile and use a simpler CMD ["CMD", "curl", "-f", "http://127.0.0.1:8080/health"].
- Trade-off: the python one-liner is slightly less readable than a plain curl command, but avoids an extra apt-get install layer and additional installed package.
- Evidence / commit: fixed only the URL path (/healthz -> /health) in troubleshooting.md Entry 5; the underlying python-based approach itself was kept as-is.
- Production improvement: if a dedicated healthcheck binary becomes a recurring need across multiple services, consider a small dedicated healthcheck tool baked into a shared base image instead of repeating the python one-liner.

## Decision 4: Removing NGINX from the backend network entirely, rather than using firewall rules
- Choice: removed nginx from the backend network so it can only reach app-01/app-02 via frontend, instead of keeping it on both networks and relying on some other access control mechanism.
- Why: Docker's own network segmentation is the simplest, most direct way to enforce "NGINX should never reach postgres/redis" - if NGINX is never on the same network as those services, there is no address for it to even attempt to reach.
- Alternative: could have kept NGINX on both networks and instead relied on PostgreSQL/Redis-level authentication alone to prevent unauthorized access.
- Trade-off: relying on network segmentation alone means if a new service is later added to the backend network by mistake, it would automatically gain access; authentication at the database/cache level would remain a defense-in-depth measure regardless of network topology, so both should ideally be used together in production.
- Evidence / commit: see troubleshooting.md Entry 9.
- Production improvement: add network policies or a service mesh for defense in depth beyond Docker's basic network segmentation.

## Decision 5: Restart policy (unless-stopped) and resource limit values
- Choice: set restart: unless-stopped for all services, and mem_limit/cpus values of 256MB/0.5 CPU per app instance, 512MB/1.0 CPU for postgres, and 256MB/0.5 CPU for redis.
- Why: unless-stopped ensures services recover automatically from crashes without requiring manual intervention, while still respecting an intentional docker compose stop. The specific resource values were chosen as reasonable, conservative defaults for a small assessment workload (a simple Flask app, a lightly-used database, and a cache), not derived from load testing.
- Alternative: could have used restart: always (restarts even after an intentional stop, including after a host reboot) or on-failure (only restarts on non-zero exit codes, not e.g. an OOM kill).
- Trade-off: unless-stopped is a reasonable middle ground for a locally-run assessment; a production deployment under an orchestrator (Kubernetes, ECS) would typically let the orchestrator manage restart behavior instead of relying on Compose's policy.
- Evidence / commit: see troubleshooting.md Entry 8.
- Production improvement: size resource limits based on real observed load rather than estimates, and consider using an orchestrator's autoscaling rather than fixed limits.

## Decision 6: Correcting the PostgreSQL volume mount path rather than restructuring storage entirely
- Choice: fixed the existing named volume (postgres-data) to mount at PostgreSQL's real data directory (/var/lib/postgresql/data), rather than introducing a different volume or storage strategy.
- Why: the project already had a correctly-defined named volume in the volumes: top-level section; the only problem was where it was mounted inside the container. Correcting the mount path was the minimal, targeted fix rather than a larger restructuring.
- Alternative: could have used a bind mount to a specific host folder instead of a named Docker volume, which would make the data directly browsable from the host filesystem.
- Trade-off: named volumes are managed by Docker and are more portable across machines, but are less directly inspectable than a bind mount would be; named volumes were kept as the better default for this containerized workflow.
- Evidence / commit: see troubleshooting.md Entry 7, including proof that a record survives full container destruction and recreation.
- Production improvement: pair the named volume with a scheduled backup process (backup.sh run via cron or a sidecar container) that copies data off-host, since a named volume alone does not protect against host disk failure.


