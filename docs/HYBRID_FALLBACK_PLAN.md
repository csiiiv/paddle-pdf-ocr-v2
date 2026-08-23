# PDF fallback safety plan

**Status:** Archived/deferred; PDF fallback is out of v2 scope  
**Recorded at:** 2026-08-23T07:38:01+08:00  
**Timestamp source:** reconstructed from document modification time

## Decision

As of the subsequent simplification decision, v2 assumes no PDF OCR/text
fallback at all. This document retains the safety analysis only. None of the
candidate or patch stages below are planned for implementation unless the
project explicitly reopens fallback scope.

PDF/Acrobat text is diagnostic evidence and a source of review proposals. It
must never replace overlapping Paddle text automatically.

This supersedes v1's `pdf_ocr_crumb_replace` behavior. Source-raster review of
all five historical replacements found that Paddle was already correct and the
PDF replacement was degraded:

| Page | Source/Paddle | PDF proposal | Disposition |
|-----:|---------------|--------------|-------------|
| 138 | `15,100,000` | `15!100,000` | reject |
| 147 | `3.` | `!` | reject |
| 149 | `21,000,000` | `21!0001000` | reject |
| 247 | `424` | `4?4`, later `474` | reject |
| 480 | `District 1-` | `!-` | reject |

The retained decisions live in `fixtures/pdf_patch_reviews.json` and
`output/extraction-smoke/qa/pdf_patch_review.json`.

## Failure modes learned from prior work

1. Presence of `!` or `?` was treated as evidence that PDF text was better.
   It was actually evidence of malformed PDF OCR.
2. Nearby numeric matching replaced high-confidence Paddle tokens rather than
   recovering missing geometry.
3. Later normalization (`?` to `7`) converted uncertainty into invented data.
4. Token-only review hid row context; expanded source-raster crops showed that
   Paddle's complete line was already correct.
5. Aggregate patch counts made rare mutations look useful without measuring
   whether any mutation was correct.

## Safer architecture

Keep three separate products:

1. `layers/pdf/`: immutable fallback evidence.
2. `qa/pdf_patch_candidates.json`: proposals only, never canonical text.
3. `extract/`: Paddle-first canonical text; reviewed patches are explicit
   allowlisted transforms with provenance, if a valid case is ever found.

Candidate generation may report a possible *insertion* only when all conditions
hold:

- the PDF box has negligible overlap with every Paddle token and line;
- it lies inside an active non-chrome region;
- neighboring Paddle lines provide a structural continuation context;
- the candidate is not merely punctuation or an ambiguous OCR glyph;
- normalized duplicates are absent nearby;
- the candidate records page, box, PDF text, context, and rejection reasons.

Candidate generation must not mutate artifacts. Overlapping disagreements are
reported separately and default to Paddle.

## Promotion gates

### Gate F0 — deterministic proposal generation

- Synthetic geometry tests cover overlap, duplicate, chrome, and ambiguity.
- Identical layer fingerprints produce identical proposals.
- No proposal code has access to canonical write paths.

### Gate F1 — reviewed gold

- Every proposed insertion on the migration pages is reviewed against the
  source raster with row context.
- Precision must be 100% on the reviewed set; false positives are more harmful
  than missed optional fallback candidates.
- A review records `accept`, `reject`, or `unknown`; `unknown` never mutates.

### Gate F2 — representative slices

- Run proposal-only detection on contiguous By-OU and PAP slices.
- Retain candidate counts, reasons, and viewer links.
- Confirm zero changes to canonical extract hashes.

### Gate F3 — optional explicit patching

Only if F1 finds a real missing Paddle fragment may an allowlisted patch stage be
implemented. It must:

- identify the reviewed case by input fingerprint and bounded geometry;
- insert rather than overwrite clean overlapping Paddle text;
- preserve raw PDF text separately from reviewed normalized text;
- record reviewer, evidence, reason, and affected token/line IDs;
- fail closed when fingerprints or geometry differ.

## Stop conditions

Do not implement automatic canonical patching if:

- the reviewed candidate set contains no true Paddle omissions;
- proposal precision is below 100% on gold;
- the source cannot resolve the glyph;
- downstream normalization is required to guess a digit;
- a patch changes an amount, code, station, bullet, or identifier without an
  explicit reviewed value.

Given current evidence—zero valid replacements out of five—v2 remains
Paddle-only canonically. The next useful work is proposal diagnostics, not merge
mutation.
