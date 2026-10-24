# Does the dev GitHub image-push role exist in an account

Type: task
Status: open
Blocked by:

## Question

Does IAM role `edgartools-dev-github-actions-ecr` exist, and if it does, what trust subject and actions does it have? Read-only. Do not assume the role, read a secret value, or start an execution.

Source at `6a272d4d` instantiates that role only from `infra/terraform/access/aws/accounts/dev/main.tf`. The trust subject is any ref of `paulananth/edgartools-platform`. The prod access root does not instantiate the module. `.github/workflows/ci.yml` does not assume it. A file in git is not proof the role was applied. Dev AWS was decommissioned in the repo notes. That note is not an IAM observation.

The audit lead is `iam:edgartools-dev-github-actions-ecr:oidc-sub-any-ref:ecr-push-secret-read`.

## Checklist

- [ ] Owner records whether the role exists and its trust subject and actions.
- [ ] Learning → skill: none until the observation exists.
