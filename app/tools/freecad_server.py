"""FreeCAD's RPC surface, served headlessly, for testing without a desktop.

The MCP addon opens its XML-RPC port inside a running FreeCAD *with a GUI*,
driven by a Qt timer. That is the right design for the desktop and the wrong
one for a test: nobody runs a test suite that needs an application window
open, so the FreeCAD half of this app went untested on real geometry.

This serves the same protocol - the same method names, the same
``{"success": ..., "error": ...}`` shape, the same ``"Output: "`` prefix on
what a script printed - out of a FreeCAD imported as a Python module. No GUI,
no Qt, no window. ``app/tests/test_freecad.py`` fakes this protocol with a
dictionary; this one is FreeCAD underneath, so what it proves is the
geometry, which a fake never can.

It is a test fixture, not a deployment. Two things are missing on purpose:
there is no screenshot, because there is no viewport to photograph, and
there is no token, because it binds to the loopback interface and should
never be anywhere it needs one.

Run it with the Python that has FreeCAD on its path:

    PYTHONPATH=/path/to/freecad/lib python -m app.tools.freecad_server
    python -m app.tools.freecad_check --port 9875
"""

from __future__ import annotations

# FreeCAD first, and this is not a style choice. Importing it clears the
# running module's globals - run `import argparse; import FreeCAD` and
# argparse is gone, with a NameError pages later that names a module you can
# see imported at the top of the file. Anything imported before it is lost,
# so nothing is.
import FreeCAD                                             # noqa: E402

import argparse                                            # noqa: E402
import io                                                  # noqa: E402
import sys                                                 # noqa: E402
import traceback                                           # noqa: E402
from contextlib import redirect_stdout                     # noqa: E402
from xmlrpc.server import SimpleXMLRPCServer                # noqa: E402


class Headless:
    """Enough of the addon's surface to drive a build end to end."""

    # -- is anybody there ---------------------------------------------------

    def ping(self) -> bool:
        return True

    def get_rpc_status(self) -> dict:
        return {"version": ".".join(FreeCAD.Version()[:3]),
                "gui_responsive": False, "headless": True}

    # -- documents ----------------------------------------------------------

    def list_documents(self) -> list:
        return list(FreeCAD.listDocuments())

    def create_document(self, name: str = "New_Document") -> dict:
        try:
            doc = FreeCAD.newDocument(name)
            return {"success": True, "document_name": doc.Name}
        except Exception as error:
            return {"success": False, "error": str(error)}

    # -- objects ------------------------------------------------------------

    def create_object(self, doc_name: str, obj_data: dict) -> dict:
        doc = FreeCAD.getDocument(doc_name) if doc_name in FreeCAD.listDocuments() \
            else None
        if doc is None:
            return {"success": False, "error": f"no document called {doc_name!r}"}
        try:
            obj = doc.addObject(obj_data["Type"], obj_data.get("Name") or "Object")
            for prop, value in (obj_data.get("Properties") or {}).items():
                setattr(obj, prop, value)
            doc.recompute()
            return {"success": True, "object_name": obj.Name}
        except Exception as error:
            return {"success": False, "error": f"{type(error).__name__}: {error}"}

    def edit_object(self, doc_name: str, obj_name: str, properties: dict) -> dict:
        doc = FreeCAD.getDocument(doc_name) if doc_name in FreeCAD.listDocuments() \
            else None
        if doc is None:
            return {"success": False, "error": f"no document called {doc_name!r}"}
        obj = doc.getObject(obj_name)
        if obj is None:
            return {"success": False, "error": f"no object called {obj_name!r}"}
        try:
            for prop, value in (properties.get("Properties") or {}).items():
                setattr(obj, prop, value)
            doc.recompute()
            return {"success": True, "object_name": obj.Name}
        except Exception as error:
            return {"success": False, "error": f"{type(error).__name__}: {error}"}

    def delete_object(self, doc_name: str, obj_name: str) -> dict:
        doc = FreeCAD.getDocument(doc_name) if doc_name in FreeCAD.listDocuments() \
            else None
        if doc is None or doc.getObject(obj_name) is None:
            return {"success": False, "error": f"no object called {obj_name!r}"}
        doc.removeObject(obj_name)
        doc.recompute()
        return {"success": True, "object_name": obj_name}

    def get_objects(self, doc_name: str) -> list:
        if doc_name not in FreeCAD.listDocuments():
            return []
        return [self._describe(obj)
                for obj in FreeCAD.getDocument(doc_name).Objects]

    def get_object(self, doc_name: str, obj_name: str):
        if doc_name not in FreeCAD.listDocuments():
            return None
        obj = FreeCAD.getDocument(doc_name).getObject(obj_name)
        return self._describe(obj) if obj is not None else None

    @staticmethod
    def _describe(obj) -> dict:
        """An object as the addon reports it: name, type, properties.

        Only the properties that carry a number or a string. A Placement or
        a link is not something this protocol can put on the wire, and the
        caller reads these to find a value it could set back.
        """
        properties = {}
        for prop in getattr(obj, "PropertiesList", []):
            try:
                value = getattr(obj, prop)
            except Exception:
                continue
            if hasattr(value, "Value"):          # a FreeCAD Quantity
                value = value.Value
            if isinstance(value, (int, float, str, bool)):
                properties[prop] = value
        return {"Name": obj.Name, "Label": obj.Label,
                "Type": obj.TypeId, "Properties": properties}

    # -- the wide door ------------------------------------------------------

    def execute_code(self, code: str, timeout=None) -> dict:
        """Run a script and hand back what it printed, as the addon does."""
        printed = io.StringIO()
        try:
            with redirect_stdout(printed):
                exec(compile(code, "<rpc>", "exec"),                # noqa: S102
                     {"__name__": "__rpc__", "FreeCAD": FreeCAD})
        except Exception as error:
            return {"success": False,
                    "error": f"{type(error).__name__}: {error}\n"
                             + traceback.format_exc()[-1500:]}
        return {"success": True,
                "message": "Python code executed successfully.\nOutput: "
                           + printed.getvalue()}

    def get_active_screenshot(self, view: str = "Isometric"):
        # No viewport without a GUI. The bridge treats this as a failure and
        # the version simply carries no render, which is the truth.
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9875)
    args = parser.parse_args()

    server = SimpleXMLRPCServer((args.host, args.port), allow_none=True,
                                logRequests=False)
    server.register_instance(Headless())
    print(f"FreeCAD {'.'.join(FreeCAD.Version()[:3])} (headless) on "
          f"{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
