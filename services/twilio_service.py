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


def place_prank_call(order_or_smackagram_id: int, recipient_phone: str, record: bool = True) -> str:
    """
    Fires the actual outbound call. Twilio hits our /call-instructions
    endpoint the moment it's actually safe to start talking — see
    machine_detection below — which returns the TwiML script.
    Returns the Twilio call SID for tracking.

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

    print(f"[twilio] Placing call — to={to_number!r} from={from_number!r}")

    call = _get_client().calls.create(
        to=to_number,
        from_=from_number,
        url=f"{base_url}/call-instructions/{order_or_smackagram_id}",
        time_limit=59,  # hard cap on total call duration, enforced by Twilio itself
        machine_detection="DetectMessageEnd",
        # Twilio's default timeout here is 30 seconds — that's the source
        # of the 5-30s lag before the message starts on live answers,
        # since Twilio has to finish analyzing audio (to tell human from
        # voicemail) before it'll even request our TwiML. Capping this
        # much lower keeps voicemail-greeting timing accurate for the
        # vast majority of real greetings (which are well under 15s) while
        # putting a hard ceiling on how long a live human ever waits.
        machine_detection_timeout=15,
        status_callback=f"{base_url}/call-status/{order_or_smackagram_id}",
        status_callback_event=["completed"],
        status_callback_method="POST",
    )
    return call.sid


def build_twiml(audio_urls, record: bool = True, record_callback_url: str = None, record_action_url: str = None) -> str:
    """
    The actual call script. Discloses recording (FL is two-party consent),
    plays each audio clip in sequence (message, slap sound effect, tagline),
    optionally records via <Record>, hangs up.

    audio_urls: a single URL (str) or a list of URLs played back-to-back.

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
    response.say(
        "Heads up — this call may be recorded. Here's your message.",
        voice="Polly.Matthew",
    )
    for url in audio_urls:
        response.play(url)

    if record:
        # max_length is intentionally generous here — it does NOT need to be
        # precisely budgeted against message length. The call's time_limit=59
        # (set in place_prank_call) is enforced by Twilio at the connection
        # level and will hang up at exactly 59s no matter which verb is
        # running. So: message plays (whatever length), then this holds the
        # line in silence (timeout=0 disables early-stop-on-silence) until
        # Twilio's hard limit ends the call — never earlier, never later.
        record_kwargs = {"max_length": 55, "play_beep": False, "timeout": 0}
        if record_callback_url:
            record_kwargs["recording_status_callback"] = record_callback_url
        if record_action_url:
            record_kwargs["action"] = record_action_url
        response.record(**record_kwargs)

    response.pause(length=1)
    response.hangup()
    return str(response)
