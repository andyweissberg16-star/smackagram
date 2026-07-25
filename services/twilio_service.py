import os
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
    Guarantees a phone number has the leading '+' Twilio requires (E.164).
    Without it, Twilio treats '18189262835' as a completely different,
    unverified number from '+18189262835' — even though a human reads them
    as the same thing.
    """
    number = number.strip()
    if not number.startswith("+"):
        number = "+" + number
    return number


def place_prank_call(order_or_smackagram_id: int, recipient_phone: str, record: bool = True) -> str:
    """
    Fires the actual outbound call. Twilio hits our /call-instructions
    endpoint the moment the call connects, which returns the TwiML script.
    Returns the Twilio call SID for tracking.

    Kept intentionally minimal — record/status_callback/machine_detection at
    call-creation time all hit "trial accounts have limited parameter access"
    errors. Recording instead happens via <Record> inside the TwiML script
    itself (see build_twiml), which trial accounts do support.
    """
    base_url = os.environ["BASE_URL"]
    to_number = _to_e164(recipient_phone)
    from_number = _to_e164(os.environ["TWILIO_PHONE_NUMBER"])

    print(f"[twilio] Placing call — to={to_number!r} from={from_number!r}")

    call = _get_client().calls.create(
        to=to_number,
        from_=from_number,
        url=f"{base_url}/call-instructions/{order_or_smackagram_id}",
    )
    return call.sid


def build_twiml(audio_urls, record: bool = True, record_callback_url: str = None) -> str:
    """
    The actual call script. Discloses recording (FL is two-party consent),
    plays each audio clip in sequence (message, slap sound effect, tagline),
    optionally records via <Record>, hangs up.

    audio_urls: a single URL (str) or a list of URLs played back-to-back.
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
        record_kwargs = {"max_length": 60, "play_beep": False}
        if record_callback_url:
            record_kwargs["recording_status_callback"] = record_callback_url
        response.record(**record_kwargs)

    response.pause(length=1)
    response.hangup()
    return str(response)
