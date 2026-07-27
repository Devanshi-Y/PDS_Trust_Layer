"""
QR-based verification, mirroring TrueSeal's qrService.js: encode a
verify-URL (not the raw data) into the QR, so scanning it always checks
the *current* server-side record rather than trusting whatever is printed
on paper.
"""
import os
import qrcode
import io
import base64

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")


def generate_event_qr(event_id: str, event_hash: str) -> dict:
    """Returns a base64 data URL for the QR image plus the verify URL it encodes.
    A beneficiary or auditor scans this to hit /trust/verify/{event_id} and
    confirm the printed weight/date matches the tamper-evident record."""
    verify_url = f"{FRONTEND_URL}/verify-ration?event={event_id}&sig={event_hash[:16]}"

    img = qrcode.make(verify_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")

    return {"qr_data_url": data_url, "verify_url": verify_url}
