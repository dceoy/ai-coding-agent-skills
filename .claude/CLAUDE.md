# Claude Code routing

- Prefer `haiker` for repository exploration, code search, routine implementation, mechanical refactoring, focused debugging, testing, linting, formatting, and other well-scoped repository work that Haiku can handle reliably.
- Prefer `haiker` over the built-in `Explore` agent for repository exploration so search and codebase reconnaissance stay on Haiku when practical.
- Keep architecture, planning, ambiguous decisions, security-sensitive or high-risk trade-offs, difficult cross-cutting debugging, and final validation in the main agent.
- Delegate only decision-complete implementation work. If `haiker` reports a material decision or blocker, resolve it in the main agent before delegating again.
- Do not delegate a task merely to reduce cost when it materially benefits from the main model's stronger reasoning.
