"""
Slowing down guessing.
======================
There was nothing on the login endpoint. A script could try a thousand
passwords a minute against every email it knows, and nothing anywhere
would notice or stop it.

HOW IT WORKS
------------
Failures are counted per EMAIL and per ADDRESS, separately.

  Per email    stops somebody grinding one account, wherever they are
               coming from.
  Per address  stops somebody trying one common password against a
               thousand emails - which is the attack that actually works
               against real user bases, and which per-email counting
               misses entirely.

After a threshold, further attempts are refused for a period that grows
each time. Five failures is a person who forgot; fifty is a script.

HELD IN MEMORY, ON PURPOSE
--------------------------
A database write on every login attempt is exactly the load an attacker
wants to create. Memory is free.

The trade is that a restart clears the counters - but an attacker cannot
trigger a restart, and deploys are rare enough that the window is
theoretical.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
Tell the caller which limit they hit, or whether the email exists. Every
failure returns the same message. Anything more specific is a tool for
enumerating accounts.
"""

import threading
import time

# Attempts allowed before the door closes.
EMAIL_THRESHOLD = 6
IP_THRESHOLD = 20          # higher: an office or a phone network shares one

# How long a lockout lasts, growing each time it trips.
LOCKOUT_STEPS = [60, 300, 900, 3600]      # 1m, 5m, 15m, 1h

# Failures older than this stop counting - somebody who mistyped their
# password twice last Tuesday is not suspicious today.
WINDOW_SECONDS = 900

_lock = threading.Lock()
_fails = {}        # key -> [timestamps]
_locked = {}       # key -> (until_ts, how_many_times_locked)


def _prune(times, now):
    return [t for t in times if now - t < WINDOW_SECONDS]


def check(email, ip):
    """
    May this attempt proceed?

    Returns (True, 0) to allow, or (False, seconds_remaining) to refuse.
    """
    now = time.time()
    with _lock:
        for key in (f"e:{(email or '').lower()}", f"i:{ip or ''}"):
            until, _ = _locked.get(key, (0, 0))
            if now < until:
                return False, int(until - now)
    return True, 0


def record_failure(email, ip):
    """
    Note a wrong password, and lock the door if there have been enough.

    Returns True if this failure caused a lockout, so the caller can log
    or alert on it.
    """
    now = time.time()
    tripped = False
    with _lock:
        for key, threshold in ((f"e:{(email or '').lower()}", EMAIL_THRESHOLD),
                               (f"i:{ip or ''}", IP_THRESHOLD)):
            times = _prune(_fails.get(key, []), now)
            times.append(now)
            _fails[key] = times
            if len(times) >= threshold:
                until, level = _locked.get(key, (0, 0))
                step = LOCKOUT_STEPS[min(level, len(LOCKOUT_STEPS) - 1)]
                _locked[key] = (now + step, level + 1)
                _fails[key] = []          # start the count again
                tripped = True
    return tripped


def record_success(email, ip):
    """A correct password clears the slate for that email."""
    with _lock:
        _fails.pop(f"e:{(email or '').lower()}", None)
        _locked.pop(f"e:{(email or '').lower()}", None)
        # The ADDRESS counter is deliberately not cleared. Somebody
        # guessing a thousand emails will eventually get one right, and
        # that success should not reset the evidence of the other 999.


def status():
    """What is currently locked - for the admin panel."""
    now = time.time()
    with _lock:
        active = [{
            "target": ("email" if k.startswith("e:") else "address"),
            "value": k[2:],
            "locked_for": int(v[0] - now),
            "times_locked": v[1],
        } for k, v in _locked.items() if now < v[0]]
        watching = sum(1 for times in _fails.values()
                       if _prune(times, now))
    return {"locked_out": active,
            "keys_with_recent_failures": watching,
            "email_threshold": EMAIL_THRESHOLD,
            "address_threshold": IP_THRESHOLD}
