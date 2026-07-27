# `ust-protocol/` — the reserved namespace for UST discovery mirrors

One directory per **publisher**, named by its `domain_shard`; inside it, the discovery
artifacts under the names they carry at the origin:

```
ust-protocol/
  <domain_shard>/
    ust-genesis     ← byte-identical to https://<domain_shard>/.well-known/ust-genesis
    ust-keylog
    ust-cadence
    ust-witness
```

**Why publisher-first.** A mirror host may serve several publishers, and grouping by
artifact type (`mirror/genesis/`, `mirror/witness/`) collides on the first neighbour.
Grouping by publisher is collision-free by construction, and the path reads one-to-one
with the origin it mirrors — a verifier needs no second mental model.

**Why a reserved prefix.** This repository may hold anything else; one reserved name
keeps UST artifacts from ever colliding with it.

**What a mirror is, and what it is not.** §20.1 vendor-independence is about
AVAILABILITY: if the canonical vendor goes down, the identity stays fetchable. It is
NOT a second opinion — the `content_hash` decides, and a mirror serving different bytes
is a FAILURE, not a partial success. These bytes must be byte-identical to the origin,
served anonymously, with no transformation.

This layout is a CONVENTION, not a normative requirement. §20.1 attests properties, not
mechanisms, and deliberately fixes no hosting layout — `--mirror` accepts any URL that
returns the right bytes.

Attest it:

```
npx @ust-protocol/cli@next discovery <domain_shard> \
  --mirror https://raw.githubusercontent.com/noospheremd/ust-anchors/main/ust-protocol/<domain_shard>/ust-genesis
```
