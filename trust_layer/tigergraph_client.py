"""
Thin REST wrapper around TigerGraph, mirroring the Node.js tigerGraphService
pattern from the TrueSeal project (token caching, upsert helpers, named
query calls) but in Python so it drops straight into the FastAPI backend.
"""
import os
import time
import requests

TG_HOST = os.getenv("TIGERGRAPH_HOST", "http://localhost")
TG_PORT = os.getenv("TIGERGRAPH_PORT", "9000")
TG_GRAPH = os.getenv("TIGERGRAPH_GRAPH", "PDS_TrustGraph")
TG_SECRET = os.getenv("TIGERGRAPH_SECRET", "")

BASE_URL = f"{TG_HOST}:{TG_PORT}"

_cached_token = None
_token_expiry = 0


def _get_token() -> str:
    global _cached_token, _token_expiry
    if _cached_token and time.time() < _token_expiry:
        return _cached_token

    resp = requests.post(
        f"{BASE_URL}/restpp/requesttoken",
        json={"secret": TG_SECRET, "lifetime": 3600},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    _cached_token = data["results"]["token"]
    _token_expiry = time.time() + 55 * 60  # refresh 5 min early
    return _cached_token


def _request(method: str, endpoint: str, json_body: dict | None = None) -> dict:
    token = _get_token()
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.request(
        method, f"{BASE_URL}{endpoint}", json=json_body, headers=headers, timeout=15
    )
    resp.raise_for_status()
    return resp.json()


def tg_get(endpoint: str) -> dict:
    return _request("GET", endpoint)


def tg_post(endpoint: str, data: dict) -> dict:
    return _request("POST", endpoint, data)


# ---------- vertex / edge upsert helpers ----------

def upsert_vertex(vertex_type: str, vertex_id: str, attributes: dict) -> dict:
    payload = {"vertices": {vertex_type: {vertex_id: attributes}}}
    return tg_post(f"/restpp/graph/{TG_GRAPH}", payload)


def upsert_edge(
    from_type: str, from_id: str, edge_type: str, to_type: str, to_id: str,
    attributes: dict | None = None,
) -> dict:
    payload = {
        "edges": {
            from_type: {
                from_id: {edge_type: {to_type: {to_id: attributes or {}}}}
            }
        }
    }
    return tg_post(f"/restpp/graph/{TG_GRAPH}", payload)


# ---------- domain helpers used by sync.py ----------

def add_shop(shop_id: str, name: str, region: str, registered_at_iso: str) -> dict:
    return upsert_vertex("FairPriceShop", shop_id, {
        "name": {"value": name},
        "region": {"value": region},
        "registered_at": {"value": registered_at_iso},
    })


def add_dispatch_batch(batch_id: str, item: str, quantity_g: float,
                        dispatch_date_iso: str, data_hash: str, shop_id: str) -> None:
    upsert_vertex("DispatchBatch", batch_id, {
        "item": {"value": item},
        "quantity_g": {"value": quantity_g},
        "dispatch_date": {"value": dispatch_date_iso},
        "data_hash": {"value": data_hash},
        "status": {"value": "delivered"},
    })
    upsert_edge("DispatchBatch", batch_id, "DISPATCHED_TO", "FairPriceShop", shop_id,
                {"delivered_at": {"value": dispatch_date_iso}})


def record_distribution_event(event_id: str, shop_id: str, item: str, weight_g: float,
                               change_g: float, timestamp_iso: str, event_hash: str,
                               rfid_uid: str | None = None, batch_id: str | None = None) -> None:
    upsert_vertex("DistributionEvent", event_id, {
        "item": {"value": item},
        "weight_g": {"value": weight_g},
        "change_g": {"value": change_g},
        "timestamp": {"value": timestamp_iso},
        "event_hash": {"value": event_hash},
        "verified": {"value": True},
    })
    upsert_edge("DistributionEvent", event_id, "DISTRIBUTED_AT", "FairPriceShop", shop_id)

    if rfid_uid:
        upsert_vertex("Beneficiary", rfid_uid, {"first_seen": {"value": timestamp_iso}})
        upsert_edge("DistributionEvent", event_id, "CLAIMED_BY", "Beneficiary", rfid_uid)

    if batch_id:
        upsert_edge("DistributionEvent", event_id, "FROM_BATCH", "DispatchBatch", batch_id)


def record_complaint(complaint_id: str, shop_id: str, reason: str,
                      raised_at_iso: str, event_id: str | None = None) -> None:
    upsert_vertex("Complaint", complaint_id, {
        "raised_at": {"value": raised_at_iso},
        "reason": {"value": reason},
    })
    upsert_edge("Complaint", complaint_id, "COMPLAINT_AGAINST", "FairPriceShop", shop_id)
    if event_id:
        upsert_edge("Complaint", complaint_id, "COMPLAINT_ABOUT_EVENT",
                    "DistributionEvent", event_id)


def increment_anomaly_score(shop_id: str, increment: float = 0.1) -> float:
    current = tg_get(f"/restpp/graph/{TG_GRAPH}/vertices/FairPriceShop/{shop_id}")
    score = 0.0
    try:
        score = current["results"][0]["attributes"].get("anomaly_score", 0.0)
    except (KeyError, IndexError):
        pass
    new_score = min(1.0, score + increment)
    upsert_vertex("FairPriceShop", shop_id, {"anomaly_score": {"value": new_score}})
    return new_score


# ---------- named-query wrappers ----------

def get_batch_journey(batch_id: str) -> list:
    return tg_get(f"/restpp/query/{TG_GRAPH}/getBatchJourney?batch_id={batch_id}").get("results", [])


def get_anomalous_shops(threshold: float = 0.5) -> list:
    return tg_get(f"/restpp/query/{TG_GRAPH}/getAnomalousShops?threshold={threshold}").get("results", [])


def get_repeat_offenders(top_n: int = 10) -> list:
    return tg_get(f"/restpp/query/{TG_GRAPH}/getRepeatOffenders?top_n={top_n}").get("results", [])


def get_regional_clusters(region: str) -> list:
    return tg_get(f"/restpp/query/{TG_GRAPH}/getRegionalClusters?region={region}").get("results", [])


def get_suspicious_beneficiaries(distinct_shop_threshold: int = 3) -> list:
    return tg_get(
        f"/restpp/query/{TG_GRAPH}/getSuspiciousBeneficiaries"
        f"?distinct_shop_threshold={distinct_shop_threshold}"
    ).get("results", [])
