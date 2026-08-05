"""
Sending email over HTTPS.
=========================
Render blocks outbound SMTP on ports 25, 465 and 587 for free services.
The existing email_service is correct in every respect except that it
cannot connect, which is not a thing more code can fix.

An HTTP API goes over 443 like any other request, so it is not blocked -
and it works identically on a paid instance, which means moving to one
later changes nothing here.

TWO PROVIDERS, ON PURPOSE
-------------------------
David asked for both a panel notification and an email, so that nothing
is missed. The same reasoning applies one level down: if the email
provider is having a bad morning, a support ticket should not vanish
because of it.

Set either key and it works. Set both and the second is tried when the
first fails.

    RESEND_API_KEY      resend.com
    POSTMARK_API_KEY    postmarkapp.com

NEITHER SET
-----------
Nothing is sent and it says so in the log. The ticket is still saved and
still visible in the panel - the email is the convenience, the record is
the point.
"""

import os

FROM = os.environ.get("SUPPORT_FROM", "Smackagram <noreply@smackagram.com>")


def _resend(to, subject, text, reply_to=None):
    key = os.environ.get("RESEND_API_KEY")
    if not key:
        return False, "no RESEND_API_KEY"
    import requests
    payload = {"from": FROM, "to": [to] if isinstance(to, str) else to,
               "subject": subject, "text": text}
    if reply_to:
        # So hitting Reply in a mail client answers the CUSTOMER, not a
        # noreply address. Small thing that decides whether anybody
        # actually replies.
        payload["reply_to"] = reply_to
    r = requests.post("https://api.resend.com/emails",
                      headers={"Authorization": f"Bearer {key}"},
                      json=payload, timeout=10)
    if r.status_code in (200, 201):
        return True, "sent via resend"
    return False, f"resend {r.status_code}: {r.text[:120]}"


def _postmark(to, subject, text, reply_to=None):
    key = os.environ.get("POSTMARK_API_KEY")
    if not key:
        return False, "no POSTMARK_API_KEY"
    import requests
    payload = {"From": FROM, "To": to, "Subject": subject, "TextBody": text,
               "MessageStream": "outbound"}
    if reply_to:
        payload["ReplyTo"] = reply_to
    r = requests.post("https://api.postmarkapp.com/email",
                      headers={"X-Postmark-Server-Token": key,
                               "Accept": "application/json"},
                      json=payload, timeout=10)
    if r.status_code == 200:
        return True, "sent via postmark"
    return False, f"postmark {r.status_code}: {r.text[:120]}"


def send(to, subject, text, reply_to=None):
    """
    Send one email. Returns (ok, detail).

    Tries every configured provider before giving up, so one being down
    does not lose a message. Never raises - a failed notification must
    not take down the thing that triggered it.
    """
    attempts = []
    for fn in (_resend, _postmark):
        try:
            ok, detail = fn(to, subject, text, reply_to)
            attempts.append(detail)
            if ok:
                print(f"[mail] to {to}: {detail}", flush=True)
                return True, detail
        except Exception as e:
            attempts.append(f"{fn.__name__}: {e}")

    why = " | ".join(attempts) or "no provider configured"
    print(f"[mail] COULD NOT SEND to {to}: {why}", flush=True)
    return False, why


def configured():
    """Which providers are usable - for the admin panel to report."""
    return [n for n, k in (("resend", "RESEND_API_KEY"),
                           ("postmark", "POSTMARK_API_KEY"))
            if os.environ.get(k)]
