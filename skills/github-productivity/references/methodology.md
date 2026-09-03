# Methodology: Collection

This document covers only what is implemented so far: repository/PR/review/timeline/commit **collection**. Normalization, the organization-week panel, statistical analysis, and reporting are follow-up work and are not described here.

## GitHub API contract

- Every REST call goes through `gh api`, the only HTTP client this skill uses.
- Every call pins `X-GitHub-Api-Version: 2026-03-10` and records that version in the run manifest. GitHub's unversioned default behavior is never relied on for reproducibility.
- Pagination is always explicit (`page`, `per_page`); `gh api --paginate` is never used, because this skill retains per-page provenance (endpoint, repository ID, page number, non-secret parameters, API version, run ID) that a merged multi-page response would destroy.
- Request provenance is scrubbed before it is ever persisted: any key or embedded value that looks credential-shaped (`authorization`, `token`, `password`, `secret`, `cookie`, case-insensitive) is redacted. `Authorization` headers and `GH_TOKEN`/credential-bearing environment values are never constructed by this skill in the first place — `gh` supplies its own authentication.

## Transaction model

- `collect` is single-writer per workdir. It acquires an exclusive lock (`<workdir>/.collect.lock`) before reading committed state, and holds it through discovery, canonical bundle refetches, manifest finalization, and the atomic `state.json` commit. A second concurrent `collect` invocation fails closed (exit code `3`) before performing any live collection.
- Every collection attempt gets a run ID and an append-only raw evidence directory (`raw/<run-id>/`). Raw endpoint responses are only ever appended, never rewritten.
- A run's manifest (`manifests/<run-id>.json`) is finalized **exactly once**, with `status` either `"complete"` or `"incomplete"`. A finalized manifest is never rewritten.
- `state.json`'s `committed_run_id` — not `manifest.status == "complete"` — is the acceptance frontier. A `complete` manifest is only committed after `state.json` is atomically replaced to point at it. A manifest that is `complete` but not reachable by walking `committed_run_id` → `previous_committed_run_id` → … is **uncommitted orphan evidence**: it may be inspected for freshness diagnostics, but it must never be treated as canonical.
- If the process crashes after a manifest is finalized as `complete` but before `state.json` is replaced, that run is left orphaned. The next `collect` run starts from the still-committed prior state (or no state, if none was ever committed) and repeats the required overlap/backfill — it does not implicitly adopt the orphan.
- A run is marked `incomplete` if any endpoint call fails anywhere in that run (repository enumeration, discovery, reconciliation, or any PR's canonical bundle refetch). An incomplete run's watermarks are not advanced and `state.json` is left byte-identical; the failure is recorded in the manifest's `failures` list.

## Per-repository state

`state.json` keys per-repository entries by the stable numeric **repository ID**, never by name, so a rename updates the existing entry's `name` field rather than creating a duplicate. Each entry tracks:

- `discovery_watermark` — set to the run's `refresh_started_at`, **never** to the largest observed `updated_at` (pagination order is not a substitute for a fixed point-in-time cutoff);
- `history_boundary` — the earliest point continuously covered by backfill so far, only ever extended further into the past;
- `last_seen_in_enumeration_at` — when the repository was last visible in organization enumeration.

A repository that later disappears from enumeration keeps its previously retained state entry; evidence is preserved rather than discarded. Archived repositories are enumerated and collected the same as active ones. Forks are always enumerated and retained in raw collection data — exclusion from a primary delivery cohort is a derivation-time decision, deferred to the follow-up normalization work.

## Discovery and reconciliation

A repository needing initial coverage, or whose committed `history_boundary` does not reach far enough back for a newly requested `--start` (minus overlap), goes through **backfill**: the Pulls endpoint with explicit `state=all&sort=updated&direction=desc`, paged newest-first, stopping once an item's `updated_at` is older than the required boundary.

A repository with sufficient existing coverage goes through **incremental discovery** instead: the Issues endpoint with `state=all&since=<watermark - overlap>&sort=created&direction=asc`, filtered to items carrying a `pull_request` key (GitHub's issues listing includes PRs, distinguished this way).

Either path is always followed by a **reconciliation pass**: the Issues endpoint again, with `since=<refresh_started_at - overlap>&sort=updated&direction=asc`, to catch PRs updated while the primary scan was still paging. Touched PR identities from both passes are unioned by `(repository_id, number)`.

Every touched PR gets its canonical snapshot bundle refetched in the same run: the PR object, its formal reviews, its commits, and its issue timeline — all fetched fresh and appended to that run's raw evidence. (Bundle _selection_ across runs — choosing the newest eligible bundle and replacing rather than unioning child rows — is normalization work, deferred to the follow-up PR.)

## Observation-range semantics

The requested observation interval is half-open UTC `[start, end)`; `end <= start` is rejected. A date-only CLI value (`YYYY-MM-DD`) converts deterministically to UTC midnight (`YYYY-MM-DDT00:00:00Z`); any other value must carry an explicit UTC offset.

`start` (minus overlap) is the only bound `collect` actually enforces against live discovery — it is the backfill boundary described above. `end` is validated and recorded verbatim as `requested_interval.end` in the run manifest, but `collect` does not stop discovery or bundle refetching at it: every run discovers and reconciles through its own `refresh_started_at` regardless of the requested `end`, because collection is meant to retain broad raw evidence once, not to be re-run every time an analysis window's end date changes. The half-open `[start, end)` convention governs **event inclusion at derivation time** (`effective_observation_end = min(requested_end, committed_refresh_started_at)`, per the issue this skill implements) — that filtering step is not yet implemented (it lands with normalization). Do not read `requested_interval.end` in a manifest as "no evidence after this timestamp was collected"; it only means "no evidence after this timestamp is in scope for analysis once derivation exists."

## Known limitations

- Repository ownership-history transfers are not reconstructed. A repository transferred into the organization can expose PR history predating the transfer; a repository transferred out or deleted can disappear from enumeration entirely. The core repository/PR endpoints cannot reliably reconstruct historical transfer dates, so this skill never guesses historical organization membership — it only reports what current enumeration and retained evidence show.
- `--overlap-hours` and repository-cohort choices such as fork inclusion are not yet exposed as full derivation-time sensitivities; that lands with normalization.
- No merge-on-write or per-repository concurrent collectors: v1 collection is strictly single-writer per workdir.
- No automatic stale-lock recovery in v1. Each individual `gh api` call is bounded (120s), so a single wedged call cannot hang a run forever — but that bound is per call, not per run: a run touching many PRs still runs those bounded calls serially, so a wedged endpoint can still make one run take a long time to report `incomplete`. If the `collect` process itself is killed (SIGKILL, host loss) while holding the lock, `<workdir>/.collect.lock` is left in place and every subsequent `collect` fails closed (exit code `3`) until an operator manually removes that file. Manual removal is safe only once the holding process is confirmed dead — the lock file's `pid` and `run_id` fields identify which run to check — since nothing prevents a still-alive holder and a newly started run from both committing if the lock is cleared while the original process is merely slow rather than actually gone (last writer wins). Once the holder truly is dead, removal is safe because no run can be committed without holding the lock through the full transaction: whatever the killed run had done, the next run repeats the required overlap/backfill from the last actually committed state.
- A workdir is scoped to one organization. Reusing the same `--workdir` for a different `--org` is rejected before any live collection (`OrganizationMismatchError`, exit code `2`), even before the workdir's first successful commit — the check looks at every manifest that exists, complete or incomplete, not only committed `state.json`. Comparison is case-insensitive, matching GitHub's own organization-login semantics. Use a separate workdir per organization.
