---
name: codex
description: Use OpenAI Codex from Claude Code to review code or delegate coding tasks. Use when the user wants a Codex code review, adversarial review, task delegation, session transfer, or job management (status, result, cancel).
allowed-tools: AskUserQuestion, Bash(codex:*), Bash(node:*), Bash(which:*), Bash(npm:*), Bash(git diff:*), Bash(git status:*), Bash(git log:*), Bash(git branch:*), Read, Grep, Glob
---

# Codex Skill

Use OpenAI Codex from Claude Code to run code reviews, adversarial reviews, and delegate investigation or implementation tasks to Codex.

Source: [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc)

## When to Use

- **Review**: Run a read-only Codex review of current uncommitted changes or a branch diff.
- **Adversarial review**: Challenge implementation choices, design tradeoffs, and hidden assumptions.
- **Rescue / delegate**: Hand off a bug investigation, fix, or implementation task to Codex.
- **Setup**: Check whether Codex is installed and authenticated; manage the stop-gate review.
- **Job management**: Check status, retrieve results, or cancel a background Codex job.
- **Transfer**: Continue the current Claude Code session inside a Codex thread.

## Agent Compatibility

This skill runs in Claude Code. Full functionality requires the `openai/codex-plugin-cc` plugin installed
via `/plugin install codex@openai-codex`. When the plugin is active, `CLAUDE_PLUGIN_ROOT` is set and all
operations go through the companion script. Without the plugin, setup and basic review are available via
the standalone `codex` CLI.

## Inputs

- The user's stated intent: which operation and any arguments (`--base main`, `--background`, task text).
- Current repository state (git status, diff).

## Pre-flight: Availability Check

Before running any operation, verify Codex is ready.

### Plugin context (preferred)

When `CLAUDE_PLUGIN_ROOT` is set, run:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" setup --json
```

If the result shows Codex is unavailable and npm is present, offer to install it. If Codex is installed
but not authenticated, tell the user to run `!codex login`.

### Standalone context

When `CLAUDE_PLUGIN_ROOT` is not set, check for the `codex` binary:

```bash
codex --version
```

### If neither is available

Tell the user how to get started:

```
Codex CLI is not installed. Options:

Install the full codex plugin for Claude Code (recommended):
  /plugin marketplace add openai/codex-plugin-cc
  /plugin install codex@openai-codex
  /reload-plugins
  /codex:setup

Or install the standalone Codex CLI only:
  npm install -g @openai/codex
  !codex login
```

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

---

## Review

Run a read-only Codex review of current changes.

**Arguments:**

| Flag           | Meaning                                                              |
| -------------- | -------------------------------------------------------------------- |
| `--base <ref>` | Review branch diff against a base branch instead of the working tree |
| `--wait`       | Run in the foreground without asking                                 |
| `--background` | Run in a background task without asking                              |

**Execution mode** (when neither `--wait` nor `--background` is given):

1. Estimate review size:
   - Working tree: `git status --short --untracked-files=all` + `git diff --shortstat` + `git diff --shortstat --cached`
   - Branch diff: `git diff --shortstat <base>...HEAD`
   - Untracked files and directories count as reviewable work even when `git diff --shortstat` is empty.
2. If clearly tiny (roughly 1–2 files, no broader directory-sized change): recommend foreground.
3. In every other case, including unclear size: recommend background.
4. Use `AskUserQuestion` exactly once with two options, leading with the recommended choice (append
   `(Recommended)` to its label):
   - `Wait for results`
   - `Run in background`

**Plugin context — foreground:**

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" review "$ARGUMENTS"
```

**Plugin context — background** (`run_in_background: true`):

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" review "$ARGUMENTS"
```

**Standalone context:**

```bash
codex review [--base <ref>]
```

**Rules:**

- Return output verbatim. Do not paraphrase, summarize, or add commentary.
- This command is **read-only**. Do not fix issues, apply patches, or suggest you are about to make changes.
- After presenting findings, stop and explicitly ask the user which issues, if any, they want fixed.

---

## Adversarial Review

Run a steerable review that challenges whether the current approach is right — not just whether the
implementation is correct. It questions design choices, tradeoffs, hidden assumptions, and failure modes.

**Arguments:** Same as review, plus optional free-form focus text after the flags.

**Execution mode selection:** Same logic as review.

**Plugin context — foreground:**

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" adversarial-review "$ARGUMENTS"
```

**Plugin context — background** (`run_in_background: true`):

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" adversarial-review "$ARGUMENTS"
```

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
| `--background`     | Run in a background task                                              |
| `--wait`           | Run in the foreground                                                 |
| `--resume`         | Continue the latest Codex thread for this repo                        |
| `--fresh`          | Start a new Codex thread                                              |
| `--model <model>`  | Specify model; `spark` maps to `gpt-5.3-codex-spark`                  |
| `--effort <level>` | Reasoning effort: `none \| minimal \| low \| medium \| high \| xhigh` |
| Remaining text     | Task description forwarded to Codex                                   |

**Thread continuity** (when neither `--resume` nor `--fresh` is given):

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
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" task [--resume-last] [--write] [--model <model>] [--effort <level>] "<task description>"
```

- Default to `--write` unless the user explicitly asks for read-only behavior (diagnosis, research, review
  without edits).
- Map `--resume` → `--resume-last`; strip `--fresh` (no flag needed).
- Strip `--background` and `--wait` before building the `task` command — those are Claude-side execution
  controls, not Codex flags.
- Leave `--model` and `--effort` unset unless the user specified them.

**Standalone context:**

```bash
codex "<task description>"
```

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

---

## Cancel

Cancel an active background Codex job.

**Plugin context:**

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" cancel [job-id]
```

Present the cancellation confirmation to the user.

---

## Transfer

Create a persistent Codex thread from the current Claude Code session and print a `codex resume` command.

Use when you started debugging or implementing in Claude Code and want to continue that same context
inside Codex.

**Plugin context:**

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" transfer [--source <claude-jsonl>]
```

Present the output exactly as returned, preserving the Codex session ID and the
`codex resume <session-id>` command.

The `SessionStart` hook supplies the current transcript path automatically; `--source` is available as a
manual override. The source must be under `~/.claude/projects`.

---

## Outputs

| Operation          | Output                                                             |
| ------------------ | ------------------------------------------------------------------ |
| Setup              | Installation/auth report; guidance to run `!codex login` if needed |
| Review             | Codex output verbatim; no fixes applied                            |
| Adversarial review | Codex output verbatim; no fixes applied                            |
| Rescue             | Codex task output verbatim                                         |
| Status             | Markdown table (no job ID) or full output (with job ID)            |
| Result             | Full stored result verbatim                                        |
| Cancel             | Cancellation confirmation                                          |
| Transfer           | Session ID and `codex resume <session-id>` command                 |
