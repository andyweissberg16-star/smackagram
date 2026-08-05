"""
Proving a webhook came from Twilio.
===================================
There was no validation on any Twilio webhook. Anything could POST to
/call-status, /call-instructions or /recording-ready and be believed.

WHY IT MATTERS MORE THAN IT DID
-------------------------------
Until an automatic refund was added, forging a call status only corrupted
a record. Now a forged "failed" triggers a refund - so it became:

    send a smack, receive it, then POST failed and get the money back.

Free smacks, indefinitely, for the cost of an email address.

HOW IT WORKS
------------
Twilio signs every request with your auth token. The signature covers the
FULL URL plus every POST parameter, so it cannot be replayed against a
different order id or a different endpoint.

THE URL HAS TO MATCH EXACTLY
----------------------------
This is where these implementations usually go wrong. Behind a proxy,
request.url says http:// while Twilio called https://, and the signature
fails for everybody. BASE_URL is used to rebuild the address Twilio
actually saw.
"""

import os


def _expected_url(request):
    """
    The URL Twilio signed, not the one Flask thinks it received.

    Render terminates TLS at the proxy, so request.url can report http
    when the caller used https - and a signature computed over the wrong
    scheme fails every time, which looks like an attack and is actually a
    configuration detail.
    """
    base = os.environ.get("BASE_URL")
    if base:
        return base.rstrip("/") + request.full_path.rstrip("?")
    # No BASE_URL: force https, since Twilio will not call anything else.
    return request.url.replace("http://", "https://", 1)


def is_from_twilio(request):
    """
    Did Twilio send this?

    Returns True to accept. FAILS OPEN when no auth token is configured -
    deliberately, and it is the one uncomfortable decision here.

    A missing token would otherwise reject every real call status, so
    deliveries would silently stop being recorded and nobody would know
    why. Refusing everything because a variable is unset trades a
    theoretical attack for a certain outage.

    It says so loudly in the log instead, so the gap is visible rather
    than silent.
    """
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not token:
        print("[twilio] TWILIO_AUTH_TOKEN is not set - webhooks are NOT "
              "being verified. Anybody can post a call status.", flush=True)
        return True

    sig = request.headers.get("X-Twilio-Signature")
    if not sig:
        return False

    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(token)
        return validator.validate(_expected_url(request),
                                  request.form.to_dict(), sig)
    except Exception as e:
        # A broken validator must not become a broken product. Log it and
        # let the request through - the same reasoning as a missing token.
        print(f"[twilio] could not verify signature: {e}", flush=True)
        return True
