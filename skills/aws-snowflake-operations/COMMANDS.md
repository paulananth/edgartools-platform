# Development and deploy commands

Part of the `aws-snowflake-operations` skill: [SKILL.md](SKILL.md) says when to read this.

## Development Commands

> **Tooling:** always use `uv` for Python dependency management and Python CLI
> execution in this repo. The lockfile is `uv.lock`; never invoke bare `pip`.
> Use `uv sync` for project deps, `uv pip install` for deliberate one-off
> installs, and `uv run --with <package>` for a transient tool.
>
> **Docker runtime:** use the Docker context already configured on the machine.
> Leave `DOCKER_HOST` unset. Publish images with `docker build` and
> `docker push` through `infra/scripts/publish-warehouse-image.sh --mode docker`.
> Local PostgreSQL 16 for agents is the shared server in
> "Initialize shared local PostgreSQL" (`docs/local-agent-testing.md` in the repository).

```bash
# SEC User-Agent for a provider capture (provider_capture); must contain an email
export EDGAR_IDENTITY="EdgarTools Platform <email>"
export AWS_DEFAULT_REGION=us-east-1  # infra is us-east-1, not the default us-east-2

# Install project deps (uses uv.lock)
uv sync --extra s3 --extra mdm-runtime

# CLI: start with doctor (the data-platform skill, Setup)
edgar-warehouse --help
edgar-warehouse doctor

# Terraform — AWS infra
cd infra/terraform/accounts/prod
terraform plan
terraform apply

# Docker image publish (configured Docker context; full recipe below)
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin \
    690839588395.dkr.ecr.us-east-1.amazonaws.com
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-dev-images \
  --role warehouse \
  --image-tag sha-$(git rev-parse --short=12 HEAD) \
  --mode docker \
  --cache-from-tag dev \
  --also-tag dev
```
