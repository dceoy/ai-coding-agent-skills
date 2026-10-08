#!/usr/bin/env bash
#
# Review the authenticated user's open pull requests with Oracle + ChatGPT.
# Oracle --no-wait detaches a Pro browser session and returns after dispatch.
# Requires browser access to GPT-6 Pro; exit 0 does not confirm reviews were posted.
#
# Usage:
#   oracle-pr-sweep.sh [--debug] [--max-count=<int>]
#   oracle-pr-sweep.sh [MAX_COUNT]
#   oracle-pr-sweep.sh -h|--help
#
# Options:
#   --debug             Enable shell tracing
#   --max-count=<int>   Review at most this many PRs (default: 20, range: 1-50)
#   -h, --help          Print this help text and exit
#
# Arguments:
#   MAX_COUNT           Backward-compatible positional form of --max-count

set -euo pipefail

if (( $# > 0 )); then
  for arg in "$@"; do
    [[ "$arg" == '--debug' ]] && set -x && break
  done
fi

readonly COMMAND_NAME="${0##*/}"
readonly DEFAULT_MAX_COUNT=20
readonly MAX_ALLOWED_COUNT=50
readonly MIN_ORACLE_MINOR=20
readonly MIN_ORACLE_PATCH=1

max_count="$DEFAULT_MAX_COUNT"
max_count_set=0

print_usage() {
  sed -ne '1,2d; /^#/!q; s/^#$/# /; s/^# //p' "${BASH_SOURCE[0]}"
}

abort() {
  printf '%s: %s\n' "$COMMAND_NAME" "$*" >&2
  exit 1
}

usage_error() {
  printf '%s: %s\n\n' "$COMMAND_NAME" "$*" >&2
  print_usage >&2
  exit 2
}

set_max_count() {
  (( max_count_set == 0 )) || usage_error 'MAX_COUNT may be specified only once'
  max_count="$1"
  max_count_set=1
}

parse_args() {
  while (( $# > 0 )); do
    case "$1" in
      --debug)
        shift
        ;;
      --max-count)
        (( $# >= 2 )) || usage_error 'option --max-count requires an argument'
        set_max_count "$2"
        shift 2
        ;;
      --max-count=*)
        set_max_count "${1#*=}"
        shift
        ;;
      -h|--help)
        print_usage
        exit 0
        ;;
      --)
        shift
        while (( $# > 0 )); do
          set_max_count "$1"
          shift
        done
        ;;
      -*)
        usage_error "invalid option: $1"
        ;;
      *)
        set_max_count "$1"
        shift
        ;;
    esac
  done
}

validate_max_count() {
  [[ "$max_count" =~ ^[0-9]+$ ]] \
    || usage_error "MAX_COUNT must be an integer from 1 through $MAX_ALLOWED_COUNT"
  max_count=$((10#$max_count))
  (( max_count >= 1 && max_count <= MAX_ALLOWED_COUNT )) \
    || usage_error "MAX_COUNT must be an integer from 1 through $MAX_ALLOWED_COUNT"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || abort "$1 is not available in PATH"
}

check_prerequisites() {
  local oracle_major oracle_minor oracle_patch oracle_version_output

  require_command oracle

  if ! oracle_version_output="$(oracle --version 2>&1)"; then
    printf '%s\n' "$oracle_version_output" >&2
    exit 1
  fi
  [[ "$oracle_version_output" =~ ([0-9]+)\.([0-9]+)\.([0-9]+) ]] \
    || abort "could not parse Oracle version from: $oracle_version_output"
  oracle_major=$((10#${BASH_REMATCH[1]}))
  oracle_minor=$((10#${BASH_REMATCH[2]}))
  oracle_patch=$((10#${BASH_REMATCH[3]}))
  if (( oracle_major == 0 && (
    oracle_minor < MIN_ORACLE_MINOR ||
    (oracle_minor == MIN_ORACLE_MINOR && oracle_patch < MIN_ORACLE_PATCH)
  ) )); then
    abort "Oracle 0.$MIN_ORACLE_MINOR.$MIN_ORACLE_PATCH or newer is required; found $oracle_version_output"
  fi

  oracle bridge doctor >&2
}

run_sweep() {
  oracle \
    --no-wait \
    --engine browser \
    --model gpt-6-pro \
    -p - <<EOF_PROMPT
# Account PR sweep
@GitHub Determine the authenticated GitHub user from the connected GitHub app. Review at most $max_count open, non-draft pull requests in non-archived repositories owned exactly by that user, ordered by most recently updated first. Exclude organization-owned and collaborator repositories.

For each selected PR, inspect the current diff, relevant repository context, CI/check status, existing reviews, and unresolved review feedback. Report only concrete correctness, regression, maintainability, security, or dependency/update risks; apply KISS, DRY, and YAGNI, and omit style-only findings. Classify findings as blocking, should-fix, or optional.

Before posting, re-read the PR head. Skip stale PRs whose head changed. For every current PR, post exactly one COMMENT review directly to that PR through GitHub. Include the reviewed head SHA in the top-level review body. Put actionable findings in inline review comments when they can be safely anchored to changed lines; keep unanchorable findings in the top-level body. If there are no actionable findings, say so in the top-level body. Do not modify GitHub state other than posting the requested COMMENT reviews.

After attempting all reviews, return a concise Markdown summary of which PRs were reviewed, posted, stale, blocked, or failed. If GitHub write access is unavailable, do not claim publication succeeded; report the affected PRs as failed and include the permission limitation. Stale or blocked PRs alone do not make the result failed.
EOF_PROMPT
}

main() {
  parse_args "$@"
  validate_max_count
  check_prerequisites
  run_sweep
}

main "$@"
