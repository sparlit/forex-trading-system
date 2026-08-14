# Release Governance for EAQTS V2.4

## Versioning
- Semantic versioning `MAJOR.MINOR.PATCH`.
- Increment `MAJOR` for breaking architectural changes.
- Increment `MINOR` for new features/engines.
- Increment `PATCH` for bug fixes and safety patches.

## Release Process
1. Pull latest `main`.
2. Run `make test lint typecheck format` to ensure quality.
3. Update `CHANGELOG.md` with entries.
4. Bump version in `pyproject.toml`.
5. Commit with message `Release vX.Y.Z`.
6. Tag: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`.
7. Push: `git push && git push --tags`.
8. CI pipeline automatically builds and publishes artifacts.

## Safety Gate
- The CI must pass all tests and lint checks before a tag can be pushed.
- A manual approval step (GitHub Environments) ensures a human reviews the release notes.

## Post‑Release Checklist
- Deploy updated Docker image (if used) or update Scoop package.
- Verify health checks on all services (PostgreSQL, Redis, InfluxDB, NATS, Prometheus, Grafana).
- Run smoke tests against the live system.
- Document any migration steps.
