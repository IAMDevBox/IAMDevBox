#!/usr/bin/env python3
"""
IG Groovy & Route Analyzer for PingGateway 2024.11 Migration (Groovy 3 → 4)

Usage:
    python3 ig-groovy-analyzer.py /path/to/openig
    python3 ig-groovy-analyzer.py /path/to/openig -o report.md
    python3 ig-groovy-analyzer.py /path/to/openig -s ERROR          # errors only
    python3 ig-groovy-analyzer.py /path/to/openig -f json           # JSON output

Scans an IG instance directory to:
1. Find all .groovy script files and check which are referenced
2. Analyze scripts for Groovy 4 migration issues
3. Validate route JSON configs for common misconfigurations
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


# ---------------------------------------------------------------------------
# Severity ordering
# ---------------------------------------------------------------------------
SEVERITY_ORDER = {"ERROR": 3, "WARN": 2, "INFO": 1}


# ---------------------------------------------------------------------------
# Groovy script rules (regex-based, applied to .groovy files)
# ---------------------------------------------------------------------------
RULES = [
    # --- Groovy 4 errors (0xx) ---
    ("G4-001", "ERROR", r"import\s+groovy\.util\.XmlSlurper",
     "groovy.util.XmlSlurper removed in Groovy 4",
     "Change to: import groovy.xml.XmlSlurper"),

    ("G4-002", "ERROR", r"import\s+groovy\.util\.XmlParser",
     "groovy.util.XmlParser removed in Groovy 4",
     "Change to: import groovy.xml.XmlParser"),

    ("G4-003", "ERROR", r"import\s+groovy\.util\.GroovyTestCase",
     "groovy.util.GroovyTestCase removed in Groovy 4",
     "Change to: import groovy.test.GroovyTestCase"),

    ("G4-004", "ERROR", r"import\s+groovy\.util\.AntBuilder",
     "groovy.util.AntBuilder removed in Groovy 4",
     "Change to: import groovy.ant.AntBuilder"),

    # --- Groovy 4 warnings (1xx) ---
    ("G4-101", "WARN", r"\.intersect\(",
     "intersect() now draws elements from 1st collection (was 2nd in Groovy 3)",
     "Verify the result is still correct with the new semantics"),

    ("G4-102", "WARN", r"(?:Object\s*\[\s*\]\s+\w+|def\s+\w+)\s*=\s*\w+\s*\+\s*\w+",
     "Array addition (b + c) now returns same type as b, was Object[] in Groovy 3",
     "Verify array concatenation results; use explicit typing or .union()"),

    ("G4-103", "WARN", r"catch\s*\(\s*Exception\s+\w+\s*\).*[Ss]ql|Sql\..*\.call\(",
     "Sql#call variants now throw SQLException instead of Exception",
     "Change catch blocks to catch (SQLException e)"),

    ("G4-104", "WARN", r"@\s*Field\s+private|private\s+\w+\s+\w+.*=.*\{",
     "Private field access in closures may break in Groovy 4",
     "Use @CompileStatic or change to protected"),

    ("G4-105", "WARN", r"import\s+groovy\.util\.\*",
     "groovy.util.* wildcard import may pull in removed classes",
     "Replace with specific imports from groovy.xml, groovy.test, groovy.ant"),

    # --- Groovy 4 info (2xx) ---
    ("G4-201", "INFO", r"[=!]=\s*0\.0[fd]?\b|0\.0[fd]?\s*[=!]=",
     "Groovy 4 now distinguishes 0.0f and -0.0f",
     "Use equalsIgnoreZeroSign or NumberAwareComparator if old behavior needed"),

    ("G4-202", "INFO", r"\.getProperties\(\)",
     "getProperties() now also returns public fields in Groovy 4",
     "Verify property iteration doesn't expose unintended fields"),


    # --- PingGateway errors (0xx) ---
    ("IG-001", "ERROR", r"(?:promise|Promise|future|Future)\w*\.get\(\s*\)",
     "Blocking Promise.get() can cause deadlocks in PingGateway",
     "Use .thenOnResult() or .thenAsync() instead"),

    ("IG-002", "ERROR", r"\.getOrThrow\(",
     "Blocking Promise.getOrThrow() can cause deadlocks",
     "Use .thenOnResult() or .thenAsync() instead"),

    ("IG-003", "ERROR", r"\.getOrThrowUninterruptibly\(",
     "Blocking Promise.getOrThrowUninterruptibly() can cause deadlocks",
     "Use .thenOnResult() or .thenAsync() instead"),

    # --- PingGateway warnings (1xx) ---
    ("IG-101", "WARN", r"request\.form\b",
     "request.form is deprecated in PingGateway",
     "Use Request.getQueryParams() and Entity.getForm() / Entity.setForm()"),

    ("IG-102", "WARN", r"\"matches\"\s*:|'matches'\s*:",
     "matches() deprecated in 2024.11, removed in 2025.x",
     "Replace with find() or matchesWithRegex()"),

    ("IG-103", "WARN", r"\bldap\b\s*\.|LdapClient",
     "ldap script binding and LdapClient deprecated since IG 7.1",
     "Remove or replace with alternative LDAP access method"),

    ("IG-104", "WARN", r"JwtSession\b",
     "JwtSession object deprecated in PingGateway 2024.11",
     "Use JwtSessionManager for the 'session' property instead"),

    ("IG-105", "WARN", r'"Session"\s*:',
     "Using 'Session' key (uppercase) deprecated in 2024.11",
     "Use lowercase 'session' property instead"),

    ("IG-106", "WARN", r"\b_token\s*\(|_t\s*\(|TokenResolver\b",
     "TokenResolver and _token()/_t() deprecated in PingGateway 2024.6",
     "Use expression format &{...} instead"),

    ("IG-107", "WARN", r"request\.uri\b.*(?:OAuth|oauth|token)",
     "request.uri in OAuth2 filter context deprecated in 2023.9",
     "Use IdpSelectionLoginContext instead"),

    ("IG-108", "WARN", r"\bmatches\s*\(\s*request\.",
     "matches() deprecated in 2024.11, removed in 2025.x",
     "Replace with find() or matchesWithRegex()"),

    # --- PingGateway info (2xx) ---
    ("IG-201", "INFO", r"org\.forgerock\.util\.time\.Duration",
     "org.forgerock.util.time.Duration deprecated (2025.6)",
     "Use java.time.Duration instead"),

    # --- Security checks (SEC-0xx errors, SEC-1xx warnings) ---
    ("SEC-001", "ERROR",
     r"[\"'](?:password|passwd|pass[Ww]ord|pwd|passphrase)[\"']\s*:\s*[\"'][^\"'$&{]{3,}[\"']",
     "Hardcoded password detected in config",
     "Move to secret store or use &{...} expression"),

    ("SEC-002", "ERROR",
     r"[\"'][^\"']*(?:secret|apiKey|api[_-]?[Kk]ey|api[_-]?[Ss]ecret|token|access[_-]?[Tt]oken|refresh[_-]?[Tt]oken|auth[_-]?[Tt]oken|credential|private[_-]?[Kk]ey|client[_-]?[Ss]ecret|shared[_-]?[Ss]ecret|encryption[_-]?[Kk]ey|signing[_-]?[Kk]ey|keystore[_-]?[Pp]ass|truststore[_-]?[Pp]ass|storepass|keypass)[^\"']*[\"']\s*:\s*[\"'][^\"'$&{]{3,}[\"']",
     "Hardcoded secret/key detected in config",
     "Move to secret store or use &{...} expression"),

    ("SEC-101", "WARN",
     r"(?:password|passwd|pwd|passphrase|secret|apikey|api_key|credential|private_key|client_secret|storepass|keypass)\s*=\s*[\"'][^\"'$&{]{3,}[\"']",
     "Possible hardcoded credential in script",
     "Use environment variable or secret store"),

    ("SEC-102", "WARN",
     r"[Bb]ase64\.(?:encode|decode).*(?:password|passwd|secret|key|credential|token)",
     "Base64 encoded credential detected",
     "Use proper secret management instead of Base64 encoding"),

    # --- Path checks (PATH-1xx warnings) ---
    ("PATH-101", "WARN",
     r"catalina\.base|catalina\.home|/webapps/ROOT|/tomcat\d+/|servlet[_-]?api",
     "Reference to Tomcat environment path",
     "Update to new PingGateway standalone path"),

    ("PATH-102", "INFO",
     r"[\"'(/]/(?:opt|home|etc|var|usr|tmp|srv|root|mnt|media|boot|run)/[a-zA-Z0-9._/-]+",
     "Absolute filesystem path — may not be valid after migration",
     "Verify path exists in new environment"),

    ("PATH-103", "INFO",
     r"[\"'](?:\.\./)+(.*?)[\"']",
     "Relative path referencing outside project directory",
     "Verify the referenced file is accessible from new IG location"),
]


# ---------------------------------------------------------------------------
# Required fields for route config validation
# ---------------------------------------------------------------------------
REQUIRED_FIELDS = {
    "UserProfileFilter": ["config/username"],
    "ScriptableFilter": ["config/type"],
    "ScriptableHandler": ["config/type"],
    "AmService": ["config/url", "config/agent"],
    "StaticResponseHandler": ["config/status"],
}


# ---------------------------------------------------------------------------
# Directories to skip during scanning
# ---------------------------------------------------------------------------
SKIP_DIRS = {"tmp", "temp", ".tmp", "__pycache__", "node_modules", "backup", ".git"}


def _skip_path(path, base_dir):
    """Return True if path is inside a directory (relative to base_dir) that should be skipped."""
    try:
        rel = path.relative_to(base_dir)
    except ValueError:
        return False
    for part in rel.parts:
        if part.lower() in SKIP_DIRS:
            return True
    return False


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------
def find_groovy_files(base_dir):
    return sorted(f for f in base_dir.rglob("*.groovy") if not _skip_path(f, base_dir))


def find_config_files(base_dir):
    files = []
    for ext in ("*.json", "*.groovy", "*.properties"):
        files.extend(f for f in base_dir.rglob(ext) if not _skip_path(f, base_dir))
    return sorted(files)


def find_route_files(base_dir):
    routes = []
    for d in base_dir.rglob("routes"):
        if d.is_dir() and not _skip_path(d, base_dir):
            routes.extend(sorted(d.glob("*.json")))
    return routes


# ---------------------------------------------------------------------------
# Script reference extraction
# ---------------------------------------------------------------------------
def extract_script_refs(config_file):
    refs = []
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            content = f.read()
        for m in re.finditer(r'"(?:file|source|scriptFile)"\s*:\s*"([^"]*\.groovy)"', content):
            refs.append(m.group(1))
        for m in re.finditer(r'"type"\s*:\s*"Scriptable\w+"', content):
            refs.append(f"[inline in {config_file.name}]")
        for m in re.finditer(r'(\w+\.groovy)', content):
            if m.group(1) not in refs:
                refs.append(m.group(1))
    except (UnicodeDecodeError, OSError):
        pass
    return refs


# ---------------------------------------------------------------------------
# Comment stripping for Groovy files
# ---------------------------------------------------------------------------
def strip_comments(lines):
    result = []
    in_block = False
    for line_num, line in enumerate(lines, 1):
        code = line
        if in_block:
            end = code.find("*/")
            if end >= 0:
                code = code[end + 2:]
                in_block = False
            else:
                result.append((line_num, ""))
                continue
        while not in_block:
            start = code.find("/*")
            if start < 0:
                break
            end = code.find("*/", start + 2)
            if end >= 0:
                code = code[:start] + code[end + 2:]
            else:
                code = code[:start]
                in_block = True
        stripped = code
        in_str = False
        str_char = None
        for i, ch in enumerate(code):
            if not in_str and ch in ('"', "'"):
                in_str = True
                str_char = ch
            elif in_str and ch == str_char and (i == 0 or code[i - 1] != '\\'):
                in_str = False
            elif not in_str and code[i:i + 2] == '//':
                stripped = code[:i]
                break
        result.append((line_num, stripped))
    return result


# ---------------------------------------------------------------------------
# Groovy script analysis
# ---------------------------------------------------------------------------
def analyze_script(script_path, min_severity=0):
    findings = []
    try:
        with open(script_path, "r", encoding="utf-8", errors="replace") as f:
            raw_lines = f.readlines()
    except OSError:
        return findings

    code_lines = strip_comments(raw_lines)

    for line_num, code in code_lines:
        if not code.strip():
            continue
        for rule_id, severity, pattern, desc, fix in RULES:
            if SEVERITY_ORDER.get(severity, 0) < min_severity:
                continue
            m = re.search(pattern, code)
            if m:
                detail = desc
                matched = m.group(0).strip()
                if matched and len(matched) < 80:
                    detail = "{}: `{}`".format(desc, matched)
                findings.append({
                    "rule": rule_id,
                    "severity": severity,
                    "line": line_num,
                    "text": raw_lines[line_num - 1].rstrip(),
                    "description": detail,
                    "fix": fix,
                })

    # --- File-level checks: removed class usage (not on import lines) ---
    REMOVED_CLASSES = [
        ("XmlSlurper", "groovy.xml.XmlSlurper"),
        ("XmlParser", "groovy.xml.XmlParser"),
        ("AntBuilder", "groovy.ant.AntBuilder"),
        ("GroovyTestCase", "groovy.test.GroovyTestCase"),
    ]
    for line_num, code in code_lines:
        if not code.strip() or re.match(r'\s*import\s', code):
            continue
        for cls, replacement in REMOVED_CLASSES:
            if re.search(r'\b' + cls + r'\b', code):
                if SEVERITY_ORDER["WARN"] >= min_severity:
                    findings.append({
                        "rule": "G4-106", "severity": "WARN",
                        "line": line_num,
                        "text": raw_lines[line_num - 1].rstrip(),
                        "description": "{} usage — verify import is from correct package".format(cls),
                        "fix": "Ensure import is: import {}".format(replacement),
                    })

    return findings


# ---------------------------------------------------------------------------
# Route JSON config analysis
# ---------------------------------------------------------------------------
def _deep_find(obj, target_key, path=""):
    """Recursively find all values for a target key in nested dict/list."""
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            current = f"{path}/{k}" if path else k
            if k == target_key:
                results.append((current, v))
            results.extend(_deep_find(v, target_key, current))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            results.extend(_deep_find(item, target_key, f"{path}[{i}]"))
    return results


def _deep_get(obj, path):
    """Get nested value by slash-separated path (e.g., 'config/username').
    Supports list indexing like 'filters[0]/type'."""
    parts = path.split("/")
    current = obj
    for p in parts:
        # Handle list index: key[0]
        m = re.match(r'^(.+)\[(\d+)\]$', p)
        if m:
            key, idx = m.group(1), int(m.group(2))
            if isinstance(current, dict) and key in current:
                current = current[key]
                if isinstance(current, list) and idx < len(current):
                    current = current[idx]
                else:
                    return None
            else:
                return None
        elif isinstance(current, dict) and p in current:
            current = current[p]
        else:
            return None
    return current


def _find_line(raw_text, needle):
    """Find the line number of a needle in raw text. Returns 0 if not found."""
    for i, line in enumerate(raw_text.splitlines(), 1):
        if needle in line:
            return i
    return 0


def _find_all_conditions(obj, path=""):
    """Recursively find all 'condition' values in nested dict/list."""
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            current = "{}/{}".format(path, k) if path else k
            if k == "condition" and isinstance(v, str):
                results.append((current, v))
            results.extend(_find_all_conditions(v, current))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            results.extend(_find_all_conditions(item, "{}[{}]".format(path, i)))
    return results


def analyze_route(route_path, all_route_names, min_severity=0):
    """Analyze a route JSON for config issues."""
    findings = []
    try:
        with open(route_path, "r", encoding="utf-8") as f:
            raw_text = f.read()
    except OSError:
        return findings

    raw_lines = raw_text.splitlines()

    # --- RT-001: Duplicate keys ---
    dup_keys = []
    def dup_hook(pairs):
        seen = {}
        for k, v in pairs:
            if k in seen:
                dup_keys.append(k)
            seen[k] = v
        return seen

    try:
        parsed = json.loads(raw_text, object_pairs_hook=dup_hook)
    except json.JSONDecodeError:
        return findings

    if dup_keys and SEVERITY_ORDER["ERROR"] >= min_severity:
        for dk in dup_keys:
            # Find second occurrence
            count = 0
            line_num = 0
            for i, line in enumerate(raw_lines, 1):
                if '"{}"'.format(dk) in line:
                    count += 1
                    if count == 2:
                        line_num = i
                        break
            findings.append({
                "rule": "RT-001", "severity": "ERROR",
                "line": line_num, "text": raw_lines[line_num - 1].strip() if line_num else "",
                "description": "Duplicate key '{}' in route JSON".format(dk),
                "fix": "Remove or rename the duplicate key",
            })

    # --- RT-002: Missing required config ---
    if SEVERITY_ORDER["ERROR"] >= min_severity:
        type_nodes = _deep_find(parsed, "type")
        for node_path, type_val in type_nodes:
            if not isinstance(type_val, str):
                continue
            if type_val in REQUIRED_FIELDS:
                parent_path = node_path.rsplit("/", 1)[0] if "/" in node_path else ""
                parent = _deep_get(parsed, parent_path) if parent_path else parsed
                if not isinstance(parent, dict):
                    continue
                for req in REQUIRED_FIELDS[type_val]:
                    if _deep_get(parent, req) is None:
                        line_num = _find_line(raw_text, '"type"')
                        findings.append({
                            "rule": "RT-002", "severity": "ERROR",
                            "line": line_num,
                            "text": raw_lines[line_num - 1].strip() if line_num else "",
                            "description": "{} missing required field: {}".format(type_val, req),
                            "fix": "Add '{}' to {} config".format(req.split('/')[-1], type_val),
                        })

    # --- RT-003: Duplicate route name/ID ---
    route_name = parsed.get("name", "")
    if route_name and SEVERITY_ORDER["WARN"] >= min_severity:
        if route_name in all_route_names and all_route_names[route_name] != str(route_path):
            line_num = _find_line(raw_text, '"name"')
            findings.append({
                "rule": "RT-101", "severity": "WARN",
                "line": line_num,
                "text": raw_lines[line_num - 1].strip() if line_num else "",
                "description": "Duplicate route name '{}' (also in {})".format(
                    route_name, Path(all_route_names[route_name]).name),
                "fix": "Rename one of the routes to avoid conflicts",
            })

    # --- RT-005: Deprecated matches() in all conditions (recursive) ---
    if SEVERITY_ORDER["WARN"] >= min_severity:
        conditions = _find_all_conditions(parsed)
        for _, cond_val in conditions:
            if "matches(" in cond_val:
                line_num = _find_line(raw_text, cond_val[:40])
                findings.append({
                    "rule": "RT-102", "severity": "WARN",
                    "line": line_num,
                    "text": raw_lines[line_num - 1].strip() if line_num else "",
                    "description": "matches() deprecated in 2024.11, removed in 2025.x",
                    "fix": "Replace matches() with find() or matchesWithRegex()",
                })

    # --- RT-006: Deprecated expressions in ${...} (skip if already caught by RT-005) ---
    if SEVERITY_ORDER["WARN"] >= min_severity:
        rt005_lines = set(f["line"] for f in findings if f["rule"] == "RT-102")
        for m in re.finditer(r'\$\{([^}]+)\}', raw_text):
            expr = m.group(1)
            pos = raw_text[:m.start()].count('\n') + 1
            if pos in rt005_lines:
                continue
            if 'matches(' in expr:
                findings.append({
                    "rule": "RT-103", "severity": "WARN",
                    "line": pos,
                    "text": raw_lines[pos - 1].strip() if pos <= len(raw_lines) else "",
                    "description": "matches() deprecated in 2024.11, removed in 2025.x (inline expression)",
                    "fix": "Replace matches() with find() or matchesWithRegex()",
                })
            if '.get()' in expr:
                findings.append({
                    "rule": "RT-103", "severity": "INFO",
                    "line": pos,
                    "text": raw_lines[pos - 1].strip() if pos <= len(raw_lines) else "",
                    "description": "Potential blocking .get() in inline expression",
                    "fix": "Review if this is a Promise.get() call",
                })

    # --- IG-008: Uppercase Session key ---
    if '"Session"' in raw_text and SEVERITY_ORDER["WARN"] >= min_severity:
        line_num = _find_line(raw_text, '"Session"')
        findings.append({
            "rule": "IG-105", "severity": "WARN",
            "line": line_num,
            "text": raw_lines[line_num - 1].strip() if line_num else "",
            "description": "Uppercase 'Session' config key deprecated in 2024.11",
            "fix": "Use lowercase 'session' property instead",
        })

    # --- SEC/PATH: Apply regex rules to raw JSON text ---
    SEC_PATH_RULES = [r for r in RULES if r[0].startswith(("SEC-", "PATH-"))]
    if SEC_PATH_RULES:
        for line_num, line in enumerate(raw_lines, 1):
            for rule_id, severity, pattern, desc, fix in SEC_PATH_RULES:
                if SEVERITY_ORDER.get(severity, 0) < min_severity:
                    continue
                m = re.search(pattern, line)
                if m:
                    detail = desc
                    matched = m.group(0).strip()
                    if matched and len(matched) < 80:
                        detail = "{}: `{}`".format(desc, matched)
                    findings.append({
                        "rule": rule_id, "severity": severity,
                        "line": line_num,
                        "text": line.strip(),
                        "description": detail, "fix": fix,
                    })

    return findings


# ---------------------------------------------------------------------------
# Data collection (separated from formatting)
# ---------------------------------------------------------------------------
def collect_analysis(base_dir, min_severity=0):
    groovy_files = find_groovy_files(base_dir)
    config_files = find_config_files(base_dir)
    route_files = find_route_files(base_dir)

    # Collect script references
    all_refs = {}
    for cf in config_files:
        for ref in extract_script_refs(cf):
            all_refs.setdefault(ref, []).append(cf.name)

    # Classify scripts as used/unused
    used_scripts = {}
    unused_scripts = []

    for gf in groovy_files:
        matched = False
        for ref, sources in all_refs.items():
            if ref.startswith("[inline"):
                continue
            if gf.name == ref or str(gf).endswith(ref) or ref in str(gf):
                used_scripts[str(gf)] = sources
                matched = True
                break
        if not matched:
            unused_scripts.append(str(gf))

    # Analyze scripts
    script_findings = {}
    for gf_str in used_scripts:
        findings = analyze_script(Path(gf_str), min_severity)
        if findings:
            script_findings[gf_str] = findings

    unused_findings = {}
    for gf_str in unused_scripts:
        findings = analyze_script(Path(gf_str), min_severity)
        if findings:
            unused_findings[gf_str] = findings

    # Analyze routes
    all_route_names = {}
    for rf in route_files:
        try:
            with open(rf, "r", encoding="utf-8") as f:
                data = json.load(f)
            name = data.get("name", "")
            if name:
                all_route_names.setdefault(name, str(rf))
        except (json.JSONDecodeError, OSError):
            pass

    route_findings = {}
    for rf in route_files:
        findings = analyze_route(rf, all_route_names, min_severity)
        if findings:
            route_findings[str(rf)] = findings

    # Aggregate counts — separate script vs route
    script_all = list(script_findings.values()) + list(unused_findings.values())
    route_all = list(route_findings.values())

    def _count(findings_list, sev):
        return sum(sum(1 for f in fl if f["severity"] == sev) for fl in findings_list)

    # Rule counts
    rule_counts = Counter()
    for fl in script_all + route_all:
        for f in fl:
            rule_counts[f["rule"]] += 1

    # Sort findings by severity (ERROR first, then WARN, then INFO)
    def _sort_findings(findings_dict):
        for k in findings_dict:
            findings_dict[k] = sorted(findings_dict[k],
                key=lambda f: -SEVERITY_ORDER.get(f["severity"], 0))
        return findings_dict

    _sort_findings(script_findings)
    _sort_findings(unused_findings)
    _sort_findings(route_findings)

    # Collect all absolute path references across all findings
    path_refs = {}  # path -> [{"file": ..., "line": ...}]
    _path_re = re.compile(r'["\'](/(?:opt|home|etc|var|usr|tmp|srv|root|mnt|media|boot|run)/[a-zA-Z0-9._/-]+)["\']')
    all_files_to_scan = []
    for gf_str in list(used_scripts.keys()) + unused_scripts:
        all_files_to_scan.append(gf_str)
    for rf in route_files:
        all_files_to_scan.append(str(rf))
    for fpath in all_files_to_scan:
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                for line_num, line in enumerate(f, 1):
                    for m in _path_re.finditer(line):
                        p = m.group(1)
                        path_refs.setdefault(p, []).append({
                            "file": Path(fpath).name,
                            "line": line_num,
                        })
        except OSError:
            pass

    return {
        "directory": str(base_dir),
        "groovy_count": len(groovy_files),
        "config_count": len(config_files),
        "route_count": len(route_files),
        "used_scripts": used_scripts,
        "unused_scripts": unused_scripts,
        "script_findings": script_findings,
        "unused_findings": unused_findings,
        "route_findings": route_findings,
        "script_errors": _count(script_all, "ERROR"),
        "script_warnings": _count(script_all, "WARN"),
        "script_info": _count(script_all, "INFO"),
        "route_errors": _count(route_all, "ERROR"),
        "route_warnings": _count(route_all, "WARN"),
        "route_info": _count(route_all, "INFO"),
        "rule_counts": dict(rule_counts),
        "path_refs": path_refs,
        "_severity_filter": min_severity > 0,
    }


# ---------------------------------------------------------------------------
# Markdown report formatter
# ---------------------------------------------------------------------------
def format_markdown(data):
    lines = []
    lines.append("# IG Migration Analysis Report")
    lines.append(f"\n**Directory:** `{data['directory']}`")
    lines.append("")
    lines.append("## Overview\n")
    lines.append("| Category | Count |")
    lines.append("|---|---|")
    lines.append(f"| Groovy files | {data['groovy_count']} |")
    lines.append(f"| Config files scanned | {data['config_count']} |")
    lines.append(f"| Route files | {data['route_count']} |")
    lines.append(f"| Used scripts | {len(data['used_scripts'])} |")
    lines.append(f"| Unused scripts | {len(data['unused_scripts'])} |")
    se, sw, si = data['script_errors'], data['script_warnings'], data['script_info']
    re_, rw, ri = data['route_errors'], data['route_warnings'], data['route_info']
    # Build columns based on what's visible at current severity filter
    cols = []
    if se + re_ > 0 or not data.get('_severity_filter'):
        cols.append(('Errors', se, re_, se + re_))
    if sw + rw > 0 or not data.get('_severity_filter'):
        cols.append(('Warnings', sw, rw, sw + rw))
    if si + ri > 0 or not data.get('_severity_filter'):
        cols.append(('Info', si, ri, si + ri))
    if cols:
        lines.append("")
        header = "| | " + " | ".join(c[0] for c in cols) + " |"
        sep = "|---|" + "|".join("---" for _ in cols) + "|"
        script_row = "| **Groovy scripts** | " + " | ".join(str(c[1]) for c in cols) + " |"
        route_row = "| **Route configs** | " + " | ".join(str(c[2]) for c in cols) + " |"
        total_row = "| **Total** | " + " | ".join("**%d**" % c[3] for c in cols) + " |"
        lines.append(header)
        lines.append(sep)
        lines.append(script_row)
        lines.append(route_row)
        lines.append(total_row)

    # --- Used Scripts Summary ---
    if data["used_scripts"]:
        lines.append("\n---\n")
        lines.append("## Used Scripts Summary (%d scripts)\n" % len(data["used_scripts"]))
        lines.append("| Script | Referenced By | Errors | Warnings | Info |")
        lines.append("|---|---|---|---|---|")
        for gf, sources in data["used_scripts"].items():
            name = Path(gf).name
            findings = data["script_findings"].get(gf, [])
            e = sum(1 for f in findings if f["severity"] == "ERROR")
            w = sum(1 for f in findings if f["severity"] == "WARN")
            i = sum(1 for f in findings if f["severity"] == "INFO")
            lines.append(f"| `{name}` | {', '.join(sources[:3])}{'...' if len(sources) > 3 else ''} | {e} | {w} | {i} |")

    # --- Unused Scripts Summary ---
    if data["unused_scripts"]:
        lines.append("\n---\n")
        lines.append("## Unused Scripts (%d scripts)\n" % len(data["unused_scripts"]))
        lines.append("Not referenced in any config file (may be indirectly used).\n")
        lines.append("| Script | Path | Errors | Warnings | Info |")
        lines.append("|---|---|---|---|---|")
        base = Path(data["directory"])
        for gf in data["unused_scripts"]:
            findings = data["unused_findings"].get(gf, [])
            e = sum(1 for f in findings if f["severity"] == "ERROR")
            w = sum(1 for f in findings if f["severity"] == "WARN")
            i = sum(1 for f in findings if f["severity"] == "INFO")
            try:
                rel = Path(gf).relative_to(base)
            except ValueError:
                rel = gf
            lines.append(f"| `{Path(gf).name}` | `{rel}` | {e} | {w} | {i} |")

    # --- Script Issues Detail ---
    for section_title, findings_dict, ref_dict in [
        ("Used Scripts — Issues Found", data["script_findings"], data["used_scripts"]),
        ("Unused Scripts — Issues Found", data["unused_findings"], {}),
    ]:
        if not findings_dict:
            continue
        total_f = sum(len(fl) for fl in findings_dict.values())
        lines.append("\n---\n")
        lines.append("## %s (%d files, %d findings)\n" % (section_title, len(findings_dict), total_f))
        for gf, findings in findings_dict.items():
            name = Path(gf).name
            lines.append(f"### `{name}`")
            lines.append(f"- **Path:** `{gf}`")
            refs = ref_dict.get(gf, [])
            if refs:
                lines.append(f"- **Referenced by:** {', '.join(refs)}")
            lines.append("")
            lines.append("| Line | Severity | Rule | Issue | Fix |")
            lines.append("|---|---|---|---|---|")
            for f in findings:
                lines.append(f"| {f['line']} | **{f['severity']}** | {f['rule']} | {f['description']} | {f['fix']} |")
            lines.append("")
            lines.append("<details><summary>Affected lines</summary>\n")
            lines.append("```groovy")
            for f in findings:
                lines.append(f"// Line {f['line']}: [{f['severity']}] {f['rule']}")
                lines.append(f"{f['text']}")
            lines.append("```\n</details>\n")

    # --- Route Config Issues ---
    if data["route_findings"]:
        total_rf = sum(len(fl) for fl in data["route_findings"].values())
        lines.append("\n---\n")
        lines.append("## Route Config Issues (%d routes, %d findings)\n" % (len(data["route_findings"]), total_rf))
        for rf, findings in data["route_findings"].items():
            name = Path(rf).name
            lines.append(f"### `{name}`")
            lines.append(f"- **Path:** `{rf}`\n")
            lines.append("| Line | Severity | Rule | Issue | Fix |")
            lines.append("|---|---|---|---|---|")
            for f in findings:
                ln = f['line'] if f['line'] else "-"
                lines.append(f"| {ln} | **{f['severity']}** | {f['rule']} | {f['description']} | {f['fix']} |")
            lines.append("")
            affected = [f for f in findings if f.get('text')]
            if affected:
                lines.append("<details><summary>Affected lines</summary>\n")
                lines.append("```json")
                for f in affected:
                    lines.append("// Line %s: [%s] %s" % (f['line'], f['severity'], f['rule']))
                    lines.append(f['text'])
                lines.append("```\n</details>\n")

    # --- Clean scripts ---
    used_clean = [gf for gf in data["used_scripts"] if gf not in data["script_findings"]]
    if used_clean:
        lines.append("\n---\n")
        lines.append("## Used Scripts — No Issues Found (%d scripts)\n" % len(used_clean))
        for gf in used_clean:
            refs = data["used_scripts"].get(gf, [])
            lines.append(f"- `{Path(gf).name}` ({', '.join(refs)})")

    # --- Statistics ---
    if data["rule_counts"]:
        lines.append("\n---\n")
        lines.append("## Statistics (%d rules triggered)\n" % len(data["rule_counts"]))
        lines.append("| Rule | Count | Description |")
        lines.append("|---|---|---|")
        rule_descs = {r[0]: r[3] for r in RULES}
        # RT rules
        rule_descs["RT-001"] = "Duplicate handler declarations"
        rule_descs["RT-002"] = "Missing required config fields"
        rule_descs["RT-101"] = "Duplicate route name/ID"
        rule_descs["RT-102"] = "Deprecated matches() in condition"
        rule_descs["RT-103"] = "Deprecated expression in ${...}"
        rule_descs["G4-106"] = "Removed class usage (XmlSlurper, XmlParser, etc.)"
        for rule, count in sorted(data["rule_counts"].items()):
            desc = rule_descs.get(rule, "")
            lines.append(f"| {rule} | {count} | {desc} |")

    # --- Path References ---
    if data.get("path_refs"):
        lines.append("\n---\n")
        lines.append("## Path References (%d unique paths)\n" % len(data["path_refs"]))
        lines.append("| Path | Count | Referenced In |")
        lines.append("|---|---|---|")
        for path, refs in sorted(data["path_refs"].items(), key=lambda x: -len(x[1])):
            files = sorted(set(r["file"] for r in refs))
            files_str = ", ".join(files[:5])
            if len(files) > 5:
                files_str += "..."
            lines.append("| `%s` | %d | %s |" % (path, len(refs), files_str))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON report formatter
# ---------------------------------------------------------------------------
def format_json(data):
    output = {
        "directory": data["directory"],
        "summary": {
            "groovy_files": data["groovy_count"],
            "config_files": data["config_count"],
            "route_files": data["route_count"],
            "used_scripts": len(data["used_scripts"]),
            "unused_scripts": len(data["unused_scripts"]),
            "script_errors": data["script_errors"],
            "script_warnings": data["script_warnings"],
            "route_errors": data["route_errors"],
            "route_warnings": data["route_warnings"],
        },
        "script_findings": data["script_findings"],
        "unused_findings": data["unused_findings"],
        "route_findings": data["route_findings"],
        "rule_counts": data["rule_counts"],
    }
    return json.dumps(output, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Analyze IG scripts and routes for PingGateway 2024.11 (Groovy 4) migration"
    )
    parser.add_argument("directory", help="IG instance directory (e.g., /opt/forgerock/.openig)")
    parser.add_argument("--output", "-o", help="Save report to file")
    parser.add_argument("--severity", "-s", choices=["ERROR", "WARN", "INFO"],
                        help="Only show findings at or above this severity")
    parser.add_argument("--format", "-f", choices=["markdown", "json"], default="markdown",
                        help="Output format (default: markdown)")
    args = parser.parse_args()

    base_dir = Path(args.directory)
    if not base_dir.is_dir():
        print(f"Error: {base_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    min_severity = SEVERITY_ORDER.get(args.severity, 0) if args.severity else 0
    data = collect_analysis(base_dir, min_severity)

    if args.format == "json":
        report = format_json(data)
    else:
        report = format_markdown(data)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Report saved to {args.output}")
    else:
        print(report)

    total_errors = data["script_errors"] + data["route_errors"]
    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    main()
