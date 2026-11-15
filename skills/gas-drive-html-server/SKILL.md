---
name: gas-drive-html-server
description: Deploy or update a Drive-backed HTML directory as a standalone Google Apps Script Web App using the bundled CLI.
---

# GAS Drive HTML Server

Use `scripts/deploy.mjs` with the bundled GAS templates. Do not regenerate the deployment code or edit the Drive HTML files. The Web App lists subfolders and serves HTML from Drive at request time; Drive content changes need no redeployment.

## CLI

Prerequisites: Node.js >=22.23.4, Google's `@google/clasp` CLI installed so `clasp` is on `PATH` (for example `npm install -g @google/clasp`), `clasp login`, and the Apps Script API enabled. Run from the Skill directory (the installed Skill's root, or `skills/gas-drive-html-server` in a repository checkout), with a new workdir for each attempt:

```bash
# New Web App (private by default)
node scripts/deploy.mjs \
  --folder-id 'DRIVE_FOLDER_ID' --workdir '/tmp/gas-index-new' \
  --new-project 'Drive HTML directory'

# Update an existing deployment (preserves its URL)
node scripts/deploy.mjs \
  --folder-id 'DRIVE_FOLDER_ID' --workdir '/tmp/gas-index-update' \
  --script-id 'SCRIPT_ID' --deployment-id 'DEPLOYMENT_ID' \
  --exclusive-coordination
```

Optional policy: specify `--access` (`MYSELF`, `DOMAIN`, `ANYONE`, `ANYONE_ANONYMOUS`) and `--execute-as` (`USER_DEPLOYING`, `USER_ACCESSING`) together. Broader-than-private access requires `--acknowledge-exposure`; changing an existing policy/root additionally requires `--allow-policy-change` / `--allow-folder-change`. Never infer approval.

## Guardrails

- Confirm the real Drive folder ID, deployer permissions, and intended audience. Review HTML, scripts, and editors for sensitive content; future Drive changes are served automatically.
- Default: `MYSELF` / `USER_DEPLOYING`. With `USER_DEPLOYING`, viewers can access the selected private Drive HTML without Drive permissions. Broader exposure requires explicit authorization.
- Updating requires exclusive remote coordination. The CLI enforces policy and integrity checks, but cannot atomically prevent concurrent edits.
- On failure, inspect private workdir `deployment.json` and `.clasp.json` before any retry: remote creation/deployment may already have succeeded. Do not disclose credentials.
- Return the deployment URL, and distinguish CLI metadata verification from a separately authorized runtime smoke test.

HTML Service is iframe-sandboxed, not a general-purpose static server; relative assets, arbitrary HTTP responses, and SPAs may not work. The OAuth `drive.readonly` scope extends beyond the folder, even though runtime requests are root-restricted. See [Apps Script Web Apps](https://developers.google.com/apps-script/guides/web).
