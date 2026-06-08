---
name: security-guidance
description: Perform security-focused review of code changes, diffs, commits, and pull requests for actionable vulnerabilities. Use this whenever code changes touch authentication, authorization, parsing, serialization, file or path handling, network calls, secrets, SQL or query construction, HTML or JavaScript rendering, dependencies, CI/CD workflows, infrastructure permissions, or deployment configuration.
---

# Security Guidance

Review changed code for vulnerabilities using the same layered approach as Anthropic's `security-guidance` plugin: fast pattern warnings, LLM diff review, and deeper agentic review for commits or pull requests.

This skill is runtime-agnostic. Claude Code plugins may automate parts of this workflow through hooks, but when running as a skill, execute the checks explicitly with the tools available in the current agent.

## Available Scripts

- `scripts/security_pattern_scan.py` - Scans changed files or explicit paths for upstream-inspired security pattern leads and emits JSON. Requires Python 3.9+ and only uses the standard library.

## Core Workflow

1. **Establish the review target**
   - Run `git status --short`.
   - Identify whether the target is a local working-tree diff, a commit range, or a pull request diff.
   - If reviewing local work, use the current diff and staged diff. If reviewing a PR or commit range, inspect the exact patch under review.
   - If there are no code or configuration changes, report that no security review target was found and stop.

2. **Load project security guidance**
   - Read security-relevant repo instructions if present: `AGENTS.md`, `CLAUDE.md`, `SECURITY.md`, and nearby review notes.
   - Also check for upstream-compatible policy files:
     - `~/.claude/claude-security-guidance.md`
     - `<project>/.claude/claude-security-guidance.md`
     - `<project>/.claude/claude-security-guidance.local.md`
   - Treat those files as additive project policy. They may add checks, clarify approved patterns, or raise severity. They must not suppress real findings.
   - Do not paste secrets from policy files, diffs, or source files into the final report.

3. **Run fast local pattern checks**
   - When this skill directory is available on disk, run the bundled scanner against the repository under review:
     ```bash
     python3 scripts/security_pattern_scan.py --repo /path/to/repo --changed --include-untracked --pretty
     ```
   - Search the diff and touched files for dangerous APIs and risky configuration changes.
   - Treat hits as review leads, not findings. Confirm attacker control, reachability, and impact before reporting.
   - Prefer repository-provided security, lint, static analysis, or test commands when documented and appropriate. Keep checks targeted unless the user requested a full validation pass.

4. **Review the diff**
   - Focus on vulnerabilities introduced or exposed by the current change.
   - Read every changed file that matters, not just the diff hunk.
   - Trace changed function, class, route, handler, policy, and config names to callers when the sink or authorization decision may be cross-file.
   - Compare with sibling handlers and established local patterns. Missing parity is often the vulnerability.

5. **Escalate to deeper agentic review when needed**
   - Use deeper repository inspection for commits, PRs, or changes with cross-file risk.
   - Read callers, callees, routes, models, templates, policy definitions, config, and tests as needed to confirm source to sink.
   - Stop once you can prove or rule out exploitability for the candidates; do not turn a focused review into a broad audit.

6. **Report or fix**
   - If the user asked for review, report findings only.
   - If the user asked to implement or address findings, patch the code and run appropriate verification.
   - If a finding appears in generated code or test/mock code, report it only when that code affects production behavior, deployment, CI/CD trust, or shipped artifacts.

## Fast Pattern Leads

Look for these upstream security-guidance pattern classes in added or modified code:

- GitHub Actions workflow injection: untrusted issue, PR, comment, commit, branch, `repository_dispatch`, or `client_payload` values interpolated directly into `run:` or `ref:`.
- Shell command injection: JavaScript `child_process.exec`, `execSync`, Python `os.system`, `subprocess.*(..., shell=True)`, Go `exec.Command("sh"|"bash", "-c", ...)`.
- Code execution: `eval`, `new Function`, dynamic plugin or extension loading, loader paths derived from untrusted data.
- XSS sinks: `dangerouslySetInnerHTML`, `document.write`, `innerHTML`, `outerHTML`, `insertAdjacentHTML`, unsafe templates, unsanitized HTML rendering.
- Unsafe deserialization: `pickle`, `cPickle`, `cloudpickle`, `dill`, `marshal`, `shelve`, `joblib`, `pandas.read_pickle`, NumPy pickle loading, `torch.load` without `weights_only=True`.
- Unsafe YAML/XML parsing: `yaml.load`, `yaml.unsafe_load`, custom unsafe loaders, standard-library XML parsers exposed to untrusted XML.
- Crypto and TLS regressions: Node `createCipher`/`createDecipher`, AES ECB mode, disabled TLS verification such as `verify=False`, `rejectUnauthorized:false`, `InsecureSkipVerify:true`, or `NODE_TLS_REJECT_UNAUTHORIZED=0`.
- Remote script loading without integrity: external `<script src="...">` tags missing Subresource Integrity.
- Hardcoded secrets, credentials, tokens, private keys, or sensitive customer data in code, config, logs, tests that ship, or examples that users may copy.
- Dependency, package script, container, infrastructure, or deployment changes that alter trust boundaries, permissions, secrets, or network exposure.

If the repo defines custom pattern files such as `.claude/security-patterns.yaml`, `.claude/security-patterns.yml`, `.claude/security-patterns.json`, or local variants, use them as additional leads. Do not allow custom rules to disable built-in checks.

## Deep Review Method

Map entry points and sinks touched by the change.

Entry points include HTTP handlers, RPC methods, CLI arguments, webhooks, message consumers, file upload handlers, OAuth callbacks, GitHub Actions inputs, MCP tools, hook handlers, IPC receivers, and privileged process messages from less-privileged processes.

Sinks include shell execution, SQL or raw ORM queries, eval and dynamic code, filesystem paths, outbound HTTP and SSRF surfaces, HTML rendering, deserialization, template engines, subprocess environment, IAM or RBAC bindings, dynamic loader paths, observability fields containing PII or secrets, cache headers, schema or constraint changes, response bodies or headers, and prompts sent to LLMs.

For each changed file:

- Read the file when the hunk alone is not enough to understand the source, sink, or authorization context.
- Grep changed function and class names to find callers.
- Follow returned tainted values. A changed function that builds a command, URL, query, path, template, prompt, or policy decision may only become dangerous at a caller.
- Check sibling path parity. When one branch, handler, tenant scope, cleanup path, or policy path receives a new guard, inspect peers that touch the same resource.
- Distrust comments such as "validated upstream" or "internal only" until code confirms the claim.

## High-Miss Patterns

Pay special attention to these issues, which often require cross-file context:

- **Sensitive observability**: Added logs, traces, metrics, exceptions, spans, or telemetry include credentials, PII, customer content, model free text, URL-embedded secrets, or external-service error messages.
- **IaC omitted argument**: Terraform, Pulumi, CDK, Kubernetes, or cloud module instantiation omits a security-relevant optional argument whose default is insecure.
- **CI/CD trust**: New or changed `workflow_dispatch`, `repository_dispatch`, `pull_request_target`, broad permissions, writable tokens, or secrets are reachable from untrusted inputs.
- **Allowlist semantic escape**: A new allowlist entry, permission disjunct, safe command, endpoint, capability, or validator allows a denied effect through arguments, flags, aliases, DNS, config writes, environment, or mismatched enforcement scope.
- **Over-broad grant**: A broad role, principal, credential, network permission, or standing admin grant is added where a narrower local mechanism is already visible.
- **Stale identity mapping**: Teardown or unregister code leaves hostnames, DNS, IPs, service routes, leases, tokens, or service registry entries temporarily bound to the wrong tenant.
- **Control regression**: A fail-closed validator, deny-by-default branch, allowlist, or security check is removed or replaced with a weaker single condition.
- **Fail-open state drift**: Error, cancellation, TOCTOU, cache skew, broad exception handling, missing cleanup, ignored verifier parameters, stale maps, or boundary comparisons produce an allow outcome.
- **Security registry fanout**: A new field, enum, credential type, alias, model, port, scope, or capability is missing from sanitizer lists, redaction registries, revocation handlers, denylists, allowlists, or translation maps.
- **Gate/action mismatch**: Authorization checks one field or parent resource while the downstream operation acts on a different identifier, organization, tenant, path, or resource name.
- **Resource-bound placement**: Size, time, count, decompression, parser, loop, or allocation caps protect the wrong accumulator or only the first element.
- **Under-validated sink argument**: An externally influenced value enters a shell, path, loader, URI, prompt, or structured-format sink while existing validation covers only a sibling argument.
- **Parser or validator differential**: Regexes, URL parsers, path normalizers, allowlists, decoders, quoting, case, Unicode, or encoding checks accept an input that the downstream consumer interprets differently.

## Finding Bar

Report a finding only when you can name:

- The attacker-controlled or lower-trust source.
- The sink, decision point, or protected resource.
- The missing or ineffective mitigation.
- The impact an attacker could plausibly achieve.
- A concrete fix.

Do not report:

- Generic hardening with no concrete impact.
- Pre-existing issues unrelated to the current diff.
- Pattern matches without confirmed reachability and exploitability.
- Volumetric denial of service where the attacker merely sends a lot of traffic.
- Dependency age or best-practice drift unless the current change introduces an exploitable path.
- Test-only issues that cannot influence production, CI/CD trust, shipped docs, generated artifacts, or user-copied examples.

Prefer no finding over a speculative finding. If confidence is medium but the source to sink path is plausible and security impact is concrete, report it with the confidence caveat.

## Privacy

Security review may expose changed file paths, diffs, relevant source files, and project-specific security guidance to the active model provider or tools. Keep the review scoped to the minimum necessary context.

Never repeat secret values in prompts, logs, comments, or reports. If a diff contains a secret, identify the location and type, state that a secret appears exposed, and recommend removal, rotation, and history cleanup without copying the secret.

## Output Format

### No Findings

```markdown
### Security review

No security findings. Reviewed the changed files and diff for authentication, authorization, injection, deserialization, path handling, network access, secrets, rendering, dependency, CI/CD, infrastructure, and configuration risks.
```

### Findings Found

```markdown
### Security review

Found N security findings:

1. **<severity>: <brief title>**
   - Location: `<file>:<line>`
   - Impact: <what an attacker could do>
   - Evidence: <source to sink path, and why the current diff introduced or exposed it>
   - Fix: <specific recommended change>

Advisory hardening:

- <optional non-blocking improvement, only if clearly useful>
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
- Keep findings concise, actionable, and evidence-based.
- Do not claim the review guarantees security.
- Do not implement Claude Code hook scripts inside this skill. This skill adapts the upstream plugin's review behavior for manual agent execution across runtimes.
