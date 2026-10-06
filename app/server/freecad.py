"""Drive a running FreeCAD from this server.

FreeCAD is a full parametric CAD with a real feature tree, a Sketcher, and
thirty years of part primitives. What it has never had is a way for another
program to use it. The `FreeCAD MCP addon`_ supplies one: a workbench that
opens an XML-RPC port inside the running application, so a caller can make
documents, add and edit objects, and execute Python in FreeCAD's own
interpreter.

This module is that caller. It is deliberately **not** an MCP client: the
MCP server in that project is itself a thin bridge onto this same XML-RPC
surface, written so that a generic client like a chat application can reach
it. This app is not a generic client - it is a specific one - so it speaks
the protocol directly and skips a process and a protocol that would earn
nothing. The tool vocabulary below is kept in the shape MCP uses, so putting
MCP back in front later costs a transport class and nothing else.

**What this gets us that CadQuery does not.** A persistent, parametric
document: add a `Part::Box`, change its `Length`, and FreeCAD recomputes the
tree. That is the feature tree a STEP file cannot carry and `direct.py` has
to reconstruct. The cost is that FreeCAD must be running, with the addon
started, on a machine this server can reach.

**Getting the geometry back is the part the addon does not do.** There is no
export method on the RPC surface. There is `execute_code`, which runs inside
FreeCAD and hands back whatever the code printed - so an export is written
to a temporary file there, read back, and returned base64 through stdout.
That works whether FreeCAD is on this machine or another one, which a shared
file path would not.

.. _FreeCAD MCP addon: https://github.com/neka-nat/freecad-mcp
"""

from __future__ import annotations

import base64
import re
import textwrap
import xmlrpc.client
from pathlib import Path
from typing import Any, Optional

#: The addon's default port. Settable there, so it is settable here.
DEFAULT_PORT = 9875

#: The addon answers `get_rpc_status` without touching the GUI thread, so a
#: healthy FreeCAD replies at once and a wedged one does not hold up a page
#: load for the full call timeout.
PING_TIMEOUT = 5.0

#: Everything else waits on FreeCAD's GUI thread, which is busy while the
#: user drags the view and while OCCT grinds through a boolean.
CALL_TIMEOUT = 150.0

#: Exported bytes come back wrapped in these, because `execute_code` returns
#: FreeCAD's console chatter along with the script's own output.
_MARK_OPEN, _MARK_CLOSE = "<<<CADSMITH:", ":CADSMITH>>>"
#: Non-greedy and any character: this carries base64 for an export and JSON
#: for a measurement, and a base64-only class silently matched neither when
#: the payload was JSON.
_PAYLOAD = re.compile(re.escape(_MARK_OPEN) + r"(.*?)" + re.escape(_MARK_CLOSE),
                      re.DOTALL)


class FreeCADError(RuntimeError):
    """FreeCAD refused, or could not be reached.

    Carries the addon's own words. They are worth passing on intact: the
    dispatcher says whether a call timed out waiting for the GUI thread,
    which is a different problem from a part that would not build.
    """


class _Timeout(xmlrpc.client.Transport):
    """XML-RPC with a socket timeout, and the token on every request.

    Python's default transport has no timeout at all, so a FreeCAD whose GUI
    thread is stuck leaves this server waiting on the socket for as long as
    the kernel allows - minutes - with a request thread held the whole time.
    """

    def __init__(self, timeout: float, token: str = "") -> None:
        # The token goes in a header rather than the URL. xmlrpc.client
        # repeats the URL in its exception text, and those strings end up in
        # logs and in the browser.
        super().__init__(headers=[("Authorization", f"Bearer {token}")] if token else [])
        self._timeout = timeout

    def make_connection(self, host):
        connection = super().make_connection(host)
        connection.timeout = self._timeout
        return connection


class Bridge:
    """A connection to one running FreeCAD."""

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT,
                 token: str = "", timeout: float = CALL_TIMEOUT) -> None:
        self.host, self.port = host, port
        self._token = token
        self._timeout = timeout
        self._uri = f"http://{host}:{port}"

    def _proxy(self, timeout: Optional[float] = None) -> xmlrpc.client.ServerProxy:
        return xmlrpc.client.ServerProxy(
            self._uri, allow_none=True,
            transport=_Timeout(timeout or self._timeout, self._token))

    def _call(self, method: str, *args: Any,
              timeout: Optional[float] = None) -> Any:
        try:
            return getattr(self._proxy(timeout), method)(*args)
        except xmlrpc.client.Fault as fault:
            raise FreeCADError(f"FreeCAD refused {method}: {fault.faultString}")
        except Exception as error:
            raise FreeCADError(
                f"Could not reach FreeCAD at {self._uri}: {error}. Is FreeCAD "
                f"open with the MCP addon's RPC server started?") from error

    @staticmethod
    def _checked(result: Any, what: str) -> dict:
        """The addon answers every mutating call with success and a reason."""
        if isinstance(result, dict) and result.get("success"):
            return result
        reason = (result or {}).get("error", result) if isinstance(result, dict) \
            else result
        raise FreeCADError(f"{what}: {reason}")

    # -- is anybody there ---------------------------------------------------

    def alive(self) -> bool:
        """Whether FreeCAD is up with its RPC server running.

        Never raises. The health panel asks this on every page load and a
        FreeCAD that is simply not open is an ordinary state, not a fault.
        """
        try:
            return bool(self._call("ping", timeout=PING_TIMEOUT))
        except FreeCADError:
            return False

    def status(self) -> dict:
        """What the addon says about itself - version, budgets, GUI health."""
        return self._call("get_rpc_status", timeout=PING_TIMEOUT) or {}

    # -- documents and objects ----------------------------------------------

    def documents(self) -> list[str]:
        return list(self._call("list_documents") or [])

    def new_document(self, name: str = "CADSmith") -> str:
        """Open a document, and report the name FreeCAD actually gave it.

        FreeCAD sanitises what it is given ("My Doc" becomes "My_Doc") and
        de-duplicates ("Doc" becomes "Doc001"). Every later call keys on the
        real name, so the requested one is of no further use.
        """
        answer = self._checked(self._call("create_document", name),
                               f"could not open a document called {name!r}")
        return answer.get("document_name") or answer.get("name") or name

    def add(self, document: str, kind: str, name: str = "",
            **properties: Any) -> str:
        """Add an object, and report the name it was actually given.

        ``kind`` is a FreeCAD type - "Part::Box", "Part::Cylinder",
        "PartDesign::Body", "Part::Cut". Properties are FreeCAD's own
        property names, so a box takes Length, Width and Height.
        """
        answer = self._checked(
            self._call("create_object", document,
                       {"Name": name or kind.split("::")[-1],
                        "Type": kind, "Properties": properties or {}}),
            f"could not add a {kind}")
        return answer.get("object_name") or name

    def edit(self, document: str, name: str, **properties: Any) -> str:
        """Change an object's properties and let FreeCAD recompute.

        This is the thing a STEP file cannot do and the reason for going
        through FreeCAD at all: the tree is live, so one changed number
        re-runs everything downstream of it.
        """
        answer = self._checked(
            self._call("edit_object", document, name, {"Properties": properties}),
            f"could not edit {name!r}")
        return answer.get("object_name") or name

    def remove(self, document: str, name: str) -> None:
        self._checked(self._call("delete_object", document, name),
                      f"could not delete {name!r}")

    def objects(self, document: str) -> list[dict]:
        """Every object in the document, as the addon describes them."""
        return list(self._call("get_objects", document) or [])

    def object(self, document: str, name: str) -> Optional[dict]:
        return self._call("get_object", document, name)

    # -- running code inside FreeCAD ----------------------------------------

    def run(self, code: str, timeout: Optional[float] = None) -> str:
        """Execute Python in FreeCAD's own interpreter; return what it printed.

        This is the widest door in the protocol and the reason the addon is
        worth having: anything FreeCAD can do from its Python console can be
        done here, including the parts of the API that have no RPC method of
        their own. It is also the reason the addon takes a token.
        """
        answer = self._checked(self._call("execute_code", code, timeout,
                                          timeout=timeout or self._timeout),
                               "FreeCAD could not run that")
        message = answer.get("message", "")
        _, _, printed = message.partition("Output: ")
        return printed

    def screenshot(self, view: str = "Isometric") -> bytes:
        """What FreeCAD is showing, as PNG bytes."""
        raw = self._call("get_active_screenshot", view)
        if not raw:
            raise FreeCADError("FreeCAD returned no screenshot")
        return base64.b64decode(raw)

    # -- getting the geometry out -------------------------------------------

    #: Objects nothing else consumes. A Cut keeps its two operands in the
    #: document, and exporting all three would hand back the part plus the
    #: tool that made it. FreeCAD records the dependency the other way round
    #: in ``InList``, so an empty InList means "nobody builds on this" -
    #: which is the finished part.
    _TIPS = textwrap.dedent("""
        def _tips(doc):
            out = []
            for obj in doc.Objects:
                shape = getattr(obj, "Shape", None)
                if shape is None or shape.isNull():
                    continue
                if getattr(obj, "InList", None):
                    continue
                out.append(obj)
            if not out:
                out = [o for o in doc.Objects
                       if getattr(o, "Shape", None) is not None
                       and not o.Shape.isNull()]
            return out
    """)

    def fetch(self, document: str, kind: str = "step",
              timeout: Optional[float] = None) -> bytes:
        """Export the finished part from FreeCAD and bring the bytes back.

        The addon has no export method, so this runs one inside FreeCAD and
        returns the file base64 through what the script prints. Bytes rather
        than a shared path on purpose: FreeCAD may be on another machine, and
        a path that only resolves at one end is a bug waiting for the first
        remote install.
        """
        suffix = {"step": "step", "stp": "step", "stl": "stl",
                  "brep": "brep"}.get(kind.lower())
        if suffix is None:
            raise ValueError(f"cannot export {kind!r}; try step, stl or brep")

        write = {
            "step": 'import Part; Part.export(shapes, path)',
            "stl": ('import Part; '
                    'Part.makeCompound([s.Shape for s in shapes]).exportStl(path)'),
            "brep": ('import Part; '
                     'Part.makeCompound([s.Shape for s in shapes]).exportBrep(path)'),
        }[suffix]

        code = textwrap.dedent(f"""
            import base64, os, tempfile
            import FreeCAD
            {self._TIPS}
            doc = FreeCAD.getDocument({document!r})
            shapes = _tips(doc)
            if not shapes:
                raise RuntimeError("that document has no solid to export")
            path = os.path.join(tempfile.gettempdir(),
                                "cadsmith_export.{suffix}")
            {write}
            with open(path, "rb") as handle:
                blob = base64.b64encode(handle.read()).decode("ascii")
            os.remove(path)
            print({_MARK_OPEN!r} + blob + {_MARK_CLOSE!r})
        """)
        printed = self.run(code, timeout=timeout)
        found = _PAYLOAD.search(printed)
        if not found:
            raise FreeCADError(
                "FreeCAD ran the export but returned no file. It printed: "
                + (printed.strip()[:300] or "nothing"))
        return base64.b64decode("".join(found.group(1).split()))

    def save(self, document: str, path: Path, kind: str = "") -> Path:
        """Export straight into a file here, named by its own suffix."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.fetch(document, kind or path.suffix.lstrip(".")))
        return path

    def measure(self, document: str) -> dict:
        """What FreeCAD makes of the finished part, without exporting it.

        Cheap next to a round trip through STEP, and enough to tell whether
        anything was built at all. The real measuring is done here, on the
        exported solid, by ``spec.measure_step`` - FreeCAD's own numbers are
        a sanity check, not evidence.
        """
        code = textwrap.dedent(f"""
            import json
            import FreeCAD
            {self._TIPS}
            doc = FreeCAD.getDocument({document!r})
            shapes = _tips(doc)
            out = []
            for obj in shapes:
                box = obj.Shape.BoundBox
                out.append({{"name": obj.Name, "label": obj.Label,
                             "volume": obj.Shape.Volume,
                             "area": obj.Shape.Area,
                             "faces": len(obj.Shape.Faces),
                             "valid": obj.Shape.isValid(),
                             "bbox": [box.XLength, box.YLength, box.ZLength]}})
            print({_MARK_OPEN!r} + json.dumps(out) + {_MARK_CLOSE!r})
        """)
        import json
        printed = self.run(code)
        found = _PAYLOAD.search(printed)
        if not found:
            raise FreeCADError("FreeCAD returned no measurements. It printed: "
                               + (printed.strip()[:300] or "nothing"))
        return {"solids": json.loads(found.group(1))}
