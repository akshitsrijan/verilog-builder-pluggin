"""Project model and shared helpers for the iverilog-builder plugin.

An "Icarus project" is just a directory containing a `.ivproj.json` manifest.
No proprietary project format, no GUI, no database - the manifest names the
sources, the testbenches, the top module and where build artifacts go, and
every other module in this plugin works off that.

Stdlib only, on purpose: this module is imported by the MCP server process
and by any optional companion module (yosys_runner, gtkwave_runner) without
dragging in dependencies.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone

MANIFEST_NAME = ".ivproj.json"

#: Verilog/SystemVerilog source extensions we consider addable sources.
SOURCE_SUFFIXES = (".v", ".sv", ".vh", ".svh")

#: env var -> default absolute path for each external tool.
_TOOL_ENV = {
    "iverilog": ("IVERILOG_BIN", "/usr/bin/iverilog"),
    "vvp": ("VVP_BIN", "/usr/bin/vvp"),
    "yosys": ("YOSYS_BIN", "/usr/bin/yosys"),
    "gtkwave": ("GTKWAVE_BIN", "/usr/bin/gtkwave"),
}


def tool_path(name: str) -> str:
    """Absolute path to an external tool.

    Honours the per-tool env override (IVERILOG_BIN, VVP_BIN, YOSYS_BIN,
    GTKWAVE_BIN), then PATH, then the known /usr/bin location. Always
    returns a string - callers surface a friendly error if it doesn't run.
    """
    env_var, default = _TOOL_ENV.get(name, (name.upper() + "_BIN", "/usr/bin/" + name))
    override = os.environ.get(env_var)
    if override:
        return override
    found = shutil.which(name)
    if found:
        return found
    return default


def run_cmd(argv, cwd=None, timeout: int = 120) -> dict:
    """Run a command, capturing output. Never raises for tool failure.

    Returns {"rc": int, "stdout": str, "stderr": str}. rc is -1 on timeout
    and -2 when the executable could not be launched at all, with the
    reason in stderr.
    """
    argv = [str(a) for a in argv]
    try:
        proc = subprocess.run(argv, cwd=str(cwd) if cwd else None, capture_output=True,
                              text=True, timeout=timeout)
        return {"rc": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    except subprocess.TimeoutExpired as exc:
        return {"rc": -1, "stdout": exc.stdout or "", "stderr": f"timed out after {timeout}s"}
    except OSError as exc:
        return {"rc": -2, "stdout": "", "stderr": f"could not run {argv[0]}: {exc}"}


@dataclass
class Project:
    """In-memory view of a `.ivproj.json` manifest.

    `root` is the project directory (absolute). `sources` and `testbenches`
    are stored relative to `root` in the manifest but exposed here as
    absolute resolved paths, so callers never have to think about cwd.
    """

    root: pathlib.Path
    name: str
    top: str = ""
    sources: list = field(default_factory=list)       # absolute Paths
    testbenches: list = field(default_factory=list)   # absolute Paths
    build_dir: str = "build"
    std: str = "2012"
    include_dirs: list = field(default_factory=list)  # absolute Paths
    created: str = ""
    toolchain: dict = field(default_factory=dict)

    def build_path(self) -> pathlib.Path:
        """Absolute build directory, created on demand."""
        p = self.root / self.build_dir
        p.mkdir(parents=True, exist_ok=True)
        return p

    def manifest_path(self) -> pathlib.Path:
        return self.root / MANIFEST_NAME

    def rel(self, p) -> str:
        """Path relative to the project root when possible, else absolute."""
        p = pathlib.Path(p)
        try:
            return str(p.relative_to(self.root))
        except ValueError:
            return str(p)

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
        """JSON-safe summary suitable for returning straight from an MCP tool."""
        d = self.to_dict()
        d["path"] = str(self.root)
        d["manifest"] = str(self.manifest_path())
        return d


def _resolve(root: pathlib.Path, entry) -> pathlib.Path:
    p = pathlib.Path(entry).expanduser()
    if not p.is_absolute():
        p = root / p
    return p.resolve()


def looks_like_testbench(path) -> bool:
    """Heuristic used when a caller doesn't say which file is a testbench."""
    lower = pathlib.Path(path).name.lower()
    return bool(re.search(r"(^|_)tb(_|\.)", lower)) or "testbench" in lower or lower.startswith("tb_")


def module_name_for_file(path) -> str:
    """First `module <name>` declared in a file, else the file stem."""
    p = pathlib.Path(path)
    try:
        text = p.read_text(errors="ignore")
    except OSError:
        return p.stem
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    m = re.search(r"\bmodule\s+(\w+)", text)
    return m.group(1) if m else p.stem


def manifest_for(path) -> pathlib.Path:
    """Given a project dir or the manifest file itself, return the manifest path."""
    p = pathlib.Path(path).expanduser().resolve()
    if p.is_dir():
        return p / MANIFEST_NAME
    if p.name == MANIFEST_NAME:
        return p
    # A source file inside a project, or a stale path: try its directory.
    return p.parent / MANIFEST_NAME


def load_project(path) -> Project:
    """Load a project from a directory path or a `.ivproj.json` path.

    Raises FileNotFoundError if there is no manifest there.
    """
    mp = manifest_for(path)
    if not mp.exists():
        raise FileNotFoundError(f"no {MANIFEST_NAME} found at {mp.parent}")
    root = mp.parent
    with open(mp) as f:
        data = json.load(f)
    return Project(
        root=root,
        name=data.get("name") or root.name,
        top=data.get("top", ""),
        sources=[_resolve(root, s) for s in data.get("sources", [])],
        testbenches=[_resolve(root, t) for t in data.get("testbenches", [])],
        build_dir=data.get("build_dir", "build"),
        std=data.get("std", "2012"),
        include_dirs=[_resolve(root, i) for i in data.get("include_dirs", [])],
        created=data.get("created", ""),
        toolchain=data.get("toolchain", {}),
    )


def save_project(p: Project) -> pathlib.Path:
    """Write the manifest atomically. Returns the manifest path."""
    p.root.mkdir(parents=True, exist_ok=True)
    mp = p.manifest_path()
    tmp = mp.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(p.to_dict(), f, indent=2)
    tmp.replace(mp)
    return mp


def create_project(name: str, dir: str, sources=None, top: str = "") -> Project:
    """Create a new project directory with a `.ivproj.json` manifest.

    `sources` may be empty - that's the normal path when the user is going to
    describe their modules in English and have them written with
    write_module afterwards. Files listed are classified into sources vs
    testbenches by name heuristic unless they're clearly one or the other.

    Raises FileExistsError if a manifest already exists at `dir`.
    """
    root = pathlib.Path(dir).expanduser().resolve()
    if (root / MANIFEST_NAME).exists():
        raise FileExistsError(f"a project already exists at {root}")
    root.mkdir(parents=True, exist_ok=True)

    srcs, tbs = [], []
    for s in sources or []:
        rp = _resolve(root, s)
        if not rp.exists():
            raise FileNotFoundError(f"source file not found: {rp}")
        (tbs if looks_like_testbench(rp) else srcs).append(rp)

    if not top and srcs:
        top = module_name_for_file(srcs[-1])

    p = Project(
        root=root, name=name, top=top, sources=srcs, testbenches=tbs,
        build_dir="build", std="2012", include_dirs=[],
        created=datetime.now(timezone.utc).isoformat(),
        toolchain={"iverilog": tool_path("iverilog"), "vvp": tool_path("vvp")},
    )
    save_project(p)
    p.build_path()
    return p


def add_sources(p: Project, files) -> Project:
    """Register additional files with the project, in place, and save.

    Testbenches (by name heuristic) land in `testbenches`; everything else in
    `sources`. Duplicates are ignored. Raises FileNotFoundError for missing
    files. Returns the same Project for chaining.
    """
    for f in files or []:
        rp = _resolve(p.root, f)
        if not rp.exists():
            raise FileNotFoundError(f"source file not found: {rp}")
        bucket = p.testbenches if looks_like_testbench(rp) else p.sources
        if rp not in bucket:
            bucket.append(rp)
    if not p.top and p.sources:
        p.top = module_name_for_file(p.sources[-1])
    save_project(p)
    return p


def list_projects(search_root: str = "~") -> list:
    """Find Icarus projects at, or up to two levels under, search_root.

    Returns [{"name", "path", "top", "sources": n, "manifest"}], newest
    manifest first.
    """
    root = pathlib.Path(search_root).expanduser()
    if not root.exists():
        return []
    candidates = [root / MANIFEST_NAME,
                  *root.glob("*/" + MANIFEST_NAME),
                  *root.glob("*/*/" + MANIFEST_NAME)]
    seen, out = set(), []
    for mp in candidates:
        rp = mp.resolve()
        if rp in seen or not rp.exists():
            continue
        seen.add(rp)
        try:
            p = load_project(rp)
        except (OSError, ValueError):
            continue
        out.append({"name": p.name, "path": str(p.root), "top": p.top,
                    "sources": len(p.sources), "manifest": str(rp),
                    "created": p.created})
    out.sort(key=lambda d: d.get("created") or "", reverse=True)
    return out
