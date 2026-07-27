"""
Tamper-evidence layer for PDS.

TrueSeal anchors a SHA-256 hash of each product batch on a real blockchain
(Polygon, via a Solidity contract). For a class-scale PDS deployment a full
chain is overkill, so this module gives you the same guarantee with a
locally-verifiable hash chain (each record's hash includes the previous
record's hash, exactly like a blockchain's block-linking, minus the
distributed consensus). If you later want the full on-chain version, see
`anchor_to_chain()` below, which is a stub for wiring in web3.py the same
way TrueSeal's blockchainService.js wires in ethers.js.

Any edit to a past row breaks every hash after it — auditors can detect
tampering by recomputing the chain and comparing to the stored `event_hash`.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone

DB_FILE = "pds_trust_chain.db"

GENESIS_HASH = "0" * 64


def _get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_chain_db():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hash_chain (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            shop_id TEXT NOT NULL,
            item TEXT NOT NULL,
            weight_g REAL,
            change_g REAL,
            timestamp TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _get_last_hash() -> str:
    conn = _get_conn()
    row = conn.execute(
        "SELECT event_hash FROM hash_chain ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row["event_hash"] if row else GENESIS_HASH


def compute_event_hash(event_id: str, shop_id: str, item: str, weight_g: float,
                        change_g: float, timestamp_iso: str, prev_hash: str) -> str:
    """Deterministic hash of one distribution event, chained to the previous one.
    Field order matters — the same order must be used everywhere the hash
    is recomputed for verification."""
    # weight_g/change_g are always cast to float before formatting so the
    # hash is stable whether the value arrives as an int (e.g. from MQTT
    # JSON) or a float (e.g. read back out of SQLite as REAL) — otherwise
    # "4500" vs "4500.0" would silently break verification.
    payload = "|".join([
        event_id, shop_id, item,
        f"{float(weight_g)}", f"{float(change_g)}", timestamp_iso, prev_hash,
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def append_event(event_id: str, shop_id: str, item: str, weight_g: float,
                  change_g: float, timestamp_iso: str | None = None) -> str:
    """Call this once per distribution event (e.g. from the MQTT weight
    handler). Returns the event_hash to store alongside the event / put
    in a QR code."""
    timestamp_iso = timestamp_iso or datetime.now(timezone.utc).isoformat()
    prev_hash = _get_last_hash()
    event_hash = compute_event_hash(event_id, shop_id, item, weight_g,
                                     change_g, timestamp_iso, prev_hash)

    conn = _get_conn()
    conn.execute("""
        INSERT INTO hash_chain
            (event_id, shop_id, item, weight_g, change_g, timestamp, prev_hash, event_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (event_id, shop_id, item, weight_g, change_g, timestamp_iso, prev_hash, event_hash))
    conn.commit()
    conn.close()
    return event_hash


def verify_chain() -> dict:
    """Recomputes every hash in sequence and reports the first row (if any)
    that doesn't match what's stored — i.e. where the underlying log was
    edited after the fact."""
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM hash_chain ORDER BY id ASC").fetchall()
    conn.close()

    prev_hash = GENESIS_HASH
    for row in rows:
        expected = compute_event_hash(
            row["event_id"], row["shop_id"], row["item"],
            row["weight_g"], row["change_g"], row["timestamp"], prev_hash,
        )
        if expected != row["event_hash"]:
            return {
                "valid": False,
                "broken_at_id": row["id"],
                "event_id": row["event_id"],
                "reason": "stored hash does not match recomputed hash — record was likely altered",
            }
        prev_hash = row["event_hash"]

    return {"valid": True, "records_checked": len(rows)}


def verify_single_event(event_id: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM hash_chain WHERE event_id = ?", (event_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "event_id": row["event_id"],
        "shop_id": row["shop_id"],
        "item": row["item"],
        "weight_g": row["weight_g"],
        "change_g": row["change_g"],
        "timestamp": row["timestamp"],
        "event_hash": row["event_hash"],
    }


def anchor_to_chain(event_hash: str) -> dict:
    """
    Stub for anchoring the local chain's tip hash to a public blockchain
    periodically (e.g. once a day), the way TrueSeal anchors each batch hash
    via its Solidity contract on Polygon Amoy. Wire this up with web3.py
    once you have a deployed contract + funded wallet:

        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
        tx = contract.functions.anchorHash(bytes.fromhex(event_hash)).transact(...)

    Left unimplemented here so the trust layer works fully offline for a
    demo; the local hash chain alone already gives tamper-evidence.
    """
    raise NotImplementedError(
        "Optional: wire up web3.py + a deployed anchor contract here, "
        "following the same pattern as trueseal/backend/src/services/blockchainService.js"
    )
