#!/usr/bin/env bash
#
# Review the authenticated user's open pull requests with Oracle + ChatGPT.
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
readonly MIN_ORACLE_MINOR=18
readonly -a RETRY_DELAYS=(1 2 4 8 16 30 30 30 30 30)

max_count="$DEFAULT_MAX_COUNT"
max_count_set=0
out_file=''
err_file=''

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
  local oracle_major oracle_minor oracle_version_output

  require_command oracle

  if ! oracle_version_output="$(oracle --version 2>&1)"; then
    printf '%s\n' "$oracle_version_output" >&2
    exit 1
  fi
  [[ "$oracle_version_output" =~ ([0-9]+)\.([0-9]+)\.([0-9]+) ]] \
    || abort "could not parse Oracle version from: $oracle_version_output"
  oracle_major="${BASH_REMATCH[1]}"
  oracle_minor="${BASH_REMATCH[2]}"
  if (( oracle_major == 0 && oracle_minor < MIN_ORACLE_MINOR )); then
    abort "Oracle 0.$MIN_ORACLE_MINOR.0 or newer is required; found $oracle_version_output"
  fi

  oracle bridge doctor >&2
}

create_temp_files() {
  out_file="$(mktemp)"
  err_file="$(mktemp)"
}

cleanup() {
  [[ -z "$out_file" ]] || rm -f -- "$out_file"
  [[ -z "$err_file" ]] || rm -f -- "$err_file"
}

run_sweep() {
  oracle \
    --wait \
    --heartbeat 15 \
    --engine browser \
    --model gpt-5.6-sol \
    --browser-thinking-time high \
    -p - >"$out_file" 2>"$err_file" <<EOF_PROMPT
# Account PR sweep
@GitHub Determine the authenticated GitHub user from the connected GitHub app. Review at most $max_count open, non-draft pull requests in non-archived repositories owned exactly by that user, ordered by most recently updated first. Exclude organization-owned and collaborator repositories.

For each selected PR, inspect the current diff, relevant repository context, CI/check status, existing reviews, and unresolved review feedback. Report only concrete correctness, regression, maintainability, security, or dependency/update risks; apply KISS, DRY, and YAGNI, and omit style-only findings. Classify findings as blocking, should-fix, or optional, and explicitly note PRs with no actionable findings or unavailable required context.

Before finalizing, re-read each reviewed PR head and mark it stale if the SHA changed. Do not modify GitHub state. Return only a concise consolidated Markdown report.
EOF_PROMPT
}

run_with_retries() {
  local exit_code last_stderr last_stdout_error retry_index=0

  while :; do
    : >"$out_file"
    : >"$err_file"

    if run_sweep; then
      cat -- "$out_file"
      [[ ! -s "$err_file" ]] || cat -- "$err_file" >&2
      return 0
    else
      exit_code=$?
    fi

    last_stderr="$(awk 'NF { line = $0 } END { print line }' "$err_file")"
    last_stdout_error="$(awk '/^ERROR:/ { line = $0 } END { print line }' "$out_file")"

    if [[ "$last_stderr" == '✖ read ETIMEDOUT' || "$last_stdout_error" == 'ERROR: read ETIMEDOUT' ]]; then
      cat -- "$out_file"
      cat -- "$err_file" >&2
      return "$exit_code"
    fi

    if [[ "$last_stderr" == '✖ busy' || "$last_stdout_error" == 'ERROR: busy' ]]; then
      if (( retry_index < ${#RETRY_DELAYS[@]} )); then
        sleep "${RETRY_DELAYS[$retry_index]}"
        ((retry_index += 1))
        continue
      fi
    fi

    cat -- "$out_file"
    cat -- "$err_file" >&2
    return "$exit_code"
  done
}

main() {
  parse_args "$@"
  validate_max_count
  check_prerequisites
  create_temp_files
  trap cleanup EXIT

  run_with_retries
}

main "$@"
