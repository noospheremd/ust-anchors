# ust-anchors

Public anchor journal for [noosphere.md](https://noosphere.md) — the UST
planetary-state notary.

Every hour, one file: `anchors/YYYY/MM/DD/HH.json` — the Merkle root over the
hashes of all 120 thirty-second slots sealed in that hour, committed here by
the anchor worker. A GitHub Action in this repo then stamps each anchor with
OpenTimestamps (`<anchor>.json.ots` appears beside it) and upgrades pending
proofs daily once the calendars commit them into Bitcoin.

## Why this exists

A signed receipt from noosphere.md proves the operator attested a state.
This journal removes even that trust requirement:

```
slot hash → merkle path → root → git commit → .ots → Bitcoin block
```

Every link is verifiable by anyone, forever, without asking the operator —
and cannot be rewritten retroactively, including by the operator.

## Anchor format

```json
{
  "protocol": "UST",
  "hour_ust": "ust:20260612.15",
  "merkle_root": "sha256:…",
  "slot_count": 120,
  "hash_algo": "sha256-merkle-sorted-asc-odd-promotes",
  "index_url": "https://archive.noosphere.md/archive/2026/06/12/15.index.json",
  "jwks": "https://noosphere.md/.well-known/jwks.json",
  "committed_at": "…"
}
```

`index_url` returns the hour index: every slot's `ust_id` and `hash`,
sorted ascending. Merkle: sha256 over the concatenation of each pair,
odd node promotes unchanged.

## Verify by hand

**1. Recompute the Merkle root from the public slot hashes** (no tools
beyond Python):

```bash
python3 - anchors/2026/06/12/15.json <<'EOF'
import json, hashlib, sys, urllib.request
a = json.load(open(sys.argv[1]))
req = urllib.request.Request(a["index_url"], headers={"User-Agent": "ust-verify"})
idx = json.loads(urllib.request.urlopen(req).read())
level = [bytes.fromhex(s["hash"].removeprefix("sha256:")) for s in idx["slots"]]
while len(level) > 1:
    level = [hashlib.sha256(level[i] + level[i + 1]).digest() if i + 1 < len(level) else level[i]
             for i in range(0, len(level), 2)]
root = "sha256:" + level[0].hex()
print("recomputed :", root)
print("anchor says:", a["merkle_root"])
print("MATCH" if root == a["merkle_root"] else "MISMATCH")
EOF
```

**2. Verify the Bitcoin timestamp** (proof matures within hours of the
anchor commit; `upgrade` is idempotent and works any time later):

```bash
pip install opentimestamps-client
ots upgrade anchors/2026/06/12/15.json.ots   # pulls the Bitcoin merkle path from the calendars
ots verify  anchors/2026/06/12/15.json.ots   # → "Success! Bitcoin block <height> attests existence as of <date>"
```

No terminal: drag the `.json` and `.json.ots` onto
[opentimestamps.org](https://opentimestamps.org) — it shows the attesting
Bitcoin block.

**3. Verify the operator's signature on the hour** (independent layer):
every sealed hour also ships a free Ed25519 receipt at
`https://archive.noosphere.md/archive/YYYY/MM/DD/HH.receipt.json` —
verify `sig` over `canonical` against
[noosphere.md/.well-known/jwks.json](https://noosphere.md/.well-known/jwks.json).

Protocol: [github.com/thelabmd/UST](https://github.com/thelabmd/UST) ·
Contact: contact@noosphere.md
