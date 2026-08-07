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


# THE DEAD-AIR BUG, FIXED AT ITS ROOT (Aug 7, caught live at 3:22am):
# this dict is PER-WORKER MEMORY. The cron pass cached the audio in
# one gunicorn worker; Twilio's webhook landed on another of the four;
# miss - "generating audio live inside the webhook, expect dead air" -
# and the person who answered got silence while ElevenLabs ran
# mid-call. On a 4-worker box that is ~75% of answered calls.
#
# The fix: the DB is the shared memory. stash() writes a Setting row
# (key/value - "rows are cheaper than migrations", per that model's
# own docstring) and commits IMMEDIATELY so any worker can see it;
# take() checks this worker's dict first (free when the same worker
# answers), then the DB, deleting on read. Rows older than a day are
# swept on stash - an unanswered call's audio should not live forever.

def _kv_key(record_type, record_id):
    return f"callaudio:{record_type or 'legacy'}:{record_id}"


def stash_call_audio(record_type, record_id, audio_urls):
    """Make the audio visible to EVERY worker before the call places."""
    key = (record_type, record_id) if record_type else record_id
    pending_call_audio[key] = audio_urls          # same-worker fast path
    try:
        import json
        from datetime import datetime, timedelta
        from models import db, Setting
        kv = _kv_key(record_type, record_id)
        row = Setting.query.filter_by(key=kv).first()
        if row is None:
            row = Setting(key=kv)
            db.session.add(row)
        row.value = json.dumps({
            "urls": list(audio_urls),
            "at": datetime.utcnow().isoformat(),
        })
        # opportunistic sweep: yesterday's unanswered calls
        cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        for old in Setting.query.filter(
                Setting.key.like("callaudio:%")).all():
            try:
                if json.loads(old.value).get("at", "") < cutoff:
                    db.session.delete(old)
            except Exception:
                db.session.delete(old)
        db.session.commit()
    except Exception as e:
        try:
            from models import db as _db
            _db.session.rollback()
        except Exception:
            pass
        print(f"[audio-stash] DB stash failed for "
              f"{record_type}:{record_id}: {e} - same-worker cache "
              f"only, cross-worker answer will regenerate", flush=True)


def take_call_audio(record_type, record_id):
    """This worker's dict first, then the shared DB. None on miss."""
    key = (record_type, record_id) if record_type else record_id
    hit = pending_call_audio.pop(key, None)
    if hit is not None:
        return hit
    try:
        import json
        from models import db, Setting
        row = Setting.query.filter_by(
            key=_kv_key(record_type, record_id)).first()
        if row is None:
            return None
        urls = json.loads(row.value).get("urls")
        db.session.delete(row)
        db.session.commit()
        print(f"[audio-stash] cross-worker hit for "
              f"{record_type or 'legacy'}:{record_id} - no dead air",
              flush=True)
        return urls
    except Exception as e:
        try:
            from models import db as _db
            _db.session.rollback()
        except Exception:
            pass
        print(f"[audio-stash] DB take failed: {e}", flush=True)
        return None


def get_invite_url(base_url: str, answered_by: str = "") -> str:
    """
    The invitation that plays AFTER the outro, or "" for silence.

    A SEPARATE FILE, DELIBERATELY.

    The outro is a brand element - the slap and the tagline - and should
    not change. This is marketing, which gets rewritten and tested. Two
    <Play> verbs cost nothing and keep the two things independent.

    It also means the invitation can be REMOVED IN ONE STEP. If a carrier
    or an app reviewer ever objects to soliciting the recipient, deleting
    one file turns it off without touching the outro or the code.

    LIVE AND VOICEMAIL ARE DIFFERENT.

    Somebody who answered can act on it. A machine cannot, and by the
    time it plays the message back the joke has already outstayed its
    welcome - so the default is SILENCE on voicemail unless somebody
    deliberately adds the file.

    Nothing plays until the audio exists. A missing file is not an error,
    it is simply no invitation.
    """
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # ONE FILE FOR BOTH, with a voicemail version only if one is dropped
    # in later.
    #
    # The case for playing it on voicemail is stronger than the case
    # against: somebody interested can REPLAY a message, which they
    # cannot do with a live call - so the voicemail listener may be the
    # better prospect, not the worse one.
    #
    # A single mention of the address either way. Repeating it sounds
    # like an infomercial to somebody who is actually listening.
    machine = str(answered_by or "").lower().startswith("machine")
    names = (["invite-voicemail.mp3", "invite-live.mp3"] if machine
             else ["invite-live.mp3"])
    for name in names:
        if os.path.exists(os.path.join(here, "static", name)):
            return f"{base_url}/static/{name}"

    # No file, no invitation. A missing recording is not an error - it
    # is simply the feature being off, which is also the one-step way to
    # turn it off if a carrier ever objects.
    return ""


def get_outro_url(base_url: str) -> str:
    """The signature slap sound + closing tagline, combined into one static mp3."""
    return f"{base_url}/static/outro.mp3"


def resolve_audio_url(record, base_url: str, answered_by: str = ""):
    """
    The pieces of a call, in order: message, outro, and the invitation
    when there is one.

    answered_by comes from Twilio's machine detection and defaults to
    empty - so existing callers keep working and simply get the live
    invitation, which is the one that exists.
    """
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

    # THE INVITATION LAST, and only when the audio exists.
    #
    # Kept out of the stitched file on purpose: this is the piece most
    # likely to be rewritten, and one that may need turning off at short
    # notice. Deleting the file is the off switch.
    parts = [message_url, outro_url]
    invite = get_invite_url(base_url, answered_by)
    if invite:
        parts.append(invite)
    return parts


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
