import os
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    return _client


def place_prank_call(order_or_smackagram_id: int, recipient_phone: str, record: bool = True) -> str:
    base_url = os.environ["BASE_URL"]
    to_number = recipient_phone.strip()
    from_number = os.environ["TWILIO_PHONE_NUMBER"].strip()

    print(f"[twilio] Placing call — to={to_number!r} from={from_number!r}")

    call = _get_client().calls.create(
        to=to_number,
        from_=from_number,
        url=f"{base_url}/call-instructions/{order_or_smackagram_id}",
    )
    return call.sid


def build_twiml(audio_url: str, record: bool = True, record_callback_url: str = None) -> str:
    response = VoiceResponse()
    response.say(
        "Heads up — this call may be recorded. Here's your message.",
        voice="Polly.Matthew",
    )
    response.play(audio_url)

    if record:
        record_kwargs = {"max_length": 60, "play_beep": False}
        if record_callback_url:
            record_kwargs["recording_status_callback"] = record_callback_url
        response.record(**record_kwargs)

    response.pause(length=1)
    response.hangup()
    return str(response)
