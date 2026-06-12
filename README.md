# ust-anchors

Public anchor journal for [noosphere.md](https://noosphere.md) — the UST
planetary-state notary.

Every hour, one file: `anchors/YYYY/MM/DD/HH.json` — the Merkle root over the
hashes of all 120 thirty-second slots sealed in that hour, committed here by
cron. Once a day, OpenTimestamps proofs (`.ots`) are stamped and upgraded
beside each anchor, binding the root to the Bitcoin timeline.

## Why this exists

A signed receipt from noosphere.md proves the operator attested a state.
This journal removes even that trust requirement: the chain

```
slot hash → merkle path → root → git commit → .ots → Bitcoin block
```

is verifiable by anyone, forever, without asking the operator anything —
and cannot be rewritten retroactively, including by the operator.

## Verify an anchor

```bash
# 1. take an anchor
cat anchors/2026/06/12/15.json
# 2. fetch its hour index (slot hashes) and recompute the root
#    merkle: sha256 pairwise over slot hashes sorted ASC by ust_id, odd node promotes
curl -s <index_url from the anchor> | <recompute merkle root>
# 3. compare with merkle_root in the anchor — and check the .ots:
ots verify anchors/2026/06/12/15.json.ots
```

Hour receipts (Ed25519, free, every sealed hour) and the JWKS live at
[noosphere.md/.well-known/jwks.json](https://noosphere.md/.well-known/jwks.json).
Protocol: [github.com/thelabmd/UST](https://github.com/thelabmd/UST).
