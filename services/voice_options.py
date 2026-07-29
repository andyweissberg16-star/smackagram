import os

# Friendly names shown in the picker on the site, mapped to ElevenLabs voice IDs.
# The "default" voice comes from ELEVENLABS_VOICE_ID (already in Render's env
# vars) so existing setup keeps working without changes. Add more characters
# here any time you find a voice you like — just needs a label + voice ID.

VOICE_OPTIONS = {
    "default": {
        "label": "Smacky (Classic)",
        "voice_id": os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"),
    },
    "cocky": {
        "label": "Loud, confident, cocky",
        "voice_id": "DGzg6RaUqxGRTHSBjfgF",
    },
    "sexy_female": {
        "label": "Sexy female",
        "voice_id": "eVItLK1UvXctxuaRV2Oq",
    },
    "young_kid": {
        "label": "Young kid",
        "voice_id": "XjGYkUkzth8BPs29fmcV",
    },
}

DEFAULT_VOICE_KEY = "default"


def get_voice_id(character_key: str) -> str:
    """Looks up the voice ID for a given character key, falling back to default."""
    option = VOICE_OPTIONS.get(character_key, VOICE_OPTIONS[DEFAULT_VOICE_KEY])
    return option["voice_id"]


def list_voice_options() -> list[dict]:
    """Returns [{key, label}] for populating the picker UI."""
    return [{"key": key, "label": v["label"]} for key, v in VOICE_OPTIONS.items()]
