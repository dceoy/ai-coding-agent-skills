#!/usr/bin/env python3
"""Scan changed files or explicit paths for security-review pattern leads.

This is a deterministic helper for the security-guidance skill. It reports
leads, not confirmed vulnerabilities. The reviewing agent must still verify
attacker control, reachability, and impact before reporting a finding.
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

JS_EXTS = {
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".mts",
    ".cts",
    ".vue",
    ".svelte",
}
PY_EXTS = {".py", ".pyi", ".ipynb"}
DOC_EXTS = {".md", ".mdx", ".txt", ".rst", ".json", ".yaml", ".yml"}
SECRET_CONFIG_EXTS = frozenset({
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".env",
    ".ini",
    ".conf",
})
SECRET_EXAMPLE_PARTS = ("/examples/", "/example/", "/templates/", "/template/")
SECRET_EXAMPLE_MARKERS = (".example.", ".template.", ".sample.", "-example.")
WORKFLOW_PART = ".github/workflows/"
_REDOS_SHAPES = (
    re.compile(r"\([^()]*[+*][^()]*\)[+*?]"),
    re.compile(r"\(\.\*[^()]*\)[+*]"),
)
_ALT_UNDER_REP = re.compile(r"\(([^()]*)\|([^()|]*)(?:\|[^()]*)*\)[+*]")
CUSTOM_PATTERN_STEMS = (
    "security-patterns",
    "security-patterns.local",
)
CUSTOM_PATTERN_EXTS = (".json", ".yaml", ".yml")
CUSTOM_PATTERN_LIMIT = 50


@dataclass(frozen=True)
class Rule:
    """Security pattern rule used to produce review leads."""

    rule_id: str
    category: str
    summary: str
    regex: str | None = None
    substrings: tuple[str, ...] = ()
    extensions: frozenset[str] | None = None
    path_contains: str | None = None
    path_globs: tuple[str, ...] = ()
    exclude_path_globs: tuple[str, ...] = ()
    source: str = "built-in"


RULES: tuple[Rule, ...] = (
    Rule(
        "github_actions_workflow",
        "ci_cd_trust",
        "GitHub Actions workflow changes can introduce command, ref, permission, "
        "or secret-handling risk.",
        path_contains=WORKFLOW_PART,
    ),
    Rule(
        "js_child_process_exec",
        "command_injection",
        "child_process.exec/execSync runs through a shell; prefer execFile/spawn "
        "with an argument array.",
        regex=r"(?<![A-Za-z0-9_.])exec\(|child_process\.exec|execSync\(",
        extensions=frozenset(JS_EXTS),
    ),
    Rule(
        "new_function",
        "code_injection",
        "new Function executes generated code; never interpolate untrusted strings "
        "into function bodies.",
        substrings=("new Function",),
        extensions=frozenset(JS_EXTS),
    ),
    Rule(
        "eval",
        "code_injection",
        "eval executes arbitrary code; use structured parsers or safe expression "
        "evaluators.",
        regex=r"(?<![A-Za-z0-9_.])eval\(",
        extensions=frozenset({
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".mjs",
            ".cjs",
            ".mts",
            ".cts",
            ".py",
        }),
    ),
    Rule(
        "react_dangerously_set_html",
        "xss",
        "dangerouslySetInnerHTML is an XSS sink unless the HTML is sanitized.",
        substrings=("dangerouslySetInnerHTML",),
        extensions=frozenset(JS_EXTS),
    ),
    Rule(
        "dom_html_sink",
        "xss",
        "DOM HTML assignment is an XSS sink; prefer textContent or sanitize HTML.",
        substrings=(
            "document.write",
            ".innerHTML =",
            ".innerHTML=",
            ".outerHTML =",
            ".outerHTML=",
            ".insertAdjacentHTML(",
        ),
        extensions=frozenset(JS_EXTS),
    ),
    Rule(
        "python_pickle",
        "unsafe_deserialization",
        "Pickle-family loaders can execute code when input is untrusted.",
        regex=r"(?<![A-Za-z0-9_])(?:pickle|cPickle|cloudpickle|dill)\.(?:load|loads)\b|(?<![A-Za-z0-9_])pkl_load\(",
        extensions=frozenset(PY_EXTS),
    ),
    Rule(
        "python_pickle_wrappers",
        "unsafe_deserialization",
        "Common pickle-backed loaders can execute code when input is untrusted.",
        regex=r"\b(?:joblib\.load|pandas\.read_pickle|pd\.read_pickle|shelve\.open|marshal\.load|marshal\.loads)\s*\(",
        extensions=frozenset(PY_EXTS),
    ),
    Rule(
        "torch_load",
        "unsafe_deserialization",
        "torch.load without weights_only=True may unpickle arbitrary Python objects.",
        regex=r"(?:\btorch\.load|\.torch_load)\s*\((?![^)\n]{0,200}weights_only\s*=\s*True)",
        extensions=frozenset(PY_EXTS),
    ),
    Rule(
        "yaml_load",
        "unsafe_deserialization",
        "yaml.load/unsafe_load can construct arbitrary Python objects; prefer "
        "safe_load plus schema validation.",
        regex=r"\byaml\.(?:unsafe_load|load)\s*\((?![^)\n]{0,80}\bSafe)",
    ),
    Rule(
        "xml_stdlib_parse",
        "xxe",
        "Stdlib XML parsers can be unsafe for untrusted XML; prefer defusedxml.",
        regex=r"\b(?:xml\.etree\.ElementTree|ElementTree|ET)\.(?:parse|fromstring|XML)\s*\(|\bminidom\.(?:parse|parseString)\s*\(|\bxml\.sax\.(?:parse|make_parser)\b",
        extensions=frozenset(PY_EXTS),
    ),
    Rule(
        "python_os_system",
        "command_injection",
        "os.system runs a shell; prefer subprocess.run with an argument list.",
        regex=r"\bos\.system\s*\(|from\s+os\s+import\s+system\b",
        extensions=frozenset(PY_EXTS),
    ),
    Rule(
        "python_subprocess_shell",
        "command_injection",
        "subprocess with shell=True enables command injection when arguments are "
        "attacker influenced.",
        regex=r"subprocess\.(?:run|call|Popen|check_output|check_call)\([^;\n]*shell\s*=\s*True",
        extensions=frozenset(PY_EXTS),
    ),
    Rule(
        "go_shell_exec",
        "command_injection",
        "exec.Command with sh/bash -c enables command injection.",
        regex=r'exec\.Command\(\s*"(?:sh|bash|/bin/sh|/bin/bash)"',
        extensions=frozenset({".go"}),
    ),
    Rule(
        "tls_verification_disabled",
        "tls_verification",
        "Disabled TLS verification allows man-in-the-middle attacks.",
        regex=r"\bverify\s*=\s*False\b|rejectUnauthorized\s*:\s*false|InsecureSkipVerify\s*:\s*true|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*['\"]?0|ssl\._create_unverified_context|check_hostname\s*=\s*False",
    ),
    Rule(
        "weak_crypto",
        "cryptography",
        "Weak crypto mode or API detected; prefer authenticated encryption and "
        "modern APIs.",
        regex=r"\bcrypto\.(?:createCipher|createDecipher)\b|\bAES\.MODE_ECB\b|\bmodes\.ECB\s*\(|['\"]aes-\d+-ecb['\"]",
    ),
    Rule(
        "script_without_sri",
        "supply_chain",
        "External script tag lacks Subresource Integrity.",
        regex=r"<script\s+(?![^>]{0,400}integrity\s*=)[^>]{0,200}src\s*=\s*['\"](?:https?:)?//[^'\"]{1,300}['\"][^>]{0,100}>",
    ),
    Rule(
        "possible_secret",
        "secret_exposure",
        "Possible hardcoded secret or private key. Do not copy the value; verify "
        "and rotate if real.",
        regex=(
            r"(?i)(?:[\"']?(?:api[_-]?key|secret|token|password|passwd|private[_-]?key)"
            r"[\"']?\s*[:=]\s*"
            r"(?:['\"][^'\"\n]{12,}|[^\s#;\"']{12,}))"
            r"|"
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----"
        ),
    ),
)


def run_git(args: list[str], cwd: Path) -> str:
    """Run a git command and return stdout on success.

    Args:
        args: Git subcommand arguments (without the ``git`` executable).
        cwd: Working directory for the command.

    Returns:
        Standard output from git, or an empty string if git is unavailable
        or the command fails.
    """
    git = shutil.which("git")
    if git is None:
        return ""
    try:
        proc = subprocess.run(  # noqa: S603
            [git, *args],
            cwd=cwd,
            check=False,
            text=True,
            capture_output=True,
        )
    except OSError:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout


def git_root(repo: Path) -> Path:
    """Resolve the git repository root for a path.

    Args:
        repo: Path inside or at the repository root.

    Returns:
        Resolved repository root, or ``repo`` when git is unavailable.
    """
    root = run_git(["rev-parse", "--show-toplevel"], repo).strip()
    if not root:
        return repo.resolve()
    return Path(root).resolve()


def custom_pattern_paths(repo: Path) -> list[Path]:
    """Collect custom security-pattern files from user and repo config dirs.

    Args:
        repo: Repository used to locate project-local pattern files.

    Returns:
        Existing custom pattern file paths in discovery order.
    """
    roots = [Path.home() / ".claude", git_root(repo) / ".claude"]
    paths = []
    for root in roots:
        for stem in CUSTOM_PATTERN_STEMS:
            for ext in CUSTOM_PATTERN_EXTS:
                candidate = root / f"{stem}{ext}"
                if candidate.is_file():
                    paths.append(candidate)
    return paths


def load_custom_rules(repo: Path) -> list[Rule]:
    """Load validated custom rules from discovered pattern files.

    Args:
        repo: Repository used to locate project-local pattern files.

    Returns:
        Parsed custom rules, capped at ``CUSTOM_PATTERN_LIMIT``.
    """
    rules: list[Rule] = []
    for path in custom_pattern_paths(repo):
        data = load_custom_pattern_file(path)
        if not isinstance(data, dict):
            continue
        patterns = data.get("patterns", [])
        if not isinstance(patterns, list):
            continue
        for entry in patterns:
            rule = custom_rule_from_entry(entry, path)
            if rule is not None:
                rules.append(rule)
            if len(rules) >= CUSTOM_PATTERN_LIMIT:
                return rules
    return rules


def _parse_json_text(raw: str) -> object | None:
    """Parse JSON pattern text.

    Args:
        raw: JSON document text.

    Returns:
        Parsed JSON value, or None when parsing fails.
    """
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _parse_yaml_text(raw: str) -> object | None:
    """Parse YAML pattern text.

    Args:
        raw: YAML document text.

    Returns:
        Parsed YAML value, or None when PyYAML is unavailable or parsing fails.
    """
    try:
        yaml_module = importlib.import_module("yaml")
    except ImportError:
        return None
    try:
        return yaml_module.safe_load(raw)
    except yaml_module.YAMLError:
        return None


def load_custom_pattern_file(path: Path) -> object | None:
    """Load and parse a custom security-patterns file.

    Args:
        path: Path to a JSON or YAML pattern definition file.

    Returns:
        Parsed pattern data, or None if the file is missing, empty, or invalid.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not raw.strip():
        return None
    if path.suffix == ".json":
        return _parse_json_text(raw)
    return _parse_yaml_text(raw)


def has_redos_structure(regex: str) -> bool:
    """Heuristic catastrophic-backtracking check aligned with upstream plugin.

    Args:
        regex: Regular expression pattern to inspect.

    Returns:
        True when the pattern has ReDoS-like structure.
    """
    if any(pattern.search(regex) for pattern in _REDOS_SHAPES):
        return True
    for match in _ALT_UNDER_REP.finditer(regex):
        branches = [
            branch for branch in match.group(0).strip("()*+").split("|") if branch
        ]
        for index, left in enumerate(branches):
            for right in branches[index + 1 :]:
                if left.startswith(right) or right.startswith(left):
                    return True
    return False


def validate_custom_regex(regex: str) -> bool:
    """Validate a user-supplied regex before loading it as a scan rule.

    Args:
        regex: Regular expression pattern to validate.

    Returns:
        True when the pattern compiles and passes ReDoS heuristics.
    """
    if has_redos_structure(regex):
        return False
    try:
        re.compile(regex)
    except re.error:
        return False
    return True


def parse_glob_list(raw: object) -> tuple[str, ...] | None:
    """Normalize a glob list from custom pattern metadata.

    Args:
        raw: Raw ``paths`` or ``exclude_paths`` value from a pattern entry.

    Returns:
        Normalized glob tuple, an empty tuple when absent, or None when invalid.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        return None
    return tuple(item.strip() for item in raw if item.strip())


def glob_path_matches(
    path: str, include: tuple[str, ...], exclude: tuple[str, ...]
) -> bool:
    """Match a path against include/exclude globs. ``**`` matches any depth.

    Args:
        path: File path to test.
        include: Glob patterns that must match when non-empty.
        exclude: Glob patterns that reject a match when any hit.

    Returns:
        True when the path passes include/exclude filtering.
    """
    normalized = path.replace("\\", "/")
    base = Path(normalized).name

    def hits(globs: tuple[str, ...]) -> bool:
        return any(
            fnmatch.fnmatch(normalized, glob) or fnmatch.fnmatch(base, glob)
            for glob in globs
        )

    if include and not hits(include):
        return False
    return not (exclude and hits(exclude))


def custom_rule_from_entry(entry: object, path: Path) -> Rule | None:
    """Convert one custom pattern entry into a validated scan rule.

    Args:
        entry: Raw pattern object from a custom patterns file.
        path: Source file used for rule provenance metadata.

    Returns:
        Parsed rule, or None when the entry is invalid or unsafe.
    """
    if not isinstance(entry, dict):
        return None
    rule_name = str(entry.get("rule_name") or entry.get("ruleName") or "").strip()
    reminder = str(entry.get("reminder") or entry.get("summary") or "").strip()
    regex = str(entry.get("regex") or "").strip()
    raw_substrings = entry.get("substrings") or ()
    if not isinstance(raw_substrings, list):
        raw_substrings = ()
    substrings = tuple(item for item in raw_substrings if isinstance(item, str))
    extensions = parse_extensions(entry.get("extensions"))
    path_globs = parse_glob_list(entry.get("paths"))
    exclude_path_globs = parse_glob_list(entry.get("exclude_paths"))
    if path_globs is None or exclude_path_globs is None:
        return None
    if not rule_name or not reminder or (not regex and not substrings):
        return None
    if regex and not validate_custom_regex(regex):
        return None
    return Rule(
        rule_id=f"user:{rule_name}",
        category=str(entry.get("category") or "custom"),
        summary=reminder[:1024],
        regex=regex or None,
        substrings=substrings,
        extensions=extensions,
        path_globs=path_globs,
        exclude_path_globs=exclude_path_globs,
        source=path.as_posix(),
    )


def parse_extensions(raw: object) -> frozenset[str] | None:
    """Normalize extension filters from custom pattern metadata.

    Args:
        raw: Raw ``extensions`` value from a pattern entry.

    Returns:
        Normalized extension set, None when unrestricted, or None when invalid.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        values: Sequence[object] = [raw]
    elif isinstance(raw, list):
        values = raw
    else:
        return None
    extensions = []
    for value in values:
        if not isinstance(value, str):
            continue
        ext = value.strip()
        if not ext:
            continue
        extensions.append(ext if ext.startswith(".") else f".{ext}")
    return frozenset(extensions) if extensions else None


def changed_paths(repo: Path, include_untracked: bool) -> list[Path]:
    """Collect changed file paths from the git working tree.

    Args:
        repo: Repository to inspect.
        include_untracked: Whether to include untracked files.

    Returns:
        Sorted unique changed file paths relative to the repository root.
    """
    root = git_root(repo)
    paths = set()
    for command in (["diff", "--name-only"], ["diff", "--cached", "--name-only"]):
        paths.update(
            root / line.strip()
            for line in run_git(command, root).splitlines()
            if line.strip()
        )
    if include_untracked:
        paths.update(
            root / line.strip()
            for line in run_git(
                ["ls-files", "--others", "--exclude-standard"], root
            ).splitlines()
            if line.strip()
        )
    return sorted(paths)


def iter_files(paths: Iterable[Path]) -> Iterable[Path]:
    """Yield files from explicit paths, expanding directories recursively.

    Args:
        paths: Files or directories selected for scanning.

    Yields:
        Resolved file paths, skipping ``.git`` directories.
    """
    for raw in paths:
        path = raw.resolve()
        if path.is_file():
            yield path
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and ".git" not in child.parts:
                    yield child


def secret_scan_applies(path: Path) -> bool:
    """Decide whether the secret-exposure rule should scan a file.

    Args:
        path: Candidate file path.

    Returns:
        True when secret scanning should run for the file.
    """
    normalized = path.as_posix().lower()
    suffix = path.suffix.lower()
    if suffix in SECRET_CONFIG_EXTS:
        return True
    if any(part in normalized for part in SECRET_EXAMPLE_PARTS):
        return True
    lowered_name = path.name.lower()
    if any(marker in lowered_name for marker in SECRET_EXAMPLE_MARKERS):
        return True
    return path.suffix not in DOC_EXTS


def rule_applies(rule: Rule, path: Path) -> bool:
    """Decide whether a rule should be evaluated for a file.

    Args:
        rule: Candidate security pattern rule.
        path: File path under scan.

    Returns:
        True when the rule applies to the file.
    """
    normalized = path.as_posix()
    if (rule.path_globs or rule.exclude_path_globs) and not glob_path_matches(
        normalized, rule.path_globs, rule.exclude_path_globs
    ):
        return False
    if rule.path_contains and rule.path_contains not in normalized:
        return False
    if rule.rule_id == "possible_secret":
        return secret_scan_applies(path)
    if rule.extensions is not None and path.suffix not in rule.extensions:
        return False
    return not (
        path.suffix in DOC_EXTS and rule.extensions is None and not rule.path_contains
    )


def line_matches(rule: Rule, line: str) -> bool:
    """Test one source line against a rule's matchers.

    Args:
        rule: Security pattern rule to evaluate.
        line: Single source line.

    Returns:
        True when the line matches the rule.
    """
    if rule.substrings and any(item in line for item in rule.substrings):
        return True
    if rule.regex and re.search(rule.regex, line):
        return True
    return bool(rule.path_contains and not rule.regex and not rule.substrings)


def scan_file(path: Path, rules: Iterable[Rule]) -> list[dict[str, object]]:
    """Scan one file against the provided rules.

    Args:
        path: File to scan.
        rules: Security pattern rules to evaluate.

    Returns:
        Match records for the file, or a single error record on read failure.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [{"path": path.as_posix(), "error": str(exc)}]

    results: list[dict[str, object]] = []
    for rule in rules:
        if not rule_applies(rule, path):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if line_matches(rule, line):
                results.append(format_match(path, line_no, line, rule))
                break
        else:
            if rule.path_contains and rule_applies(rule, path):
                results.append(format_match(path, 1, "", rule))
    return results


_SELF_CHECK_SOURCE = Path(".claude/security-patterns.json")


def _self_check_custom_regex_rules(failures: list[str]) -> Rule | None:
    invalid = custom_rule_from_entry(
        {
            "rule_name": "bad_regex",
            "reminder": "invalid regex should be skipped",
            "regex": r"(?P<unclosed",
        },
        _SELF_CHECK_SOURCE,
    )
    if invalid is not None:
        failures.append("invalid custom regex was not skipped")

    redos = custom_rule_from_entry(
        {
            "rule_name": "redos_regex",
            "reminder": "ReDoS-like regex should be skipped",
            "regex": r"(a+)*",
        },
        _SELF_CHECK_SOURCE,
    )
    if redos is not None:
        failures.append("ReDoS-like custom regex was not skipped")

    path_rule = custom_rule_from_entry(
        {
            "rule_name": "scoped_rule",
            "reminder": "only src files",
            "substrings": ["needle"],
            "paths": ["**/src/**"],
            "exclude_paths": ["**/tests/**"],
        },
        _SELF_CHECK_SOURCE,
    )
    if path_rule is None:
        failures.append("valid path-filtered custom rule was rejected")
    elif path_rule.path_globs != ("**/src/**",):
        failures.append("custom rule paths were not parsed")
    elif path_rule.exclude_path_globs != ("**/tests/**",):
        failures.append("custom rule exclude_paths were not parsed")
    return path_rule


def _self_check_path_and_secret_rules(
    failures: list[str], path_rule: Rule | None
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        included = root / "src" / "app.py"
        excluded = root / "tests" / "app.py"
        other = root / "lib" / "app.py"
        included.parent.mkdir(parents=True)
        excluded.parent.mkdir(parents=True)
        other.parent.mkdir(parents=True)
        for file_path in (included, excluded, other):
            file_path.write_text("needle\n", encoding="utf-8")

        if path_rule is None:
            failures.append("path filter checks skipped because path_rule was missing")
            return
        if not rule_applies(path_rule, included):
            failures.append("paths filter did not include matching file")
        if rule_applies(path_rule, excluded):
            failures.append("exclude_paths filter did not exclude matching file")
        if rule_applies(path_rule, other):
            failures.append("paths filter matched file outside include globs")

        config = root / "config.json"
        config.write_text(
            '{\n  "api_key": "supersecretvalue123"\n}\n',
            encoding="utf-8",
        )
        secret_hits = [
            match
            for match in scan_file(config, RULES)
            if match.get("rule_id") == "possible_secret"
        ]
        if not secret_hits:
            failures.append("possible_secret did not detect JSON config secret")
        elif secret_hits[0].get("excerpt") != "[redacted possible secret line]":
            failures.append("possible_secret excerpt was not redacted")

        claude_dir = root / ".claude"
        claude_dir.mkdir()
        (claude_dir / "security-patterns.json").write_text(
            "{not valid json", encoding="utf-8"
        )
        load_custom_rules(root)

        (claude_dir / "security-patterns.json").write_text(
            json.dumps({
                "patterns": [
                    {
                        "rule_name": "bad",
                        "reminder": "invalid sibling regex",
                        "regex": "(?P<unclosed",
                    },
                    {
                        "rule_name": "good",
                        "reminder": "valid sibling rule",
                        "substrings": ["valid-marker"],
                    },
                ]
            }),
            encoding="utf-8",
        )
        loaded = load_custom_rules(root)
        if not any(rule.rule_id == "user:good" for rule in loaded):
            failures.append("valid custom rule skipped due to sibling invalid regex")


def run_self_checks() -> int:
    """Run minimal built-in checks for custom rule validation and secret scanning.

    Returns:
        Process exit code: 0 on success, 1 when any self-check fails.
    """
    failures: list[str] = []
    path_rule = _self_check_custom_regex_rules(failures)
    _self_check_path_and_secret_rules(failures, path_rule)

    if failures:
        print(json.dumps({"self_check_failures": failures}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps({"self_check": "ok"}, indent=2))
    return 0


def format_match(path: Path, line_no: int, line: str, rule: Rule) -> dict[str, object]:
    """Build one JSON-serializable match record.

    Args:
        path: Matched file path.
        line_no: One-based line number for the match.
        line: Source line content.
        rule: Rule that produced the match.

    Returns:
        Match payload for JSON output.
    """
    excerpt = line.strip()
    if rule.category == "secret_exposure" and excerpt:
        excerpt = "[redacted possible secret line]"
    return {
        "path": path.as_posix(),
        "line": line_no,
        "rule_id": rule.rule_id,
        "category": rule.category,
        "summary": rule.summary,
        "excerpt": excerpt[:240],
        "source": rule.source,
    }


def main(argv: list[str]) -> int:
    """Parse CLI arguments and run the security pattern scan.

    Args:
        argv: Command-line arguments excluding the program name.

    Returns:
        Process exit code: 0 when no matches, 1 when matches exist, 2 on usage
        errors.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Scan files for security-review pattern leads. Findings require "
            "manual verification."
        ),
        epilog=(
            "Examples:\n"
            "  security_pattern_scan.py --repo /path/to/repo --changed\n"
            "  security_pattern_scan.py --paths app.py src/\n"
            "  security_pattern_scan.py --changed --include-untracked --pretty"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="repository to inspect for --changed, default: current directory",
    )
    parser.add_argument(
        "--changed",
        action="store_true",
        help="scan files changed in the selected git working tree",
    )
    parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="include untracked files with --changed",
    )
    parser.add_argument(
        "--paths", nargs="*", default=[], help="explicit files or directories to scan"
    )
    parser.add_argument(
        "--pretty", action="store_true", help="pretty-print JSON output"
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="run built-in validation checks and exit",
    )
    args = parser.parse_args(argv)

    if args.self_check:
        return run_self_checks()

    repo = Path(args.repo).resolve()
    rules = (*RULES, *load_custom_rules(repo))
    selected = [Path(path) for path in args.paths]
    if args.changed:
        selected.extend(changed_paths(repo, args.include_untracked))
    selected = sorted(set(selected))
    if not selected:
        print(
            json.dumps(
                {"error": "no paths selected; pass --changed or --paths"}, indent=2
            ),
            file=sys.stderr,
        )
        return 2

    matches: list[dict[str, object]] = []
    for path in iter_files(selected):
        matches.extend(scan_file(path, rules))

    output = {
        "matches": matches,
        "summary": {
            "files_selected": len(selected),
            "matches": len(matches),
            "rules_loaded": len(rules),
            "note": (
                "Pattern matches are leads. Confirm source, sink, reachability, "
                "and impact before reporting."
            ),
        },
    }
    print(json.dumps(output, indent=2 if args.pretty else None, sort_keys=args.pretty))
    return 1 if matches else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
