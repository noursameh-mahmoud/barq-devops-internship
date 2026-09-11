# BARQ DevOps Assessment - Setup and Operations Guide

## Prerequisites
- Docker Desktop with WSL2 integration enabled (Windows) or Docker Engine + Compose (Linux)
- Git

## Setup
```bash
git clone <this-repo-url>
cd BARQ-Academy
cp config/app.env.example config/app.env
# Edit config/app.env with real values if needed (defaults work for local testing)
```

## Build and Start
```bash
docker compose up -d --build
sleep 20
docker compose ps
```
All 5 containers (app-01, app-02, nginx, postgres, redis) should show `Up` and `healthy`.

## Test
```bash
curl http://localhost:8080/
curl http://localhost:8080/health
curl http://localhost:8080/ready
curl http://localhost:8080/instance
curl http://localhost:8080/records
curl -X POST http://localhost:8080/records -H "Content-Type: application/json" -d '{"title":"example"}'
curl http://localhost:8080/counter
```

Run full automated validation:
```bash
python3 validate.py
```
Exits 0 and prints `RESULT: PASS` if all checks succeed; non-zero exit and `RESULT: FAIL` otherwise.

## Failure Test
Stops app-01, proves app-02 continues serving traffic, restores app-01, and proves it serves again:
```bash
python3 failure_test.py
```

## Backup and Restore
Create a backup:
```bash
./backup.sh
```
Creates a timestamped `.dump` file in `./backups/`.

Restore from a backup:
```bash
./restore.sh ./backups/<filename>.dump
```
Automatically verifies records via `/records` after restoring.

## Stop
```bash
docker compose stop
```

## Full Cleanup
```bash
docker compose down -v
```
The `-v` flag also removes the named PostgreSQL volume — use this only when you want to fully reset all data.

## Architecture
See `architecture.png` for request flow, ports, networks, storage, and health check relationships.

## Documentation
- `troubleshooting.md` - investigation journal with real evidence for each fix
- `log_analysis.md` - analysis of the three supplied historical logs
- `decisions.md` - key technical decisions and trade-offs
- `security_review.md` - security/production-readiness findings
- `AI_USAGE.md` - AI usage disclosure

## CI
See `.github/workflows/ci.yml` - runs on push and pull request: checkout, syntax/Compose validation, build, start, wait for readiness, run `validate.py`.