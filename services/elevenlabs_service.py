import os
import uuid
import hashlib
import requests
import boto3

# In-memory cache: identical text won't regenerate audio (and won't burn
# ElevenLabs credits) twice. Resets on redeploy — fine for now, move to
# a real cache (Redis) if this needs to survive restarts later.
_audio_cache = {}

# Separate cache for voice sample preview URLs — these are static per voice
# and never change, so once fetched there's no reason to ever ask again.
_voice_preview_cache = {}

# Cache for generated sound effects — same prompt always produces effectively
# the same sound, generate once per prompt and reuse (saves credits, and the
# slap sound should stay consistent as a piece of brand identity).
_sfx_cache = {}


def generate_sound_effect(prompt: str, duration_seconds: float = 1.5) -> str:
    """
    Generates a short sound effect from a text description using ElevenLabs'
    Sound Effects endpoint — a different feature from voice TTS, built for
    exactly this: short stingers/effects like a slap, whoosh, or ding.
    Requires the API key to have "Sound Effects" access enabled.
    """
    if prompt in _sfx_cache:
        return _sfx_cache[prompt]

    s3_bucket = os.environ["AUDIO_S3_BUCKET"]
    s3_region = os.environ.get("AWS_REGION", "us-east-1")

    resp = requests.post(
        "https://api.elevenlabs.io/v1/sound-generation",
        headers={
            "xi-api-key": os.environ["ELEVENLABS_API_KEY"],
            "Content-Type": "application/json",
        },
        json={
            "text": prompt,
            "duration_seconds": duration_seconds,
            "prompt_influence": 1.0,
        },
        timeout=30,
    )
    resp.raise_for_status()

    filename = f"sfx/{uuid.uuid4()}.mp3"
    s3 = boto3.client("s3", region_name=s3_region)
    s3.put_object(
        Bucket=s3_bucket,
        Key=filename,
        Body=resp.content,
        ContentType="audio/mpeg",
    )

    url = f"https://{s3_bucket}.s3.{s3_region}.amazonaws.com/{filename}"
    _sfx_cache[prompt] = url
    return url


def get_voice_preview_url(voice_id: str) -> str:
    """
    Returns ElevenLabs' free built-in sample clip for a voice — the same
    preview audio you hear browsing their voice library. This hits their
    voice-info endpoint, NOT the text-to-speech endpoint, so it costs no
    credits and generates no new audio — just retrieves an existing file.
    """
    if voice_id in _voice_preview_cache:
        return _voice_preview_cache[voice_id]

    resp = requests.get(
        f"https://api.elevenlabs.io/v1/voices/{voice_id}",
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
        timeout=15,
    )
    resp.raise_for_status()
    preview_url = resp.json()["preview_url"]

    _voice_preview_cache[voice_id] = preview_url
    return preview_url


def generate_audio_url(message: str, voice_id: str = None) -> str:
    """
    Sends a custom message to ElevenLabs, gets back an mp3, uploads it to S3,
    and returns a public URL Twilio can fetch and play on the call.

    Uses the 'turbo' model — about half the credit cost of the standard
    multilingual model, and plenty good enough for a 15-20 second prank line.

    voice_id defaults to ELEVENLABS_VOICE_ID if not passed — see
    services/voice_options.py for the list of selectable voice characters.
    """
    if voice_id is None:
        voice_id = os.environ["ELEVENLABS_VOICE_ID"]

    # cache key includes the voice, since the same text sounds different
    # (and needs separate storage) per voice
    cache_key = hashlib.sha256(f"{voice_id}:{message}".encode()).hexdigest()
    if cache_key in _audio_cache:
        return _audio_cache[cache_key]

    s3_bucket = os.environ["AUDIO_S3_BUCKET"]
    s3_region = os.environ.get("AWS_REGION", "us-east-1")

    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={
            "xi-api-key": os.environ["ELEVENLABS_API_KEY"],
            "Content-Type": "application/json",
        },
        json={
            "text": message,
            "model_id": "eleven_turbo_v2",
            "voice_settings": {
                "stability": 0.4,
                "similarity_boost": 0.8,
            },
        },
        timeout=30,
    )
    resp.raise_for_status()

    filename = f"tts/{uuid.uuid4()}.mp3"
    s3 = boto3.client("s3", region_name=s3_region)
    s3.put_object(
        Bucket=s3_bucket,
        Key=filename,
        Body=resp.content,
        ContentType="audio/mpeg",
    )

    url = f"https://{s3_bucket}.s3.{s3_region}.amazonaws.com/{filename}"
    _audio_cache[cache_key] = url
    return url
