# GitHub Container Registry

The agent image name is `ghcr.io/<owner>/hermes-agent:<tag>`.

## Local build and push

```bash
export GHCR_OWNER=your-github-org
export IMAGE_TAG=0.1.0
echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$GITHUB_USER" --password-stdin
docker/scripts/build.sh
docker/scripts/push.sh
```

`build.sh` tags the runtime stage. `push.sh` pushes that tag. The package must be readable by the account that deploys it. For a private package, the deploying host logs in before `deploy.sh prod`.

## Production pull

`docker/docker-compose.prod.yml` sets `pull_policy: always` and refuses to start when `GHCR_OWNER` or `IMAGE_TAG` is empty. `docker/scripts/deploy.sh prod` runs `docker compose pull` and then `up -d`.

## GitHub Actions

`.github/workflows/release.yml` publishes on tags that match `v*.*.*`. It logs in with `GITHUB_TOKEN`, builds the runtime target, and pushes:

- `ghcr.io/<repository owner>/hermes-agent:<tag>`
- `ghcr.io/<repository owner>/hermes-agent:latest`

The workflow needs `packages: write`. The repository package permission must allow the default `GITHUB_TOKEN` to publish.

`.github/workflows/build.yml` builds the same target on pull requests and on `main`, and does not push.
