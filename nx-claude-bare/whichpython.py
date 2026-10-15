"""Which Python is NX running, and where is it?

Run this in NX first - File -> Execute -> NX Open... - before anything
else here. It is four lines, it changes nothing, and it answers the one
question you cannot answer from outside: which interpreter the journal
will be using, and whether it is new enough.

`sys.executable` in an embedded interpreter is often the host program
(ugraf.exe) rather than a python.exe, so `sys.prefix` is the more useful
of the two: the python.exe that goes with it, if there is one, is usually
in that directory or its Scripts folder. That is the interpreter worth
running `hello.py` with, because it is the one that has to reach AWS.
"""

import sys

import NXOpen

window = NXOpen.Session.GetSession().ListingWindow
window.Open()
window.WriteLine("version    " + sys.version.replace("\n", " "))
window.WriteLine("executable " + str(sys.executable))
window.WriteLine("prefix     " + str(sys.prefix))
for found in ("ssl", "urllib.request", "hmac", "hashlib", "configparser",
              "json"):
    try:
        __import__(found)
        window.WriteLine("import     " + found + "  ok")
    except Exception as error:
        # If ssl is the one that fails, nothing here can reach AWS from
        # inside NX and the split design on the NX branch is the answer.
        window.WriteLine("import     " + found + "  FAILED: " + str(error))
