# AWS Agent Toolkit Setup for Prepza Development

Last verified: 2026-10-28
Scope: local developer tooling only. This document records setup state and guardrails; it is not evidence that Prepza is deployed on AWS.

## Verified local setup

- OS: Windows PowerShell.
- AWS CLI: v2.39.0 installed for the current Windows user at the default user-local AWS CLI location.
- The official AWS CLI installer script's Authenticode signature was verified as valid and signed by Amazon Web Services, Inc.; the installer independently verified the downloaded MSI signature before installation.
- AWS CLI executable works by its full path. If `aws` is not recognized in a new or existing shell, use the user-local executable or refresh/check PATH; do not reinstall blindly.
- AWS CLI profile name: `prepza-dev`.
- Profile default region: `eu-north-1` (Stockholm), the intended Prepza application region.
- AWS browser-based CLI login completed after switching from a hanging Firefox flow to another browser.
- `aws sts get-caller-identity` succeeded for `prepza-dev`. Do not record the returned account ID, ARN, tokens, or credential material in repository documentation.
- Agent Toolkit configuration region: `us-east-1` (this is intentionally different from the application's default region).
- `aws agent-toolkit list-available-skills --region us-east-1 --profile prepza-dev` succeeded and returned the available skills catalog.

## Installed agent integrations

The setup command detected and installed AWS skills for:

- Claude Code: `%USERPROFILE%/.claude/skills`
- Codex: `%USERPROFILE%/.agents/skills/`

It also reported AWS MCP server configuration updates for:

- Claude Code: `%USERPROFILE%/.claude.json`
- Gemini CLI: `%USERPROFILE%/.gemini/settings.json`

Codex MCP setup was **not** completed automatically because the installer could not find `codex` on PATH. Do not claim Codex MCP is configured until verified. Gemini CLI MCP configuration was updated, but the skills installer did not report installing skills into a Gemini-specific skills directory. Other agents were not detected and were not configured.

The setup output reported 24 default skills installed. The available-skills listing contains a larger catalogue; a listing is not proof that every listed skill has been installed locally.

## Important boundaries and remaining setup

1. This is a local tooling setup, not a cloud deployment. No AWS application resources were provisioned by these setup steps.
2. Toolkit installation/configuration alone does not connect the current ChatGPT conversation directly to the user's local AWS MCP server. Tool access must be verified in the actual coding agent/environment that will use it.
3. Add the official AWS starter rules to the relevant project-level agent rules without overwriting existing content. Before editing any rules file, inspect it and merge only the missing AWS guidance. Preserve all existing Prepza instructions.
4. Inspect the MCP configuration entries and ensure the generated AWS MCP entry uses `AWS_MCP_PROXY_PROFILES: "prepza-dev"` as required by the official setup guide. Preserve its generated command, arguments, timeout and transport. Do not modify unrelated MCP servers. If an AWS MCP entry already exists, reconcile it rather than duplicating it.
5. Verify the MCP server from the target coding agent and use read-only AWS inspection first. Confirm effective IAM permissions before any write operation.
6. Do not create or purchase paid resources, deploy, invoke billable model workloads, or start a billable GPU workload without explicit approval. Use test/sandbox credentials for provider tests; never expose credentials, account IDs, session tokens or secret values in repository docs or chat.
7. AWS CLI login credentials are temporary. If authentication expires, rerun `aws login --region eu-north-1 --profile prepza-dev` and complete the browser flow; do not paste credentials into chat.
8. Keep the application region (`eu-north-1`) separate from the Agent Toolkit configuration region (`us-east-1`).

## Safe verification commands

Use the full executable path if `aws` is not on PATH:

```powershell
$aws = Join-Path $env:LOCALAPPDATA "Programs\\Amazon\\AWSCLIV2\\aws.exe"
& $aws --version
& $aws sts get-caller-identity --profile prepza-dev --query '{Account:Account,Arn:Arn}' --output table
& $aws agent-toolkit list-available-skills --region us-east-1 --profile prepza-dev
```

The identity query still displays an account identifier and ARN; keep its output private and do not commit it to the repository.

## Next local setup actions

- Read the current official AWS Agent Toolkit setup guide and AWS starter rules again before applying rules/config edits.
- Inspect existing MCP and project-rule files for Claude Code, Gemini CLI, Codex, and the actual agent the developer uses; do not assume Antigravity is configured.
- Reconcile the AWS MCP profile environment setting and add rules without overwriting existing content.
- Confirm read-only MCP access in the target coding agent.
- Only then perform a read-only AWS inventory and cost/security review; record sanitized findings separately from this setup record.
