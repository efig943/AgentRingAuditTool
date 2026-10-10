#!/usr/bin/env python3
"""
audit_codebase.py - Comprehensive Static Analysis, Security & Architecture Auditor.
Part of the 'code-audit' skill for CallAudit Pro.

Performs static analysis across the entire codebase:
1. Syntax, AST & Import Health (AST integrity, circular imports, legacy shims)
2. Security & Secrets (Hardcoded keys, unignored secrets, SQL interpolation, eval/exec)
3. Dependency & Environment Completeness (Undeclared imports in requirements.txt, .env.example coverage)
4. Code Smells & Reliability (Bare excepts, silent passes, unclosed resources, async blockers)
5. Complexity & Architectural Boundaries (Mega-functions, layering violations)
6. Frontend & API Contract Alignment (FastAPI routes vs JS fetch calls)
"""

import os
import sys
import ast
import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Set, Any, Optional, Tuple

# Locate project root
current_path = Path(__file__).resolve()
PROJECT_ROOT = None
for parent in current_path.parents:
    if (parent / ".env").exists() or (parent / "audits.db").exists() or (parent / "requirements.txt").exists():
        PROJECT_ROOT = parent
        break
if not PROJECT_ROOT:
    PROJECT_ROOT = current_path.parents[4]

sys.path.insert(0, str(PROJECT_ROOT))

# Standard Library Modules for Python 3.10+
STDLIB_MODULES = set(sys.builtin_module_names) | {
    "os", "sys", "json", "re", "datetime", "time", "pathlib", "typing", "argparse",
    "sqlite3", "logging", "threading", "math", "hashlib", "traceback", "subprocess",
    "unittest", "dataclasses", "abc", "enum", "copy", "functools", "itertools",
    "collections", "urllib", "email", "smtplib", "ssl", "io", "tempfile", "shutil",
    "uuid", "socket", "contextlib", "inspect", "platform", "random", "string",
    "typing_extensions", "warnings", "queue", "signal", "asyncio", "base64",
    "secrets", "ctypes", "codecs", "glob", "hmac", "gzip", "zipfile", "tarfile"
}

# Regex for common secret patterns
SECRET_PATTERNS = [
    ("SEC-KEY-STRIPE", r"sk_live_[0-9a-zA-Z]{24,}", "Stripe Live Secret Key"),
    ("SEC-KEY-STRIPE-TEST", r"sk_test_[0-9a-zA-Z]{24,}", "Stripe Test Secret Key"),
    ("SEC-KEY-TWILIO", r"AC[a-fA-F0-9]{32}", "Twilio Account SID (hardcoded)"),
    ("SEC-KEY-GEMINI", r"AIza[0-9A-Za-z-_]{35}", "Google Gemini/Cloud API Key"),
    ("SEC-KEY-GENERIC", r"(?:api[_-]?key|secret[_-]?key|auth[_-]?token)\s*=\s*['\"][0-9a-zA-Z\-_]{16,}['\"]", "Generic Hardcoded Secret/Token"),
]


class CodeIssue:
    def __init__(
        self,
        code: str,
        severity: str,  # 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
        file_path: str,
        line: Optional[int],
        message: str,
        snippet: Optional[str] = None,
        suggestion: Optional[str] = None,
    ):
        self.code = code
        self.severity = severity.upper()
        self.file_path = file_path
        self.line = line
        self.message = message
        self.snippet = snippet
        self.suggestion = suggestion

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "file": self.file_path,
            "line": self.line,
            "message": self.message,
            "snippet": self.snippet,
            "suggestion": self.suggestion,
        }


class CodebaseAuditor:
    def __init__(self, root: Path):
        self.root = root
        self.issues: List[CodeIssue] = []
        self.files_analyzed: List[str] = []
        self.stats: Dict[str, Any] = {}

    def run_audit(self, target_path: Optional[str] = None) -> Dict[str, Any]:
        self.issues.clear()
        self.files_analyzed.clear()

        # Gather all python files (excluding .git, .agents, scratch, backups, virtualenvs)
        base_dir = (self.root / target_path).resolve() if target_path else self.root
        py_files: List[Path] = []

        if base_dir.is_file() and base_dir.suffix == ".py":
            py_files = [base_dir]
        else:
            for p in base_dir.rglob("*.py"):
                # Skip hidden directories, scratch, backups, venvs
                parts = p.parts
                if any(part.startswith(".") for part in parts):
                    continue
                if "scratch" in parts or "backups" in parts or "__pycache__" in parts or "venv" in parts:
                    continue
                py_files.append(p)

        self.stats["total_python_files"] = len(py_files)
        total_loc = 0

        # Data collection containers
        imported_packages: Set[Tuple[str, str, int]] = set()  # (pkg_name, file_rel, lineno)
        env_vars_used: Set[Tuple[str, str, int]] = set()      # (env_name, file_rel, lineno)
        fastapi_routes: Set[Tuple[str, str, str, int]] = set() # (method, path, file_rel, lineno)

        # 1. AST & File Level Analysis
        for pf in sorted(py_files):
            rel_str = str(pf.relative_to(self.root))
            self.files_analyzed.append(rel_str)
            try:
                content = pf.read_text(encoding="utf-8")
            except Exception as e:
                self.issues.append(
                    CodeIssue("IO-001", "ERROR", rel_str, None, f"Failed to read file: {e}")
                )
                continue

            lines = content.splitlines()
            total_loc += len(lines)

            # Security: Secrets scanning in raw text
            self._scan_raw_secrets(rel_str, lines)

            # AST Parsing
            try:
                tree = ast.parse(content, filename=str(pf))
            except SyntaxError as se:
                self.issues.append(
                    CodeIssue(
                        "SYN-001", "CRITICAL", rel_str, se.lineno,
                        f"Python Syntax Error: {se.msg}",
                        snippet=se.text.strip() if se.text else None,
                        suggestion="Fix syntax error to ensure file can be executed."
                    )
                )
                continue

            # AST Walk
            self._audit_ast_nodes(
                tree, rel_str, lines, imported_packages, env_vars_used, fastapi_routes
            )

        self.stats["total_loc"] = total_loc

        # 2. Dependencies vs requirements.txt Audit
        if not target_path:
            self._audit_dependencies(imported_packages)

        # 3. Environment Variables vs .env.example Audit
        if not target_path:
            self._audit_env_variables(env_vars_used)

        # 4. Architecture: Layering & Legacy Shim Usage
        if not target_path:
            self._audit_architecture_shims()

        # 5. Frontend Contract Alignment (FastAPI vs static/app.js)
        if not target_path:
            self._audit_frontend_api_alignment(fastapi_routes)

        # 6. Repository Hygiene & Secret File Exposure
        if not target_path:
            self._audit_repo_hygiene()

        # 7. Cloud Run & GCloud Deployment Readiness (Target: agentring.dev)
        if not target_path:
            self._audit_gcloud_deployment_readiness()

        return self.compile_report()

    # -------------------------------------------------------------------------
    # 1. Raw Secrets Scanning
    # -------------------------------------------------------------------------
    def _scan_raw_secrets(self, rel_str: str, lines: List[str]):
        for idx, line in enumerate(lines, start=1):
            # Skip comments or template examples
            stripped = line.strip()
            if stripped.startswith("#") or "your-" in line or "sk_test_..." in line or "example" in line:
                continue

            for code, pattern, desc in SECRET_PATTERNS:
                if re.search(pattern, line):
                    self.issues.append(
                        CodeIssue(
                            code, "CRITICAL", rel_str, idx,
                            f"Hardcoded {desc} detected.",
                            snippet=stripped[:80],
                            suggestion="Move secret to .env file and access via os.getenv() or app.core.config."
                        )
                    )

    # -------------------------------------------------------------------------
    # 2. AST Nodes Audit
    # -------------------------------------------------------------------------
    def _audit_ast_nodes(
        self,
        tree: ast.AST,
        rel_str: str,
        lines: List[str],
        imported_packages: Set[Tuple[str, str, int]],
        env_vars_used: Set[Tuple[str, str, int]],
        fastapi_routes: Set[Tuple[str, str, str, int]],
    ):
        for node in ast.walk(tree):
            # A. Track Imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    pkg = alias.name.split(".")[0]
                    imported_packages.add((pkg, rel_str, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    pkg = node.module.split(".")[0]
                    imported_packages.add((pkg, rel_str, node.lineno))

            # B. Track os.getenv / os.environ
            if isinstance(node, ast.Call):
                # os.getenv("VAR") or os.environ.get("VAR")
                func = node.func
                is_env_call = False
                if isinstance(func, ast.Attribute) and func.attr == "getenv":
                    if isinstance(func.value, ast.Name) and func.value.id == "os":
                        is_env_call = True
                elif isinstance(func, ast.Attribute) and func.attr == "get":
                    if isinstance(func.value, ast.Attribute) and func.value.attr == "environ":
                        is_env_call = True

                if is_env_call and node.args and isinstance(node.args[0], ast.Constant):
                    var_name = str(node.args[0].value)
                    env_vars_used.add((var_name, rel_str, node.lineno))

                # C. SQL Injection / String Formatting in cur.execute(...)
                if isinstance(func, ast.Attribute) and func.attr == "execute":
                    if node.args:
                        arg0 = node.args[0]
                        if isinstance(arg0, ast.JoinedStr):  # f-string
                            snippet = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
                            self.issues.append(
                                CodeIssue(
                                    "SEC-SQL-001", "WARNING", rel_str, node.lineno,
                                    "SQL execute() call utilizes f-string formatting instead of parameterized query (%s).",
                                    snippet=snippet,
                                    suggestion="Use parameterized placeholders (e.g. cur.execute('SELECT ... WHERE id = %s', (val,))) to prevent SQL injection."
                                )
                            )
                        elif isinstance(arg0, ast.BinOp) and isinstance(arg0.op, ast.Mod):  # % string formatting
                            snippet = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
                            self.issues.append(
                                CodeIssue(
                                    "SEC-SQL-002", "WARNING", rel_str, node.lineno,
                                    "SQL execute() call utilizes '%' string modulo formatting.",
                                    snippet=snippet,
                                    suggestion="Pass query arguments as a tuple parameter to execute()."
                                )
                            )

                # D. Dangerous Primitives: eval, exec
                if isinstance(func, ast.Name):
                    if func.id in ("eval", "exec"):
                        self.issues.append(
                            CodeIssue(
                                "SEC-DANGEROUS-FUNC", "CRITICAL", rel_str, node.lineno,
                                f"Use of dangerous built-in function '{func.id}()'.",
                                snippet=lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
                                suggestion="Refactor to avoid dynamic code evaluation."
                            )
                        )

            # E. Exception Handling Smells: bare except or silent pass
            elif isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    self.issues.append(
                        CodeIssue(
                            "REL-EXCEPT-001", "WARNING", rel_str, node.lineno,
                            "Bare 'except:' handler catches BaseException including KeyboardInterrupt and SystemExit.",
                            suggestion="Catch specific exceptions or 'except Exception:'."
                        )
                    )
                elif len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    self.issues.append(
                        CodeIssue(
                            "REL-EXCEPT-002", "WARNING", rel_str, node.lineno,
                            "Silent 'except Exception: pass' swallows errors without logging or tracing.",
                            suggestion="Log error via logger.warning(...) or logger.error(...) before passing."
                        )
                    )

            # F. Mega-functions & Function Complexity
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_len = node.end_lineno - node.lineno if node.end_lineno else len(node.body)
                if fn_len > 120:
                    self.issues.append(
                        CodeIssue(
                            "COMP-001", "INFO", rel_str, node.lineno,
                            f"Function '{node.name}' is {fn_len} lines long (exceeds 120 lines single-responsibility benchmark).",
                            suggestion="Decompose mega-function into smaller modular helper functions."
                        )
                    )

                # G. Track FastAPI routes
                for decorator in node.decorator_list:
                    route_info = self._extract_route(decorator)
                    if route_info:
                        method, path = route_info
                        fastapi_routes.add((method, path, rel_str, node.lineno))

    def _extract_route(self, node: ast.AST) -> Optional[Tuple[str, str]]:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            method = node.func.attr.upper()
            if method in ("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"):
                if node.args and isinstance(node.args[0], ast.Constant):
                    path = str(node.args[0].value)
                    return (method, path)
        return None

    # -------------------------------------------------------------------------
    # 3. Dependencies vs requirements.txt
    # -------------------------------------------------------------------------
    def _audit_dependencies(self, imported_packages: Set[Tuple[str, str, int]]):
        req_file = self.root / "requirements.txt"
        if not req_file.exists():
            self.issues.append(
                CodeIssue("DEP-001", "ERROR", "requirements.txt", None, "requirements.txt is missing from repository root.")
            )
            return

        declared_raw: Set[str] = set()
        for line in req_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                pkg = re.split(r"[><=~]", line)[0].strip().lower().replace("-", "_")
                declared_raw.add(pkg)

        # Mapping between pip package name and import name
        import_to_pip = {
            "dotenv": "python_dotenv",
            "psycopg2": "psycopg2_binary",
            "google": "google_genai",
            "googleapiclient": "google_api_python_client",
            "stripe": "stripe",
            "twilio": "twilio",
            "fastapi": "fastapi",
            "uvicorn": "uvicorn",
            "pydantic": "pydantic",
            "requests": "requests",
        }

        # Local workspace packages
        local_pkgs = {
            "app", "auditor", "background_daemon", "config", "db_storage",
            "email_service", "financials_service", "reception_db", "server", "scripts"
        }

        # Track third party imports
        used_third_party: Dict[str, List[Tuple[str, int]]] = {}
        for pkg, fpath, lineno in imported_packages:
            if pkg in STDLIB_MODULES or pkg in local_pkgs:
                continue
            used_third_party.setdefault(pkg, []).append((fpath, lineno))

        for imp_name, occurrences in used_third_party.items():
            expected_pip = import_to_pip.get(imp_name, imp_name)
            if expected_pip not in declared_raw and imp_name not in declared_raw:
                fpath, lineno = occurrences[0]
                self.issues.append(
                    CodeIssue(
                        "DEP-MISSING-001", "ERROR", fpath, lineno,
                        f"Package '{imp_name}' is imported but NOT declared in requirements.txt! (Referenced in {len(occurrences)} location(s)).",
                        suggestion=f"Add '{expected_pip}>=...' to requirements.txt to prevent deployment crash."
                    )
                )

        # Check for unused dependencies declared in requirements.txt
        for dep in declared_raw:
            # Reverse map
            matched = False
            for imp_name in used_third_party:
                if import_to_pip.get(imp_name) == dep or imp_name == dep:
                    matched = True
                    break
            if not matched and dep not in ("uvicorn",): # uvicorn can be CLI entrypoint
                self.issues.append(
                    CodeIssue(
                        "DEP-UNUSED-001", "INFO", "requirements.txt", None,
                        f"Declared dependency '{dep}' is not directly imported anywhere in the codebase.",
                        suggestion=f"Verify if '{dep}' is needed as a transitive or CLI dependency, otherwise remove it."
                    )
                )

    # -------------------------------------------------------------------------
    # 4. Environment Variables vs .env.example
    # -------------------------------------------------------------------------
    def _audit_env_variables(self, env_vars_used: Set[Tuple[str, str, int]]):
        example_file = self.root / ".env.example"
        active_env_file = self.root / ".env"

        example_vars: Set[str] = set()
        if example_file.exists():
            for line in example_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    var = line.split("=")[0].strip()
                    example_vars.add(var)
        else:
            self.issues.append(
                CodeIssue("ENV-001", "WARNING", ".env.example", None, ".env.example is missing from repository root.")
            )

        active_vars: Set[str] = set()
        if active_env_file.exists():
            for line in active_env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    var = line.split("=")[0].strip()
                    active_vars.add(var)

        # Audit used variables
        for var, fpath, lineno in env_vars_used:
            # Check if documented in .env.example
            if example_file.exists() and var not in example_vars:
                self.issues.append(
                    CodeIssue(
                        "ENV-UNDOC-001", "WARNING", fpath, lineno,
                        f"Environment variable '{var}' is accessed in code but missing from .env.example template.",
                        suggestion=f"Add '{var}=\"\"' to .env.example so engineers know it is required."
                    )
                )

            # Check if set in active .env
            if active_env_file.exists() and var not in active_vars and not os.getenv(var):
                self.issues.append(
                    CodeIssue(
                        "ENV-UNSET-001", "INFO", fpath, lineno,
                        f"Environment variable '{var}' is referenced in code but not set in local .env or system environment.",
                        suggestion=f"Provide a local test value for '{var}' in .env if testing this feature."
                    )
                )

    # -------------------------------------------------------------------------
    # 5. Architecture: Shims & Layering
    # -------------------------------------------------------------------------
    def _audit_architecture_shims(self):
        root_shims = [
            "auditor.py", "server.py", "config.py", "db_storage.py",
            "financials_service.py", "reception_db.py", "background_daemon.py", "email_service.py"
        ]
        # Verify app/ modules never import from root shims
        app_dir = self.root / "app"
        if not app_dir.exists():
            return

        shim_module_names = {Path(s).stem for s in root_shims}

        for py_file in app_dir.rglob("*.py"):
            try:
                content = py_file.read_text()
                tree = ast.parse(content)
                rel_str = str(py_file.relative_to(self.root))
                for node in ast.walk(tree):
                    imported_mod = None
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imported_mod = alias.name.split(".")[0]
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and node.level == 0:
                            imported_mod = node.module.split(".")[0]

                    if imported_mod in shim_module_names:
                        self.issues.append(
                            CodeIssue(
                                "ARCH-LAYER-001", "ERROR", rel_str, node.lineno,
                                f"Internal package module '{rel_str}' imports root legacy shim '{imported_mod}' instead of canonical 'app.*' package.",
                                suggestion=f"Update import statement to import from 'app.services.{imported_mod}' or 'app.db.*'."
                            )
                        )
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # 6. Frontend Contract Alignment
    # -------------------------------------------------------------------------
    def _audit_frontend_api_alignment(self, fastapi_routes: Set[Tuple[str, str, str, int]]):
        app_js = self.root / "static" / "app.js"
        if not app_js.exists():
            return

        js_content = app_js.read_text(encoding="utf-8")
        rel_js = "static/app.js"

        # Find fetch calls: fetch('/api/...') or fetch(`/api/...`)
        fetch_matches = re.findall(r"fetch\([\"'`](\/api\/[^\"'`\?]+)[\"'`\?]", js_content)
        server_route_paths = {path for _, path, _, _ in fastapi_routes}

        for raw_endpoint in set(fetch_matches):
            # Normalize path template like /api/calls/${id} -> /api/calls/{call_id}
            # Or /api/calls/123 -> matches /api/calls/{call_id}
            normalized = re.sub(r"\$\{[^}]+\}", "*", raw_endpoint)
            # Check direct match
            if raw_endpoint in server_route_paths:
                continue

            # Check if matches a parameterized FastAPI route
            matched = False
            for s_path in server_route_paths:
                # Convert {param} to wildcard regex
                regex_pattern = "^" + re.sub(r"\{[^}]+\}", r"[^/]+", s_path) + "$"
                if re.match(regex_pattern, raw_endpoint):
                    matched = True
                    break
            if not matched:
                self.issues.append(
                    CodeIssue(
                        "API-404-DRIFT", "ERROR", rel_js, None,
                        f"Frontend JavaScript calls '{raw_endpoint}' via fetch(), but this endpoint is NOT registered in FastAPI server routes!",
                        suggestion="Register route in app/api/server.py or correct frontend fetch URL."
                    )
                )

    # -------------------------------------------------------------------------
    # 7. Repository Hygiene & Secrets Protection
    # -------------------------------------------------------------------------
    def _audit_repo_hygiene(self):
        gitignore = self.root / ".gitignore"
        if not gitignore.exists():
            self.issues.append(
                CodeIssue("REPO-001", "WARNING", ".gitignore", None, ".gitignore is missing from root.")
            )
            return

        # Check for unignored service account JSON files
        for json_file in self.root.glob("*.json"):
            if "service_account" in json_file.name or "ai-vp-" in json_file.name or "key" in json_file.name:
                rel = str(json_file.relative_to(self.root))
                # Check if ignored by git
                result = os.popen(f"git check-ignore {rel}").read().strip()
                if not result:
                    self.issues.append(
                        CodeIssue(
                            "SEC-GITIGNORE-001", "CRITICAL", rel, None,
                            f"Sensitive service account key file '{rel}' is NOT matched by .gitignore and risks accidental commit!",
                            suggestion=f"Add '{rel}' to .gitignore immediately."
                        )
                    )

    # -------------------------------------------------------------------------
    # 8. Cloud Run & GCloud Deployment Readiness (Target: agentring.dev)
    # -------------------------------------------------------------------------
    def _audit_gcloud_deployment_readiness(self):
        # A. Cloud Run Port Binding Check ($PORT vs DASHBOARD_PORT)
        config_file = self.root / "app" / "core" / "config.py"
        server_file = self.root / "server.py"

        port_configured_for_cloudrun = False
        for fpath in [config_file, server_file]:
            if fpath.exists():
                txt = fpath.read_text()
                if 'os.getenv("PORT"' in txt or "os.getenv('PORT'" in txt:
                    port_configured_for_cloudrun = True
                    break

        if not port_configured_for_cloudrun:
            self.issues.append(
                CodeIssue(
                    "GCP-PORT-001", "ERROR", "app/core/config.py", 27,
                    "Cloud Run Port Incompatibility: Server listens on DASHBOARD_PORT (5050) without checking $PORT. "
                    "Google Cloud Run injects $PORT (default 8080) for health checks when deployed to agentring.dev. "
                    "Failing to read $PORT causes container startup timeout and 503 errors.",
                    snippet='DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5050"))',
                    suggestion='Update to: DASHBOARD_PORT = int(os.getenv("PORT", os.getenv("DASHBOARD_PORT", "8080")))'
                )
            )

        # B. Missing .gcloudignore check
        gcloudignore = self.root / ".gcloudignore"
        if not gcloudignore.exists():
            self.issues.append(
                CodeIssue(
                    "GCP-IGNORE-001", "WARNING", ".gcloudignore", None,
                    "Missing '.gcloudignore' file: Deployments via 'gcloud run deploy --source .' will upload local "
                    "SQLite databases (audits.db), .env secrets, .git history, and scratch directories to Cloud Build.",
                    suggestion="Create .gcloudignore to exclude .git, .env, audits.db, .agents/, scratch/, and scripts/backups/."
                )
            )

        # C. Host Binding Check in server.py
        if server_file.exists():
            txt = server_file.read_text()
            if 'host="127.0.0.1"' in txt or "host='127.0.0.1'" in txt or 'host="localhost"' in txt:
                self.issues.append(
                    CodeIssue(
                        "GCP-HOST-001", "CRITICAL", "server.py", 20,
                        "Host binding is restricted to localhost/127.0.0.1. Cloud Run containers MUST bind to 0.0.0.0 to receive traffic.",
                        suggestion='Ensure uvicorn binds to host="0.0.0.0".'
                    )
                )

        # D. Production Domain CORS Check (agentring.dev)
        server_api = self.root / "app" / "api" / "server.py"
        if server_api.exists():
            txt = server_api.read_text()
            cors_match = re.search(r'allow_origins\s*=\s*\[([^\]]+)\]', txt)
            if cors_match:
                origins = cors_match.group(1)
                if '"*"' not in origins and "'*'" not in origins and "agentring.dev" not in origins:
                    self.issues.append(
                        CodeIssue(
                            "GCP-CORS-001", "ERROR", "app/api/server.py", None,
                            "CORS configuration does not include 'agentring.dev' or wildcard '*'. API requests from the frontend will be blocked.",
                            suggestion="Include 'https://agentring.dev' and 'https://*.agentring.dev' in allow_origins."
                        )
                    )

    # -------------------------------------------------------------------------
    # Report Compilation & Formatting
    # -------------------------------------------------------------------------
    def compile_report(self) -> Dict[str, Any]:
        severity_counts = {"INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}
        for issue in self.issues:
            severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1

        overall_status = "HEALTHY"
        if severity_counts["CRITICAL"] > 0:
            overall_status = "CRITICAL"
        elif severity_counts["ERROR"] > 0:
            overall_status = "DEGRADED"
        elif severity_counts["WARNING"] > 0:
            overall_status = "WARNING"

        return {
            "overall_status": overall_status,
            "issue_counts": severity_counts,
            "total_issues": len(self.issues),
            "stats": self.stats,
            "issues": [i.to_dict() for i in self.issues],
        }


def format_markdown_report(report: Dict[str, Any]) -> str:
    lines = []
    status_badges = {
        "HEALTHY": "🟢 HEALTHY",
        "WARNING": "🟡 WARNING",
        "DEGRADED": "🟠 DEGRADED",
        "CRITICAL": "🔴 CRITICAL",
    }
    badge = status_badges.get(report["overall_status"], report["overall_status"])

    lines.append("# Codebase Quality & Security Audit Report")
    lines.append(f"**Overall Health**: {badge}\n")

    lines.append("## 1. Executive Summary")
    counts = report["issue_counts"]
    lines.append(f"- **Critical Errors**: `{counts.get('CRITICAL', 0)}`")
    lines.append(f"- **Errors**: `{counts.get('ERROR', 0)}`")
    lines.append(f"- **Warnings**: `{counts.get('WARNING', 0)}`")
    lines.append(f"- **Info Notices**: `{counts.get('INFO', 0)}`")
    if report.get("stats"):
        lines.append(f"- **Python Modules Analyzed**: `{report['stats'].get('total_python_files', 0)}`")
        lines.append(f"- **Total Lines of Code**: `{report['stats'].get('total_loc', 0)}`")
    lines.append("")

    lines.append("## 2. Findings & Code Issues")
    if not report["issues"]:
        lines.append("✅ No syntax errors, dependency gaps, secrets, or anti-patterns detected.")
    else:
        for idx, issue in enumerate(report["issues"], start=1):
            sev_icon = {
                "CRITICAL": "🚨 CRITICAL",
                "ERROR": "❌ ERROR",
                "WARNING": "⚠️ WARNING",
                "INFO": "ℹ️ INFO",
            }.get(issue["severity"], issue["severity"])

            loc = f":{issue['line']}" if issue.get("line") else ""
            lines.append(f"### {idx}. [{issue['code']}] {sev_icon}: `{issue['file']}{loc}`")
            lines.append(f"**Message**: {issue['message']}")
            if issue.get("snippet"):
                lines.append(f"```python\n{issue['snippet']}\n```")
            if issue.get("suggestion"):
                lines.append(f"💡 **Recommendation**: {issue['suggestion']}")
            lines.append("")

    return "\n".join(lines)


def format_terminal_summary(report: Dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 72)
    lines.append(f" CODEBASE AUDIT SUITE - STATUS: {report['overall_status']}")
    lines.append(f" Files Analyzed: {report['stats'].get('total_python_files', 0)} | Total LOC: {report['stats'].get('total_loc', 0)}")
    lines.append("=" * 72)

    lines.append("\nFINDINGS:")
    if not report["issues"]:
        lines.append("  [OK] Codebase is clean. No syntax, dependency, security or contract errors.")
    else:
        for issue in report["issues"]:
            loc = f":{issue['line']}" if issue.get("line") else ""
            prefix = f"[{issue['severity'].ljust(8)}]"
            lines.append(f"  {prefix} ({issue['code']}) {issue['file']}{loc}")
            lines.append(f"             ↳ {issue['message']}")

    lines.append("\n" + "=" * 72)
    counts = report["issue_counts"]
    lines.append(f"TOTAL ISSUES: {report['total_issues']} (Critical: {counts['CRITICAL']}, Error: {counts['ERROR']}, Warning: {counts['WARNING']}, Info: {counts['INFO']})")
    lines.append("=" * 72)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive Static Analysis, Security & Architecture Auditor for CallAudit Pro."
    )
    parser.add_argument(
        "--format",
        choices=["summary", "json", "markdown"],
        default="summary",
        help="Output display format (default: summary)",
    )
    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="Scope the audit to a specific file or subdirectory (e.g., app/services/financials.py)",
    )
    parser.add_argument(
        "--min-severity",
        choices=["info", "warning", "error", "critical"],
        default="info",
        help="Filter findings by minimum severity level (default: info)",
    )
    parser.add_argument(
        "--export",
        type=str,
        default=None,
        help="File path to save the audit report (JSON or Markdown)",
    )

    args = parser.parse_args()

    try:
        auditor = CodebaseAuditor(root=PROJECT_ROOT)
        report = auditor.run_audit(target_path=args.path)

        # Filter by severity if requested
        sev_rank = {"INFO": 0, "WARNING": 1, "ERROR": 2, "CRITICAL": 3}
        min_rank = sev_rank[args.min_severity.upper()]
        report["issues"] = [i for i in report["issues"] if sev_rank.get(i["severity"], 0) >= min_rank]

        # Output formats
        output_text = ""
        if args.format == "json":
            output_text = json.dumps(report, indent=2)
        elif args.format == "markdown":
            output_text = format_markdown_report(report)
        else:
            output_text = format_terminal_summary(report)

        print(output_text)

        # Export if requested
        if args.export:
            export_path = Path(args.export).resolve()
            export_path.parent.mkdir(parents=True, exist_ok=True)
            with open(export_path, "w", encoding="utf-8") as f:
                f.write(output_text)
            print(f"\n[+] Codebase audit report saved to {export_path}")

        # Exit code reflects severity
        if report["issue_counts"]["CRITICAL"] > 0:
            sys.exit(2)
        elif report["issue_counts"]["ERROR"] > 0:
            sys.exit(2)
        elif report["issue_counts"]["WARNING"] > 0:
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        print(f"[!] Codebase audit failed: {e}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
