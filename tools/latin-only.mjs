// This journal is a PUBLIC surface, so everything written into it is addressed to a stranger: commit
// messages, workflow names, file content. This check enforces that — a letter from a non-Latin script
// anywhere in the surface is a failure.
//
// WHY A LETTER AND NOT "NON-ASCII". Em dashes, typographic quotes and the odd degree sign are punctuation;
// forbidding them would produce noise and, worse, a rule people learn to bypass. The rule that carries the
// intent is about SCRIPT: `\p{L}` outside `\p{Script=Latin}`. Emoji are not letters and pass; a Cyrillic
// commit message does not.
//
// WHAT IT CAN AND CANNOT DO. Writes reach this repository through the contents API, not through a push over
// SSH, so nothing here can REFUSE a write — there is no pre-receive hook to hang it on. This is a detector:
// it turns red after the fact. That is a real limit and it is the reason the check runs on every push rather
// than nightly, so the window between a violation and its being visible is one workflow run.
//
// HISTORY IS NOT RE-JUDGED. One Cyrillic commit message exists, from 2026-08-06, before the rule was stated.
// Rewriting the history of a public journal that consumers may pin costs more than the blemish, so the scan
// starts at BASELINE. A check that no reachable state can satisfy is a check that gets switched off.
//
//   node tools/latin-only.mjs                 scan the working tree and commits since BASELINE
//   node tools/latin-only.mjs <from> <to>     scan a specific commit range (used by CI on push)

import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

/** First commit judged by this rule. Everything before it predates the rule and is left alone. */
const BASELINE = '2026-08-07T00:00:00Z';

/** OpenTimestamps proofs are binary; decoding them as text would produce meaningless matches. */
const BINARY = /\.ots$/;

const NON_LATIN = /\p{L}/gu;
const isLatin = (ch) => /\p{Script=Latin}/u.test(ch);

const git = (...args) => execFileSync('git', args, { encoding: 'utf8', maxBuffer: 1 << 28 });

/** Returns the offending characters, deduplicated, or an empty array. */
function offenders(text) {
  const bad = new Set();
  for (const m of text.matchAll(NON_LATIN)) if (!isLatin(m[0])) bad.add(m[0]);
  return [...bad];
}

const [, , fromArg, toArg] = process.argv;
const failures = [];

// ── commit messages ────────────────────────────────────────────────────────────────────────────────
// On push CI passes the range explicitly; the first push to a new branch reports an all-zero `before`,
// which is not a commit — falling back to BASELINE keeps the check meaningful instead of silently empty.
const zero = /^0{40}$/;
const range = fromArg && toArg && !zero.test(fromArg)
  ? [`${fromArg}..${toArg}`]
  : [`--since=${BASELINE}`];

const log = git('log', '--no-merges', '--format=%H%x00%s%n%b%x01', ...range);
let scanned = 0;
for (const entry of log.split('\x01')) {
  const [sha, message] = entry.replace(/^\n/, '').split('\x00');
  if (!sha || !message) continue;
  scanned++;
  const bad = offenders(message);
  if (bad.length) failures.push(`commit ${sha.slice(0, 8)} — message contains ${bad.join(' ')}: ${message.split('\n')[0].slice(0, 60)}`);
}

// ── file content ───────────────────────────────────────────────────────────────────────────────────
// The whole tree, every time. Restricting this to changed files would make the check depend on which run
// happened to see a file, and a file that entered before the check existed would never be judged at all.
const files = git('ls-files', '-z').split('\0').filter(Boolean).filter((f) => !BINARY.test(f));
for (const f of files) {
  const bad = offenders(readFileSync(f, 'utf8'));
  if (bad.length) failures.push(`file ${f} — contains ${bad.join(' ')}`);
}

console.log(`latin-only: ${scanned} commit message(s), ${files.length} text file(s)`);
if (!scanned && !files.length) {
  console.error('::error::nothing was scanned — an empty enumeration is not a pass');
  process.exit(1);
}
if (failures.length) {
  for (const f of failures) console.error(`::error::${f}`);
  console.error(`\n${failures.length} violation(s). This journal is public: write it in English.`);
  process.exit(1);
}
console.log('OK — Latin script only');
