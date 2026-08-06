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
    return '/'.join(path.parts[-4:-1] + (path.stem,))


def collect(base: Path):
    todo, skipped_old, skipped_done, bad = [], 0, 0, []
    for p in sorted(base.rglob('*.json')):
        if p.name.endswith('.ots'):
            continue
        if hour_key(p) < BOUNDARY:
            skipped_old += 1
            continue
        if p.with_suffix('.root.ots').exists() or Path(str(p)[:-5] + '.root.ots').exists():
            skipped_done += 1
            continue
        try:
            root = json.loads(p.read_text())['merkle_root']
            digest = bytes.fromhex(root.replace('sha256:', ''))
            if len(digest) != 32:
                raise ValueError('root is not 32 bytes')
        except Exception as e:                                    # noqa: BLE001 — report, never guess
            bad.append((p, str(e)[:80]))
            continue
        todo.append((p, digest))
    return todo, skipped_old, skipped_done, bad


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
    total = stamped = stale = 0
    for p in sorted(base.rglob('*.json')):
        if p.name.endswith('.ots') or hour_key(p) < BOUNDARY:
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
                print(f'  БЕЗ КОРНЕВОГО ШТАМПА: {p}')

    print(f'корневые штампы с {BOUNDARY}: {stamped}/{total} · {stale} старше {slack_hours}ч без штампа')
    if stale:
        print(f'::error::{stale} якорь(ей) за границей без КОРНЕВОГО штампа — bitcoin-ots требует аттестации '
              f'корня, поэтому такие часы НЕ конформны, сколько бы файловых штампов у них ни было')
        return 1
    if total == 0:
        # Zero examined is not a pass. Past the boundary there is always at least the current hour, so an
        # empty roster means the roster is broken, not that the tree is clean.
        print('::error::за границей не найдено ни одного якоря — перечисление сломано, а не дерево чисто')
        return 1
    print('ОК — каждый якорь за границей несёт корневой штамп')
    return 0


def main():
    base = Path('anchors')
    if '--check' in sys.argv:
        if not base.is_dir():
            print('нет каталога anchors/', file=sys.stderr)
            return 1
        return check(base, float(os.environ.get('ROOT_STAMP_SLACK_H', '3')))
    if not base.is_dir():
        print('нет каталога anchors/ — запускать из корня репозитория якорей', file=sys.stderr)
        return 1

    todo, skipped_old, skipped_done, bad = collect(base)
    print(f'граница               {BOUNDARY}')
    print(f'до границы, пропущено {skipped_old}')
    print(f'уже отштамповано      {skipped_done}')
    print(f'к штамповке           {len(todo)}')
    for p, why in bad:
        print(f'  ОТКАЗ {p}: {why}')
    if bad:
        return 1
    if not todo:
        return 0

    written = 0
    for i in range(0, len(todo), CHUNK):
        batch = todo[i:i + CHUNK]
        print(f'штампую {len(batch)} корней одним вызовом')
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
                print(f'  ОТКАЗ {out}: записанный msg не равен корню', file=sys.stderr)
                return 1
            written += 1

    print(f'записано корневых штампов: {written}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
