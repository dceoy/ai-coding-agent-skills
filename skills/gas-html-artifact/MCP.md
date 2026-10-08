# Deploying an HTML artifact with Google Apps Script MCP

This is the agent-driven backend for Claude Code, including **Claude Code on the web**.
It uses a user-authorized Google MCP server to call Apps Script API methods directly.
It **does not need `clasp login`**, and must not read, copy, or reuse clasp credentials.
The skill's artifact assessment and safety rules in [SKILL.md](SKILL.md) apply unchanged.

## Capability and authentication checks

Before any mutation, inspect the connected MCP tools and verify that **the same Google
account** has Apps Script API access and that all the following operations are available:

| Apps Script API operation | Purpose |
| --- | --- |
| `projects.create` | Create a standalone project, only when explicitly requested |
| `projects.get`, `projects.getContent` | Verify binding; read HEAD and selected immutable version |
| `projects.updateContent` | Replace the **complete** project payload |
| `projects.deployments.list`, `projects.deployments.get` | Enumerate **every page**, verify selected deployment and URL |
| `projects.versions.create` | Create an immutable version only after payload readback |
| `projects.deployments.create`, `projects.deployments.update` | Create an additional/initial deployment or update a selected ID |

Tool names can differ by MCP provider. Check tool schemas, not the provider's name.
Require full Apps Script REST response fields: file `name`, `type`, `source`;
`deploymentConfig`; and `entryPoints[].webApp`. For updates, reading
`projects.getContent(scriptId, versionNumber)` must be supported.
A Drive/Docs/Sheets MCP, a connector with only Apps Script execution tools, or
a tool returning merely success messages **does not satisfy** this capability gate.
Never widen OAuth scopes, Google Workspace administrative policy, access, or
execution identity to bypass a missing operation.

Enable the [Apps Script API](https://script.google.com/home/usersettings)
and authorize the MCP server independently of clasp. Keep OAuth credentials in
the MCP provider's authentication flow, outside source artifacts and repository files.

## Safe deployment protocol

1. **Assess the provided HTML** as described in SKILL.md. Do not execute embedded
   code. Validate assessment SHA-256 against the original (and derivative, if any),
   report `secretReview: passed`, and require no unresolved issues. Preserve
   compatible HTML exactly; keep a converted derivative separate.

2. **Select an explicit project and deployment**:
   - Existing project: require a specific `scriptId`; do not search for an
     arbitrary similarly titled project.
   - New project: require an explicit title and initial deployment choice;
     obtain authorization for the project and Web App policy **before**
     calling `projects.create({title})`. Record its returned `scriptId`
     immediately, including when subsequent steps fail.
   - Select exactly one of initial, additional, or update by **explicit
     `deploymentId`**. Both `access` and `executeAs` must be supplied for
     initial/additional deployments, using the values in SKILL.md.
     Never infer a public access setting.

3. **Read before writing**. Call `projects.get(scriptId)`, 
   `projects.getContent(scriptId)` for HEAD, and exhaust all pages of
   `projects.deployments.list(scriptId)`. For an update, call
   `projects.deployments.get(scriptId, deploymentId)` and read the
   **selected version** via `projects.getContent(scriptId, versionNumber)`.
   Require a matching script ID, positive version number and Web App entry point.
   The selected *versioned manifest*, not HEAD, determines the published policy.
   Preserve that policy unless the user explicitly authorizes **both** replacement
   access/execute-as values. If unknown, stop. For initial deployment, reject
   projects with existing versioned deployments.

4. **Construct the full `projects.updateContent` body** using all files from
   HEAD, mapped exactly to `{name, type, source}`, including empty files.
   The Apps Script manifest is `{name:"appsscript", type:"JSON", source:"..."}`;
   the artifact is `{name:"Index", type:"HTML", source:"..."}`;
   the minimal `doGet` wrapper is `{name:"Code", type:"SERVER_JS", source:"..."}`
   or `GasHtmlArtifact` if an unrelated `Code` already exists.
   Use the exact wrapper source from [templates/Code.gs](templates/Code.gs).
   The agent must **not** invent a different wrapper.

   - Preserve every unrelated file, manifest field, scope and advanced service.
   - Only a **byte-identical** minimal wrapper in `Code` or
     `GasHtmlArtifact` establishes ownership. Refuse to overwrite an
     existing `Index` if no owned wrapper is present.
   - Conservatively reject other server scripts containing a `doGet` symbol;
     reject duplicate/conflicting file names. Reconcile manually rather
     than deleting unknown code.
   - New manifests or changed HEAD/production `webapp` policies require explicit
     authorization (`--allow-manifest-update` in the clasp backend).
     Retain all other manifest fields; do not silently broaden permission.

   **Important:** `projects.updateContent` replaces **all** files. Do not send
   only the HTML file or a partial set of changed files.

5. **Coordinate and check for races**. For existing projects, establish
   exclusive edit/deployment coordination, including remote editor activity.
   Immediately before mutation, retrieve complete HEAD and the full deployment
   list again, compare the file names/types/source and deployment metadata to the
   earlier snapshots, and abort on any difference. There is **no atomic CAS**
   between this comparison and `updateContent`; the user must maintain
   exclusive coordination. Display the complete target file set and approved
   policy for inspection, without printing sensitive content.

6. **Update and read back**. Call `projects.updateContent(scriptId, {files})`
   with the **complete** payload, then `projects.getContent(scriptId)`.
   Compare all names, types and exact source strings against the staged payload.
   If they differ, stop before creating a version or deployment. Do not retry a
   non-idempotent operation blindly.

7. **Version and deploy**. Call `projects.versions.create(scriptId)`; record
   its returned `versionNumber`. Read
   `projects.getContent(scriptId, versionNumber)` and verify the immutable
   version matches exactly. Only then call:
   - `projects.deployments.create(scriptId, {versionNumber, manifestFileName:"appsscript", description})`
     for explicitly requested initial/additional deployments, or
   - `projects.deployments.update(scriptId, deploymentId, {deploymentConfig:{scriptId, versionNumber, manifestFileName:"appsscript", description}})`
     for an explicitly selected existing deployment.

   Adapt the call arguments to the **actual MCP tool schema**, preserving the
   Apps Script `DeploymentConfig` fields. Capture returned IDs immediately.
   For uncertain create/update results, inspect remote metadata first rather
   than repeating calls and risking duplicate deployments.

8. **Verify production metadata**. Call `projects.deployments.get` for the
   actual deployment ID. Verify script ID, deployment ID, version, selected
   manifest, Web App access and execute-as policy, and the returned
   `entryPoints[].webApp.url`. The URL must be HTTPS on `script.google.com`,
   with path `/macros/s/<deploymentId>/exec` and no query/fragment.
   Updating a deployment must preserve its previous production URL.
   Only return this **server-reported verified** URL and the recorded IDs.
   Do not synthesize the URL or substitute `/dev`. Report browser runtime
   smoke testing separately as **not performed** unless actually authorized
   and executed.

## Failure and environment considerations

An unavailable MCP method, truncated pagination, missing versioned files,
unsupported HTML, stale HEAD, ownership collision, policy uncertainty,
missing user authorization or missing permissions **stops** the workflow.
Do not silently fall back to clasp or create a replacement project.
If a partial failure occurs after `updateContent`, remote HEAD may have
changed without advancing production; a version might exist without a
deployment. No automatic rollback is implied. Reconcile recorded IDs
before resuming.

For Claude Code on the web, the MCP must be **connected and accessible
within that Claude Code environment**. A local stdio-only server on a user's
laptop is not automatically available to the cloud session. Use an
authorized remote MCP server that exposes the required Apps Script API
operations. OAuth approval is handled by the MCP integration, not by clasp.

Official references:
[Apps Script API](https://developers.google.com/apps-script/api/reference/rest),
[project content](https://developers.google.com/apps-script/api/how-tos/manage-projects),
[deployment resource](https://developers.google.com/apps-script/api/reference/rest/v1/projects.deployments).
