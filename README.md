# PDS Trust Layer

A drop-in add-on for the [IoT-Based Public Distribution System](https://github.com/YOUR_USERNAME/PDS_PROJECT)
that adds three things the original project's own "Future Improvements"
list calls for but doesn't yet have:

1. **Graph-based diversion analytics (TigerGraph)** — models the ration
   supply chain as `Warehouse → DispatchBatch → FairPriceShop → Beneficiary`
   so fraud patterns (diversion, ghost beneficiaries, repeat-offender shops,
   regional complaint clusters) are queryable instead of buried in
   per-row SQLite logs.
2. **Tamper-evident record-keeping (hash chain)** — every distribution
   event is SHA-256 hash-chained, so if anyone edits a past row in the
   SQLite logs after the fact, the chain no longer recomputes and an
   audit immediately shows exactly where.
3. **QR-based beneficiary verification** — every ration disbursement gets
   a QR code that a beneficiary or field auditor can scan to confirm the
   recorded weight/time wasn't altered.

This design mirrors [TrueSeal](https://github.com/YOUR_USERNAME/trueseal),
a product-authenticity supply-chain project (TigerGraph + Solidity/Polygon
hash-anchoring + QR verification) — adapted here to Python/FastAPI to match
the PDS backend, and simplified to a local hash chain instead of a full
smart contract so it runs with zero blockchain infra for a demo.

## Structure

```
pds-trust-layer/
├── gsql/
│   ├── schema.gsql        # TigerGraph vertex/edge types
│   ├── queries.gsql        # anomaly / repeat-offender / journey queries
│   └── setup.sh
├── trust_layer/
│   ├── tigergraph_client.py  # REST wrapper (token caching, upsert, queries)
│   ├── hash_chain.py          # local tamper-evident hash chain + audit
│   ├── qr_service.py          # QR generation for verify URLs
│   ├── sync.py                 # bridges MQTT ingestion -> graph + chain
│   ├── api_routes.py            # new FastAPI endpoints
│   └── models.py
├── docs/
│   └── INTEGRATION.md      # exact diffs to apply to the PDS repo
├── requirements.txt
└── .env.example
```

## Quick start (standalone)

```bash
pip install -r requirements.txt --break-system-packages
export $(cat .env.example | xargs)   # or your own .env with a real TigerGraph secret

# Optional: stand up TigerGraph Community Edition and install the schema
bash gsql/setup.sh

python -c "
from trust_layer import hash_chain, sync
hash_chain.init_chain_db()
print(sync.on_weight_event('shop-001', 'rice', 4500, 500))
print(hash_chain.verify_chain())
"
```

## Wiring into the PDS repo

See [`docs/INTEGRATION.md`](docs/INTEGRATION.md) for the exact three-file
patch (`subscriber.py`, `api.py`) and the `git subtree` command to merge
this repo in while keeping both commit histories.

## Why this, not just "add TigerGraph because it's advanced"

PDS's own README already lists AI-based demand prediction and general
transparency as future work, and ration diversion (ghost beneficiaries,
black-market resale, falsified stock logs) is a documented real-world
failure mode of PDS systems — a graph query answering "which shops show
anomalous drop patterns right before audits" and a hash chain proving
"this log wasn't edited after the fact" are direct, defensible answers to
that problem, not tech added for its own sake.
