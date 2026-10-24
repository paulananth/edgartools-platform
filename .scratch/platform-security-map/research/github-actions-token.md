# What GitHub documents for `GITHUB_TOKEN` when a workflow omits `permissions`

Read 2026-10-23 from GitHub's own docs. This note does not read this repository's Actions settings and does not call the GitHub API.

## Conclusion

Omitting the `permissions` key does not mean the token has no access, and it is not the same as `permissions: {}` (that form disables every listed permission). GitHub starts from the enterprise, organization, or repository default, then applies a separate rule for pull requests that come from a fork.

A pull request from the same repository is not that fork case. The token keeps the account default. GitHub documents two settings:

- Restricted: read access only for the `contents` and `packages` scopes. This is what a new personal repository gets, and what a new organization gets. A repository created in an organization inherits the organization setting. A more restrictive choice at enterprise or organization level forces that choice downward and disables the permissive option.
- Permissive: read and write access for all permissions.

A pull request from a fork, on the `pull_request` event, gets a read-only `GITHUB_TOKEN`. The workflow-syntax page is more precise than "read-only": any write permission is changed to read-only, unless an admin has selected **Send write tokens to workflows from pull requests**. That exception is documented for fork workflows in private repositories. `pull_request_target` is not included in that write-to-read step. Secrets other than `GITHUB_TOKEN` are not passed to a workflow triggered from a fork.

These pages do not publish a scope-by-scope matrix for the permissive default beyond "all permissions," and they do not say what this repository's live setting is.

## Same-repository pull request

No page states a special scope list for a pull request whose head is in the same repository. The fork limits are written as applying to a forked repository, so they do not apply here. With `permissions` omitted, the token is the account default.

Sources, quoted:

- Workflow syntax, "How permissions are calculated for a workflow job": "The permissions for the `GITHUB_TOKEN` are initially set to the default setting for the enterprise, organization, or repository. If the default is set to the restricted permissions at any of these levels then this will apply to the relevant repositories. ... The permissions are then adjusted based on any configuration within the workflow file, first at the workflow level and then at the job level. Finally, if the workflow was triggered by a pull request event other than `pull_request_target` from a forked repository, and the **Send write tokens to workflows from pull requests** setting is not selected, the permissions are adjusted to change any write permissions to read only." https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#how-permissions-are-calculated-for-a-workflow-job
- Repository settings: "Under \"Workflow permissions\", choose whether you want the `GITHUB_TOKEN` to have read and write access for all permissions (the permissive setting), or just read access for the `contents` and `packages` permissions (the restricted setting)." "By default, when you create a new repository in your personal account, `GITHUB_TOKEN` only has read access for the `contents` and `packages` scopes. If you create a new repository in an organization, the setting is inherited from what is configured in the organization settings." A more restrictive organization default selects that option in the repository and disables the permissive option. https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository#setting-the-permissions-of-the-github_token-for-your-repository
- Organization settings: "By default, when you create a new organization, `GITHUB_TOKEN` only has read access for the `contents` and `packages` scopes." The same permissive-versus-restricted choice is offered. If the organization belongs to an enterprise and the enterprise chose the more restrictive default, the organization cannot choose the more permissive default. https://docs.github.com/en/organizations/managing-organization-settings/disabling-or-limiting-github-actions-for-your-organization#setting-the-permissions-of-the-github_token-for-your-organization
- Enterprise policy, "Workflow permissions": enterprises and organizations created on or after February 2, 2023 default to read-only access for all scopes; those created before that date default to read and write access for all scopes. The other choice on that page is "Read repository contents and packages permissions": only read access for `contents` and `packages`, and organizations and repositories cannot then choose the more permissive default. https://docs.github.com/en/enterprise-cloud@latest/admin/enforcing-policies/enforcing-policies-for-your-enterprise/enforcing-policies-for-github-actions-in-your-enterprise#workflow-permissions

The enterprise page's "read-only access for all scopes" is not the same phrase as the organization and repository pages' "read access for the `contents` and `packages` scopes." Both are GitHub's words. The organization and repository pages are the ones that define the two settings an admin selects. The enterprise page is the only one that dates the split.

A separate switch, off by default for a new personal repository and a new organization, stops workflows from creating or approving pull requests even when the token otherwise has write access. The enterprise page says **Allow GitHub Actions to create and approve pull requests** is disabled by default, and that enabling it lets `GITHUB_TOKEN` create and approve pull requests. https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository#preventing-github-actions-from-creating-or-approving-pull-requests and the enterprise URL above.

The token's permissions are limited to the repository that contains the workflow. https://docs.github.com/en/actions/concepts/security/github_token

The REST schema for the organization default is only `default_workflow_permissions`: `read` or `write`, plus whether Actions can approve pull request reviews. It does not list scopes. This research did not call that API. https://docs.github.com/en/rest/actions/permissions#get-default-workflow-permissions-for-an-organization

## Pull request from a fork

- Events reference, under `pull_request`, "Workflows in forked repositories": "With the exception of `GITHUB_TOKEN`, secrets are not passed to the runner when a workflow is triggered from a forked repository. The `GITHUB_TOKEN` has read-only permissions in pull requests from forked repositories." Dependabot pull requests are treated as if they came from a fork. For a private base repository, those workflows run only when enabled. https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflows-in-forked-repositories
- Workflow syntax: for a fork, `permissions` can add or remove read access, "but typically you can't grant write access." The exception is **Send write tokens to workflows from pull requests**. The calculation paragraph (quoted above) turns write into read for a pull request event other than `pull_request_target` when that setting is not selected. https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#changing-the-permissions-in-a-forked-repository
- Private repositories: **Run workflows from fork pull requests** allows those workflows "using a `GITHUB_TOKEN` with read-only permission, and with no access to secrets." **Send write tokens to workflows from pull requests** "Allows pull requests from forks to use a `GITHUB_TOKEN` with write permission." https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository#enabling-workflows-for-forks-of-private-repositories
- Enterprise, private and internal repositories: the same fork policy. By default, enabled fork workflows "use a `GITHUB_TOKEN` with read-only permission, with no access to secrets." **Send write tokens to workflows from pull requests** makes that token a write token. If the enterprise disables the policy, an organization or repository cannot enable it. https://docs.github.com/en/enterprise-cloud@latest/admin/enforcing-policies/enforcing-policies-for-your-enterprise/enforcing-policies-for-github-actions-in-your-enterprise#fork-pull-request-workflows-in-private-repositories
- Workflow syntax also says Dependabot pull request runs "use a read-only `GITHUB_TOKEN`" and cannot access secrets. https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#permissions-for-workflow-runs-triggered-by-dependabot

`pull_request_target` is a different event. The syntax page says that when a workflow is triggered by it, "the `GITHUB_TOKEN` is granted read/write repository permission, even when it is triggered from a public fork," and the calculation paragraph does not apply the write-to-read adjustment to that event. The events page warns that running untrusted code on `pull_request_target` can grant write privileges or secrets. https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#permissions and https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request_target

That read/write sentence does not say `pull_request_target` overrides a restricted enterprise, organization, or repository default. The calculation order on the same page starts from that default and only skips the fork downgrade.

## What was not used

No request to `api.github.com` for this repository. No read of this repository's Actions settings.
