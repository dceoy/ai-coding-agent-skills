# Claude Code routing

- Delegate well-scoped, low-risk repository work to built-in subagents using Haiku (`model: haiku`): use `Explore` for read-only repository exploration and code search, and `general-purpose` for routine implementation, mechanical refactoring, focused debugging, testing, linting, formatting, and verification.
- Keep architecture, planning, ambiguous decisions, security-sensitive or high-risk trade-offs, difficult cross-cutting debugging, and final validation in the main agent.
- Delegate implementation only when decisions are settled. If a subagent reports a material decision or blocker, resolve it in the main agent before delegating again.
