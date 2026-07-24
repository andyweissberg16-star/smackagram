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


def place_prank_call(order_or_smackagram_id: int, recipient_phone: str, record: bool = True) -> str:
    """
    Fires the actual outbound call. Twilio hits our /call-instructions
    endpoint the moment the call connects, which returns the TwiML script.
    Returns the Twilio call SID for tracking.
    """
    base_url = os.environ["BASE_URL"]
    call = _get_client().calls.create(
        to=recipient_phone,
        from_=os.environ["TWILIO_PHONE_NUMBER"],
        url=f"{base_url}/call-instructions/{order_or_smackagram_id}",
        status_callback=f"{base_url}/call-status/{order_or_smackagram_id}",
        status_callback_event=["completed"],
        record=record,
        recording_status_callback=f"{base_url}/recording-ready/{order_or_smackagram_id}" if record else None,
        # machine_detection removed — Twilio trial accounts don't support AMD.
        # Add machine_detection="DetectMessageEnd" back once the account is
        # upgraded off trial, to distinguish voicemail from a live answer.
    )
    return call.sid


def build_twiml(audio_url: str) -> str:
    """
    The actual call script. Discloses recording (FL is two-party consent),
    plays the message, hangs up.
    """
    response = VoiceResponse()
    response.say(
        "Heads up — this call may be recorded. Here's your message.",
        voice="Polly.Matthew",
    )
    response.play(audio_url)
    response.pause(length=1)
    response.hangup()
    return str(response)
