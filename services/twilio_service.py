import os
import re
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

# Lazy client — built on first real use, not at import time. This lets the
# app boot and serve pages even before Twilio keys are filled in; you'll
# only hit an error if you actually try to place a call without real keys.
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    return _client


def _to_e164(number: str) -> str:
    """
    Converts a phone number to E.164 format, which Twilio requires.
    Strips any formatting (parentheses, dashes, spaces, dots) rather
    than just prepending '+' — a naive prepend on something like
    "(555) 555-5555" would produce "+(555) 555-5555", which Twilio
    rejects outright as an invalid number.
    """
    digits = re.sub(r"[^\d+]", "", number.strip())
    if not digits.startswith("+"):
        # Assume US/Canada if it's a bare 10-digit number; otherwise
        # just add the + and let Twilio validate the rest.
        if len(digits) == 10:
            digits = "1" + digits
        digits = "+" + digits
    return digits


def send_sms(to_phone: str, body: str) -> str:
    """
    Sends a plain SMS — used for 2FA verification codes. Returns the
    Twilio message SID. Same account/from-number as the prank calls,
    just the messages API instead of calls.
    """
    client = _get_client()
    from_number = _to_e164(os.environ["TWILIO_PHONE_NUMBER"])
    message = client.messages.create(
        to=_to_e164(to_phone),
        from_=from_number,
        body=body,
    )
    return message.sid


def place_smackcast_call(recap_id: int, recipient_phone: str) -> str:
    """
    Calls a league owner and plays their weekly Smackcast recap. Separate
    from place_prank_call() since that one caps at 59 seconds (fine for
    a short prank line, nowhere near enough for a 3-5 minute recap) and
    is tied to the order/smackagram pre-resolved audio dict rather than
    a recap ID.
    """
    base_url = os.environ["BASE_URL"]
    to_number = _to_e164(recipient_phone)
    from_number = _to_e164(os.environ["TWILIO_PHONE_NUMBER"])

    call = _get_client().calls.create(
        to=to_number,
        from_=from_number,
        url=f"{base_url}/smackcast-call-instructions/{recap_id}",
        time_limit=360,  # 6 minutes — covers the longest (5 min) recap plus buffer
        machine_detection="DetectMessageEnd",
    )
    return call.sid


def place_prank_call(record_type: str, record_id: int, recipient_phone: str, record: bool = True) -> str:
    """
    Fires the actual outbound call. Twilio hits our /call-instructions
    endpoint the moment it's actually safe to start talking — see
    machine_detection below — which returns the TwiML script.
    Returns the Twilio call SID for tracking.

    record_type: "order" or "smackagram" - Order and Smackagram are
    separate tables with independent autoincrementing primary keys, so
    the same integer id can (and eventually will) exist in both. The
    webhook URLs are namespaced by record_type specifically so the
    handlers never have to guess which table an id belongs to - a
    guess that previously always favored Order, silently serving the
    wrong record's audio to whichever Smackagram happened to collide.

    machine_detection='DetectMessageEnd': makes this SYNCHRONOUS — Twilio
    delays requesting our /call-instructions URL until it has determined
    whether a human or an answering machine picked up, and specifically
    (with DetectMessageEnd) waits until the machine's greeting has
    actually finished — right around when the beep happens — before
    fetching our instructions. This is what makes the message start after
    the beep instead of during the greeting, where a voicemail box
    wouldn't even be recording it yet.

    This previously wasn't set because the Twilio account was on the
    trial tier, which restricts this parameter — now that it's a real
    paid account, this works correctly.
    """
    base_url = os.environ["BASE_URL"]
    to_number = _to_e164(recipient_phone)
    from_number = _to_e164(os.environ["TWILIO_PHONE_NUMBER"])

    # Last line of defence before dialling.
    #
    # Checked HERE rather than at each of the three call sites, because a
    # fourth will be added eventually and whoever adds it will not remember.
    # The one place every call funnels through is the only place this cannot
    # be forgotten.
    try:
        from app import is_opted_out
        if is_opted_out(to_number):
            print(f"[twilio] BLOCKED - {to_number!r} has opted out", flush=True)
            raise ValueError("This number has opted out of Smackagram calls.")
    except ValueError:
        raise
    except Exception as _e:
        print(f"[twilio] opt-out check unavailable: {_e}", flush=True)

    print(f"[twilio] Placing call — to={to_number!r} from={from_number!r} record_type={record_type!r} record_id={record_id!r}")

    call = _get_client().calls.create(
        to=to_number,
        from_=from_number,
        url=f"{base_url}/call-instructions/{record_type}/{record_id}",
        time_limit=119,  # hard cap on total call duration (1:59), enforced by Twilio itself
        machine_detection="DetectMessageEnd",
        # Twilio's default (30s) is a CEILING on analysis time, not a wait -
        # AMD resolves as soon as it has signal, so a live "Hello?" is
        # typically decided in ~2-3s regardless of this value. The ceiling
        # only actually engages on genuinely ambiguous audio, which in
        # practice means unusually long voicemail greetings. Setting this
        # too low (previously 15s) meant a long greeting could hit the
        # ceiling before AMD was confident, returning AnsweredBy="unknown"
        # and requesting our TwiML immediately - mid-greeting, not after
        # it, so the smack played over the greeting instead of landing
        # after the beep. Left at Twilio's own default for that reason;
        # live-answer lag is a caching concern (see call_audio_service),
        # not this setting.
        machine_detection_timeout=30,
        status_callback=f"{base_url}/call-status/{record_type}/{record_id}",
        status_callback_event=["completed"],
        status_callback_method="POST",
    )
    return call.sid


def build_twiml(audio_urls, record: bool = True, record_callback_url: str = None, record_action_url: str = None) -> str:
    """
    The actual call script. Plays each audio clip in sequence (message,
    slap sound effect, tagline), optionally records via <Record>, hangs up.

    audio_urls: a single URL (str) or a list of URLs played back-to-back.

    The recording disclosure is welded to `record` — it plays if and
    only if <Record> is present. DO NOT DECOUPLE THESE. Florida is
    two-party consent, and calls reach recipients in other two-party
    states too — the only way to record without disclosing is to make
    these two separate decisions, so they're deliberately kept as one.
    Live answer: disclosure + smack. Voicemail (or any answer that
    isn't confidently human): no disclosure, smack only, no recording.

    IMPORTANT: <Record> defaults its `action` to re-fetching the SAME URL
    that started the call if no action is given — meaning without an
    explicit record_action_url, Twilio re-requests /call-instructions after
    recording finishes, replaying the entire script from scratch. Always
    pass record_action_url pointing somewhere else (e.g. a route that just
    hangs up) to prevent this.
    """
    if isinstance(audio_urls, str):
        audio_urls = [audio_urls]

    response = VoiceResponse()
    if record:
        response.say(
            "Heads up — this call may be recorded. Here's your message.",
            voice="Polly.Matthew",
        )
    for url in audio_urls:
        response.play(url)

    if record:
        # max_length is intentionally generous here — it does NOT need to be
        # precisely budgeted against message length. The call's time_limit=119
        # (set in place_prank_call) is enforced by Twilio at the connection
        # level and will hang up at exactly 119s no matter which verb is
        # running. So: message plays (whatever length), then this holds the
        # line in silence (timeout=0 disables early-stop-on-silence) until
        # Twilio's hard limit ends the call — never earlier, never later.
        record_kwargs = {"max_length": 115, "play_beep": False, "timeout": 0}
        if record_callback_url:
            record_kwargs["recording_status_callback"] = record_callback_url
        if record_action_url:
            record_kwargs["action"] = record_action_url
        response.record(**record_kwargs)

    response.pause(length=1)
    response.hangup()
    return str(response)
