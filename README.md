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
  "hash_algo": "rfc6962-sha256",
  "index_url": "https://archive.noosphere.md/archive/2026/06/12/15.index.json",
  "jwks": "https://noosphere.md/.well-known/jwks.json",
  "committed_at": "…"
}
```

`index_url` returns the hour index: every slot's `ust_id` and `hash`,
sorted ascending. Merkle: **RFC 6962** — a leaf is `sha256(0x00 || hash)`, an
interior node is `sha256(0x01 || left || right)`, and a level of `n` leaves
splits at the largest power of two **below** `n` (so 120 splits 64 / 56, not
60 / 60). The odd-node-promotes tree this document described until 2026-08-06
was never what the anchor worker computed; the recipe below is executed against
a live anchor before each change to this file.

## Verify by hand

**1. Recompute the Merkle root from the public slot hashes** (no tools
beyond Python):

```bash
python3 - anchors/2026/08/05/21.json <<'EOF'
import json, hashlib, sys, urllib.request
a = json.load(open(sys.argv[1]))
req = urllib.request.Request(a["index_url"], headers={"User-Agent": "ust-verify"})
idx = json.loads(urllib.request.urlopen(req).read())

H    = lambda b: hashlib.sha256(b).digest()
leaf = lambda d: H(b"\x00" + d)                 # RFC 6962 leaf
node = lambda l, r: H(b"\x01" + l + r)          # RFC 6962 interior

def root(xs):
    if len(xs) == 1:
        return xs[0]
    k = 1 << ((len(xs) - 1).bit_length() - 1)   # largest power of two BELOW len(xs)
    return node(root(xs[:k]), root(xs[k:]))

leaves = [leaf(bytes.fromhex(s["hash"].removeprefix("sha256:"))) for s in idx["slots"]]
got = "sha256:" + root(leaves).hex()
print("slots      :", len(leaves))
print("recomputed :", got)
print("anchor says:", a["merkle_root"])
print("MATCH" if got == a["merkle_root"] else "MISMATCH")
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
