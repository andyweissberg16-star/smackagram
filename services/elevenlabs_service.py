import os
import uuid
import hashlib
import subprocess
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


def generate_sound_effect(prompt: str, duration_seconds: float = 1.5, target_lufs: int = None) -> str:
    """
    Generates a short sound effect from a text description using ElevenLabs'
    Sound Effects endpoint — a different feature from voice TTS, built for
    exactly this: short stingers/effects like a slap, whoosh, or ding.
    Requires the API key to have "Sound Effects" access enabled.

    Runs through the same loudness normalization as speech, but targeting
    a louder level by default (-10 LUFS vs speech's -16) — effects like a
    bell or crowd cheer are supposed to hit hard and punchy, not sit at a
    conversational volume like a voice line. Pass target_lufs explicitly
    for an effect that needs to stand out even louder than the rest
    (e.g. the ring bell).
    """
    if target_lufs is None:
        target_lufs = SFX_TARGET_LUFS

    cache_key = f"{prompt}::{target_lufs}"
    if cache_key in _sfx_cache:
        return _sfx_cache[cache_key]

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

    normalized_audio = normalize_loudness(resp.content, target_lufs=target_lufs)

    filename = f"sfx/{uuid.uuid4()}.mp3"
    s3 = boto3.client("s3", region_name=s3_region)
    s3.put_object(
        Bucket=s3_bucket,
        Key=filename,
        Body=normalized_audio,
        ContentType="audio/mpeg",
    )

    url = f"https://{s3_bucket}.s3.{s3_region}.amazonaws.com/{filename}"
    _sfx_cache[cache_key] = url
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



# Loudness target — matched to a standard, gentle broadcast level (-16 LUFS
# is a common streaming/podcast target). The previous -8.1 target was far
# too hot and, combined with dynamic-mode loudnorm, caused audible pumping/
# breathing artifacts. linear=true below uses a single flat gain instead of
# adaptive frame-by-frame correction, which eliminates that pumping entirely.
TARGET_LUFS = -16
# Sound effects target louder than speech — a bell or crowd roar is
# supposed to hit hard, not sit at conversational volume.
SFX_TARGET_LUFS = -10


def normalize_loudness(audio_bytes: bytes, target_lufs: int = TARGET_LUFS) -> bytes:
    """
    Runs generated audio through ffmpeg loudness normalization to match
    target_lufs (defaults to TARGET_LUFS, speech's level). If ffmpeg isn't
    available on the server for any reason, fails safe by returning the
    original, unnormalized audio rather than breaking the call — you'd
    just be back to the volume mismatch, not a broken feature.

    Timeout scales with audio size — the original 15s was set for a
    15-20 second prank-call clip; a multi-minute Smackcast script is a
    much larger file for ffmpeg to process, and legitimately needs more
    time, especially on Render's limited free-tier CPU.
    """
    try:
        timeout_seconds = max(15, len(audio_bytes) // 20000)  # rough scaling, floor of 15s
        process = subprocess.run(
            [
                "ffmpeg", "-i", "pipe:0",
                "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=7:linear=true",
                "-f", "mp3", "pipe:1",
            ],
            input=audio_bytes,
            capture_output=True,
            timeout=timeout_seconds,
        )
        if process.returncode != 0 or not process.stdout:
            print(f"[elevenlabs] loudness normalization failed, using original audio: {process.stderr[:300]}")
            return audio_bytes
        return process.stdout
    except Exception as e:
        print(f"[elevenlabs] loudness normalization error, using original audio: {e}")
        return audio_bytes


def generate_speech_bytes(text: str, voice_id: str = None) -> bytes:
    """
    Same ElevenLabs TTS call as generate_audio_url, but returns raw,
    un-normalized audio bytes instead of uploading to S3 — used when
    multiple pieces of speech need to be stitched together with sound
    effects in between before one final upload (Smackcast's segmented
    recaps), rather than each piece needing its own separate URL.
    """
    if voice_id is None:
        voice_id = os.environ["ELEVENLABS_VOICE_ID"]

    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={
            "xi-api-key": os.environ["ELEVENLABS_API_KEY"],
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": "eleven_turbo_v2",
            "voice_settings": {
                "stability": 0.4,
                "similarity_boost": 0.8,
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.content


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

    normalized_audio = normalize_loudness(resp.content)

    filename = f"tts/{uuid.uuid4()}.mp3"
    s3 = boto3.client("s3", region_name=s3_region)
    s3.put_object(
        Bucket=s3_bucket,
        Key=filename,
        Body=normalized_audio,
        ContentType="audio/mpeg",
    )

    url = f"https://{s3_bucket}.s3.{s3_region}.amazonaws.com/{filename}"
    _audio_cache[cache_key] = url
    return url
