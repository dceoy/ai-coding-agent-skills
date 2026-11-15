---
name: gas-drive-html-server
description: Deploy or update a standalone Google Apps Script Web App that indexes and serves HTML files from a Google Drive folder using the bundled CLI. Use when the user needs a browsable Drive-backed HTML directory.
---

# GAS Drive HTML Server

Use the bundled `scripts/deploy.mjs` CLI; do not recreate its deployment logic or modify the GAS templates. The Web App lists subfolders and serves HTML files from the selected Drive folder at request time, so changes to Drive HTML do not require redeployment. This skill does not create or edit those HTML files.

## Run

Prerequisites: Node.js (see the repository's `package.json`), installed `@google/clasp` via `pnpm install`, `clasp login`, and the Apps Script API enabled. Use an existing parent directory and a **fresh** `--workdir` for every attempt.

From the repository root:

```bash
# Create (private by default)
node skills/gas-drive-html-server/scripts/deploy.mjs \
  --folder-id 'DRIVE_FOLDER_ID' --workdir '/tmp/gas-index-new' \
  --new-project 'Drive HTML directory'

# Update the same Web App URL
node skills/gas-drive-html-server/scripts/deploy.mjs \
  --folder-id 'DRIVE_FOLDER_ID' --workdir '/tmp/gas-index-update' \
  --script-id 'SCRIPT_ID' --deployment-id 'DEPLOYMENT_ID' \
  --exclusive-coordination
```

For an explicit access policy, pass `--access` (`MYSELF`, `DOMAIN`, `ANYONE`, `ANYONE_ANONYMOUS`) **together with** `--execute-as` (`USER_DEPLOYING` or `USER_ACCESSING`). Non-private access also requires `--acknowledge-exposure`. Updates that change the access policy or Drive root additionally require `--allow-policy-change` or `--allow-folder-change`, respectively. Do not add approval flags without the user's authorization.

## Safety and verification

- Obtain and confirm the actual Drive folder ID and the deploying account's access; never guess IDs. Review the HTML, its editors, and external dependencies for secrets, active scripts, and unintended disclosure. Newly added Drive files become available without redeployment.
- Default deployment is `MYSELF` / `USER_DEPLOYING`. With `USER_DEPLOYING`, visitors may see private Drive HTML through the Web App even without Drive permissions; `USER_ACCESSING` instead requires viewer authorization and access. Confirm the exposure model before choosing broader access.
- Updating an existing script requires exclusive remote edit coordination. The CLI performs project ownership, policy, remote-state, payload, and deployment checks, but cannot provide an atomic remote compare-and-swap.
- Inspect `deployment.json` and `.clasp.json` in the private workdir after a failure. Remote creation or deployment may have succeeded; **do not blindly retry**. Keep credentials and workdir metadata private.
- Report the verified deployment URL, but distinguish metadata verification from a runtime test. Check the actual page and links separately with appropriate access.

## Limitations

Apps Script HTML Service is iframe-sandboxed, **not** a general-purpose static web server. HTML should be self-contained or use compatible HTTPS assets; relative assets, arbitrary headers/status codes, SPA fallback, and unrestricted APIs are unsupported. Large folders may hit quotas; shared drives may require a different Drive API implementation. The OAuth `drive.readonly` scope is broader than the selected root, which the Web App restricts at runtime.

See [Apps Script Web Apps](https://developers.google.com/apps-script/guides/web) and [HTML Service](https://developers.google.com/apps-script/guides/html).
