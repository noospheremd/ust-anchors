# -*- coding: utf-8 -*-
"""Stamp the MERKLE ROOT, not the anchor file.

Why this script exists instead of `ots stamp <file>`.

The registered `bitcoin-ots` substrate requires the proof to attest the ROOT: the connector checks
`ots.timestamp.msg == bytes.fromhex(root)`. `ots stamp` always hashes the FILE it is given, so every stamp
this repository holds attests `sha256(anchor.json)` — real, Bitcoin-backed, and rejected by the verifier as
"not mine". Measured 2026-08-06: 1033 stamps, 1031 Bitcoin-attested, zero hours conformant.

There is no CLI flag for this: `ots stamp` takes files only, and no file can hash to a chosen root (that
would be a preimage). So the DetachedTimestampFile is built over the digest directly, which is what
"stamping a digest" means in OTS, and everything else — nonce per entry, one Merkle tree per batch, one
submission per calendar — is kept identical to the client's own `stamp_command`.

TWO THINGS THIS SCRIPT REFUSES TO DO.

1. It does not stamp anchors before BOUNDARY. Re-stamping the historical set would mint conformant-looking
   proofs dated today over hours that were never anchored properly, drawing a continuous record that did not
   happen. Owner's decision, 2026-08-06: the past is not rewritten; it is fixed FORWARD.

2. It writes `<anchor>.root.ots`, never `<anchor>.json.ots`. The two kinds of proof cannot share a name
   while both exist in the tree — a consumer holding one must be able to tell what it attests, and the
   boundary between the two eras must be visible in the filesystem rather than only in prose.
"""

import json
import os
import sys
from pathlib import Path

from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp, make_merkle_tree
from opentimestamps.core.op import OpAppend, OpSHA256
from opentimestamps.core.serialize import BytesSerializationContext
from otsclient.cmds import create_timestamp

# The first hour whose ROOT is stamped. Anchors before it keep their file-stamps and are described by what
# those actually prove: the file existed, not the root.
BOUNDARY = os.environ.get('ROOT_STAMP_BOUNDARY', '2026/08/06/10')
CHUNK = int(os.environ.get('ROOT_STAMP_CHUNK', '250'))

CALENDARS = [
    'https://a.pool.opentimestamps.org',
    'https://b.pool.opentimestamps.org',
    'https://a.pool.eternitywall.com',
    'https://ots.btc.catallaxy.com',
]


class Args:
    calendar_urls = CALENDARS
    calendar_whitelist = None
    timeout = 5
    m = 2
    btc_wallet = False
    wait = False
    # create_timestamp reads these two by name; absent, it raises AttributeError rather than defaulting.
    use_btc_wallet = False
    setup_bitcoin = False


def hour_key(path: Path) -> str:
    """anchors/2026/08/06/12.json -> 2026/08/06/12 — comparable as a string because the parts are padded."""
    return '/'.join(path.parts[-4:-1] + (anchor_stem(path),))


def anchor_stem(path: Path) -> str:
    """The HOUR a file belongs to, with every companion suffix removed.

    `12.json`, `12.ust1.json` and `12.ust1.proofs.json` all belong to hour 12. `Path.stem` gives `12`, `12.ust1`
    and `12.ust1.proofs`, which sort fine but are not hours: `int('12.proofs')` raises, and the freshness check
    below did exactly that on every proofs file it met.
    """
    return path.name.split('.', 1)[0]


# EVERY `*.json` UNDER `anchors/` BELONGS TO EXACTLY ONE DECLARED CLASS.
#
# This sweeper walks a DIRECTORY, so a new artifact type joins its domain on the day something starts writing
# one — no edit here, no review, no warning. Measured 2026-08-14: `*.proofs.json` began appearing on
# 2026-08-12T15:02Z, every `ots` run since refused the entire journal, and because the refusal returns before the
# stamping and the upgrade steps, pending OTS attestations went 38 hours without an upgrade. Nothing was wrong
# with the anchors; an unknown shape was read as a malformed one.
#
# Classifying is not filtering. A named companion is counted and skipped; a file the roster does NOT name is
# still refused out loud, so the next new type stops the sweeper rather than being silently stamped or silently
# ignored. The roster is here, in one place, read by both the stamper and the freshness check.
ANCHOR, COMPANION = 'anchor', 'companion'


def classify(path: Path):
    """(class, digest, why-refused) — exactly one of the first two is set, or the third is."""
    try:
        doc = json.loads(path.read_text())
    except Exception as e:                                        # noqa: BLE001 — report, never guess
        return None, None, f'unreadable JSON: {str(e)[:60]}'

    if path.name.endswith('.proofs.json'):
        # An inclusion-path bundle: the paths it carries run under a root that the anchor beside it already
        # commits. Stamping this file would attest that THE FILE existed — the weaker claim this whole tool
        # exists to stop being mistaken for a root proof.
        if isinstance(doc, dict) and 'root' in doc and 'proofs' in doc:
            return COMPANION, None, None
        return None, None, 'a .proofs.json carrying no `root` and `proofs` is not an inclusion bundle'

    if isinstance(doc, dict) and 'merkle_root' in doc:
        try:
            digest = bytes.fromhex(str(doc['merkle_root']).replace('sha256:', ''))
        except Exception as e:                                    # noqa: BLE001
            return None, None, str(e)[:80]
        if len(digest) != 32:
            return None, None, 'root is not 32 bytes'
        return ANCHOR, digest, None

    return None, None, ('no `merkle_root`, and the name matches no declared companion — '
                        'add it to the roster in classify() or fix the producer')


def collect(base: Path):
    todo, skipped_old, skipped_done, companions, bad = [], 0, 0, 0, []
    for p in sorted(base.rglob('*.json')):
        if p.name.endswith('.ots'):
            continue
        if hour_key(p) < BOUNDARY:
            skipped_old += 1
            continue
        kind, digest, why = classify(p)
        if why is not None:
            bad.append((p, why))
            continue
        if kind is COMPANION:
            companions += 1
            continue
        if p.with_suffix('.root.ots').exists() or Path(str(p)[:-5] + '.root.ots').exists():
            skipped_done += 1
            continue
        todo.append((p, digest))
    return todo, skipped_old, skipped_done, companions, bad


def stamp(batch):
    """One Merkle tree over the batch, one submission per calendar — the property that made the backlog affordable."""
    detached, roots = [], []
    for _, digest in batch:
        d = DetachedTimestampFile(OpSHA256(), Timestamp(digest))
        # A nonce per entry: the proofs get separated later, and without it one would leak its neighbours'
        # digests. Same reasoning as the client's own.
        nonced = d.timestamp.ops.add(OpAppend(os.urandom(16)))
        roots.append(nonced.ops.add(OpSHA256()))
        detached.append(d)
    create_timestamp(make_merkle_tree(roots), CALENDARS, Args())
    return detached


def check(base: Path, slack_hours: float) -> int:
    """Assert every anchor past BOUNDARY carries a root proof, and say so out loud when it does.

    This lives HERE rather than in the workflow's shell for two reasons. The boundary and the `.root.ots`
    naming are then written once, so the producer and the gate cannot drift apart. And the first attempt at
    writing it in bash measured NOTHING on the author's machine — `globstar` is bash 4+, `date -d` is GNU —
    and printed a green verdict over an empty loop. A gate that examines zero items and passes is the failure
    mode this whole file exists to close.
    """
    import datetime as dt

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=slack_hours)
    total = stamped = stale = companions = 0
    unknown = []
    for p in sorted(base.rglob('*.json')):
        if p.name.endswith('.ots') or hour_key(p) < BOUNDARY:
            continue
        # The SAME roster the stamper uses. Before 2026-08-14 this loop counted every companion as an anchor
        # owing a root stamp, so `stamped/total` understated coverage — and then it crashed, because a companion
        # stem is not an hour: `int('14.proofs')` raises, and a freshness check that raises returns no verdict.
        kind, _, why = classify(p)
        if why is not None:
            unknown.append((p, why))
            continue
        if kind is COMPANION:
            companions += 1
            continue
        total += 1
        if Path(str(p)[:-5] + '.root.ots').exists():
            stamped += 1
            continue
        y, m, d, h = hour_key(p).split('/')
        when = dt.datetime(int(y), int(m), int(d), int(h), tzinfo=dt.timezone.utc)
        if when < cutoff:
            stale += 1
            if stale <= 5:
                print(f'  NO ROOT STAMP: {p}')

    print(f'root stamps since {BOUNDARY}: {stamped}/{total} · {stale} older than {slack_hours}h unstamped '
          f'· {companions} declared companion(s) skipped')
    if unknown:
        for p, why in unknown[:5]:
            print(f'  UNCLASSIFIED {p}: {why}')
        print(f'::error::{len(unknown)} file(s) under anchors/ match no declared class — the roster in '
              f'classify() no longer describes what is being written, and a sweeper that cannot name a file '
              f'must not decide whether it needs a proof')
        return 1
    if stale:
        print(f'::error::{stale} anchor(s) past the boundary carry no ROOT stamp — bitcoin-ots attests the '
              f'root, so those hours are NOT conformant however many file stamps they hold')
        return 1
    if total == 0:
        # Zero examined is not a pass. Past the boundary there is always at least the current hour, so an
        # empty roster means the roster is broken, not that the tree is clean.
        print('::error::no anchor found past the boundary — the enumeration is broken, not the tree clean')
        return 1
    print('OK — every anchor past the boundary carries a root stamp')
    return 0


def main():
    base = Path('anchors')
    if '--check' in sys.argv:
        if not base.is_dir():
            print('anchors/ not found', file=sys.stderr)
            return 1
        return check(base, float(os.environ.get('ROOT_STAMP_SLACK_H', '3')))
    if not base.is_dir():
        print('anchors/ not found — run from the root of the anchor journal', file=sys.stderr)
        return 1

    todo, skipped_old, skipped_done, companions, bad = collect(base)
    print(f'boundary              {BOUNDARY}')
    print(f'before boundary, skipped {skipped_old}')
    print(f'already stamped       {skipped_done}')
    print(f'declared companions   {companions}')
    print(f'to stamp              {len(todo)}')
    for p, why in bad:
        print(f'  REFUSED {p}: {why}')
    if bad:
        return 1
    if not todo:
        return 0

    written = 0
    for i in range(0, len(todo), CHUNK):
        batch = todo[i:i + CHUNK]
        print(f'stamping {len(batch)} roots in one call')
        for (p, digest), d in zip(batch, stamp(batch)):
            ctx = BytesSerializationContext()
            d.serialize(ctx)
            out = Path(str(p)[:-5] + '.root.ots')
            out.write_bytes(ctx.getbytes())
            # Read back what was written — a serializer that produced the wrong msg would otherwise be
            # discovered hours later, by a verifier, on a proof already committed to the repository.
            from opentimestamps.core.serialize import BytesDeserializationContext
            back = DetachedTimestampFile.deserialize(BytesDeserializationContext(out.read_bytes()))
            if back.timestamp.msg != digest:
                print(f'  REFUSED {out}: the written msg is not the root', file=sys.stderr)
                return 1
            written += 1

    print(f'root stamps written: {written}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
