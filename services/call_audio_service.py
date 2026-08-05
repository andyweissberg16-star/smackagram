from services import voice_options, elevenlabs_service

# Pre-resolved audio URLs for calls about to be placed, keyed by
# (record_type, record_id) - e.g. ("order", 42) or ("smackagram", 42).
# Lives here (not in app.py) specifically so scheduler.py's Locked &
# Loaded call path can reach it too - previously it had no import path
# to app.py's own module-level dict at all, meaning every single
# Auto-Smack call unconditionally generated its audio live inside
# the /call-instructions webhook while the customer was already
# holding the phone, rather than using the same pre-resolve-before-
# placing-the-call approach the immediate "Send a Smack" flow used.
# Generating the message/sfx/tagline audio takes a few seconds
# (multiple ElevenLabs calls + S3 uploads) — doing that INSIDE the
# webhook response risks Twilio timing out and retrying (which
# replays the whole call from scratch), on top of the dead air itself.
pending_call_audio = {}


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


def stitch_full_call(message_url: str, base_url: str) -> str:
    """
    Message + slap + tagline as ONE file, for listening on the site.

    The phone call plays the message and the outro as two separate clips
    back to back, which Twilio handles fine. A browser cannot - the wall
    player is given one URL, so it played the message and stopped dead
    before the slap. Somebody listening on the site heard a different, worse
    thing than the person who was actually called.

    Returns the stitched URL, or the original message URL if anything fails.
    A wall post with the plain message is far better than one with no audio.
    """
    import hashlib
    import os
    import subprocess
    import tempfile

    import requests

    if not message_url:
        return message_url

    try:
        import boto3

        bucket = os.environ["AUDIO_S3_BUCKET"]
        region = os.environ.get("AWS_REGION", "us-east-1")

        # Hashed key: the same call stitched twice reuses the object rather
        # than leaving a duplicate behind on every republish.
        key = "tts/full-" + hashlib.sha256(
            message_url.encode()
        ).hexdigest()[:32] + ".mp3"
        url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"

        s3 = boto3.client("s3", region_name=region)
        try:
            s3.head_object(Bucket=bucket, Key=key)
            return url                      # already stitched
        except Exception:
            pass

        outro_url = get_outro_url(base_url)

        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for i, src in enumerate((message_url, outro_url)):
                p = os.path.join(tmp, f"{i}.mp3")
                r = requests.get(src, timeout=30)
                r.raise_for_status()
                with open(p, "wb") as fh:
                    fh.write(r.content)
                paths.append(p)

            # Re-encoded rather than concat-copied. The message comes from
            # ElevenLabs and the outro is a hand-made file; if their sample
            # rates differ, a stream copy produces a file that plays at the
            # wrong speed after the join - the same bug that hit the daily
            # show.
            listing = os.path.join(tmp, "list.txt")
            with open(listing, "w") as fh:
                for p in paths:
                    fh.write(f"file '{p}'\n")

            out = os.path.join(tmp, "full.mp3")
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listing,
                 "-ar", "44100", "-ac", "1", "-b:a", "128k", out],
                check=True, capture_output=True, timeout=90,
            )

            with open(out, "rb") as fh:
                s3.put_object(Bucket=bucket, Key=key, Body=fh.read(),
                              ContentType="audio/mpeg")

        return url

    except Exception as e:
        print(f"[audio] stitch failed, using message only: {e}", flush=True)
        return message_url
