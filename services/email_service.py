"""
Sending email.
==============
Used for support replies, and available to anything else that needs it -
order confirmations and password resets are both waiting on this existing.

CONFIGURATION
-------------
Four environment variables. Without them this is silently off, and every
caller gets a clear "not configured" rather than an exception:

    SMTP_HOST      smtpout.secureserver.net    (GoDaddy)
    SMTP_PORT      465
    SMTP_USER      support@smackagram.com
    SMTP_PASSWORD  the mailbox password

GoDaddy uses port 465 with SSL. Port 587 with STARTTLS also works on some
plans; both are handled.

WHY NOT AN API SERVICE
----------------------
SendGrid or Postmark would be more reliable and give delivery tracking.
But the mailboxes are already being set up at GoDaddy, sending from the
same place people reply to keeps the thread intact, and this needs no new
account or spend. Worth revisiting if volume grows - deliverability from a
shared host is worse than from a dedicated sender.
"""

import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid


def configured():
    """Is there enough to send with?"""
    return all(os.environ.get(k) for k in
               ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"))


def status():
    return {
        "configured": configured(),
        "host": os.environ.get("SMTP_HOST") or None,
        "port": os.environ.get("SMTP_PORT") or "465",
        "from": os.environ.get("SMTP_USER") or None,
    }


def _valid(address):
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", (address or "").strip()))


# Common hosts, so a wrong one is easier to spot than to debug.
KNOWN_HOSTS = {
    "smtpout.secureserver.net": "GoDaddy's own mail platform (older plans)",
    "smtp.office365.com": "Microsoft 365 - what most GoDaddy email is now",
    "smtp.gmail.com": "Google Workspace",
}


def send_async(to, subject, body, **kw):
    """
    Send without making anybody wait.

    A mail server that is slow, or simply the wrong address, holds the
    connection open - and with one worker that means the whole site stops
    answering. Nothing about a support reply needs the sender to wait for
    the SMTP handshake.

    The result is logged rather than returned, which is the trade: the
    caller finds out from the log rather than immediately.
    """
    import threading

    def _go():
        ok, detail = send(to, subject, body, **kw)
        if not ok:
            print(f"[email] background send to {to} failed: {detail}",
                  flush=True)

    threading.Thread(target=_go, daemon=True).start()
    return True, "queued"


def send(to, subject, body, reply_to=None, from_name="Smackagram Support"):
    """
    Send one plain-text email.

    Returns (True, message_id) or (False, reason). Never raises - a failed
    email should not take down whatever was trying to send it, and the
    caller always needs to know rather than guess.
    """
    if not configured():
        return False, ("email is not configured - set SMTP_HOST, SMTP_USER "
                       "and SMTP_PASSWORD")
    if not _valid(to):
        return False, f"'{to}' is not a valid address"
    if not (subject or "").strip():
        return False, "no subject"
    if not (body or "").strip():
        return False, "no message body"

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT") or 465)
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]

    msg = EmailMessage()
    msg["Subject"] = subject[:200]
    msg["From"] = formataddr((from_name, user))
    msg["To"] = to.strip()
    # Replies go to the mailbox somebody actually reads. Usually the same
    # address, but this lets a reply be routed elsewhere without changing
    # who the mail appears to come from.
    msg["Reply-To"] = (reply_to or user)
    mid = make_msgid(domain=user.split("@")[-1])
    msg["Message-ID"] = mid
    msg.set_content(body)

    # FORCE IPv4.
    #
    # smtp.office365.com resolves to BOTH IPv6 and IPv4. Python tries IPv6
    # first, and a host with no IPv6 route gets "Network is unreachable"
    # immediately - which looks like the mail server is down when it is
    # simply on a road this machine cannot drive.
    #
    # Resolving to an IPv4 address ourselves and connecting to that avoids
    # it. The hostname is still used for TLS, so certificate validation is
    # unaffected.
    try:
        import socket
        info = socket.getaddrinfo(host, port, socket.AF_INET,
                                  socket.SOCK_STREAM)
        ipv4 = info[0][4][0] if info else None
    except Exception as e:
        return False, f"could not resolve {host}: {e}"

    try:
        # EIGHT SECONDS, NOT TWENTY.
        #
        # This server runs a SINGLE gunicorn worker, so while a mail
        # connection hangs, NOTHING ELSE ON THE SITE IS SERVED. A wrong
        # SMTP host does not refuse the connection - it hangs - and twenty
        # seconds of that took the whole site down while a test ran.
        #
        # Eight is plenty for a mail server that is actually listening,
        # and short enough that a wrong one is an annoyance rather than an
        # outage.
        ctx = ssl.create_default_context()
        if port == 465:
            # SMTP_SSL wraps the socket immediately and gives no way to
            # connect by IP while validating the certificate against the
            # name. So 465 uses the hostname - if IPv6 is the problem,
            # 587 is the port to use anyway.
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=8) as s:
                s.login(user, password)
                s.send_message(msg)
        else:
            # Connect to the IPv4 address, then tell the TLS handshake the
            # real hostname - otherwise the certificate is checked against
            # a bare IP and fails.
            with smtplib.SMTP(ipv4 or host, port, timeout=8) as s:
                s._host = host
                s.ehlo(host)
                s.starttls(context=ctx)
                s.ehlo(host)
                s.login(user, password)
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        return False, ("SMTP rejected the login - check SMTP_USER and "
                       "SMTP_PASSWORD")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

    print(f"[email] sent to {to}: {subject[:60]}", flush=True)
    return True, mid
