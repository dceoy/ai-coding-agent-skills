Run an autonomous pull request review modeled on Anthropic Claude Code Action's `/review-pr`, its reviewer agents, and Anthropic's `pr-review-toolkit`.

This routine is review-only: do not modify repository source files, push unrelated commits, merge branches, approve PRs, or request changes unless explicitly instructed. Only environment preparation, such as configuring Git identity or installing required CLI tools, is allowed.

## Required detail file

Before reviewing, read `routines/pr-review/details.md` and treat it as part of this routine's normative instructions.

`details.md` preserves the full review coverage, setup procedure, aspect-token handling, instruction-source safety guard, reviewer-pass checklists, final arbitration policy, posting strategy, severity thresholds, and output templates.

## Execution summary

1. Apply the compatibility and runtime constraints in `details.md`.
2. Prepare the environment, resolve PR or local-diff mode, and parse aspect tokens.
3. Run selected reviewer passes independently and keep candidate findings internal.
4. Deduplicate, filter, rank, and post or return only the final arbitrated result.

If `routines/pr-review/details.md` is unavailable, stop and report that the routine is incomplete rather than improvising missing policy.
