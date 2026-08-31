# Cross-implementation check — four OpenTimestamps readers, one Bitcoin block

Run 2026-08-31 in throwaway containers, against `hour-root.ots` in this folder. Every command below is reproducible
by anyone with Docker; nothing was run on a machine of ours that had anything configured.

**The point is not that our verifier says `final: true`.** It is that three independent implementations, written by
different people in different languages, read the same bytes and name the same Bitcoin block — and that we
publish the one place where the walkthrough did *not* work.

| implementation | language | what it read | verdict |
|---|---|---|---|
| `@ust-protocol/ots-verify` 1.0.0-rc.35 (ours, zero deps) | JS | `hour-root.ots` | `final: true`, block **964576**, `explorer-corroborated`, 2 explorers |
| `opentimestamps-client` 0.7.2 (reference) | Python | same file | `BitcoinBlockHeaderAttestation(964576)` |
| `opentimestamps` 0.4.9 (unmaintained) | JS | same file | `BitcoinBlockHeaderAttestation(964576)` |
| `@otskit/core` (new, 2026) | TypeScript | same file | digest parsed, matches `proof.root` |

All four read the same digest: `46e1836310ebac22174e12681daef063a65c52fa8770fafe2605b8b88c713e14` — which is
exactly the `proof.root` inside `transcript.ust.json`.

## 1 · Ours, from a clean `node:22`

```bash
docker run --rm -it node:22 bash
npm init -y && npm install @ust-protocol/ots-verify
#   added 1 package, and audited 2 packages
#   found 0 vulnerabilities
curl -sSL -O https://raw.githubusercontent.com/noospheremd/ust-anchors/main/public-proof/transcript.ust.json
curl -sSL -O https://raw.githubusercontent.com/noospheremd/ust-anchors/main/public-proof/hour-root.ots
node -e '
import("@ust-protocol/ots-verify").then(async ({ makeSubstrateVerify }) => {
  const fs = await import("node:fs");
  const doc = JSON.parse(fs.readFileSync("transcript.ust.json", "utf8"));
  const ots = fs.readFileSync("hour-root.ots").toString("base64");
  console.log(await makeSubstrateVerify()({ substrate: "bitcoin-ots", ots }, doc.proof.root));
});'
```

```
{ final: true, time: '2026-08-29T13:38:38Z', block_height: '964576',
  assurance: 'explorer-corroborated', explorers: 2 }
```

## 2 · The reference Python client

```bash
docker run --rm -it python:3.12 bash
pip install opentimestamps-client
curl -sSL -O https://raw.githubusercontent.com/noospheremd/ust-anchors/main/public-proof/hour-root.ots
ots info hour-root.ots
```

```
File sha256 hash: 46e1836310ebac22174e12681daef063a65c52fa8770fafe2605b8b88c713e14
...
verify PendingAttestation('https://alice.btc.calendar.opentimestamps.org')
verify BitcoinBlockHeaderAttestation(964576)
# Bitcoin block merkle root a1b2cfcfaba49f37ccb258b7f7da525ab431be7430e4984b00163ebada79e170
```

## 3 · The unmaintained JavaScript library

Included deliberately: it is the library most JS projects still reach for, and it reads our proof correctly.

```bash
docker run --rm -it node:22 bash
npm init -y && npm install opentimestamps      # note: npm reports vulnerabilities here
node -e '
const OpenTimestamps = require("opentimestamps"), fs = require("fs");
const d = OpenTimestamps.DetachedTimestampFile.deserialize(fs.readFileSync("hour-root.ots"));
console.log("digest:", Buffer.from(d.fileDigest()).toString("hex"));
console.log(OpenTimestamps.info(d).split("\n").find(l => /BitcoinBlockHeader/.test(l)).trim());'
```

```
digest: 46e1836310ebac22174e12681daef063a65c52fa8770fafe2605b8b88c713e14
verify BitcoinBlockHeaderAttestation(964576)
```

## 4 · Where the walkthrough did NOT work, and why that is worth publishing

`ots verify` assumes you are verifying a **file**. Our timestamp is over a **digest** — the hour's Merkle root —
and no file has those bytes as its content, so the obvious command fails:

```
$ ots verify hour-root.ots
Assuming target filename is 'hour-root'
Could not open target: [Errno 2] No such file or directory: 'hour-root'
```

The client does offer `ots verify -d DIGEST`, and that is the correct invocation for a digest timestamp — but it
then requires a **local Bitcoin node**:

```
$ ots verify -d 46e1836310eb…3e14 hour-root.ots
Could not connect to Bitcoin node: Cookie file unusable … rpcpassword not specified
```

Which is the honest state of affairs, and worth stating plainly rather than routing around:

- **`ots info` reads the attestation without trusting anyone** — it parses the proof and tells you which block it
  claims. It does not check that the block is real.
- **`ots verify -d` with your own node is the trustless answer.** If you run a node, that is the check to make.
- **Our `explorer-corroborated` sits between the two**: two independent explorers agreed on the block's merkle
  root and burial depth. Stronger than parsing, weaker than a node, and labelled as such by the connector rather
  than described as "verified".

We would rather show you the command that fails and name the ceiling of the one that succeeds than publish a
walkthrough that only works if you do not look sideways.

## One asymmetry worth knowing if you build on OTS

The reference client can **read** a digest timestamp (`ots verify -d`) but cannot **create** one: `ots stamp` takes
`[FILE ...]` and has no digest option. Anything that commits a Merkle root inside a document — as this journal
does — has to drive the OTS primitives directly to stamp the root rather than the file containing it. Getting that
backwards is not hypothetical: on 2026-08-06 this journal held 1,033 stamps, 1,031 genuinely Bitcoin-attested, and
**zero** attesting the root they were meant to commit. See `tools/stamp-roots.py`.
