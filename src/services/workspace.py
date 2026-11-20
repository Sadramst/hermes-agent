"""Sandboxed multi-project workspace manager for the Mini PC Personal Brain stack."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from utils.settings import DEFAULT_WORKSPACE_ALLOWED_CMDS

IGNORED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".next",
        ".nuxt",
    }
)
SECRET_EXACT_NAMES: frozenset[str] = frozenset(
    {
        ".env",
        "auth.json",
        "credentials.json",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "id_dsa",
        ".npmrc",
        ".pypirc",
        ".netrc",
    }
)
SECRET_EXTENSIONS: frozenset[str] = frozenset({".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".kdbx"})

MAX_READ_CHARS = 16_000
MAX_WRITE_CHARS = 200_000
MAX_EXEC_OUTPUT_CHARS = 16_000
DEFAULT_EXEC_TIMEOUT = 30
MAX_EXEC_TIMEOUT = 120
MAX_SEARCH_FILE_BYTES = 512_000
_PROJECT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_DESTRUCTIVE_COMMANDS = frozenset(
    {"rm", "rmdir", "shred", "dd", "mkfs", "sudo", "su", "shutdown", "reboot", "poweroff"}
)


class WorkspaceDisabledError(PermissionError):
    """Raised when workspace operations are requested while HERMES_WORKSPACE_MODE is off."""


class WorkspacePermissionError(PermissionError):
    """Raised when a workspace action violates read-only mode, allowlists, or secret boundaries."""


class WorkspaceConfirmationRequired(RuntimeError):
    """Raised when an execution request matches a destructive pattern needing human sign-off."""


def is_secret_path(rel_path: Path) -> bool:
    """Return True when any path component targets .git metadata or a secret credential file."""
    for part in rel_path.parts:
        lower = part.lower()
        if lower == ".git" or lower in SECRET_EXACT_NAMES:
            return True
        if Path(lower).suffix in SECRET_EXTENSIONS:
            return True
        if lower.startswith(".env.") and not lower.endswith((".example", ".sample")):
            return True
    return False


class WorkspaceManager:
    """Path-jailed file and allowlisted-command interface across projects under `root`."""

    def __init__(
        self,
        root: str | Path | None,
        mode: str = "off",
        allowed_cmds: tuple[str, ...] = DEFAULT_WORKSPACE_ALLOWED_CMDS,
    ) -> None:
        self.root = Path(root) if root else None
        self.mode = mode if mode in {"off", "ro", "rw"} else "off"
        self.allowed_cmds = tuple(allowed_cmds)

    @property
    def enabled(self) -> bool:
        return self.mode in {"ro", "rw"} and self.root is not None

    @property
    def writable(self) -> bool:
        return self.mode == "rw" and self.root is not None

    def project_count(self) -> int:
        if not self.enabled or self.root is None or not self.root.is_dir():
            return 0
        return sum(1 for entry in self.root.iterdir() if entry.is_dir() and not entry.name.startswith("."))

    def list_projects(self) -> list[dict[str, object]]:
        base = self._resolved_root()
        if not base.is_dir():
            return []
        items: list[dict[str, object]] = []
        for entry in sorted(base.iterdir(), key=lambda p: p.name.lower()):
            if entry.is_dir() and not entry.name.startswith(".") and _PROJECT_NAME.fullmatch(entry.name):
                items.append(
                    {
                        "name": entry.name,
                        "is_git": (entry / ".git").exists(),
                        "has_readme": (entry / "README.md").is_file(),
                    }
                )
        return items

    def resolve_project(self, project: str) -> Path:
        base = self._resolved_root()
        if not project or _PROJECT_NAME.fullmatch(project) is None:
            raise ValueError(f"Invalid project name: {project}")
        target = (base / project).resolve()
        if not target.is_relative_to(base) or target == base:
            raise WorkspacePermissionError("Project path escapes workspace root")
        if not target.is_dir():
            raise FileNotFoundError(f"Project not found: {project}")
        return target

    def resolve_file(self, project: str, rel_path: str, *, for_write: bool = False) -> Path:
        proj_root = self.resolve_project(project)
        cleaned = rel_path.strip()
        if not cleaned:
            raise ValueError("Relative file path is required")
        candidate = Path(cleaned)
        if candidate.is_absolute():
            raise WorkspacePermissionError("Absolute file paths are forbidden")
        if ".." in candidate.parts:
            raise WorkspacePermissionError("Path traversal outside project is forbidden")
        if is_secret_path(candidate):
            raise WorkspacePermissionError("Access to secret or .git files is blocked")
        resolved = (proj_root / candidate).resolve()
        if not resolved.is_relative_to(proj_root) or (for_write and resolved == proj_root):
            raise WorkspacePermissionError("Target path escapes project root")
        return resolved

    def list_files(self, project: str, subpath: str = "", limit: int = 100) -> list[str]:
        proj_root = self.resolve_project(project)
        start_dir = proj_root
        if subpath.strip():
            rel = Path(subpath.strip())
            if rel.is_absolute() or ".." in rel.parts:
                raise WorkspacePermissionError("Invalid subpath")
            if is_secret_path(rel):
                raise WorkspacePermissionError("Access to secret or .git paths is blocked")
            start_dir = (proj_root / rel).resolve()
            if not start_dir.is_relative_to(proj_root):
                raise WorkspacePermissionError("Subpath escapes project root")
            if not start_dir.is_dir():
                raise FileNotFoundError(f"Directory not found: {subpath}")

        capped = max(1, min(limit, 500))
        results: list[str] = []
        for dirpath, dirnames, filenames in os.walk(start_dir):
            dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
            cur = Path(dirpath)
            for fname in sorted(filenames):
                full = cur / fname
                try:
                    rel_item = full.resolve().relative_to(proj_root)
                except ValueError:
                    continue
                if is_secret_path(rel_item):
                    continue
                results.append(rel_item.as_posix())
                if len(results) >= capped:
                    return results
        return results

    def read_file(
        self,
        project: str,
        rel_path: str,
        start_line: int = 1,
        end_line: int = 200,
    ) -> dict[str, object]:
        if start_line < 1 or end_line < start_line:
            raise ValueError("Invalid line range: expected 1 <= start_line <= end_line")
        target = self.resolve_file(project, rel_path, for_write=False)
        if not target.is_file():
            raise FileNotFoundError(f"File not found: {rel_path}")
        raw = target.read_bytes()
        if b"\x00" in raw[:8192]:
            raise ValueError("Binary files cannot be read as text")
        lines = raw.decode("utf-8", errors="replace").splitlines()
        total_lines = len(lines)
        sliced = lines[start_line - 1 : end_line]
        joined = "\n".join(sliced)
        truncated = len(joined) > MAX_READ_CHARS
        if truncated:
            joined = joined[:MAX_READ_CHARS]
        return {
            "project": project,
            "path": Path(rel_path.strip()).as_posix(),
            "start_line": start_line,
            "end_line": min(end_line, total_lines),
            "total_lines": total_lines,
            "truncated": truncated,
            "content": joined,
        }

    def search_files(self, project: str, query: str, limit: int = 20) -> list[dict[str, object]]:
        proj_root = self.resolve_project(project)
        needle = query.strip().lower()
        if not needle:
            raise ValueError("Search query is empty")
        capped = max(1, min(limit, 100))
        matches: list[dict[str, object]] = []
        for rel_posix in self.list_files(project, limit=500):
            target = proj_root / rel_posix
            try:
                if target.stat().st_size > MAX_SEARCH_FILE_BYTES:
                    continue
                raw = target.read_bytes()
            except OSError:
                continue
            if b"\x00" in raw[:8192]:
                continue
            for line_no, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), start=1):
                if needle in line.lower():
                    matches.append(
                        {
                            "path": rel_posix,
                            "line": line_no,
                            "snippet": line.strip()[:240],
                        }
                    )
                    if len(matches) >= capped:
                        return matches
        return matches

    def write_file(
        self,
        project: str,
        rel_path: str,
        content: str,
        create_dirs: bool = False,
    ) -> dict[str, object]:
        self._require_writable()
        if len(content) > MAX_WRITE_CHARS:
            raise ValueError(f"Content exceeds {MAX_WRITE_CHARS} characters")
        target = self.resolve_file(project, rel_path, for_write=True)
        if not target.parent.exists():
            if not create_dirs:
                raise FileNotFoundError("Parent directory does not exist (set create_dirs=true to create)")
            target.parent.mkdir(parents=True, exist_ok=True)
        payload = content.encode("utf-8")
        target.write_bytes(payload)
        return {
            "project": project,
            "path": Path(rel_path.strip()).as_posix(),
            "bytes": len(payload),
        }

    def run_command(
        self,
        project: str,
        argv: list[str],
        timeout: int = DEFAULT_EXEC_TIMEOUT,
    ) -> dict[str, object]:
        self._require_writable()
        proj_root = self.resolve_project(project)
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
            raise ValueError("Command argv must be a non-empty list of strings")
        if any("\x00" in a for a in argv):
            raise ValueError("Invalid null byte in command arguments")
        if not 1 <= timeout <= MAX_EXEC_TIMEOUT:
            raise ValueError(f"Timeout must be between 1 and {MAX_EXEC_TIMEOUT} seconds")

        reason = _needs_confirmation(argv)
        if reason is not None:
            raise WorkspaceConfirmationRequired(reason)

        binary = argv[0]
        if Path(binary).name != binary or "/" in binary or "\\" in binary:
            raise WorkspacePermissionError("Path-qualified command binaries are forbidden")
        if binary not in self.allowed_cmds:
            raise WorkspacePermissionError(f"Command is not on allowlist: {binary}")

        try:
            proc = subprocess.run(
                argv,
                cwd=str(proj_root),
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            stdout, stderr = _truncate_output(proc.stdout, proc.stderr)
            return {
                "project": project,
                "argv": list(argv),
                "returncode": proc.returncode,
                "timed_out": False,
                "stdout": stdout,
                "stderr": stderr,
            }
        except FileNotFoundError as exc:
            raise ValueError(f"Command binary not installed: {binary}") from exc
        except subprocess.TimeoutExpired as exc:
            out = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            err = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            stdout, stderr = _truncate_output(out, err)
            return {
                "project": project,
                "argv": list(argv),
                "returncode": -1,
                "timed_out": True,
                "stdout": stdout,
                "stderr": stderr,
            }

    def _resolved_root(self) -> Path:
        if not self.enabled or self.root is None:
            raise WorkspaceDisabledError("Workspace access is disabled (HERMES_WORKSPACE_MODE=off)")
        return self.root.resolve()

    def _require_writable(self) -> None:
        if not self.enabled:
            raise WorkspaceDisabledError("Workspace access is disabled (HERMES_WORKSPACE_MODE=off)")
        if not self.writable:
            raise WorkspacePermissionError("Workspace is read-only (HERMES_WORKSPACE_MODE=ro)")


def _needs_confirmation(argv: list[str]) -> str | None:
    binary = Path(argv[0]).name.lower()
    if binary in _DESTRUCTIVE_COMMANDS:
        return f"Confirmation required for destructive command '{binary}'"
    if binary == "git":
        args = [token.lower() for token in argv[1:]]
        # Locate subcommand skipping option/flag pairs at the front if any.
        sub_index = next((idx for idx, tok in enumerate(args) if not tok.startswith("-")), None)
        if sub_index is not None:
            sub = args[sub_index]
            tail = args[sub_index + 1 :]
            if sub == "push" and any(
                tok in {"-f", "--force"} or tok.startswith("--force-with-lease") for tok in tail
            ):
                return "Confirmation required for force git push"
            if sub == "reset" and "--hard" in tail:
                return "Confirmation required for git reset --hard"
            if sub == "clean" and any(
                tok == "--force" or (tok.startswith("-") and not tok.startswith("--") and "f" in tok[1:])
                for tok in tail
            ):
                return "Confirmation required for git clean -f"
            if sub == "branch" and "-D" in argv[sub_index + 2 :]:
                return "Confirmation required for git branch -D"
            if sub in {"checkout", "restore"} and "." in tail:
                return f"Confirmation required for destructive git {sub} ."
    return None


def _truncate_output(stdout: str, stderr: str) -> tuple[str, str]:
    total = len(stdout) + len(stderr)
    if total <= MAX_EXEC_OUTPUT_CHARS:
        return stdout, stderr
    half = MAX_EXEC_OUTPUT_CHARS // 2
    out = stdout[:MAX_EXEC_OUTPUT_CHARS] if not stderr else stdout[:half]
    rem = max(0, MAX_EXEC_OUTPUT_CHARS - len(out))
    return out, stderr[:rem]
