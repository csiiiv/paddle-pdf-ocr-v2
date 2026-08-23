# Prior-work migration ledger

**Purpose:** Prevent v2 from rediscovering settled decisions or discarding
working behavior from `paddle_ocr`, `pdf_ocr`, and `paddle_pdf_ocr`.

**Classifications**

- **PRESERVE:** supported by prior evidence; port/reuse unless new evidence
  demonstrates a regression.
- **RETEST:** promising or partially validated; must pass retained v2 gates.
- **REPLACE:** known design failure; preserve only its test cases and lessons.
- **HISTORICAL:** useful context, not a current design requirement.

## 1. Extraction and geometry

| Finding | Class | Evidence | V2 consequence |
|---------|-------|----------|----------------|
| Paddle is the only v2 text source | **PRESERVE** | V1 used 359,153 Paddle tokens; all 5 PDF replacements were later rejected | Paddle-only extraction; the PDF is rasterized but embedded text is ignored |
| PDF/Acrobat fallback is out of v2 scope | **REPLACE/deferred** | V1 attempted only 5 replacements across 672 pages and source review rejected all five | No PDF-text layer, merge dependency, viewer control, or runtime command |
| PDF embedded-font decoding is often malformed | **HISTORICAL** | `ACTIVffiES`, `ACTIVmES`; Paddle produced `ACTIVITIES` | Retain as rationale for the Paddle-only decision, not as a live comparison stage |
| Paddle fixes Acrobat mega-blocks and common OCR dirt | **PRESERVE** | `paddle_ocr/docs/edge-compare.md`: p.8 regions, `!locos`, comma spacing; p.688 money letters | Port word/line Paddle parsing and retain the cited pages as gold |
| Paddle can drop rare numeric wraps | **RETEST** | Historical p.247 claim was disproven by v2 source-raster review; other continuation risks remain | Hybrid hole probes still include chainage/GPS cases, but do not cite p.247 as a Paddle omission |
| 200 DPI is the production default | **PRESERVE** | ADR-007: 150 DPI saved ~5% but lost rows at p.480 | Do not retune DPI without fidelity evidence; default 200 |
| OCR, layout, and cell detection are separate models | **PRESERVE** | Pipeline modules M3/M4/M5; layout/cells add signals OCR cannot derive | Separate layers and invalidation; do not treat one Paddle call as the pipeline |
| LayoutDetection is valuable for multi-zone pages | **PRESERVE** | p.8, 108, 109 zones; p.13 lattice uses layout + cells | Port after OCR with viewer overlays and zone fixtures |
| Table cells matter chiefly on lattice/By-OU pages | **PRESERVE** | p.13 cells; measured PAP savings; `--tables-pages 13-108` | Do not burn cell model across PAP by default |
| Cell boxes can precede merge; cell text cannot | **PRESERVE** | Pipeline modules open question M5/M6 | Separate cell geometry from text fill in the contract |
| Raw Paddle prediction capture may aid parser migration | **RETEST** | Pipeline modules open question | Capture bounded parser fixtures for selected pages, not necessarily every volume page |

### Historical fallback baseline — closed

The five v1 PDF replacements are evidence, not automatically correct gold:

| Page | V1 replacement | Classification |
|-----:|----------------|----------------|
| 138 | `100` ← `15!100,000`, normalized `15,100,000` | **REJECTED**: source and Paddle already read `15,100,000`; PDF injected `!` |
| 147 | bullet `.` ← `!`, final `3!` | **REJECTED**: source and Paddle read `3.`; PDF corrupted the bullet |
| 149 | `000` ← `21!0001000`, normalized `21,000,000` | **REJECTED**: source and Paddle already read `21,000,000`; PDF was malformed |
| 247 | `424` ← `4?4`, then `?`→`7` produced `474` | **REJECTED** after 600-DPI source-raster review: source reads `424`; Paddle was correct and v1 introduced the error |
| 480 | label `1-` ← `!-` | **REJECTED**: source and Paddle read `District 1-`; PDF substituted `!` |

All five replacements were rejected by source-raster review. V2 must not
reproduce them. PDF fallback is out of scope under ADR-002; the archived
`HYBRID_FALLBACK_PLAN.md` retains analysis only.

## 2. Schema, zones, and routing

| Finding | Class | Evidence | V2 consequence |
|---------|-------|----------|----------------|
| Geometry/schema mode replaces Kind as builder router | **PRESERVE** | ADR-001 and cross-volume smoke | Use `lattice`, `amount_anchored`, `years`, `prose`, `passthrough`; Kind may be a QA label only |
| Multi-zone pages cannot have one page-wide builder | **PRESERVE** | p.8, 108, 109 fixtures | Infer and build per zone; retain zone identity in output |
| Prose mentioning money/OU terms must remain prose | **PRESERVE** | p.11 special-provision failure | Prose evidence can override superficial currency/OU cues |
| Thin continuation pages need schema carry | **PRESERVE** | By-OU p.14 and PAP p.116 G3 results | Carry only through contiguous ascending pages |
| `years`, `prose`, and `passthrough` policies were incomplete in v1 builders | **RETEST** | v1 inference emitted modes but builders mainly handled lattice/PAP | V2 must explicitly build, pass through, or flag unsupported output; never silently empty |
| Volume-specific Kind A–J routing | **HISTORICAL** | `pdf_ocr` taxonomy; superseded by ADR-001 | Retain edge cases and semantics, not router taxonomy |

## 3. Row construction

| Finding | Class | Evidence | V2 consequence |
|---------|-------|----------|----------------|
| Amount-top bands are the correct PAP row anchor | **PRESERVE** | p.452 deep wraps; `pdf_ocr/docs/edge-cases.md`; G1 | Port amount-anchored builder before redesigning it |
| Numeric continuation lines are structural label content | **PRESERVE** | p.195 chainage, p.247 source `424`, p.680 GPS | Preserve `K/C` and digit-only continuation cases; a `?` remains uncertainty, not an automatic `7` |
| First prose token, not bullet or wrap, defines indent | **PRESERVE** | v1 prose-indent tests: numeric/letter bullets, A.H./P. initials, leftward wraps | Port tests and geometry behavior unchanged initially |
| PAP rows need inline money probes | **PRESERVE** | `pdf_ocr` missing-amount lesson | Ensure inline amounts feed amount anchoring |
| Lattice amounts require column roles and row-sum QA | **PRESERVE** | p.13 exact compare; money repair and G0 | Port money geometry and verify PS/MOOE/CO/Total relationships |
| PREXC must not become a money column | **PRESERVE** | `is_money_value` no-comma rule | Retain as a hard fixture |
| Currency prefix `P` can be glued to amounts | **PRESERVE** | p.114 COE/Kind E | Strip prefix before amount parsing |
| Units are semantic, not always pesos | **PRESERVE** | staffing counts; thousand-peso continuation p.109 | Carry/infer `staff_count`, `thousand_pesos`, `pesos` explicitly |
| FAP `GOP` / `Loan Proceeds` gutter is funding metadata | **PRESERVE** | p.688 edge case | Fold into prior row `funding[]`; do not emit hierarchy nodes |
| Row output was generally effective but not comprehensively proven | **RETEST** | G0/G1 partial gold, viewer use, no broad automated suite | Port before rewrite, then validate gold plus contiguous slices |

## 4. Domain semantics

| Finding | Class | Evidence | V2 consequence |
|---------|-------|----------|----------------|
| Raw OCR and normalized values must coexist | **PRESERVE** | `label_ocr`, patch reasons, amount repair metadata | Never normalize destructively without provenance |
| Title, description, chainage, and GPS are distinct fields | **PRESERVE** | G1b: p.195 title `Maharlika Highway (LZ)`, 3 chainages | Hierarchy consumes the title, not the full OCR blob |
| Anatomy depends on correct row attachment | **PRESERVE** | Gate order G1 → G1b | Do not use anatomy to mask attachment failures |
| Normalize/enrich before DSC; DSC last | **PRESERVE** | `pdf_ocr` DSC rehydration failure | Preserve step ordering if DSC is enabled |
| Domain steps need named dependencies and recorded execution | **PRESERVE** | ADR-005 registry | V2 may simplify API but keeps dependency validation and run metadata |
| DSC dictionary quality is not a blocking v2 concern | **HISTORICAL/deferred** | v1 test plan out of scope | Keep optional and out of core migration gates |

## 5. Carry and orchestration

| Finding | Class | Evidence | V2 consequence |
|---------|-------|----------|----------------|
| Carry is valid only for `page == previous + 1` | **PRESERVE** | G3 and pipeline rebuild guide | One sequence state machine; gaps reset all schema/stitch/hierarchy carry |
| Sequential stages must run in ascending order | **PRESERVE** | M8/M10/M11 behavior | Reject nonascending commits |
| Resume must walk/hydrate skipped carry | **PRESERVE** | v1 consistency defect found during audit | Resume validates and reconstructs state; never simply skips sequential artifacts |
| GPU layers should be independently reusable | **PRESERVE** | ADR-002 iteration experience | V2 keeps layered artifacts even though fresh reburn is acceptable |
| 4 GB GPU requires tier barriers and one worker | **PRESERVE** | ADR-003; 2.7–3.0 GB/model measured | Do not parallelize mixed models or duplicate a tier on GTX 1650 |
| Direct JSON writes and marker-only resume | **REPLACE** | v1 interruption risk | Atomic writes plus content/dependency validation |
| Four overlapping orchestrators | **REPLACE** | v1 audit | One package pipeline; thin CLI only |
| Structured JSON duplicated inside extract | **REPLACE** | stale embed/viewer reconciliation | One owner per stage; persisted pre-hierarchy rows and final hierarchy separately |

## 6. Hierarchy

| Finding | Class | Evidence | V2 consequence |
|---------|-------|----------|----------------|
| Hierarchy begins only after row attachment and anatomy | **PRESERVE** | Gate order G1/G1b → G2 | Persist pre-hierarchy rows as the engine input |
| Amount-relative coordinate `u` reduces page shift/skew | **PRESERVE feature** | ADR-008 | Reuse as observation evidence |
| First-line prose indent is the structural measurement | **PRESERVE feature** | tests and ADR-009 | Carry confidence/provenance with the observation |
| Column order is monotonic across pages | **PRESERVE feature** | ADR-009 | Ordered alignment, never crossing greedy matches |
| Missing shallow levels can survive as ghost parents | **PRESERVE feature** | v1 ghost-column tests | Retain bounded ghost evidence in track state |
| Local column, persistent track, and semantic level differ | **PRESERVE conclusion** | ADR-009 repeated-revision analysis | Separate fields and contracts |
| Confidence QA is not canonical hierarchy truth | **PRESERVE** | ADR-006 | Confidence flags review; structural gold/collation decides correctness |
| Continuous indent likelihood/page bias | **REPLACE** | p.134 runaway to L24, ADR-004 superseded | Keep failure case; do not revive model unchanged |
| Page-local gap clusters + greedy stack | **REPLACE** | repeated radius revisions; dense/thin page failures | Joint sequence inference is experimental candidate |
| Fixed 12 pt cross-page snap floor | **REPLACE/RETEST** | symptom tuning, midpoint ambiguity | Track uncertainty and ordered matching; retain 8–12 pt drift case |
| Existing hierarchy is production-proven | **FALSE** | G6: 8 By-OU level jumps; PAP incomplete coverage; confidence has 1,518 review rows | V1 is baseline only, not gold |

### Exact hierarchy baseline

- Confidence run: 14,458 PAP rows; 12,940 accept; 1,518 review; 0 reject.
  This measures column-fit confidence, **not parent accuracy**.
- Full By-OU assembly: 96/96 pages, 1,897 rows, 8 `level_jump` issues.
- PAP assembly: 501/576 pages present, 14,458 rows, 75 missing pages and 36
  `page_gap` issue groups. This cannot establish full PAP hierarchy accuracy.
- Sparse multipage smoke passed 13→14 and 115→116, but the smoke G6 report
  correctly failed full-span coverage. Do not describe that artifact as full G6
  success.

## 7. QA and viewer practice

| Finding | Class | Evidence | V2 consequence |
|---------|-------|----------|----------------|
| Viewer is a primary troubleshooting instrument | **PRESERVE** | v1 PDF overlays, Rows, Tree, QA panels | Ship viewer with stages, not after pipeline completion |
| At least two views must agree | **PRESERVE** | v1 Test Plan multi-view rule | Script/JSON plus spatial/tree evidence per gate |
| Page-local rows can look fine while table hierarchy is wrong | **PRESERVE** | v1 table-scale review | Collated contiguous table is mandatory for hierarchy promotion |
| QA JSON is retained under each run | **PRESERVE** | `pdf_ocr/output/*/qa`, v1 viewer | Every gate writes detailed and summary JSON consumed by viewer |
| Unit tests prove named invariants, not extraction accuracy | **PRESERVE** | hierarchy baseline warning | Never report a pass count as fidelity proof |
| Full-volume burn before G0–G6 | **REPLACE** | hard rule in v1 Test Plan | Gold → slices → cross-volume → full volume |

## 8. Canonical regression pages

The machine-readable form is [`../fixtures/migration_gold.json`](../fixtures/migration_gold.json).

| Page | Required observation |
|-----:|----------------------|
| 8 | Multi-zone; Paddle splits regional mega-label; clean Ilocos/IVB; money commas |
| 11 | Dense special-provision prose must not become a money table |
| 13 | By-OU lattice; cells; four money roles; row-sum fidelity |
| 14 | Lattice continuation with schema/column/hierarchy carry |
| 29 | Only CO+Total occupied without role collapse |
| 108 | Multi-zone lattice + years boundary |
| 109 | Years/prose/passthrough; thousand-peso inheritance |
| 114 | COE lattice and glued `P` currency |
| 115–116 | PAP start/continuation and carry |
| 134 | Large leftward hierarchy transition; historical L24 failure |
| 138,147,149 | Preserve correct Paddle values; historical PDF patches rejected |
| 195 | Chainage wrap attachment and title/anatomy split |
| 247 | Source raster reads `424`; preserve Paddle `424`; reject historical PDF `4?4` and `?`→`7` patch |
| 446 | Kilometer/station noise context |
| 452 | Deep wrap stays with prior amount-top row |
| 480 | 150-DPI row loss; preserve `District 1-`; historical PDF patch rejected |
| 680 | GPS digit-only continuation |
| 688 | FAP funding gutter fold and Paddle money-letter advantage |

## 9. Source hierarchy

When documents conflict, prefer evidence in this order:

1. Reviewed PDF + viewer disposition tied to a page/row.
2. Retained QA JSON from a representative contiguous run.
3. Gold fixture assertion with cited source.
4. Accepted/superseding ADR.
5. Current implementation behavior.
6. Historical plan prose.

This prevents stale status tables or high confidence counts from overriding a
known visual or table-scale failure.
