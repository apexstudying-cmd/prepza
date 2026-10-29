# Proposed AWS launch architecture for Prepza

**Status:** Proposed decision; no AWS application resources have been provisioned.
**Decision date:** 2026-10-29
**Target:** A small, controlled Kenyan student pilot first—not a claim of broad-production capacity.
**Existing AWS setup:** CLI profile prepza-dev, default application region eu-north-1 (Stockholm), verified as local tooling only.

## Recommendation

Use **Amazon Lightsail Linux VM (4 GB RAM, 2 vCPU, 80 GB SSD, public IPv4 bundle listed at USD 24/month)** as the initial Docker Compose host if the Render deployment is no longer suitable. Build images in GitHub Actions, not on the production VM. Keep the initial topology small and avoid ECS/Fargate, EKS, an Application Load Balancer, and managed Redis until measured traffic justifies their additional cost and operational complexity.

Official pricing is region- and date-dependent; re-check the [Lightsail pricing page](https://aws.amazon.com/lightsail/pricing/) and AWS Pricing Calculator before creating a resource. The USD 24 instance price is only the compute-host baseline; it excludes domain registration, email usage, object storage, backups, AI providers, and other optional services.

### Initial deployment shape

- **Compute:** one Lightsail Linux VM, 4 GB RAM. Run the existing Docker Compose app, realtime service, chat worker and Redis. Do not build Docker images on the production server.
- **Database (migration gate):** the current `docker-compose.vps.yml` defines a local PostgreSQL service and hard-codes the app database URL to that service. Before provisioning, inspect the actual current production DB and decide explicitly whether to retain the existing managed PostgreSQL source of truth or migrate to a new database. If retaining it, update the production Compose/config contract to accept a securely supplied external `DATABASE_URL` and do not start a competing production DB. If migrating, require a verified backup, disposable restore/migration rehearsal, data-preservation checks and a rollback plan first. Never create a second production database or switch endpoints by assumption.
- **Object storage:** retain Cloudflare R2 initially because the repository already has an R2-oriented storage boundary. Do not perform an unplanned S3 migration during the compute move.
- **HTTPS and domain:** attach a Lightsail static IP, point the chosen domain/subdomain at it, and use Caddy or an equivalently maintained reverse proxy for HTTPS and WebSocket forwarding. Public ingress should be limited to ports 80/443; restrict SSH to the operator's current IP. PostgreSQL and Redis must not be exposed publicly.
- **Image delivery:** build/test in GitHub Actions and deploy a pinned image/release. Keep deployment credentials separate from source and never bake secrets into the image.
- **Transactional email:** use Amazon SES only after sender/domain verification, production access out of sandbox, and end-to-end verification-link/password-recovery delivery tests. SES being wired in code is not proof that live delivery works.
- **Payments:** retain Paystack; verify test-mode checkout, signatures, duplicate webhook/idempotency, retries and entitlement transitions before any approved live-payment test.
- **AI and audio:** retain the current OpenAI and configured audio/TTS providers. Add spend/usage limits and controlled tests; do not trigger billable generation/GPU work without explicit approval.
- **Backups:** schedule encrypted database backups using the database provider's supported mechanism and store protected backup copies in S3 if appropriate. Set retention/lifecycle policy and rehearse restoring a backup into a disposable database. A backup that has never been restored is not verified.
- **Monitoring and cost control:** enable Lightsail metrics/alarms for CPU, network and availability; centralize app/realtime/worker logs with rotation; add alarms for app health, database connectivity, queue depth, disk pressure and AI spend where telemetry supports them. Create an AWS Budget and billing alerts before resources are launched.
- **Access/secrets:** use least-privilege IAM, MFA for the AWS console, no root access keys, no committed .env files, and restrictive permissions for server-side secrets.

## Why not ECS/Fargate yet?

ECS/Fargate is a good managed container platform and removes VM maintenance, but it adds more AWS networking/service configuration and can cost more for always-on app + realtime + worker tasks. Lightsail is a better first step for a small team already using Docker Compose. Reconsider ECS/Fargate when scaling, deployment isolation or availability requirements justify the extra baseline spend. See the [AWS container-service decision guide](https://docs.aws.amazon.com/decision-guides/latest/decision-guides/choosing-aws-container-service.html) and [ECS pricing](https://aws.amazon.com/ecs/pricing/).

## Go-live gates (must not be skipped)

1. Confirm the actual production database, current schema/revision and restore point; rehearse migrations against a disposable restored copy.
2. Confirm the exact main commit passes frontend build, backend/contract tests, security tests, and full browser/mobile/offline regression.
3. Verify HTTPS, domain, service-worker/PWA assets, login/signup/email verification, password recovery and account deletion.
4. Verify uploads and object reads/deletes/presigned URLs using non-sensitive test data.
5. Verify Redis restart/reconnect, worker recovery, realtime auth and WebSocket routing through HTTPS.
6. Verify Paystack sandbox/webhook idempotency and SES delivery using safe test credentials; do not use live payment credentials until separately approved.
7. Verify AI quotas/cost limits and configured audio provider in controlled tests.
8. Verify backups, restore, rollback and deployment recovery.
9. Run a progressive load test against the actual staging server and record CPU/RAM, latency, error rates, database connections, Redis queue depth and spend. Begin with a small invited cohort and increase only with evidence.
10. Keep launch blocked if any required gate lacks current, source-linked evidence.

## Explicitly not approved by this document

- Creating or paying for any AWS resources.
- Switching production DNS, database endpoints, object storage or provider credentials.
- Deploying to production, running migrations on a production database, sending live emails to real users, taking live payments, or starting billable AI/GPU jobs.

This is a proposed architecture and checklist, not evidence of a deployed or production-ready system.
