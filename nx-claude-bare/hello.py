"""One call to Bedrock, with no NX anywhere near it.

    python hello.py
    python hello.py "reply with the word fine and nothing else"

Run this first, on the machine, before opening NX. It answers one
question - can this machine reach Bedrock with these credentials and this
model id - and when the answer is no it says which of the three is
wrong. Finding that out from inside a journal, with NX's Information
window as the only output, is much harder than it needs to be.

It can be run by NX's own Python as well as by any other, and that is
worth doing too: NX's interpreter is the one that has to make the call,
and it is the one whose ssl and proxy settings are in question.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bedrock
import sigv4

ADVICE = """
  * 403 AccessDenied or UnrecognizedClient: the key is wrong, or it has
    no bedrock:InvokeModel permission.
  * 404 ResourceNotFound: the id %r is not callable by this account in
    %s. Nearly always the version or the prefix - try the geography form
    (us.anthropic....), or whichever id already works elsewhere on this
    account. Set it with BARE_MODEL.
  * 400 ValidationException about access: the model is not enabled for
    the account. Bedrock console -> Model access.
  * could not reach: a proxy. Set HTTPS_PROXY and try again.
"""


def main():
    asked = " ".join(sys.argv[1:]).strip() or (
        "In one short sentence: what are you, and can you see a CAD "
        "program from there?")
    where = sigv4.region()
    which = bedrock.model()
    print("python  %s" % sys.version.split()[0])
    print("region  %s" % where)
    print("model   %s" % which)
    try:
        creds = sigv4.credentials()
    except RuntimeError as error:
        print("\n%s" % error)
        return 1
    print("key     %s" % creds.key)
    print("asking  %s\n" % asked)

    try:
        reply = bedrock.ask([{"role": "user", "content": asked}],
                            max_tokens=512)
    except RuntimeError as error:
        print("FAILED: %s" % error)
        print(ADVICE % (which, where))
        return 1

    print(bedrock.text_of(reply) or "(the reply had no text in it)")
    usage = reply.get("usage") or {}
    print("\ntokens in %s, out %s" % (usage.get("input_tokens", "?"),
                                      usage.get("output_tokens", "?")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
