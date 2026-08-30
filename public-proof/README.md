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

The OpenTimestamps proof is read by **`@ust-protocol/ots-verify`** — a zero-dependency OTS proof verifier written
from scratch for this protocol. It parses the proof, finds the Bitcoin attestation, and then does the part that
matters: it checks the committed value against the **real merkle root of the block at that height**, fetched from
two independent explorers, and requires the block to be buried under ≥ 6 confirmations. A structurally valid proof
that does not match the chain is *not* accepted.

```bash
npm i @ust-protocol/ots-verify      # zero dependencies — check `npm ls` if you like
node -e '
import("@ust-protocol/ots-verify").then(async ({ makeSubstrateVerify }) => {
  const fs = await import("node:fs");
  const doc = JSON.parse(fs.readFileSync("transcript.ust.json", "utf8"));
  const ots = fs.readFileSync("hour-root.ots").toString("base64");
  const r = await makeSubstrateVerify()({ substrate: "bitcoin-ots", ots }, doc.proof.root);
  console.log(r);
});'
```

Expected:

```
{ final: true, time: "2026-08-29T13:38:38Z", block_height: "964576",
  assurance: "explorer-corroborated", explorers: 2 }
```

`assurance: explorer-corroborated` is deliberately not called *Bitcoin finality*: two explorers agreeing is a
weaker statement than a PoW-validated header chain, and the connector names its own ceiling rather than inflating
it. Point it at your own node and it says so differently.

**Cross-check with an independent implementation**, if you want the proof read by something that is not ours:

```bash
pip install --quiet opentimestamps-client
ots info hour-root.ots        # shows the BitcoinBlockHeaderAttestation and its height
```

And the block itself, from any explorer:

```bash
curl -s https://blockstream.info/api/block-height/964576 \
  | xargs -I{} curl -s https://blockstream.info/api/block/{} \
  | python3 -c "import json,sys,datetime; b=json.load(sys.stdin); print('height', b['height']); print('time  ', datetime.datetime.utcfromtimestamp(b['timestamp']).isoformat()+'Z'); print('merkle', b['merkle_root'])"
```

## Why this folder exists at all, and not just a pointer to the proofs file

The `anchor.ots` inside `transcript.ust.json` is the **upgraded** proof. The copy embedded in
`anchors/2026/08/29/12.ust1.proofs.json` is the same timestamp as it stood at publication time — *pending*, with
no Bitcoin attestation yet. Upgrading writes a separate file (`12.ust1.root.ots`) and does not rewrite the
published proofs file.

**And it never will.** Measured 2026-08-30 across the journal: **398 of 398** published `*.proofs.json` files
still carry a pending anchor — not one has been upgraded in place, including hours whose root reached Bitcoin
weeks ago. So a reader who assembles a document straight from the proofs file gets `unproven / pending` today and
gets it a year from now. That is a correct verdict about those bytes — pending is a true state, not a failure —
but it is not the whole evidence the operator holds, and nothing in the file says where the rest of it lives.

That gap is the reason this folder exists: it pairs the transcript with the proof that *is* final, so the walk to
Bitcoin can be completed by someone who has never spoken to us. The underlying fix belongs on the operator side —
either the proofs file carries the upgraded anchor, or it points at the file that does.

This is the ordinary shape of Bitcoin anchoring in practice: the cryptography was never the hard part; batching,
calendars, upgrades and where the upgraded bytes end up are.
