"""
Quick standalone test — confirms your ElevenLabs API key works and
generates real audio, before touching Flask/Twilio/Stripe at all.

Usage:
    1. pip install requests
    2. Set your API key below (or export ELEVENLABS_API_KEY as an env var)
    3. python test_elevenlabs.py
    4. Open the generated test_output.mp3 and listen to it

Get your API key: elevenlabs.io -> profile icon -> API keys
Get a voice ID: elevenlabs.io -> Voices -> click any voice -> copy the ID
                (or use the default below, "Rachel", a built-in stock voice)
"""

import os
import requests

API_KEY = os.environ.get("ELEVENLABS_API_KEY", "PASTE_YOUR_KEY_HERE")
VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel, stock voice

TEST_MESSAGE = "Hey, just checking in to let you know your team blew a fourteen point lead. Again."

url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"

response = requests.post(
    url,
    headers={
        "xi-api-key": API_KEY,
        "Content-Type": "application/json",
    },
    json={
        "text": TEST_MESSAGE,
        "model_id": "eleven_turbo_v2",
        "voice_settings": {
            "stability": 0.4,
            "similarity_boost": 0.8,
        },
    },
)

if response.status_code == 200:
    with open("test_output.mp3", "wb") as f:
        f.write(response.content)
    print("Success — saved test_output.mp3, go listen to it.")
    print(f"Used roughly {len(TEST_MESSAGE)} characters / credits.")
else:
    print(f"Failed: {response.status_code}")
    print(response.text)
