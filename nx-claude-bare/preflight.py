"""Will this machine run it? Answer before anybody travels.

Run it as an NX journal:  File -> Execute -> NX Open...
It changes nothing, opens nothing and saves nothing. It prints a report
into NX's Information window and writes the same text to
`preflight-report.txt` beside this file.

It can also be run from a command line by any Python 3 - NX's own, or
any other - in which case it skips the NX section and checks everything
else. On a locked-down machine with no Python installed, the journal is
the only way, which is why it is written to work as one.

It is built around the two things that actually stop this working on a
corporate Windows machine:

* **TLS inspection.** Zscaler and its equivalents terminate HTTPS and
  re-sign it with a private CA. The report names the issuer of the
  certificate actually served for the AWS endpoint, so interception
  shows up as a fact rather than a guess, and says whether this Python
  trusts it.
* **Proxying.** urllib reads the Windows proxy settings, but it cannot
  evaluate a PAC script. A machine configured only by PAC will look
  proxy-less here and fail to connect, so the report calls that case out
  by name.

Nothing secret is printed. Credentials are reported as present or
absent, never by value.
"""

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


def check(label, ok, detail=""):
    mark = "ok  " if ok else "FAIL"
    say("  [%s] %-38s %s" % (mark, label, detail))


# ----------------------------------------------------------------- NX
def nx_section():
    head("1. NX")
    try:
        import NXOpen
    except Exception as error:
        say("  not running inside NX (%s). The rest of the report still "
            "applies." % type(error).__name__)
        return None
    try:
        session = NXOpen.Session.GetSession()
    except Exception as error:
        check("NX session", False, "%s: %s" % (type(error).__name__, error))
        return None
    check("NX Open imports and a session exists", True)
    for label, getter in (
            ("NX version", lambda: session.GetEnvironmentVariableValue(
                "UGII_FULL_VERSION")),
            ("NX base directory", lambda: os.environ.get("UGII_BASE_DIR", "")),
    ):
        try:
            value = getter()
        except Exception:
            value = ""
        say("       %-36s %s" % (label, value or "(not reported)"))
    try:
        work = session.Parts.Work
    except Exception:
        work = None
    check("a part is open", work is not None,
          "open any part before the real run; not needed for this check")
    return session


# ------------------------------------------------------------- Python
def python_section():
    head("2. Python")
    say("       version    %s" % sys.version.replace("\n", " "))
    say("       executable %s" % sys.executable)
    say("       prefix     %s" % sys.prefix)
    ok = sys.version_info >= (3, 6)
    check("Python 3.6 or newer", ok, "3.6+ needed for this code")
    for name in ("ssl", "urllib.request", "hmac", "hashlib",
                 "configparser", "json", "socket"):
        try:
            __import__(name)
            check("import %s" % name, True)
        except Exception as error:
            check("import %s" % name, False, str(error))


# ------------------------------------------------------- trust and proxy
def trust_section():
    head("3. Certificate trust store")
    try:
        import ssl
    except Exception as error:
        check("ssl available", False, str(error))
        return
    try:
        context = ssl.create_default_context()
        certs = context.get_ca_certs()
    except Exception as error:
        check("load the default trust store", False,
              "%s: %s" % (type(error).__name__, error))
        return
    check("default trust store loads", True, "%d CA certificates" % len(certs))

    private = []
    for cert in certs:
        name = ""
        for part in cert.get("subject", ()):
            for key, value in part:
                if key in ("organizationName", "commonName"):
                    name = name or value
        low = name.lower()
        if any(word in low for word in
               ("zscaler", "netskope", "bluecoat", "blue coat", "forcepoint",
                "palo alto", "fortinet", "mcafee", "yamaha", "proxy")):
            private.append(name)
    if private:
        check("an inspection CA is trusted here", True,
              ", ".join(sorted(set(private))[:3]))
        say("       An inspecting proxy's CA is in this Python's trust")
        say("       store, which is what we want: it means re-signed HTTPS")
        say("       will verify rather than fail.")
    else:
        say("       No inspection CA found by name. That is fine if the")
        say("       machine is not inspected; if section 5 shows the AWS")
        say("       certificate issued by a private CA, this Python does")
        say("       not trust it and the call will fail verification.")


def proxy_section():
    head("4. Proxy configuration")
    try:
        import urllib.request
        found = urllib.request.getproxies()
    except Exception as error:
        check("read proxy settings", False, str(error))
        found = {}
    if found:
        for scheme, where in sorted(found.items()):
            say("       %-10s %s" % (scheme, where))
        check("a proxy is configured and urllib can see it", True)
    else:
        say("       none reported")
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "NO_PROXY"):
        if os.environ.get(name):
            say("       env %-14s %s" % (name, os.environ[name]))

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
        check("PAC script in use", False, autoconfig)
        say("       THIS IS THE ONE TO WATCH. The machine is configured by a")
        say("       PAC script, and urllib cannot evaluate one - it will try")
        say("       to connect directly and may be blocked. If section 5")
        say("       fails, set HTTPS_PROXY to the proxy the PAC resolves to")
        say("       (ask IT for the host and port) before starting NX.")
    else:
        check("no PAC script configured", True)


# ------------------------------------------------------------- the reach
def region():
    for name in ("AWS_REGION", "AWS_DEFAULT_REGION", "BEDROCK_REGION"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return "us-east-1"


def reach_section(host):
    head("5. Can this machine reach %s" % host)
    try:
        import ssl
    except Exception:
        return
    try:
        addresses = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        check("DNS resolves", True, addresses[0][4][0])
    except Exception as error:
        check("DNS resolves", False, "%s: %s" % (type(error).__name__, error))
        return

    # A direct TLS handshake, to read the certificate that is actually
    # served. An inspecting proxy shows up here by name.
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
                if key == "commonName" and not issuer:
                    issuer = value
        check("direct TLS handshake", True, "certificate issued by: %s"
              % (issuer or "(unnamed)"))
        if issuer and "amazon" not in issuer.lower():
            say("       That is NOT Amazon, so HTTPS to AWS is being")
            say("       inspected and re-signed on this machine. It")
            say("       verified, so this Python trusts the inspecting CA")
            say("       and the tool will work. Worth telling whoever signs")
            say("       off on where data goes: the proxy can read it.")
    except ssl.SSLCertVerificationError as error:
        check("direct TLS handshake", False, "certificate NOT trusted: %s"
              % error)
        say("       This is the blocking case. HTTPS is being re-signed by a")
        say("       CA this Python does not trust. Fix: have IT place the")
        say("       inspection root CA where this Python reads it, or set")
        say("       SSL_CERT_FILE to a PEM bundle containing it.")
    except Exception as error:
        check("direct TLS handshake", False,
              "%s: %s" % (type(error).__name__, error))
        say("       Could be a proxy-only network, where a direct connection")
        say("       is not allowed. See section 4.")

    # And the request urllib would really make, proxies and all.
    try:
        import urllib.error
        import urllib.request
        request = urllib.request.Request(
            "https://%s/" % host, method="GET",
            headers={"User-Agent": "nx-preflight"})
        try:
            with urllib.request.urlopen(request, timeout=25) as answer:
                code, body = answer.status, answer.read(400)
        except urllib.error.HTTPError as error:
            code, body = error.code, error.read(400)
        text = body.decode("utf-8", "replace")
        aws_like = ("x-amzn" in text.lower() or "amazon" in text.lower()
                    or code in (400, 403, 404))
        check("HTTPS request completes", True, "HTTP %s" % code)
        if aws_like:
            say("       An error from AWS itself is the RIGHT answer here:")
            say("       it means the request reached Amazon. Unauthenticated")
            say("       requests are supposed to be refused.")
        else:
            say("       The reply does not look like AWS. If it looks like a")
            say("       block page, the category is filtered - that is a")
            say("       policy decision, not a technical fault, and it needs")
            say("       an allow-list entry for this hostname.")
            say("       First 200 characters of the reply:")
            say("       " + text[:200].replace("\n", " "))
    except Exception as error:
        check("HTTPS request completes", False,
              "%s: %s" % (type(error).__name__, error))


# ------------------------------------------------------- credentials, disk
def credentials_section():
    head("6. AWS credentials (presence only - no values are read)")
    env = [n for n in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                       "AWS_SESSION_TOKEN", "AWS_PROFILE")
           if os.environ.get(n)]
    where = os.path.expanduser(
        os.environ.get("AWS_SHARED_CREDENTIALS_FILE", "~/.aws/credentials"))
    on_disk = os.path.isfile(where)
    # Either route is enough, so this is one check and not two - a
    # missing file is not a failure when the environment carries them.
    check("credentials available", bool(env) or on_disk,
          "" if (env or on_disk) else "neither environment nor file")
    say("       environment: %s" % (", ".join(env) if env else "none set"))
    say("       file:        %s" % (where if on_disk else "not present"))
    say("       region:      %s" % region())
    if env and not on_disk:
        say("       Environment only. NX inherited its environment when it")
        say("       started, so a variable set after NX was already open")
        say("       will NOT reach the journal. The file is the safer route")
        say("       on a machine where NX stays running: `aws configure`.")
    if not env and not on_disk:
        say("       Run `aws configure`, or copy a credentials file into")
        say("       place, before the real run.")


def disk_section(here):
    head("7. Can it write its transcript")
    target = os.path.join(here, "preflight-write-test.tmp")
    try:
        with open(target, "w") as handle:
            handle.write("ok")
        os.remove(target)
        check("writable folder beside the journal", True, here)
    except Exception as error:
        check("writable folder beside the journal", False,
              "%s: %s" % (type(error).__name__, error))
        say("       Put the folder somewhere the user owns, such as")
        say("       C:\\Users\\<name>\\nx-claude-bare.")


def verdict():
    head("Verdict")
    bad = [line for line in LINES if line.startswith("  [FAIL]")]
    if not bad:
        say("  Nothing failed. This machine can run it.")
    else:
        say("  %d check(s) failed:" % len(bad))
        for line in bad:
            say("   " + line.strip())
        say()
        say("  Send this report back before anybody travels. Most of these")
        say("  are a setting or an allow-list entry, not a dead end.")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    say("nx-claude-bare preflight")
    say("========================")
    say("Changes nothing. Opens nothing. Saves nothing.")
    nx_section()
    python_section()
    trust_section()
    proxy_section()
    reach_section("bedrock-runtime.%s.amazonaws.com" % region())
    credentials_section()
    disk_section(here)
    verdict()

    report = "\n".join(LINES)
    try:
        session = __import__("NXOpen").Session.GetSession()
        window = session.ListingWindow
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
        out = os.path.join(here, "preflight-report.txt")
        with open(out, "w") as handle:
            handle.write(report + "\n")
        try:
            __import__("NXOpen").Session.GetSession().ListingWindow.WriteLine(
                "\nreport written to: " + out)
        except Exception:
            print("\nreport written to: " + out)
    except Exception:
        pass


try:
    main()
except Exception:
    trace = traceback.format_exc()
    try:
        w = __import__("NXOpen").Session.GetSession().ListingWindow
        w.Open()
        for line in trace.splitlines():
            w.WriteLine(line)
    except Exception:
        print(trace)
