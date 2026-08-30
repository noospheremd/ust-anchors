# public-proof — one transcript, walked all the way to a Bitcoin block

A single sealed transcript from `noosphere.md`, together with everything needed to verify — by hand, offline,
or in a browser — that its bytes were committed to Bitcoin. Nothing here has to be taken on trust, and nothing
here requires contacting the publisher.

**The transcript:** `ust:20260829.120000` — one 30-second frame, 172 public sources, sealed 2026-08-29 12:00:00 UTC.

**The claim being proven:** these exact bytes existed before Bitcoin block **964576** was mined
(2026-08-29 13:38:38 UTC).

```
transcript  →  content_hash  →  RFC 6962 path  →  hour root  →  OpenTimestamps  →  Bitcoin block 964576
```

## Files

| file | what it is |
|---|---|
| `transcript.ust.json` | the signed UST 1.0 document, with its `proof` member attached (root + inclusion path + anchor) |
| `hour-root.ots` | the OpenTimestamps proof over the hour's Merkle root, upgraded to its Bitcoin attestation |

Everything else this walkthrough uses is already public and served by someone other than us:

- the hour index (120 slot hashes) — `https://archive.noosphere.md/archive/2026/08/29/12.ust1.index.json`
- the hour anchor — [`anchors/2026/08/29/12.ust1.json`](../anchors/2026/08/29/12.ust1.json)
- the per-slot inclusion paths — [`anchors/2026/08/29/12.ust1.proofs.json`](../anchors/2026/08/29/12.ust1.proofs.json)
- the block — any Bitcoin explorer, or your own node

## 1. Verify the transcript in a browser

Open **https://verify.ustprotocol.com**, paste the contents of `transcript.ust.json`.

Expected:

```
VALID:HIGH
identity : corroborated / verified   (mode name, publisher noosphere.md)
time     : anchored / verified       anchorTime 2026-08-29T13:38:38Z
```

`time: anchored` is the line that matters here: the verifier followed the inclusion path to the hour root and
confirmed that root against Bitcoin.

**Why HIGH and not TOP, stated plainly.** TOP requires `identity: authoritative` — independent non-membership
evidence for the name. This publisher serves its own witness log, which by the protocol's own rule earns
`corroborated` and never `authoritative`. The time axis is fully anchored; the identity axis is honestly capped.
That gap is tracked in the open, in [UST-Protocol#159](https://github.com/thelabmd/UST-Protocol/issues/159) and
[#82](https://github.com/thelabmd/UST-Protocol/issues/82) — not smoothed over here.

## 2. Verify it from a terminal

The anchor connectors are opt-in, and the CLI uses whichever are installed:

```bash
npm i @ust-protocol/cli @ust-protocol/ots-verify @ust-protocol/rekor-verify @ust-protocol/rfc6962-verify
npx ust verify transcript.ust.json
```

Expected, same as the browser:

```
VALID:HIGH
  identity : corroborated/verified (mode name)  publisher_claimed noosphere.md
  time     : anchored/verified
```

Without the connectors installed the same command answers `time: unproven` — correctly, because nothing in that
build can reach Bitcoin. Pending is a true state; so is *not checked here*.

> Requires `@ust-protocol/cli` **1.0.0-rc.108 or newer**. Up to rc.107 the CLI assembled the inclusion connector
> and did not pass it to the call, so it reported `time: unproven` on this very document while the anchor beneath
> it was final in Bitcoin. Found while writing this walkthrough, fixed in round 240.

## 3. Recompute the hour root yourself — no tools beyond Python

The root the OTS proof commits to is derived from 120 published slot hashes. Recompute it and compare:

```bash
python3 - <<'EOF'
import json, hashlib, urllib.request
req = urllib.request.Request(
    "https://archive.noosphere.md/archive/2026/08/29/12.ust1.index.json",
    headers={"User-Agent": "ust-verify"})
idx = json.loads(urllib.request.urlopen(req).read())

H    = lambda b: hashlib.sha256(b).digest()
leaf = lambda d: H(b"\x00" + d)                 # RFC 6962 leaf
node = lambda l, r: H(b"\x01" + l + r)          # RFC 6962 interior

def root(xs):
    if len(xs) == 1:
        return xs[0]
    k = 1 << ((len(xs) - 1).bit_length() - 1)   # split at the largest power of two BELOW len(xs)
    return node(root(xs[:k]), root(xs[k:]))

leaves = [leaf(bytes.fromhex(s["hash"].removeprefix("sha256:"))) for s in idx["slots"]]
print("slots      :", len(idx["slots"]))
print("recomputed :", "sha256:" + root(leaves).hex())
print("expected   : sha256:46e1836310ebac22174e12681daef063a65c52fa8770fafe2605b8b88c713e14")
EOF
```

## 4. Walk the OTS proof to the block

```bash
pip install --quiet opentimestamps-client
ots info hour-root.ots        # shows the BitcoinBlockHeaderAttestation and its height
```

Then check the block against any explorer — the merkle root printed by `ots info` must equal the block's:

```bash
curl -s https://blockstream.info/api/block-height/964576 \
  | xargs -I{} curl -s https://blockstream.info/api/block/{} \
  | python3 -c "import json,sys,datetime; b=json.load(sys.stdin); print('height', b['height']); print('time  ', datetime.datetime.utcfromtimestamp(b['timestamp']).isoformat()+'Z'); print('merkle', b['merkle_root'])"
```

## One honest note about this file's `anchor`

The `anchor.ots` inside `transcript.ust.json` is the **upgraded** proof — the same timestamp as the one in
`12.ust1.proofs.json`, after the calendars committed it into Bitcoin. The copy embedded in the proofs file at
publication time was still *pending*, and upgrading it is a publisher-side operation that does not rewrite the
already-published file. A verifier handed the pending copy answers `unproven / pending`, which is the correct
answer for those bytes — pending is a true state, not a failure.

This is exactly the kind of operational seam that makes Bitcoin anchoring harder to run than to describe, and
it is recorded here rather than tidied away.
