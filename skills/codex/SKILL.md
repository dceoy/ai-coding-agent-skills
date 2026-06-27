---
name: codex
description: Use OpenAI Codex from AI coding agents to review code, run adversarial reviews, delegate coding tasks, and manage background jobs or sessions where supported. Use when the user wants a Codex code review, adversarial review, task delegation, session transfer, or job management (status, result, cancel).
allowed-tools: AskUserQuestion, Bash(codex:*), Bash(node:*), Bash(which:*), Bash(npm:*), Bash(git:*), Read, Grep, Glob
---

# Codex Skill

Use OpenAI Codex from AI coding agents to run code reviews, adversarial reviews, and delegate
investigation or implementation tasks to Codex.

Source: [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc)

## When to Use

- **Review**: Run a read-only Codex review of current uncommitted changes or a branch diff.
- **Adversarial review**: Challenge implementation choices, design tradeoffs, and hidden assumptions.
- **Rescue / delegate**: Hand off a bug investigation, fix, or implementation task to Codex.
- **Setup**: Check whether Codex is installed and authenticated; manage the stop-gate review.
- **Job management**: Check status, retrieve results, or cancel a background Codex job (plugin context only).
- **Transfer**: Continue the current session inside a Codex thread (plugin context only).

## Runtime Compatibility

This skill adapts its behavior based on the runtime context it detects.

### Plugin context (Claude Code with `openai/codex-plugin-cc`)

Detected by: `CLAUDE_PLUGIN_ROOT` environment variable is set.

Uses `node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs"` for all operations. Supports full
functionality: code review, adversarial review, task delegation, background jobs, status, result, cancel,
and session transfer.

Install with:

```
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
/reload-plugins
/codex:setup
```

### Standalone Codex CLI context

Detected by: `CLAUDE_PLUGIN_ROOT` is not set and `codex --version` succeeds.

Uses the `codex` CLI directly. Supports: setup check, review, adversarial review, and task delegation.
Plugin-managed features (background job tracking, status/result/cancel, session transfer) are not
available in this mode.

Install with:

```bash
npm install -g @openai/codex
codex login
```

### Unavailable context

Neither plugin nor standalone `codex` CLI is present.

Tell the user:

```
Codex CLI is not installed. Options:

Install the full Codex plugin for Claude Code (recommended):
  /plugin marketplace add openai/codex-plugin-cc
  /plugin install codex@openai-codex
  /reload-plugins
  /codex:setup

Or install the standalone Codex CLI only:
  npm install -g @openai/codex
  codex login
```

## Inputs

- The user's stated intent: which operation and any arguments (`--base main`, `--background`, task text).
- Current repository state (git status, diff).

## Pre-flight: Availability Check

Before running any operation, detect the runtime context:

1. If `CLAUDE_PLUGIN_ROOT` is set → **plugin context**.

   ```bash
   node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" setup --json
   ```

   If Codex is unavailable and npm is present, offer to install it. If installed but not authenticated,
   tell the user to run `codex login`.

2. Else, check for the standalone binary:

   ```bash
   which codex && codex --version
   ```

   If found → **standalone context**.

3. If neither → **unavailable context**. Show install instructions and stop.

## Operation Dispatch

After the pre-flight check, dispatch to the appropriate section based on the user's intent.

---

## Setup

Check installation and authentication state; optionally manage the stop-gate review.

**Plugin context:**

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" setup [--enable-review-gate|--disable-review-gate] [--json]
```

Present the output to the user. If installation was needed and completed, rerun setup to confirm.

**Review gate**: When enabled, a `Stop` hook runs a targeted Codex review before Claude finishes each
response. Only enable it when actively monitoring the session — it can create long-running Claude/Codex
loops that drain usage limits.

**Standalone context:**

```bash
which codex
codex --version
```

Report the installed version. If unauthenticated, instruct the user to run `codex login`. Note that
authentication cannot always be fully validated without the plugin; report uncertainty honestly.

---

## Review

Run a read-only Codex review of current changes.

**Arguments:**

| Flag           | Meaning                                                              |
| -------------- | -------------------------------------------------------------------- |
| `--base <ref>` | Review branch diff against a base branch instead of the working tree |
| `--wait`       | Run in the foreground without asking                                 |

**Execution mode:**

Review always runs in the foreground. Background job management (status, result, cancel) is available for
Rescue/task operations only — not for review or adversarial review.

**Plugin context — foreground:**

Parse user-supplied flags explicitly and build the argv — do not pass a `$ARGUMENTS` shell variable, as it
may expand to empty or collapse multi-word flags into a single argv.

Working tree (no `--base`):

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" review
```

Branch diff (with `--base`):

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" review --base <ref>
```

**Standalone context — prefer native review if available:**

Working tree (staged/unstaged/untracked changes):

```bash
codex review --uncommitted
```

Branch diff (against a base ref):

```bash
codex review --base <ref>
```

**Standalone context — fallback if `codex review` is unavailable:**

Collect git context, then invoke Codex in read-only mode:

```bash
git status --short --untracked-files=all
git diff --stat
git diff
codex --sandbox=read-only exec "<review prompt incorporating the collected diff/status output>"
```

The fallback must be strictly read-only. Do not pass `--sandbox=workspace-write`.

**Rules:**

- Return output verbatim. Do not paraphrase, summarize, or add commentary.
- This operation is **read-only**. Do not fix issues, apply patches, or suggest you are about to make
  changes.
- After presenting findings, stop and explicitly ask the user which issues, if any, they want fixed.

---

## Adversarial Review

Run a steerable review that challenges whether the current approach is right — not just whether the
implementation is correct. It questions design choices, tradeoffs, hidden assumptions, and failure modes.

**Arguments:** Same as review, plus optional free-form focus text after the flags.

**Execution mode selection:** Same logic as review.

**Plugin context — foreground:**

Parse user-supplied flags explicitly and build the argv — do not pass a `$ARGUMENTS` shell variable.

Working tree (no `--base`, no focus text):

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" adversarial-review
```

Branch diff:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" adversarial-review --base <ref>
```

With focus text (append after flags as separate argv words):

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" adversarial-review [--base <ref>] <focus text words...>
```

**Standalone context:**

Collect git context, then invoke Codex in read-only mode with an adversarial prompt:

```bash
git status --short --untracked-files=all
git diff --stat
git diff
codex --sandbox=read-only exec "<adversarial review prompt incorporating the diff and targeting the areas below>"
```

The prompt must challenge: auth/permissions/trust boundaries, data loss/corruption/irreversible state,
rollback safety/retries/idempotency, race conditions/stale state, empty-state/null/timeout behavior,
version skew/schema drift/compatibility, and observability gaps. Do not modify files.

**High-value attack surface areas to target when no focus text is given:**

- Auth, permissions, tenant isolation, and trust boundaries
- Data loss, corruption, duplication, and irreversible state changes
- Rollback safety, retries, partial failure, and idempotency gaps
- Race conditions, ordering assumptions, stale state, and re-entrancy
- Empty-state, null, timeout, and degraded dependency behavior
- Version skew, schema drift, and compatibility regressions
- Observability gaps that would hide failure or make recovery harder

**Rules:**

- Return output verbatim.
- Do not weaken the adversarial framing or rewrite the user's focus text.
- Do not fix issues without explicit user confirmation.

---

## Rescue (Delegate to Codex)

Hand off a task — debugging, investigation, fix, or implementation — to Codex.

**Arguments:**

| Flag               | Meaning                                                               |
| ------------------ | --------------------------------------------------------------------- |
| `--background`     | Run as a background task (plugin context only)                        |
| `--wait`           | Run in the foreground                                                 |
| `--resume`         | Continue the latest Codex thread for this repo (plugin context only)  |
| `--fresh`          | Start a new Codex thread                                              |
| `--model <model>`  | Specify model; `spark` maps to `gpt-5.3-codex-spark`                  |
| `--effort <level>` | Reasoning effort: `none \| minimal \| low \| medium \| high \| xhigh` |
| Remaining text     | Task description forwarded to Codex                                   |

**Thread continuity** (plugin context only, when neither `--resume` nor `--fresh` is given):

Check for a resumable thread:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" task-resume-candidate --json
```

If `available: true`, use `AskUserQuestion` exactly once with two options:

- `Continue current Codex thread` — lead with this when the request is clearly a follow-up ("continue",
  "keep going", "resume", "apply the top fix", "dig deeper").
- `Start a new Codex thread` — lead with this otherwise.

Append `(Recommended)` to the leading option.

**Plugin context:**

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" task [--background] [--resume-last] [--write] [--model <model>] [--effort <level>] "<task description>"
```

- Default to `--write` unless the user explicitly asks for read-only behavior (diagnosis, research, review
  without edits).
- Map `--resume` → `--resume-last`; strip `--fresh` (no flag needed for the companion script).
- Preserve `--background` when invoking the companion script — the companion supports `task --background`
  and passes it through to the job runner.
- Leave `--model` and `--effort` unset unless the user specified them.

**Plugin context — background execution:**

When `--background` is requested, run `codex-companion.mjs task --background ...` in the **foreground**
(do not add `run_in_background: true`). The companion enqueues a detached managed job and prints the job
ID and status guidance to stdout; backgrounding the Bash call would hide that output. Display the
companion's stdout to the user so they can track the job with `status`/`result`/`cancel`.

**Standalone context — write-capable task:**

```bash
codex --sandbox=workspace-write exec "<task description>"
```

Check `codex --help` first to verify `--sandbox` and `exec` are supported. If unsupported flags are
detected, omit them and document the limitation.

**Standalone context — read-only task (diagnosis, research, review without edits):**

```bash
codex --sandbox=read-only exec "<task description>"
```

**Standalone context — background:**

If `--background` is explicitly requested and the agent runtime has no background execution primitive,
fail fast with a clear message:

```
Background mode is not supported in this runtime without the Codex Claude Code plugin.
To use background jobs: install openai/codex-plugin-cc and use the plugin context.
Alternatively, run this task in the foreground — proceed?
```

Do not silently drop `--background` and execute foreground.

**Standalone context — `--resume`, `--fresh`, job management flags:**

These flags are plugin-managed features. In standalone mode, ignore `--resume` / `--fresh` (no thread
persistence) and note the limitation. Do not claim resume functionality works.

**Rules:**

- Return output verbatim.
- Do not inspect the repository, read files, poll status, or do any follow-up work independently.
- If Codex was not successfully invoked, report the failure and stop — do not generate a substitute answer.

---

## Status

Show active and recent Codex jobs for the current repository.

**Plugin context:**

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" status [job-id] [--all]
```

Without a job ID: render output as a compact Markdown table with columns for job ID, kind, status, phase,
elapsed/duration, summary, and follow-up commands.

With a job ID: present the full output verbatim.

**Standalone context:**

Status is a plugin-managed job operation. The standalone Codex CLI does not maintain this skill's managed
job registry. Explain this clearly and suggest using the plugin context for job tracking. Do not invent
job IDs or poll nonexistent state.

---

## Result

Show the final stored output for a finished Codex job.

**Plugin context:**

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" result [job-id]
```

Present the full output verbatim, preserving:

- Job ID and status
- Verdict, summary, findings, details, artifacts, and next steps
- File paths and line numbers exactly as reported
- Any error messages or parse errors
- Follow-up commands such as `codex resume <session-id>`

**Standalone context:**

Result retrieval requires plugin-managed job state. Explain that this operation is unavailable without the
Codex Claude Code plugin and suggest the user re-run the task or install the plugin.

---

## Cancel

Cancel an active background Codex job.

**Plugin context:**

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" cancel [job-id]
```

Present the cancellation confirmation to the user.

**Standalone context:**

Cancel requires plugin-managed job state. Explain that background job cancellation is unavailable in
standalone mode. If a `codex exec` process is running in the foreground, the user can interrupt it with
`Ctrl+C`.

---

## Transfer

Create a persistent Codex thread from the current session and print a `codex resume` command.

Use when you started debugging or implementing and want to continue that same context inside Codex.

**Plugin context:**

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" transfer [--source <claude-jsonl>]
```

Present the output exactly as returned, preserving the Codex session ID and the
`codex resume <session-id>` command.

The `SessionStart` hook supplies the current transcript path automatically; `--source` is available as a
manual override. The source must be under `~/.claude/projects`.

**Standalone / generic agent context:**

Transfer is a Claude Code plugin-only operation. It depends on Claude session JSONL files under
`~/.claude/projects`, which only exist in the Claude Code runtime.

Safe fallback: tell the user to copy the relevant context summary into a new Codex task prompt, or
install the `openai/codex-plugin-cc` plugin to use transfer.

---

## Outputs

| Operation          | Output                                                               |
| ------------------ | -------------------------------------------------------------------- |
| Setup              | Installation/auth report; guidance to run `codex login` if needed    |
| Review             | Codex output verbatim; no fixes applied                              |
| Adversarial review | Codex output verbatim; no fixes applied                              |
| Rescue             | Codex task output verbatim                                           |
| Status             | Markdown table (no job ID) or full output (with job ID); plugin only |
| Result             | Full stored result verbatim; plugin only                             |
| Cancel             | Cancellation confirmation; plugin only                               |
| Transfer           | Session ID and `codex resume <session-id>` command; plugin only      |
