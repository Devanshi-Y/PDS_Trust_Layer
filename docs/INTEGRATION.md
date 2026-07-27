# Wiring this into the PDS repo

This repo is designed to be dropped into `Public-Distribution-System-main/backend/`
as a sibling folder called `trust_layer/`, with three small edits to existing
files. Nothing in `subscriber.py`'s MQTT/SQLite logic or `api.py`'s existing
routes is removed or changed — only additive calls.

## 1. Copy the folder

```bash
cp -r pds-trust-layer/trust_layer Public-Distribution-System-main/backend/
cp pds-trust-layer/requirements.txt Public-Distribution-System-main/backend/trust_layer_requirements.txt
cp pds-trust-layer/.env.example Public-Distribution-System-main/backend/.env.example
```

## 2. Hook the MQTT ingestion path (`subscriber.py`)

Add the import near the top:

```python
from trust_layer import sync as trust_sync
```

In `insert_weight_log(...)`, after the existing `conn.commit(); conn.close()`,
add:

```python
    trust_sync.on_weight_event(
        shop_id=shop_id,
        item=item,
        weight_g=payload.get("weight_g"),
        change_g=payload.get("change_g"),
        rfid_uid=payload.get("rfid_uid"),  # if your payload includes it
    )
```

In `check_anomalies_and_act(...)`, inside the "Rule 2: repeated denied RFID
attempts" branch, right after the existing `insert_alert(...)` call, add:

```python
            trust_sync.on_repeated_denied_rfid(shop_id)
```

That's it for the hardware/ingestion side — every weight event now also
gets hash-chained and (best-effort) pushed to TigerGraph, and repeated
denied RFID attempts also raise the shop's graph anomaly score.

## 3. Mount the new API routes (`api.py`)

```python
from trust_layer.api_routes import router as trust_router
from trust_layer import hash_chain

app.include_router(trust_router, prefix="/trust")
```

And call `hash_chain.init_chain_db()` once at startup, alongside wherever
`init_db()` is already called (or add a FastAPI startup event):

```python
@app.on_event("startup")
def _init_trust_layer():
    hash_chain.init_chain_db()
```

## 4. New endpoints you get for free

| Endpoint | Purpose |
|---|---|
| `GET /trust/verify/{event_id}` | Beneficiary/auditor checks one distribution event wasn't altered |
| `GET /trust/verify-chain` | Full tamper-evidence audit across all events |
| `GET /trust/qr/{event_id}` | QR code encoding the verify URL for a receipt |
| `GET /trust/analytics/anomalous-shops?threshold=0.5` | Shops flagged by anomaly score |
| `GET /trust/analytics/repeat-offenders?top_n=10` | Shops with the most complaints |
| `GET /trust/analytics/regional-clusters?region=X` | Complaint/shop density for a region |
| `GET /trust/analytics/suspicious-beneficiaries` | RFID tags used across too many shops |
| `GET /trust/batch/{batch_id}/journey` | Full warehouse-to-shop-to-event trace |
| `POST /trust/complaints` | Beneficiary files a complaint against a shop/event |

## 5. Frontend

Add one new page, `consumer-verify` or `verify-ration`, mirroring TrueSeal's
`/consumer-verify` route: it reads `?event=...&sig=...` from the URL, calls
`GET /trust/verify/{event}`, and shows a green/red tamper-check badge plus
the shop, item, and weight. This is the single page a beneficiary or field
auditor scans the QR into.

## 6. Merging the two GitHub repos

Simplest path — treat this repo as a subtree of the PDS repo:

```bash
cd Public-Distribution-System-main
git remote add trust-layer https://github.com/<you>/pds-trust-layer.git
git fetch trust-layer
git subtree add --prefix=backend/trust_layer trust-layer main --squash
```

This keeps full commit history importable, and either repo can still be
iterated on independently before the merge.

## What's intentionally left out for now

- Real on-chain anchoring (`hash_chain.anchor_to_chain`) is stubbed, not
  wired to a live contract — the local hash chain already gives tamper
  evidence for a demo. Wire it up later with `web3.py`, following the
  same pattern as `trueseal/backend/src/services/blockchainService.js`,
  if you want an actual public-chain anchor for the final submission.
- TigerGraph calls are best-effort (wrapped in try/except) so a demo
  still runs end-to-end even if the graph server isn't up — but for the
  real analytics story you do need TigerGraph Community Edition running
  locally or on a small VM during the demo.
