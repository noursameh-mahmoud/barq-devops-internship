# AI usage disclosure

Write None if no AI was used. Otherwise record each use:

- Tool/model:
- Purpose:
- Files or decisions affected:
- What you changed or rejected:
- How you independently verified it:
- Related commit:

You may use AI and external resources. You must understand and demonstrate the work.


- Tool/model: Claude (Anthropic), used interactively throughout the investigation and fix process for this project.
- Purpose: explaining unfamiliar concepts (Docker, WSL2, Flask, NGINX, networking) since I have cloud experience but no prior DevOps/Docker background; guiding diagnostic steps (which commands to run and why); helping interpret command output and logs; drafting documentation structure and wording for troubleshooting.md, decisions.md, security_review.md, and this file, based on evidence I personally gathered by running the commands myself.
- Files or decisions affected: nginx/nginx.conf (listen port and upstream port fix), docker-compose.yml (APP_HOST, INSTANCE_ID, database/redis port and password references, healthcheck URL, network isolation for nginx, restart policy, resource limits), config/app.env (database/redis connection string fixes), Dockerfile (USER root -> USER app, removal of COPY config/app.env), .gitignore (added config/app.env), config/app.env.example (created), troubleshooting.md, decisions.md, security_review.md, AI_USAGE.md.
- What you changed or rejected: I did not blindly apply suggestions; I ran every command myself in my own WSL2/Ubuntu terminal and read the actual output before proceeding. When a suggested fix did not work as expected (for example, the deploy.resources.limits syntax initially producing 0 0 in docker inspect, and a container-recreation issue where docker compose up --build did not actually recreate containers despite the flag), I reported the real output back, and we diagnosed the actual cause together rather than assuming the first suggested fix was correct. I made the final judgment calls on decisions such as which password to treat as the source of truth (Decision 2 in decisions.md) and which risks to fix versus document as production follow-ups (security_review.md).
- How you independently verified it: every fix in troubleshooting.md includes retest evidence I personally captured by running curl, docker compose ps, docker compose logs, docker inspect, and similar commands directly in my own terminal, and pasting the real output back for interpretation, not by trusting a suggested fix would work without seeing proof. For example, the PostgreSQL persistence fix was verified by creating a real record, destroying and recreating the containers myself, and confirming the record was still present via curl.
- Related commit: applies across all commits from "Fix NGINX listen port..." through "Complete decisions.md...", visible in git log --oneline.


