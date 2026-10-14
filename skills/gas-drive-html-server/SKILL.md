---
name: gas-drive-html-server
description: Create or update an independent Google Apps Script Web App that indexes and serves HTML files from a specified Google Drive folder, including its subfolders. Does not depend on gas-html-artifact.
---

# GAS Drive HTML Server

Deploy a **self-contained** Google Apps Script directory index. The GAS project's
`Index.html` is an Apache/Nginx-style autoindex page: on each request it lists
HTML files and subfolders beneath a chosen Google Drive root. Drive HTML is
read at request time; content changes do **not** require GAS redeployment.
This skill never creates or edits the HTML artifacts in Drive.

## Routing

| URL                   | Behavior                       |
| --------------------- | ------------------------------ |
| `/exec`               | Index configured root folder   |
| `/exec?dir=FOLDER_ID` | List a descendant folder       |
| `/exec?file=FILE_ID`  | Display a descendant HTML file |

Links use an absolute Web App URL, Drive IDs (avoids duplicate names) and
`<base target="_top">` for iframe navigation. The index displays names, last
modified times and byte sizes, with folders listed before files. All user
data in `Index.html` is contextually escaped by `<?= ... ?>` scriptlets.
Child containment follows parents to the configured root; shortcuts are not
traversed. Only `.html`/`.htm` files with `text/html` MIME type are served.
No cache or background synchronization is required.

## Preconditions and security

1. Obtain a real Google Drive folder ID. Confirm the deploying Google account
   can read the folder and intended descendants. Do not guess a replacement.
2. Review the folder's HTML, editors and dependencies for secrets, hostile
   scripts, unsupported HTML Service features and unintended disclosure.
   Files added/modified later become visible *without* code deployment.
3. Choose deployment access/identity deliberately. New deployments default to
   `MYSELF`/`USER_DEPLOYING`. Broader access requires an explicit flag.
   `USER_DEPLOYING` reads private Drive data as the deployer even for visitors
   with no direct Drive permissions. `USER_ACCESSING` requires viewers' OAuth
   consent and their own Drive access.
4. Install Google's `@google/clasp` CLI, Node.js >=20, authenticate with
   `clasp login`, and enable the Apps Script API.
5. Use a fresh dedicated workdir and ensure exclusive remote edit coordination
   before updating an existing project.

## Deploy

The skill's own `scripts/deploy.mjs` and `templates/` are self-contained and
do **not** call or import `gas-html-artifact`.

```bash
# New standalone Web App; defaults to deployer-only visibility
node scripts/deploy.mjs \
  --folder-id 'DRIVE_FOLDER_ID' --workdir '/tmp/gas-index-new' \
  --new-project 'Drive HTML directory'

# Update an existing deployment, keeping its deployment URL
node scripts/deploy.mjs \
  --folder-id 'DRIVE_FOLDER_ID' --workdir '/tmp/gas-index-update' \
  --script-id 'SCRIPT_ID' --deployment-id 'DEPLOYMENT_ID' \
  --exclusive-coordination
```

Provide `--access` (`MYSELF`, `DOMAIN`, `ANYONE`, `ANYONE_ANONYMOUS`)
and `--execute-as` (`USER_DEPLOYING`, `USER_ACCESSING`) together. Wider access
requires `--acknowledge-exposure`. Changes to an existing policy additionally
require `--allow-policy-change`, and changing its Drive root requires
`--allow-folder-change`. Reassess published content before either change.

The deployer refuses an existing GAS project that is not exclusively owned by
this skill. It validates selected deployment metadata, checks production and
HEAD policies, re-clones before pushing to detect concurrent modifications,
checks readback, creates a version and verifies the deployed `/exec` URL.
There is no atomic compare-and-swap; exclusive remote coordination is mandatory.

Inspect `deployment.json` and `.clasp.json` inside the private workdir for
recovery. Remote creation/push/deployment may succeed despite CLI failure.
**Never blindly retry a project creation.** Credentials must not be committed,
displayed, or stored in the deployment payload. A metadata-verified URL is not
a runtime smoke test; verify the real page and links separately with consent.

## Limitations

- Apps Script HTML Service runs in an iframe sandbox and is not a general
  Nginx/Apache static server. Relative CSS/JS/image assets, arbitrary HTTP
  headers, status codes, MIME types, SPA fallback and unrestricted APIs are
  unsupported. HTML must be self-contained or reference compatible HTTPS assets.
- Error pages returned by HTML Service cannot set HTTP 403/404 status codes.
- Very large directories may exceed Apps Script execution/Drive quotas.
- DriveApp has limitations for shared drives; Advanced Drive Service would
  require separate implementation.
- The script needs the `drive.readonly` OAuth scope, which covers more than
  one folder at authorization time. The runtime applies its own root restriction.
  Publishing the Web App publicly exposes the selected folder's HTML to visitors.

Documentation: [Apps Script Web Apps](https://developers.google.com/apps-script/guides/web),
[DriveApp](https://developers.google.com/apps-script/reference/drive/drive-app),
[HTML templates](https://developers.google.com/apps-script/guides/html/templates).
