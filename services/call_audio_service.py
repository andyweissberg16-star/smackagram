from services import voice_options, elevenlabs_service


def get_outro_url(base_url: str) -> str:
    """The signature slap sound + closing tagline, combined into one static mp3."""
    return f"{base_url}/static/outro.mp3"


def resolve_audio_url(record, base_url: str):
    """
    Builds the full audio sequence for a call: the message (pre-recorded
    clip or generated TTS), then the outro (slap + tagline combined) —
    played back-to-back as separate clips, not stitched into one file.

    Works for both Order and Smackagram records — both have custom_message,
    voice_key, and scenario_id in the same shape.
    """
    from models import Scenario  # local import avoids circularity at module load time

    voice_id = voice_options.get_voice_id(getattr(record, "voice_key", None) or voice_options.DEFAULT_VOICE_KEY)

    if record.custom_message:
        message_url = elevenlabs_service.generate_audio_url(record.custom_message, voice_id=voice_id)
    else:
        scenario = Scenario.query.get(record.scenario_id)
        message_url = scenario.audio_url

    outro_url = get_outro_url(base_url)
    return [message_url, outro_url]
