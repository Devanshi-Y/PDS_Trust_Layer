"""
Bridges the existing PDS MQTT ingestion path (subscriber.py) to the two
new trust-layer stores, without changing any existing SQLite behaviour.

Call `on_weight_event(...)` from inside subscriber.py's insert_weight_log
(or right after it), and `on_complaint(...)` from wherever complaints get
created. Both TigerGraph and the hash chain are best-effort: if TigerGraph
is unreachable (e.g. not running during a demo), the hash chain still
records tamper-evidence, and vice versa. Failures are logged, not raised,
so a flaky graph server never takes down ration distribution.
"""
import logging
import uuid
from datetime import datetime, timezone

from . import hash_chain, tigergraph_client as tg

logger = logging.getLogger("trust_layer.sync")

# Same threshold PDS already uses for "large weight drop" alerts (see
# subscriber.py LARGE_DROP_THRESHOLD_G) — reused here so an anomalous
# weight event also bumps the shop's TigerGraph anomaly_score.
LARGE_DROP_THRESHOLD_G = 150


def on_weight_event(shop_id: str, item: str, weight_g: float, change_g: float,
                     rfid_uid: str | None = None, batch_id: str | None = None) -> dict:
    """
    Call once per weight_logs insert. Returns the event_id and event_hash
    so the caller can attach them to a QR code or an API response.
    """
    event_id = f"{shop_id}-{item}-{uuid.uuid4().hex[:8]}"
    timestamp_iso = datetime.now(timezone.utc).isoformat()

    event_hash = hash_chain.append_event(
        event_id=event_id, shop_id=shop_id, item=item,
        weight_g=weight_g, change_g=change_g, timestamp_iso=timestamp_iso,
    )

    try:
        tg.record_distribution_event(
            event_id=event_id, shop_id=shop_id, item=item,
            weight_g=weight_g, change_g=change_g, timestamp_iso=timestamp_iso,
            event_hash=event_hash, rfid_uid=rfid_uid, batch_id=batch_id,
        )
        if change_g and change_g > LARGE_DROP_THRESHOLD_G:
            tg.increment_anomaly_score(shop_id, increment=0.15)
    except Exception as exc:  # noqa: BLE001 — best-effort, never block ingestion
        logger.warning("TigerGraph sync failed for event %s: %s", event_id, exc)

    return {"event_id": event_id, "event_hash": event_hash, "timestamp": timestamp_iso}


def on_repeated_denied_rfid(shop_id: str) -> None:
    """Call when subscriber.py's existing rule (3+ denied RFID attempts)
    fires, so the shop's graph anomaly_score reflects it too."""
    try:
        tg.increment_anomaly_score(shop_id, increment=0.2)
    except Exception as exc:  # noqa: BLE001
        logger.warning("TigerGraph anomaly bump failed for shop %s: %s", shop_id, exc)


def on_complaint(shop_id: str, reason: str, event_id: str | None = None) -> str:
    complaint_id = f"cmp-{uuid.uuid4().hex[:10]}"
    raised_at_iso = datetime.now(timezone.utc).isoformat()
    try:
        tg.record_complaint(complaint_id, shop_id, reason, raised_at_iso, event_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("TigerGraph complaint sync failed: %s", exc)
    return complaint_id


def on_shop_registered(shop_id: str, name: str, region: str) -> None:
    try:
        tg.add_shop(shop_id, name, region, datetime.now(timezone.utc).isoformat())
    except Exception as exc:  # noqa: BLE001
        logger.warning("TigerGraph shop registration failed: %s", exc)


def on_batch_dispatched(batch_id: str, item: str, quantity_g: float,
                         shop_id: str, data_hash: str) -> None:
    try:
        tg.add_dispatch_batch(
            batch_id, item, quantity_g,
            datetime.now(timezone.utc).isoformat(), data_hash, shop_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("TigerGraph batch dispatch failed: %s", exc)
