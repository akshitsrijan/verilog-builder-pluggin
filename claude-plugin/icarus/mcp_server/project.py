"""Shared project model for the Icarus Verilog plugin.

A "project" here is deliberately much lighter than a Vivado `.xpr`: it is just
a directory containing a `.ivproj.json` manifest listing the design sources,
the testbenches, and the top module. Everything else (build products, VCDs,
schematics) lives under the project's build directory.

This module is the public API the rest of the plugin - and the optional
yosys/gtkwave tool modules contributed by other subsystems - builds on. It is
stdlib-only on purpose: importing it must never require the MCP venv.

See CONTRACT.md in this directory for the documented API surface.
"""

import json
import os
import pathlib
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone

MANIFEST_NAME = ".ivproj.json"

# Toolchain binaries. Each is overridable via the matching *_BIN environment
# variable (set by .mcp.json), falling back to the standard distro location
# and finally to a bare name resolved through PATH.
_TOOL_ENV = {
    "iverilog": ("IVERILOG_BIN", "/usr/bin/iverilog"),
    "vvp": ("VVP_BIN", "/usr/bin/vvp"),
    "yosys": ("YOSYS_BIN", "/usr/bin/yosys"),
    "gtkwave": ("GTKWAVE_BIN", "/usr/bin/gtkwave"),
    "dot": ("DOT_BIN", "/usr/bin/dot"),
    "netlistsvg": ("NETLISTSVG_BIN", "/usr/local/bin/netlistsvg"),
}

SOURCE_SUFFIXES = (".v", ".sv", ".vh", ".svh")


# --------------------------------------------------------------------------
# small shared helpers
# --------------------------------------------------------------------------

def tool_path(name: str) -> str:
    """Resolve a toolchain binary name to an executable path.

    Honours the corresponding *_BIN environment variable first, then the
    known absolute location, then falls back to the bare name so PATH
    resolution still gets a chance.
    """
    env_var, default = _TOOL_ENV.get(name, (None, None))
    if env_var:
        override = os.environ.get(env_var)
        if override:
            return override
    if default and pathlib.Path(default).exists():
        return default
    return name


def run_cmd(argv: list, cwd=None, timeout: int = 120) -> dict:
    """Run a command and capture its result.

    Returns {"rc": int, "stdout": str, "stderr": str}. A timeout or a missing
    binary is reported as a non-zero rc with the reason in stderr rather than
    raised, so callers never have to wrap this in try/except.
    """
    try:
        proc = subprocess.run([str(a) for a in argv],
                              cwd=str(cwd) if cwd else None,
                              capture_output=True, text=True, timeout=timeout)
        return {"rc": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    except subprocess.TimeoutExpired as exc:
        return {"rc": 124, "stdout": exc.stdout or "", "stderr": f"timed out after {timeout}s"}
    except OSError as exc:
        return {"rc": 127, "stdout": "", "stderr": f"could not run {argv[0]!r}: {exc}"}


def module_name_for_file(path) -> str:
    """First `module <name>` declared in a source file, else the file stem."""
    p = pathlib.Path(path)
    try:
        text = p.read_text(errors="ignore")
    except OSError:
        return p.stem
    m = re.search(r"^\s*module\s+(\w+)", text, re.M)
    return m.group(1) if m else p.stem


def looks_like_testbench(path) -> bool:
    """Heuristic: is this file a testbench rather than synthesizable RTL?"""
    name = pathlib.Path(path).name.lower()
    if re.search(r"(^|_)tb(_|\.)", name) or "testbench" in name or name.startswith("tb_"):
        return True
    try:
        text = pathlib.Path(path).read_text(errors="ignore")
    except OSError:
        return False
    # A file with no ports on its top module that drives $finish/$dumpfile is
    # a testbench even if it isn't named like one.
    return bool(re.search(r"\$(finish|dumpfile|dumpvars)\b", text))


# --------------------------------------------------------------------------
# the project model
# --------------------------------------------------------------------------

@dataclass
class Project:
    """An Icarus Verilog project, loaded from a `.ivproj.json` manifest.

    `sources`/`testbenches` are stored in the manifest relative to `root`, but
    are exposed here as resolved absolute `pathlib.Path` objects.
    """

    name: str
    root: pathlib.Path
    top: str = ""
    sources: list = field(default_factory=list)        # list[pathlib.Path]
    testbenches: list = field(default_factory=list)    # list[pathlib.Path]
    build_dir: str = "build"
    std: str = "2012"
    include_dirs: list = field(default_factory=list)   # list[pathlib.Path]
    created: str = ""
    toolchain: dict = field(default_factory=dict)

    # -- paths -------------------------------------------------------------

    @property
    def manifest_path(self) -> pathlib.Path:
        return self.root / MANIFEST_NAME

    def build_path(self) -> pathlib.Path:
        """Absolute build directory, created on demand."""
        p = self.root / self.build_dir
        p.mkdir(parents=True, exist_ok=True)
        return p

    def rel(self, path) -> str:
        """Path relative to the project root when possible, else absolute."""
        p = pathlib.Path(path).resolve()
        try:
            return str(p.relative_to(self.root))
        except ValueError:
            return str(p)

    # -- content -----------------------------------------------------------

    def all_files(self) -> list:
        """Every source and testbench, design sources first."""
        return list(self.sources) + list(self.testbenches)

    def modules(self) -> list:
        """[{"name", "file"}] for each design source (testbenches excluded)."""
        return [{"name": module_name_for_file(f), "file": str(f)} for f in self.sources]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "top": self.top,
            "sources": [self.rel(s) for s in self.sources],
            "testbenches": [self.rel(t) for t in self.testbenches],
            "build_dir": self.build_dir,
            "std": self.std,
            "include_dirs": [self.rel(i) for i in self.include_dirs],
            "created": self.created,
            "toolchain": self.toolchain,
        }

    def summary(self) -> dict:
        """Compact JSON-friendly view for returning from MCP tools."""
        d = self.to_dict()
        d["path"] = str(self.root)
        d["manifest"] = str(self.manifest_path)
        d["build_path"] = str(self.root / self.build_dir)
        return d


class ProjectError(Exception):
    """Raised for a bad or missing project; callers turn this into
    {"ok": False, "error": str(exc)}."""


def _manifest_for(path) -> pathlib.Path:
    """Accept either a project directory or the manifest file itself."""
    p = pathlib.Path(path).expanduser().resolve()
    if p.is_dir():
        return p / MANIFEST_NAME
    if p.name == MANIFEST_NAME:
        return p
    # A path to a source file inside a project is a friendly thing to accept.
    if p.suffix in SOURCE_SUFFIXES and (p.parent / MANIFEST_NAME).exists():
        return p.parent / MANIFEST_NAME
    return p


_INSTANCE_RE = re.compile(r"^\s*(\w+)\s+(?:#\s*\([^)]*\)\s*)?\w+\s*\(", re.M)


def _instantiated_modules(project: "Project") -> set:
    """Module names instantiated by any design source. Anything in here is,
    by definition, not the top of the hierarchy."""
    declared = {module_name_for_file(f) for f in project.sources}
    used = set()
    for f in project.sources:
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        # Strip comments so commented-out instantiations don't count.
        text = re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)
        self_name = module_name_for_file(f)
        for name in _INSTANCE_RE.findall(text):
            if name in declared and name != self_name:
                used.add(name)
    return used


def _infer_top(project: "Project"):
    """Set `top` to the design module that nothing else instantiates.

    Only overrides an existing `top` when that module is provably *not* the
    top (something instantiates it), so an explicit choice is respected.
    """
    if not project.sources:
        return
    instantiated = _instantiated_modules(project)
    roots = [module_name_for_file(f) for f in project.sources
             if module_name_for_file(f) not in instantiated]
    if project.top and project.top not in instantiated:
        return
    project.top = roots[-1] if roots else module_name_for_file(project.sources[-1])


def load_project(path) -> Project:
    """Load a Project from a directory, a `.ivproj.json` path, or a source
    file sitting next to one. Raises ProjectError if there is no manifest."""
    manifest = _manifest_for(path)
    if not manifest.exists():
        raise ProjectError(f"no {MANIFEST_NAME} found at {manifest}")
    try:
        data = json.loads(manifest.read_text())
    except (OSError, ValueError) as exc:
        raise ProjectError(f"could not read {manifest}: {exc}") from exc

    root = manifest.parent

    def _resolve(entries):
        out = []
        for e in entries or []:
            p = pathlib.Path(e).expanduser()
            out.append((p if p.is_absolute() else root / p).resolve())
        return out

    return Project(
        name=data.get("name", root.name),
        root=root,
        top=data.get("top", ""),
        sources=_resolve(data.get("sources")),
        testbenches=_resolve(data.get("testbenches")),
        build_dir=data.get("build_dir", "build"),
        std=str(data.get("std", "2012")),
        include_dirs=_resolve(data.get("include_dirs")),
        created=data.get("created", ""),
        toolchain=data.get("toolchain") or {},
    )


def save_project(project: Project) -> pathlib.Path:
    """Write the manifest back to disk atomically. Returns its path."""
    project.root.mkdir(parents=True, exist_ok=True)
    manifest = project.manifest_path
    tmp = manifest.with_suffix(".tmp")
    tmp.write_text(json.dumps(project.to_dict(), indent=2) + "\n")
    tmp.replace(manifest)
    return manifest


def _default_toolchain() -> dict:
    return {"iverilog": tool_path("iverilog"), "vvp": tool_path("vvp")}


def resolve_source(root, s) -> pathlib.Path:
    """Resolve a user-supplied source path.

    Absolute paths are taken as-is. A relative path is resolved against the
    project root first (the MCP server runs with an arbitrary CWD, so the
    project is the only stable frame of reference), falling back to the
    CWD for the case where the caller really did mean a path relative to
    where they are.
    """
    p = pathlib.Path(s).expanduser()
    if p.is_absolute():
        return p.resolve()
    cand = (pathlib.Path(root) / p)
    if cand.exists():
        return cand.resolve()
    return p.resolve()


def create_project(name: str, dir: str = "", sources=None, top: str = "",
                   std: str = "2012") -> Project:
    """Create a new project directory and its manifest.

    `dir` defaults to `~/<name>/`, matching the layout of the other projects
    on this machine. `sources` is an optional list of existing `.v`/`.sv`
    files to register; files that look like testbenches are sorted into
    `testbenches` automatically. Files outside the project root are recorded
    by absolute path rather than copied.

    Raises ProjectError if a project already exists at that location or a
    listed source is missing.
    """
    root = pathlib.Path(dir).expanduser().resolve() if dir else \
        (pathlib.Path.home() / name).resolve()
    if (root / MANIFEST_NAME).exists():
        raise ProjectError(f"a project already exists at {root}")

    resolved = []
    for s in sources or []:
        p = resolve_source(root, s)
        if not p.exists():
            raise ProjectError(f"source file not found: {p}")
        resolved.append(p)

    root.mkdir(parents=True, exist_ok=True)
    (root / "sources").mkdir(exist_ok=True)

    project = Project(
        name=name, root=root, top=top, build_dir="build", std=str(std),
        created=datetime.now(timezone.utc).isoformat(),
        toolchain=_default_toolchain(),
    )
    for p in resolved:
        (project.testbenches if looks_like_testbench(p) else project.sources).append(p)
    _infer_top(project)
    save_project(project)
    return project


def add_sources(project: Project, files) -> Project:
    """Register more files with a project, sorting testbenches out of the
    design sources. Duplicates are ignored. Saves the manifest and returns
    the same Project instance."""
    known = {p.resolve() for p in project.all_files()}
    for f in files or []:
        p = resolve_source(project.root, f)
        if not p.exists():
            raise ProjectError(f"source file not found: {p}")
        if p in known:
            continue
        known.add(p)
        (project.testbenches if looks_like_testbench(p) else project.sources).append(p)
    _infer_top(project)
    save_project(project)
    return project


def write_module(project: Project, filename: str, content: str,
                 is_testbench=None) -> pathlib.Path:
    """Persist a Verilog source into the project and register it.

    This is what makes the plugin prompt-driven: Claude writes the RTL and
    this puts it on disk under `<root>/sources/` (unless `filename` is an
    explicit path) and adds it to the manifest in one step.

    `is_testbench` overrides the name/content heuristic when given.
    """
    p = pathlib.Path(filename).expanduser()
    if not p.is_absolute() and p.parent == pathlib.Path("."):
        p = project.root / "sources" / p.name
    elif not p.is_absolute():
        p = project.root / p
    p = p.resolve()
    if p.suffix not in SOURCE_SUFFIXES:
        p = p.with_suffix(".v")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content if content.endswith("\n") else content + "\n")

    known = {q.resolve() for q in project.all_files()}
    if p not in known:
        tb = looks_like_testbench(p) if is_testbench is None else bool(is_testbench)
        (project.testbenches if tb else project.sources).append(p)
    _infer_top(project)
    save_project(project)
    return p


def list_projects(search_root: str = "~") -> list:
    """Find projects by walking up to two levels below search_root looking
    for `.ivproj.json`. Returns [{"name", "path", "manifest", "top",
    "source_count"}], skipping manifests that fail to parse."""
    root = pathlib.Path(search_root).expanduser()
    if not root.is_dir():
        return []

    candidates = []
    for pattern in (MANIFEST_NAME, f"*/{MANIFEST_NAME}", f"*/*/{MANIFEST_NAME}"):
        candidates.extend(root.glob(pattern))

    seen, out = set(), []
    for manifest in candidates:
        rm = manifest.resolve()
        if rm in seen:
            continue
        seen.add(rm)
        try:
            p = load_project(rm)
        except ProjectError:
            continue
        out.append({"name": p.name, "path": str(p.root), "manifest": str(rm),
                    "top": p.top, "source_count": len(p.sources)})
    return out
