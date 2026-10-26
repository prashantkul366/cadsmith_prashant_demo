"""Everything we need to know about this machine, in one run.

Run as an NX journal, with a part open:

    File -> Execute -> NX Open...   and pick this file.

It answers both halves of "can we build and run our tool here":

  * **The NX half.** Are journals permitted, does NX Open answer or does
    the licence refuse, which API names does this release actually have,
    and would a change go through. All of that is read from NX itself.
  * **The machine half.** Does this Python have what we need, is HTTPS
    being inspected and re-signed by a corporate proxy, is a PAC script
    in use, and can the AWS endpoint be reached at all.

**It changes nothing in the part** and saves nothing, unless you switch
on the write test below. It needs no AWS keys, no account and no
administrator rights.

**It makes exactly one network request**: an ordinary HTTPS GET to an
Amazon address, with no login and no data attached, purely to see
whether the network allows it or a proxy blocks it. Set CHECK_NETWORK to
False below and it makes none at all.

The report goes into NX's Information window and into
`check-report.txt` beside this file.

The single most important number in it is how many expressions carry
NX's own note saying what they drive, like `p7 (Simple Hole(12)
Diameter)`. The whole approach rests on that: it is what lets a tool
change a part somebody else modelled years ago without knowing how it
was built. If it is zero on real parts here, the design needs
rethinking, and this report is a far cheaper way to find out than a
pilot.
"""

# ---------------------------------------------------------------------
# Two switches. Both are safe to leave as they are.
# ---------------------------------------------------------------------

#: One unauthenticated HTTPS GET to an Amazon address, to find out
#: whether the network permits it. Nothing is sent and nothing is
#: downloaded. Set to False to make this file touch no network at all.
CHECK_NETWORK = True

#: Set True ONLY on a scratch part you do not care about. It proves the
#: write path by writing one expression back to THE VALUE IT ALREADY
#: HAS, then updating - the geometry cannot change. An undo mark is set
#: first. Close without saving afterwards.
DO_WRITE_TEST = False

import os
import socket
import sys
import traceback

LINES = []


def say(text=""):
    LINES.append(str(text))


def head(text):
    say()
    say(text)
    say("-" * len(text))


def mark(ok, label, detail=""):
    say("  [%s] %-44s %s" % ("ok  " if ok else "FAIL", label, detail))


def ask(thing, name):
    """One property or method, without letting a bad one stop the rest.

    Not guarded with hasattr: a .NET property that does not apply to a
    given feature type raises something other than AttributeError when
    touched, and that would take the whole report down with it.
    """
    try:
        got = getattr(thing, name)
    except Exception as error:
        return False, "%s: %s" % (type(error).__name__, error)
    if callable(got):
        try:
            got = got()
        except Exception as error:
            return True, "callable, raised %s" % type(error).__name__
    return True, got


def short(value, width=46):
    try:
        text = str(value)
    except Exception:
        return "(unprintable)"
    text = " ".join(text.split())
    return text if len(text) <= width else text[:width - 1] + "…"


FEATURE_WANTS = [
    ("JournalIdentifier", "the stable handle we refer to a feature by"),
    ("Name", "what to call it in the tree"),
    ("FeatureType", "what kind of feature it is"),
    ("Timestamp", "where it sits in the build order"),
    ("Suppressed", "whether it is currently taken out"),
    ("IsSuppressed", "the other spelling of the same thing"),
    ("GetExpressions", "the numbers that drive it"),
]

EXPRESSION_WANTS = [
    ("Name", "p1, p7, and so on"),
    ("Value", "the number"),
    ("Units", "what the number is in"),
    ("Description", "WHICH FEATURE AND PARAMETER IT DRIVES"),
    ("Equation", "the formula, where there is one"),
    ("RightHandSide", "the other spelling of the formula"),
    ("Type", "number, string, point"),
    ("EditLocked", "whether it may be written at all"),
]

#: Checked for existence only. Nothing here is ever called.
WRITE_PATH = [
    ("work.Expressions", "Edit", "change an expression's value"),
    ("work.Features", "SuppressFeatures", "take a feature out"),
    ("work.Features", "UnsuppressFeatures", "put it back"),
    ("work.Features", "DeleteFeatures", "remove it"),
    ("session", "SetUndoMark", "make the change reversible"),
    ("session.UpdateManager", "DoUpdate", "rebuild the part"),
]

NX_FAILURES = []        # blocking problems on the NX side
NET_FAILURES = []       # blocking problems on the machine / network side


# =====================================================================
# the NX half
# =====================================================================

def nx_half():
    head("1. Is it allowed to run here")
    say("  Journal execution: you are reading this, so NX ran a Python")
    say("  journal. That half is already answered - yes.")
    try:
        import NXOpen
    except Exception as error:
        mark(False, "import NXOpen", "%s: %s" % (type(error).__name__, error))
        NX_FAILURES.append("NX Open is not available")
        return None, None
    mark(True, "import NXOpen")
    try:
        session = NXOpen.Session.GetSession()
    except Exception as error:
        mark(False, "get an NX session",
             "%s: %s" % (type(error).__name__, error))
        say("  This is usually a licence refusal, and it is the answer to")
        say("  'can it be integrated here'. It needs Siemens, not us.")
        NX_FAILURES.append("NX Open refused a session (likely licensing)")
        return None, None
    mark(True, "get an NX session", "no licence refusal")

    for label, name in (("NX version", "UGII_FULL_VERSION"),
                        ("NX release", "UGII_VERSION")):
        try:
            value = session.GetEnvironmentVariableValue(name)
        except Exception:
            value = ""
        if value:
            say("       %-20s %s" % (label, value))

    try:
        work = session.Parts.Work
    except Exception as error:
        work = None
        mark(False, "reach the work part",
             "%s: %s" % (type(error).__name__, error))
    if work is None:
        mark(False, "a part is open", "open a part and run this again")
        say()
        say("  Everything about the tree needs a part. Open one - ideally")
        say("  a real one with holes, patterns and blends rather than an")
        say("  empty file - and run this again.")
        NX_FAILURES.append("no part was open, so the tree was not checked")
        return session, None
    mark(True, "a part is open", short(ask(work, "FullPath")[1]))
    return session, work


def tree_half(work):
    head("2. Can we read the feature tree")
    features = []
    try:
        features = list(work.Features)
        mark(True, "read the feature list", "%d features" % len(features))
    except Exception as error:
        mark(False, "read the feature list",
             "%s: %s" % (type(error).__name__, error))
        NX_FAILURES.append("the feature list could not be read")
        return []
    if not features:
        say("  The part has no features. Try one that was modelled rather")
        say("  than imported.")
        return []

    say()
    say("  Which properties a feature actually has on this release:")
    for name, why in FEATURE_WANTS:
        exists, value = ask(features[0], name)
        if exists:
            mark(True, name, "%s  (%s)" % (short(value, 26), why))
        else:
            mark(False, name, "not available  (%s)" % why)
    say()
    say("  The first few features, as the tool would see them:")
    for one in features[:8]:
        ident = ask(one, "JournalIdentifier")[1] or ask(one, "Name")[1]
        say("       %-30s %s" % (short(ident, 30),
                                 short(ask(one, "FeatureType")[1], 24)))
    if len(features) > 8:
        say("       ... and %d more" % (len(features) - 8))
    return features


def expression_half(work):
    head("3. Can we read the expressions that drive it")
    expressions = []
    try:
        expressions = list(work.Expressions)
        mark(True, "read the expression list",
             "%d expressions" % len(expressions))
    except Exception as error:
        mark(False, "read the expression list",
             "%s: %s" % (type(error).__name__, error))
        NX_FAILURES.append("the expression list could not be read")
        return []
    if not expressions:
        say("  No expressions on this part.")
        NX_FAILURES.append("the part carries no expressions to drive")
        return []

    say()
    say("  Which properties an expression actually has here:")
    for name, why in EXPRESSION_WANTS:
        exists, value = ask(expressions[0], name)
        if exists:
            mark(True, name, "%s  (%s)" % (short(value, 22), why))
        else:
            mark(False, name, "not available  (%s)" % why)

    described, numeric = 0, []
    for one in expressions:
        text = ask(one, "Description")[1]
        if text and str(text).strip():
            described += 1
        formula = str(ask(one, "Equation")[1] or "")
        value = ask(one, "Value")[1]
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        name = str(ask(one, "Name")[1] or "")
        if name and formula.strip() in ("", str(value), "%g" % number):
            numeric.append((one, name, number))

    say()
    say("  THE NUMBER THAT MATTERS")
    pct = 100.0 * described / len(expressions)
    mark(described > 0, "expressions that say what they drive",
         "%d of %d  (%.0f%%)" % (described, len(expressions), pct))
    if described:
        say()
        say("  Examples - this is what lets the tool work on a part it")
        say("  did not build:")
        shown = 0
        for one in expressions:
            text = ask(one, "Description")[1]
            if text and str(text).strip():
                say("       %-10s = %-12s %s"
                    % (short(ask(one, "Name")[1], 10),
                       short(ask(one, "Value")[1], 12), short(text, 42)))
                shown += 1
                if shown >= 6:
                    break
    else:
        NX_FAILURES.append(
            "no expression says what it drives - the approach depends on it")
        say()
        say("  None of them say what they drive. Either this part was")
        say("  built in a way that does not record it, or this release")
        say("  names the property differently. Try a part with holes and")
        say("  patterns before concluding anything - and send the report")
        say("  either way.")

    say()
    mark(len(numeric) > 0, "plain numbers we could safely edit",
         "%d of %d (the rest are formula-driven or not numeric)"
         % (len(numeric), len(expressions)))
    say("       A formula-driven expression is deliberately refused by the")
    say("       tool rather than overwritten, so this is the part of the")
    say("       tree it would actually offer to change.")
    return numeric


def write_path_half(session, work):
    head("4. Would a change go through")
    say("  Checked for existence only. Nothing here is called.")
    scope = {"session": session}
    for key, getter in (("session.UpdateManager", lambda: session.UpdateManager),
                        ("work.Expressions", lambda: work.Expressions),
                        ("work.Features", lambda: work.Features)):
        try:
            scope[key] = getter()
        except Exception:
            scope[key] = None
    for owner, method, why in WRITE_PATH:
        holder = scope.get(owner)
        if holder is None:
            mark(False, "%s.%s" % (owner, method), "%s is unavailable" % owner)
            NX_FAILURES.append("%s is unavailable" % owner)
            continue
        try:
            found = callable(getattr(holder, method))
        except Exception:
            found = False
        mark(found, "%s.%s" % (owner, method), why)
        if not found:
            NX_FAILURES.append("%s.%s is missing" % (owner, method))


def write_test_half(session, work, numeric):
    head("5. A real no-op write")
    if not DO_WRITE_TEST:
        say("  Skipped. Nothing in the part was changed.")
        say("  To run it: open a SCRATCH part, set DO_WRITE_TEST = True at")
        say("  the top of this file, run again, then close without saving.")
        return
    if not numeric:
        say("  Skipped: no plain numeric expression on this part to use.")
        return
    import NXOpen
    one, name, value = numeric[0]
    say("  Using %s, currently %g. Writing the same value back." %
        (name, value))
    try:
        session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                            "check no-op")
        mark(True, "set an undo mark")
    except Exception as error:
        mark(False, "set an undo mark", "%s: %s" % (type(error).__name__, error))
    try:
        work.Expressions.Edit(one, "%s=%.10g" % (name, value))
        mark(True, "edit the expression")
    except Exception as error:
        mark(False, "edit the expression",
             "%s: %s" % (type(error).__name__, error))
        NX_FAILURES.append("an expression could not be edited")
    try:
        session.UpdateManager.DoUpdate(
            session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                                "check update"))
        mark(True, "rebuild the part")
    except Exception as error:
        mark(False, "rebuild the part",
             "%s: %s" % (type(error).__name__, error))
        NX_FAILURES.append("the part would not rebuild")
    after = ask(one, "Value")[1]
    try:
        back = abs(float(after) - value) < 1e-9
    except (TypeError, ValueError):
        back = False
    mark(back, "read the value back unchanged", short(after, 20))
    say()
    say("  The part is now marked modified even though nothing moved.")
    say("  Close it without saving.")


# =====================================================================
# the machine half
# =====================================================================

def python_half():
    head("6. This Python")
    say("       version    %s" % sys.version.replace("\n", " "))
    say("       executable %s" % sys.executable)
    say("       prefix     %s" % sys.prefix)
    ok = sys.version_info >= (3, 6)
    mark(ok, "Python 3.6 or newer", "3.6+ is what the tool needs")
    if not ok:
        NET_FAILURES.append("Python is older than 3.6")
    for name in ("ssl", "urllib.request", "hmac", "hashlib",
                 "configparser", "json", "socket"):
        try:
            __import__(name)
            mark(True, "import %s" % name)
        except Exception as error:
            mark(False, "import %s" % name, str(error))
            NET_FAILURES.append("Python cannot import %s" % name)


def trust_half():
    head("7. Certificate trust")
    try:
        import ssl
        context = ssl.create_default_context()
        certs = context.get_ca_certs()
    except Exception as error:
        mark(False, "load the default trust store",
             "%s: %s" % (type(error).__name__, error))
        NET_FAILURES.append("the certificate trust store would not load")
        return
    mark(True, "default trust store loads", "%d CA certificates" % len(certs))
    private = []
    for cert in certs:
        name = ""
        for part in cert.get("subject", ()):
            for key, value in part:
                if key in ("organizationName", "commonName"):
                    name = name or value
        if any(w in name.lower() for w in
               ("zscaler", "netskope", "bluecoat", "blue coat", "forcepoint",
                "palo alto", "fortinet", "mcafee", "yamaha", "proxy")):
            private.append(name)
    if private:
        mark(True, "an inspection CA is trusted here",
             ", ".join(sorted(set(private))[:3]))
        say("       Good: re-signed HTTPS will verify rather than fail.")
    else:
        say("       No inspection CA found by name. Fine if the machine is")
        say("       not inspected - but if section 9 shows the AWS")
        say("       certificate issued by a private CA, this Python does")
        say("       not trust it and the call will fail verification.")


def proxy_half():
    head("8. Proxy configuration")
    try:
        import urllib.request
        found = urllib.request.getproxies()
    except Exception as error:
        mark(False, "read proxy settings", str(error))
        found = {}
    if found:
        for scheme, where in sorted(found.items()):
            say("       %-10s %s" % (scheme, where))
        mark(True, "a proxy is configured and urllib can see it")
    else:
        say("       none reported")
    autoconfig = ""
    try:
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
            try:
                autoconfig = winreg.QueryValueEx(key, "AutoConfigURL")[0]
            except FileNotFoundError:
                autoconfig = ""
            finally:
                key.Close()
    except Exception:
        autoconfig = ""
    if autoconfig:
        mark(False, "PAC script in use", autoconfig)
        NET_FAILURES.append("a PAC script configures the proxy")
        say("       THE ONE TO WATCH. urllib cannot evaluate a PAC script,")
        say("       so it will try to connect directly and may be blocked.")
        say("       Ask IT which proxy host and port the PAC resolves to,")
        say("       and set HTTPS_PROXY before starting NX.")
    else:
        mark(True, "no PAC script configured")


def region():
    for name in ("AWS_REGION", "AWS_DEFAULT_REGION", "BEDROCK_REGION"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return "us-east-1"


def reach_half():
    host = "bedrock-runtime.%s.amazonaws.com" % region()
    head("9. Can this machine reach %s" % host)
    if not CHECK_NETWORK:
        say("  Skipped: CHECK_NETWORK is False. No network was touched.")
        return
    try:
        import ssl
        addresses = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        mark(True, "DNS resolves", addresses[0][4][0])
    except Exception as error:
        mark(False, "DNS resolves", "%s: %s" % (type(error).__name__, error))
        NET_FAILURES.append("the AWS hostname does not resolve")
        return
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=20) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                cert = tls.getpeercert()
        issuer = ""
        for part in cert.get("issuer", ()):
            for key, value in part:
                if key == "organizationName":
                    issuer = issuer or value
                elif key == "commonName" and not issuer:
                    issuer = value
        mark(True, "direct TLS handshake",
             "certificate issued by: %s" % (issuer or "(unnamed)"))
        if issuer and "amazon" not in issuer.lower():
            say("       That is NOT Amazon, so HTTPS to AWS is inspected and")
            say("       re-signed on this machine. It verified, so the tool")
            say("       will work - and whoever signs off on where data goes")
            say("       should know the proxy can read it.")
    except ssl.SSLCertVerificationError as error:
        mark(False, "direct TLS handshake", "certificate NOT trusted: %s" % error)
        NET_FAILURES.append("HTTPS is re-signed by a CA this Python distrusts")
        say("       Fix: have IT place the inspection root CA where this")
        say("       Python reads it, or set SSL_CERT_FILE to a PEM bundle")
        say("       containing it.")
    except Exception as error:
        mark(False, "direct TLS handshake",
             "%s: %s" % (type(error).__name__, error))
        say("       Could be a proxy-only network. See section 8.")

    try:
        import urllib.error
        import urllib.request
        request = urllib.request.Request(
            "https://%s/" % host, method="GET",
            headers={"User-Agent": "nx-check"})
        try:
            with urllib.request.urlopen(request, timeout=25) as answer:
                code, body = answer.status, answer.read(400)
        except urllib.error.HTTPError as error:
            code, body = error.code, error.read(400)
        text = body.decode("utf-8", "replace")
        mark(True, "HTTPS request completes", "HTTP %s" % code)
        if "amazon" in text.lower() or "x-amzn" in text.lower() or \
                code in (400, 403, 404):
            say("       An error from AWS is the RIGHT answer: it means the")
            say("       request reached Amazon. Unauthenticated requests are")
            say("       supposed to be refused.")
        else:
            NET_FAILURES.append("the reply came from something other than AWS")
            say("       That does not look like AWS. If it is a block page,")
            say("       the category is filtered - a policy decision, not a")
            say("       fault, needing an allow-list entry for this host.")
            say("       First 200 characters:")
            say("       " + text[:200].replace("\n", " "))
    except Exception as error:
        mark(False, "HTTPS request completes",
             "%s: %s" % (type(error).__name__, error))
        NET_FAILURES.append("the AWS endpoint could not be reached")


def credentials_half():
    head("10. AWS credentials (presence only - never read, never printed)")
    env = [n for n in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                       "AWS_SESSION_TOKEN", "AWS_PROFILE")
           if os.environ.get(n)]
    where = os.path.expanduser(
        os.environ.get("AWS_SHARED_CREDENTIALS_FILE", "~/.aws/credentials"))
    # Reported, never failed: on a surveyed machine the keys usually
    # belong to somebody else and their absence is expected.
    say("  [--  ] credentials are not needed for this check")
    say("       environment: %s" % (", ".join(env) if env else "none set"))
    say("       file:        %s" % (where if os.path.isfile(where)
                                    else "not present"))
    say("       region:      %s" % region())
    if env and not os.path.isfile(where):
        say("       Environment only. NX inherited its environment when it")
        say("       started, so anything set after NX was already open will")
        say("       NOT reach a journal. The file is the safer route.")


def disk_half():
    head("11. Can it write its report")
    here = os.path.dirname(os.path.abspath(__file__))
    target = os.path.join(here, "check-write-test.tmp")
    try:
        with open(target, "w") as handle:
            handle.write("ok")
        os.remove(target)
        mark(True, "writable folder beside this file", here)
    except Exception as error:
        mark(False, "writable folder beside this file",
             "%s: %s" % (type(error).__name__, error))
        NET_FAILURES.append("the folder is not writable")
        say("       Put this file somewhere you own, such as your Desktop.")


def verdict():
    head("VERDICT")
    say("  Two separate questions, two separate answers.")
    say()
    if NX_FAILURES:
        say("  NX side:      %d thing(s) need attention" % len(NX_FAILURES))
        for one in NX_FAILURES:
            say("                - " + one)
    else:
        say("  NX side:      WORKS. NX here supports what we are building.")
    say()
    if NET_FAILURES:
        say("  Machine side: %d thing(s) need attention" % len(NET_FAILURES))
        for one in NET_FAILURES:
            say("                - " + one)
        say("                Most of these are a setting or an allow-list")
        say("                entry for IT, not a dead end.")
    else:
        say("  Machine side: WORKS. Nothing is in the way.")
    say()
    spelling = [l for l in LINES
                if l.startswith("  [FAIL]") and "not available" in l]
    if spelling:
        say("  %d API name(s) are spelled differently on this release."
            % len(spelling))
        say("  That is exactly what this report is for - a small")
        say("  correction, not a redesign.")
    say()
    say("  Send the whole report back.")


def main():
    say("NX capability and machine check")
    say("===============================")
    say("Changes nothing in the part. Needs no AWS keys, no admin rights.")
    say("Makes one unauthenticated HTTPS request, and none if")
    say("CHECK_NETWORK is set to False at the top of this file.")

    session, work = nx_half()
    if work is not None:
        tree_half(work)
        numeric = expression_half(work)
        write_path_half(session, work)
        write_test_half(session, work, numeric)
    python_half()
    trust_half()
    proxy_half()
    reach_half()
    credentials_half()
    disk_half()
    verdict()


try:
    main()
except Exception:
    LINES.append("")
    LINES.append("The check itself failed. That is useful too:")
    LINES.extend(traceback.format_exc().splitlines())

report = "\n".join(LINES)
try:
    import NXOpen
    window = NXOpen.Session.GetSession().ListingWindow
    window.Open()
    for line in LINES:
        window.WriteLine(line)
except Exception:
    pass
try:
    sys.stdout.write(report + "\n")
except Exception:
    pass
try:
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "check-report.txt")
    with open(out, "w") as handle:
        handle.write(report + "\n")
    try:
        NXOpen.Session.GetSession().ListingWindow.WriteLine(
            "\nreport written to: " + out)
    except Exception:
        print("\nreport written to: " + out)
except Exception:
    pass
