"""CadQuery code executor, run out of process.

Runs generated CadQuery scripts in a separate interpreter and returns either
a success result with paths to exported files, or a failure result with the
full error traceback.

**What the isolation is, precisely.**  The script is model-written, so it is
treated as untrusted input rather than as code the project wrote:

* it runs in its own process, so a segfault in the kernel - which OCCT can be
  provoked into - costs one part rather than the server;
* it runs under a wall-clock timeout on every platform;
* on POSIX it runs under an address-space and CPU ceiling, so a runaway
  extrude cannot take the machine down with it;
* and it is handed a deliberately small environment.  ``os.environ`` here
  holds AWS credentials and provider API keys, and generated code has no use
  for any of them.  Only the variables an interpreter needs to find its own
  libraries are passed through.

**What it is not.**  There is no filesystem or network confinement: the child
can read what the server's user can read and can open sockets.  Running
untrusted prompts from people you do not trust needs a container or a VM, and
this module does not pretend otherwise.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ExecutionResult:
    """Result of executing a CadQuery script."""
    success: bool
    time_ms: float
    # On success:
    step_path: Optional[str] = None
    stl_path: Optional[str] = None
    #: Written only for an assembly, which needs a format carrying more than
    #: one body: the component tree, its names and its colours.
    gltf_path: Optional[str] = None
    geometry_json: Optional[dict] = None  # basic shape info extracted in-process
    # On failure:
    error: Optional[str] = None
    error_type: Optional[str] = None  # e.g. "SyntaxError", "StdFail_NotDone"


#: Environment variables the child genuinely needs to be a working Python.
#: Everything else - every credential among it - is left behind.  Names are
#: matched exactly; prefixes live in ``_ENV_PREFIXES``.
_ENV_KEEP = frozenset({
    # finding the interpreter, its libraries and its temp space
    "PATH", "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "CONDA_PREFIX",
    "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH",
    "TMPDIR", "TEMP", "TMP", "HOME", "USERPROFILE",
    # OCCT reads CASROOT for its resource files
    "CASROOT",
    # Windows will not start a process without these
    "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE",
    "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
    "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS", "OS",
    # text handling, so a traceback in any language survives the pipe
    "LANG", "LC_ALL", "LC_CTYPE",
})

#: Prefixes kept wholesale. ``PYTHON*`` covers the interpreter's own knobs.
_ENV_PREFIXES = ("PYTHON",)

#: Anything a deployment finds it also needs, named here rather than by
#: reopening the whole environment.  Comma separated, read once per call so a
#: fix does not need a restart.
_ENV_PASSTHROUGH = "CADSMITH_EXEC_ENV"

#: Address space and CPU seconds the child may have, on the platforms that can
#: enforce them.  Generous: a large assembly tessellating legitimately wants
#: room, and the point is to stop a runaway, not to be frugal.
EXEC_MEMORY_MB = int(os.getenv("CADSMITH_EXEC_MEMORY_MB", "4096"))
EXEC_CPU_SECONDS = int(os.getenv("CADSMITH_EXEC_CPU_SECONDS", "300"))


def child_environment() -> dict:
    """The environment a generated script is allowed to see.

    Built by allowing names in rather than by denying credentials out: a
    deny-list is one new provider away from leaking, and the child's real
    needs are short enough to write down.
    """
    extra = {n.strip().upper()
             for n in (os.getenv(_ENV_PASSTHROUGH) or "").split(",")
             if n.strip()}
    env = {
        name: value
        for name, value in os.environ.items()
        if name.upper() in _ENV_KEEP
        or name.upper() in extra
        or name.upper().startswith(_ENV_PREFIXES)
    }
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # The child prints tracebacks from generated code, which can carry
    # non-ASCII. Without this it encodes with the Windows locale codec and
    # dies before reaching __AUTOFAB_RESULT__.
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _limit_child() -> None:
    """Cap the child's memory and CPU. POSIX only; a no-op elsewhere.

    Called in the child between fork and exec, so raising here would kill a
    process the parent is about to wait on - every failure is swallowed
    deliberately, and the wall-clock timeout remains the backstop that works
    on every platform.
    """
    try:
        import resource
    except ImportError:          # Windows
        return
    for what, limit in ((resource.RLIMIT_AS, EXEC_MEMORY_MB * 1024 * 1024),
                        (resource.RLIMIT_CPU, EXEC_CPU_SECONDS)):
        try:
            soft, hard = resource.getrlimit(what)
            ceiling = limit if hard == resource.RLIM_INFINITY else min(limit, hard)
            resource.setrlimit(what, (ceiling, hard))
        except Exception:
            pass


# This script template is what actually runs inside the subprocess.
# It executes the user's CadQuery code, extracts geometry info, and exports files.
_RUNNER_TEMPLATE = '''
import json
import sys
import os

# Redirect the user code's output
_autofab_output = {{"success": False}}

try:
    # Execute the generated CadQuery code
    _autofab_user_globals = {{}}
    exec(open("{script_path}", encoding="utf-8").read(), _autofab_user_globals)

    # Find the CadQuery result object - look for common variable names
    import cadquery as cq
    _autofab_result = None

    # Priority order for finding the result shape
    _autofab_candidate_names = ["result", "model", "part", "shape", "assembly",
                                 "drone", "chassis", "bracket", "plate", "body"]

    # An Assembly is as valid a result as a Workplane. "assembly" has been in
    # the list of names to look for since this was written, but every
    # candidate was gated behind isinstance(obj, cq.Workplane) - so a script
    # that correctly built one was told no Workplane could be found, and the
    # next attempt "fixed" it by fusing everything into a single body. The
    # components, their names and their colours were lost every time.
    _autofab_kinds = (cq.Workplane, cq.Assembly)

    for name in _autofab_candidate_names:
        obj = _autofab_user_globals.get(name)
        if obj is not None and isinstance(obj, _autofab_kinds):
            _autofab_result = obj
            break

    # Fallback: find the last result-shaped object assigned
    if _autofab_result is None:
        for name, obj in reversed(list(_autofab_user_globals.items())):
            if name.startswith("_"):
                continue
            if isinstance(obj, _autofab_kinds):
                _autofab_result = obj
                break

    if _autofab_result is None:
        _autofab_output = {{"success": False, "error": "No CadQuery Workplane or Assembly found in script output. Assign your final shape to a variable named 'result'.", "error_type": "NoResultError"}}
    else:
        _autofab_is_assembly = isinstance(_autofab_result, cq.Assembly)
        if _autofab_is_assembly:
            # One compound to measure, while the assembly itself keeps its
            # tree for the STEP and the viewer.
            _autofab_shape = _autofab_result.toCompound()
            _autofab_parts = [
                {{"name": _n, "colour": (list(_o.color.toTuple())
                                        if getattr(_o, "color", None) else None)}}
                for _n, _o in _autofab_result.traverse() if _n != _autofab_result.name
            ]
        else:
            _autofab_shape = _autofab_result.val()
            _autofab_parts = []

        # Extract geometry info
        solid = _autofab_shape
        bb = solid.BoundingBox()

        _autofab_geometry = {{
            "volume": solid.Volume(),
            "center_of_mass": solid.Center().toTuple(),
            "bounding_box": {{
                "xmin": bb.xmin, "xmax": bb.xmax, "xlen": bb.xlen,
                "ymin": bb.ymin, "ymax": bb.ymax, "ylen": bb.ylen,
                "zmin": bb.zmin, "zmax": bb.zmax, "zlen": bb.zlen,
            }},
            "is_valid": solid.isValid(),
            "num_faces": len(solid.Faces()),
            "num_edges": len(solid.Edges()),
            "num_vertices": len(solid.Vertices()),
            "is_assembly": _autofab_is_assembly,
            "components": _autofab_parts,
        }}

        if _autofab_is_assembly:
            # "default" keeps the components separate in the STEP, with
            # their names and colours; "fused" would weld the assembly into
            # one solid and throw away the thing that makes it an assembly.
            _autofab_result.export("{step_path}", exportType="STEP")
            _autofab_result.export("{stl_path}", exportType="STL")
            try:
                # GLTF carries the tree, the names and the colours straight
                # into the viewer. Best effort: an assembly is still usable
                # without it, just monochrome.
                _autofab_result.export("{gltf_path}", exportType="GLTF")
            except Exception:
                pass
        else:
            cq.exporters.export(_autofab_result, "{step_path}")
            cq.exporters.export(_autofab_result, "{stl_path}")

        _autofab_output = {{
            "success": True,
            "geometry": _autofab_geometry,
        }}

except Exception as e:
    import traceback
    _autofab_output = {{
        "success": False,
        "error": traceback.format_exc(),
        "error_type": type(e).__name__,
    }}

# Write result to stdout as JSON
print("__AUTOFAB_RESULT__")
print(json.dumps(_autofab_output))
'''


class Executor:
    """Executes CadQuery scripts in a sandboxed subprocess."""

    def __init__(self, output_dir: Optional[str] = None, timeout_seconds: int = 60):
        self.timeout = timeout_seconds
        if output_dir:
            self.output_dir = Path(output_dir).resolve()
            self.output_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.output_dir = Path(tempfile.mkdtemp(prefix="autofab_")).resolve()

    def execute(self, cadquery_code: str, name: str = "part") -> ExecutionResult:
        """Execute a CadQuery script and return the result.

        Args:
            cadquery_code: The CadQuery Python code to execute.
            name: Base name for exported files.

        Returns:
            ExecutionResult with success/failure info and geometry data.
        """
        # Write the user's script to a temp file
        script_path = self.output_dir / f"{name}_script.py"
        step_path = self.output_dir / f"{name}.step"
        stl_path = self.output_dir / f"{name}.stl"
        gltf_path = self.output_dir / f"{name}.gltf"

        script_path.write_text(cadquery_code, encoding="utf-8")

        # Build the runner script
        runner_code = _RUNNER_TEMPLATE.format(
            script_path=str(script_path).replace("\\", "\\\\"),
            step_path=str(step_path).replace("\\", "\\\\"),
            stl_path=str(stl_path).replace("\\", "\\\\"),
            gltf_path=str(gltf_path).replace("\\", "\\\\"),
        )
        runner_path = self.output_dir / f"{name}_runner.py"
        runner_path.write_text(runner_code, encoding="utf-8")

        # Execute in subprocess
        start_time = time.time()
        try:
            proc = subprocess.run(
                [sys.executable, str(runner_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                cwd=str(self.output_dir),
                env=child_environment(),
                **({} if os.name == "nt" else {"preexec_fn": _limit_child}),
            )
            elapsed_ms = (time.time() - start_time) * 1000

            # Parse the result from stdout
            stdout = proc.stdout
            if "__AUTOFAB_RESULT__" in stdout:
                result_json_str = stdout.split("__AUTOFAB_RESULT__")[1].strip()
                result_data = json.loads(result_json_str)
            else:
                # Script crashed before producing output
                return ExecutionResult(
                    success=False,
                    time_ms=elapsed_ms,
                    error=proc.stderr or proc.stdout or "No output from runner",
                    error_type="SubprocessError",
                )

            if result_data["success"]:
                return ExecutionResult(
                    success=True,
                    time_ms=elapsed_ms,
                    step_path=str(step_path),
                    stl_path=str(stl_path),
                    gltf_path=str(gltf_path) if gltf_path.exists() else None,
                    geometry_json=result_data["geometry"],
                )
            else:
                return ExecutionResult(
                    success=False,
                    time_ms=elapsed_ms,
                    error=result_data.get("error", "Unknown error"),
                    error_type=result_data.get("error_type", "Unknown"),
                )

        except subprocess.TimeoutExpired:
            elapsed_ms = (time.time() - start_time) * 1000
            return ExecutionResult(
                success=False,
                time_ms=elapsed_ms,
                error=f"Execution timed out after {self.timeout} seconds",
                error_type="TimeoutError",
            )
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            return ExecutionResult(
                success=False,
                time_ms=elapsed_ms,
                error=str(e),
                error_type=type(e).__name__,
            )
