"""
Twilio Verify - OTP without owning the risk.

STEP 4 of the Twilio handoff. The old 2FA generated its own 6-digit
codes and pushed them through raw send_sms() - which is (a) blocked
until A2P clears for normal messaging and (b) the textbook SMS-pumping
fraud surface: a public phone input wired to messages.create() lets an
attacker point traffic at premium international ranges for a revenue
share while we pay the bill. Verify uses Twilio's own registered sender
pool (NO A2P needed - confirmed with Twilio Aug 7), includes Fraud
Guard by default, and owns code generation, expiry, retries and rate
limits so nothing secret is stored on our side.
"""
import os
from services.twilio_service import _get_client, _to_e164


def start_verification(phone: str, channel: str = "sms") -> str:
    """Send an OTP. channel='voice' reads the code aloud - the
    fallback for landline/VoIP numbers that can never receive SMS."""
    return _get_client().verify.v2.services(
        os.environ["TWILIO_VERIFY_SERVICE_SID"]
    ).verifications.create(to=_to_e164(phone), channel=channel).status


def check_verification(phone: str, code: str) -> bool:
    """True only on the right code. Verify owns expiry and attempt
    limits; a wrong/expired/burned code is simply not 'approved'."""
    check = _get_client().verify.v2.services(
        os.environ["TWILIO_VERIFY_SERVICE_SID"]
    ).verification_checks.create(to=_to_e164(phone), code=code)
    return check.status == "approved"
