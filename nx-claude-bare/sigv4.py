"""Talking to AWS with nothing but the Python standard library.

NX brings its own Python interpreter and journals run inside it. There is
no pip there, nothing is installed into it, and on a corporate machine
nothing is going to be: `boto3` is not an option, so neither is
`bedrock-runtime` through boto3. What is left is to sign the request by
hand, which is a hundred lines of hmac and no dependencies at all.

Signing is the one part of this folder that cannot be checked by reading
it - a signature is either byte-identical to what AWS computes or the
call comes back 403 with no explanation. So `check.py` signs the same
request with this module and with botocore and compares the two
signatures. That test needs no AWS account and no NX; it is the reason to
trust the rest.

Everything here follows botocore's own SigV4Auth, including the details
that are not in the signing documentation: the path is percent-encoded
once with `/` and `~` left alone, and ten hop-by-hop headers are left out
of the signature even when they are sent.
"""

import configparser
import datetime
import hashlib
import hmac
import os
import urllib.error
import urllib.parse
import urllib.request

ALGORITHM = "AWS4-HMAC-SHA256"
STAMP = "%Y%m%dT%H%M%SZ"

#: Headers that are sent but never signed. A proxy is allowed to rewrite
#: these in flight, and a signature over them would break when it did.
NEVER_SIGNED = (
    "connection", "expect", "keep-alive", "proxy-authenticate",
    "proxy-authorization", "te", "trailer", "transfer-encoding",
    "upgrade", "user-agent", "x-amzn-trace-id",
)


class Credentials(object):
    """An access key, its secret, and a session token if there is one."""

    def __init__(self, key, secret, token=""):
        self.key = key
        self.secret = secret
        self.token = token or ""

    def __repr__(self):
        # The secret must never reach a log, an Information window, or a
        # transcript the engineer pastes into a chat window.
        return "Credentials(key=%r, secret=<hidden>, token=%s)" % (
            self.key, "<hidden>" if self.token else "''")


def _profile():
    return os.environ.get("AWS_PROFILE") or "default"


def _ini(path):
    parser = configparser.RawConfigParser()
    try:
        parser.read(os.path.expanduser(path))
    except Exception:
        return None
    return parser


def _from_ini(path, keys):
    """One value out of an AWS ini file, under this profile.

    `~/.aws/credentials` names the section after the profile;
    `~/.aws/config` writes it as `[profile name]` for every profile but
    default. Both spellings are tried because `aws configure` writes one
    file in each style.
    """
    parser = _ini(path)
    if parser is None:
        return ""
    name = _profile()
    for section in (name, "profile " + name):
        if not parser.has_section(section):
            continue
        for key in keys:
            if parser.has_option(section, key):
                value = parser.get(section, key).strip()
                if value:
                    return value
    return ""


def credentials():
    """Whatever credentials this machine has, or a readable complaint.

    Environment first, then the files `aws configure` writes, which is
    where they will be on a Windows machine where somebody ran that once.
    Nothing is read from the repository and nothing is written anywhere.
    """
    key = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
    token = os.environ.get("AWS_SESSION_TOKEN", "").strip()
    if not (key and secret):
        where = os.environ.get("AWS_SHARED_CREDENTIALS_FILE",
                               "~/.aws/credentials")
        key = key or _from_ini(where, ("aws_access_key_id",))
        secret = secret or _from_ini(where, ("aws_secret_access_key",))
        token = token or _from_ini(where, ("aws_session_token",))
    if not (key and secret):
        raise RuntimeError(
            "no AWS credentials. Set AWS_ACCESS_KEY_ID and "
            "AWS_SECRET_ACCESS_KEY in the environment, or run "
            "`aws configure` so that %s exists."
            % os.path.expanduser(os.environ.get(
                "AWS_SHARED_CREDENTIALS_FILE", "~/.aws/credentials")))
    return Credentials(key, secret, token)


def region():
    """The region to call, which must be one Bedrock is enabled in."""
    for name in ("AWS_REGION", "AWS_DEFAULT_REGION", "BEDROCK_REGION"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    found = _from_ini(os.environ.get("AWS_CONFIG_FILE", "~/.aws/config"),
                      ("region",))
    return found or "us-east-1"


def _hmac(key, message, hexed=False):
    mac = hmac.new(key, message.encode("utf-8"), hashlib.sha256)
    return mac.hexdigest() if hexed else mac.digest()


def _signing_key(secret, day, where, service):
    key = _hmac(("AWS4" + secret).encode("utf-8"), day)
    key = _hmac(key, where)
    key = _hmac(key, service)
    return _hmac(key, "aws4_request")


def _canonical_headers(headers):
    """The signed headers, lowercased, sorted, whitespace collapsed."""
    keep = {}
    for name, value in headers.items():
        lower = name.lower()
        if lower in NEVER_SIGNED:
            continue
        keep[lower] = " ".join(str(value).split())
    names = sorted(keep)
    block = "".join("%s:%s\n" % (name, keep[name]) for name in names)
    return block, ";".join(names)


def sign(method, url, body, headers, creds, service="bedrock",
         where=None, now=None):
    """The same headers, with Authorization and X-Amz-Date added.

    `body` is bytes, because the signature covers the bytes that go on
    the wire and not the object they were serialised from.
    """
    if where is None:
        where = region()
    if now is None:
        now = datetime.datetime.utcnow()
    moment = now.strftime(STAMP)
    day = moment[:8]

    parts = urllib.parse.urlsplit(url)
    headers = dict(headers)
    headers["Host"] = parts.hostname + (
        ":%d" % parts.port if parts.port and parts.port not in (80, 443)
        else "")
    headers["X-Amz-Date"] = moment
    if creds.token:
        headers["X-Amz-Security-Token"] = creds.token

    # Encoded once, with `/` and `~` left as themselves. This is what
    # botocore does and `check.py` is what says so; the AWS signing page
    # can be read as asking for two passes, and two passes is a 403.
    path = urllib.parse.quote(parts.path or "/", safe="/~")
    query = parts.query or ""
    if query:
        pairs = []
        for pair in query.split("&"):
            name, _, value = pair.partition("=")
            pairs.append((name, value))
        query = "&".join("%s=%s" % pair for pair in sorted(pairs))

    block, signed = _canonical_headers(headers)
    canonical = "\n".join([
        method.upper(),
        path,
        query,
        block,
        signed,
        hashlib.sha256(body or b"").hexdigest(),
    ])
    scope = "/".join([day, where, service, "aws4_request"])
    to_sign = "\n".join([
        ALGORITHM,
        moment,
        scope,
        hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    ])
    signature = _hmac(_signing_key(creds.secret, day, where, service),
                      to_sign, hexed=True)
    headers["Authorization"] = (
        "%s Credential=%s/%s, SignedHeaders=%s, Signature=%s"
        % (ALGORITHM, creds.key, scope, signed, signature))
    return headers


def post(url, body, headers, timeout=180):
    """POST signed bytes and return the response body.

    An AWS error arrives as an HTTP error with the reason in the body, so
    the body is read out of the exception and raised with it. Without
    that, a wrong model id or a region where Bedrock is not enabled is
    just "HTTP Error 404: Not Found", which says nothing about which of
    the two it was.
    """
    request = urllib.request.Request(url, data=body, method="POST")
    for name, value in headers.items():
        request.add_header(name, value)
    try:
        answer = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            detail = error.read().decode("utf-8", "replace")
        except Exception:
            pass
        raise RuntimeError("AWS said %s %s: %s"
                           % (error.code, error.reason, detail.strip()))
    except urllib.error.URLError as error:
        raise RuntimeError(
            "could not reach %s: %s. If this machine goes out through a "
            "proxy, set HTTPS_PROXY and try again."
            % (urllib.parse.urlsplit(url).hostname, error.reason))
    with answer:
        return answer.read()
