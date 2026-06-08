#!/usr/bin/env python3
"""Scan changed files or explicit paths for security-review pattern leads.

This is a deterministic helper for the security-guidance skill. It reports
leads, not confirmed vulnerabilities. The reviewing agent must still verify
attacker control, reachability, and impact before reporting a finding.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency
    yaml = None

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
WORKFLOW_PART = ".github/workflows/"
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
        extensions=frozenset(
            {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts", ".py"}
        ),
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
            r"(?i)(?:api[_-]?key|secret|token|password|passwd|private[_-]?key)"
            r"\s*[:=]\s*['\"][^'\"\n]{12,}|"
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----"
        ),
    ),
)


def run_git(args: list[str], cwd: Path) -> str:
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
    root = run_git(["rev-parse", "--show-toplevel"], repo).strip()
    if not root:
        return repo.resolve()
    return Path(root).resolve()


def custom_pattern_paths(repo: Path) -> list[Path]:
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
    rules: list[Rule] = []
    for path in custom_pattern_paths(repo):
        data = load_custom_pattern_file(path)
        if not isinstance(data, dict):
            continue
        for entry in data.get("patterns", []):
            rule = custom_rule_from_entry(entry, path)
            if rule is not None:
                rules.append(rule)
            if len(rules) >= CUSTOM_PATTERN_LIMIT:
                return rules
    return rules


def load_custom_pattern_file(path: Path) -> object | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not raw.strip():
        return None
    if path.suffix == ".json":
        try:
            return json.loads(raw)
        except ValueError:
            return None
    if yaml is None:
        return None
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError:
        return None


def custom_rule_from_entry(entry: object, path: Path) -> Rule | None:
    if not isinstance(entry, dict):
        return None
    rule_name = str(entry.get("rule_name") or entry.get("ruleName") or "").strip()
    reminder = str(entry.get("reminder") or entry.get("summary") or "").strip()
    regex = str(entry.get("regex") or "").strip()
    raw_substrings = entry.get("substrings") or ()
    substrings = tuple(item for item in raw_substrings if isinstance(item, str))
    extensions = parse_extensions(entry.get("extensions"))
    if not rule_name or not reminder or (not regex and not substrings):
        return None
    return Rule(
        rule_id=f"user:{rule_name}",
        category=str(entry.get("category") or "custom"),
        summary=reminder[:1024],
        regex=regex or None,
        substrings=substrings,
        extensions=extensions,
        source=path.as_posix(),
    )


def parse_extensions(raw: object) -> frozenset[str] | None:
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
    for raw in paths:
        path = raw.resolve()
        if path.is_file():
            yield path
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and ".git" not in child.parts:
                    yield child


def rule_applies(rule: Rule, path: Path) -> bool:
    normalized = path.as_posix()
    if rule.path_contains and rule.path_contains not in normalized:
        return False
    if rule.extensions is not None and path.suffix not in rule.extensions:
        return False
    return not (
        path.suffix in DOC_EXTS and rule.extensions is None and not rule.path_contains
    )


def line_matches(rule: Rule, line: str) -> bool:
    if rule.substrings and any(item in line for item in rule.substrings):
        return True
    if rule.regex and re.search(rule.regex, line):
        return True
    return bool(rule.path_contains and not rule.regex and not rule.substrings)


def scan_file(path: Path, rules: Iterable[Rule]) -> list[dict[str, object]]:
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


def format_match(path: Path, line_no: int, line: str, rule: Rule) -> dict[str, object]:
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
    args = parser.parse_args(argv)

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
