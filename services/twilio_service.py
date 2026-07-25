import os
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    return _client


def _to_e164(number: str) -> str:
    number = number.strip()
    if not number.startswith("+"):
        number = "+" + number
    return number


def place_prank_call(order_or_smackagram_id: int, recipient_phone: str, record: bool = True) -> str:
    base_url = os.environ["BASE_URL"]
    to_number = _to_e164(recipient_phone)
    from_number = _to_e164(os.environ["TWILIO_PHONE_NUMBER"])

    print(f"[twilio] Placing call — to={to_number!r} from={from_number!r}")

    call = _get_client().calls.create(
        to=to_number,
        from_=from_number,
        url=f"{base_url}/call-instructions/{order_or_smackagram_id}",
        time_limit=59,
    )
    return call.sid


def build_twiml(audio_urls, record: bool = True, record_callback_url: str = None) -> str:
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
        record_kwargs = {"max_length": 20, "play_beep": False}
        if record_callback_url:
            record_kwargs["recording_status_callback"] = record_callback_url
        response.record(**record_kwargs)

    response.pause(length=1)
    response.hangup()
    return str(response)
