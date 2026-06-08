---
name: security-guidance
description: Perform security-focused review of code changes, diffs, commits, and pull requests for actionable vulnerabilities.
---

# Security Guidance Skill

Review changed code for security issues using fast local checks, focused LLM diff review, and deeper commit or PR review when needed.

## When to Use

- After security-sensitive edits.
- Before committing or pushing code.
- Before completing a pull request.
- When reviewing authentication, authorization, deserialization, file or path handling, network calls, secrets, SQL or query construction, HTML or JavaScript rendering, or dependency and configuration changes.

## Agent Compatibility

This skill is tool-agnostic and can be executed by Claude Code, OpenAI Codex CLI, GitHub Copilot CLI, Gemini CLI, or similar coding agents.

Run it at equivalent agent checkpoints:

- After file edits that touch security-sensitive code.
- Before the final response for a coding task.
- Before creating a commit.
- Before pushing a branch.
- Before marking a pull request complete.

Do not depend on vendor-specific hooks such as `SessionStart`, `UserPromptSubmit`, `PostToolUse`, or `Stop`.

## Inputs

- Current repository and changed files.
- Local diff, commit range, or pull request diff.
- Project security guidance such as AGENTS.md, CLAUDE.md, SECURITY.md, or team-specific review notes when present.

If there are no code changes, report that no security review target was found and stop.

## Review Layers

1. **Fast local pattern checks**: Run local or static checks where available to catch dangerous APIs and risky edits without sending code to an LLM. Look for patterns such as unsafe deserialization, shell execution, SQL or command construction, raw HTML rendering, path traversal, TLS verification disabling, hardcoded secrets, unsafe crypto, dependency changes, and security-relevant configuration edits.

2. **LLM diff review**: Review the changed files and diff hunks for vulnerabilities introduced by the current change. Focus on exploitability, trust boundaries, attacker-controlled inputs, authorization decisions, secret handling, and output encoding.

3. **Deeper agentic commit or PR review**: When the diff suggests cross-file risk, inspect surrounding files and trace data flow. Use this for issues such as IDOR, auth bypass, SSRF, unsafe file access, confused deputy flows, and policy checks split across multiple modules.

## Workflow

1. **Inspect changes**:
   - Run `git status --short`.
   - Review the local diff, commit range, or pull request diff.
   - Identify added, modified, deleted, and renamed files.

2. **Classify risk**:
   - Mark files that affect authentication, authorization, parsing, serialization, file paths, network access, secrets, rendering, queries, dependencies, or deployment configuration.
   - Note user-controlled inputs and changed trust boundaries.

3. **Run local checks where available**:
   - Use repository-provided security, lint, static analysis, or test commands when they are documented and appropriate for the task.
   - Prefer targeted checks over broad, slow commands unless the user requested a full validation pass.
   - Treat pattern hits as review leads, not findings by themselves.

4. **Review the diff**:
   - Check whether the changed code introduces a plausible vulnerability.
   - Verify data origin, validation, encoding, escaping, authorization checks, and error handling.
   - Compare new behavior with nearby established patterns.

5. **Inspect surrounding code only when needed**:
   - Read related callers, callees, route definitions, models, templates, configuration, and tests only when they affect the security conclusion.
   - Trace data flow far enough to confirm exploitability or rule out a finding.

6. **Report or fix**:
   - Report only actionable, high-confidence findings.
   - Include the affected file and line, impact, why the current diff introduced or exposed the issue, and a concrete fix.
   - If the user requested implementation, patch the code and run appropriate verification.

## False Positive Guidelines

- Do not provide generic security advice.
- Do not report issues that are not introduced or exposed by the current diff unless they directly affect the changed code.
- Do not report a pattern match as a vulnerability without confirming attacker control, reachability, and impact.
- Distinguish blocking vulnerabilities from advisory hardening suggestions.
- Prefer no finding over a speculative finding.

## Privacy and Data Handling

- Local pattern checks do not need to send code to an LLM.
- LLM review may expose diffs, file paths, relevant file contents, and project-specific security guidance to the active model provider.
- Deeper review may expose additional related files inspected while tracing data flow.
- Do not include secrets, tokens, private keys, credentials, or sensitive customer data in prompts, logs, comments, or reports.
- If a diff contains a secret, report it as a secret exposure and avoid repeating the secret value.

## Output Format

### No Findings

```markdown
### Security review

No security findings. Reviewed the changed files and diff for authentication, authorization, injection, deserialization, path handling, network access, secrets, rendering, and dependency/configuration risks.
```

### Findings Found

```markdown
### Security review

Found N security findings:

1. **<severity>: <brief title>**
   - Location: `<file>:<line>`
   - Impact: <what an attacker could do>
   - Evidence: <why the current diff introduces or exposes the issue>
   - Fix: <specific recommended change>

Advisory hardening:

- <optional non-blocking improvement, if clearly useful>
```

### Findings Fixed

```markdown
### Security review

Fixed N security findings:

1. **<brief title>**
   - Changed: <what was patched>
   - Verification: <checks run or reason checks were not run>

Remaining findings: <none or concise list>
```

## Constraints

- Keep the review scoped to the current diff, commit, or pull request.
- Keep findings concise and evidence-based.
- Do not add vendor-specific hook or CLI implementation code.
- Do not claim the review guarantees security; it is an assistive review step.
