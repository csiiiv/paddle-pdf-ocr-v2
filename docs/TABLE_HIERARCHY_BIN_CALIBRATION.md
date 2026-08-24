# Table Hierarchy Anchor-Distance Calibration

## Purpose

This document records the empirical mapping from a main label phrase's
skew-corrected anchor distance to a provisional row hierarchy level. It is an
input to table assembly, not a replacement for row order, table classification,
or cross-page parent carry.

The measurement is:

```text
rightmost corrected amount anchor x - corrected main-label left x
```

A larger value places the label farther left and generally indicates a higher
hierarchy level. Because both edges use the same rightmost anchor, ordinary
whole-page horizontal movement is largely cancelled.

## Calibration corpus

The initial calibration used `contiguous_spans` from
`fixtures/migration_gold.json` after rebuilding stage `002.10`:

- By-OU candidate span: pages 13–108, 2,282 main-label observations;
- PAP span: pages 115–690, 16,436 main-label observations.

Only `main_text_candidate` phrases with a populated
`relative_anchor.distance_pt` were included. Four-point bins exposed modes;
neighboring bins were then consolidated around empirical medians.

## Matching tolerance

Use a provisional `±4 pt` allowance around a table-local cluster center.
Dominant cluster median absolute deviations are generally below `1 pt`.

Do not assign rows from rounded histogram bins directly: a real cluster can
cross a bin edge. Assign to the nearest table-local center and flag distances
outside tolerance.

### Jitter terminology

- **MAD** measures ordinary within-cluster jitter around the observed median.
- **P05–P95** is the central 90% observed range and is the preferred robust
  range for validating a fitted table-local center.
- **Min–max** retains all observed extremes, including page/table formatting
  shifts and misclassified transition rows. It must not be interpreted as the
  ordinary matching tolerance.

The `±4 pt` allowance applies after fitting or carrying a table-local center.
It does not absorb a whole-table displacement such as page 77's approximately
`−9 pt` shift.

## By-OU profile

| Center | Qualifier | N | Pages | Min | Max | Full range | P05–P95 | MAD | Max deviation | Typical labels | Interpretation |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 453.6 | no code requirement | 1,612 | 94 | 443.39 | 462.26 | 18.87 | 452.11–454.42 | 0.45 | 10.21 | `Engineering Office`, `Central Office` | office/leaf |
| 478.9 | no left-side `code_candidate` | 639 | 96 | 468.74 | 488.47 | 19.73 | 477.33–479.80 | 0.43 | 10.16 | region labels | region/parent |
| 478.5 | left-side `code_candidate` present | 128 | 41 | 457.39 | 503.28 | 45.89 | 476.52–479.47 | 0.46 | 24.75 | program/activity labels | coded program/activity; shared visual level |
| 503.3 | no code requirement | 22 | 3 | 499.48 | 509.35 | 9.87 | 499.88–503.64 | 0.36 | 6.05 | broader categories, including `Bridges` | higher parent; weak support |
| 549.7 | subtotal text | 7 | 4 | 533.68 | 549.95 | 16.27 | 538.32–549.92 | 0.21 | 16.02 | `Sub-total, ...` | subtotal semantic row |
| 578.9 | subtotal text | 2 | 1 | 578.88 | 578.88 | 0.00 | 578.88–578.88 | 0.00 | 0.02 | program/operations subtotals | subtotal semantic row |

The dominant By-OU hierarchy initially has two well-supported levels:
approximately `479 pt` for region parents and `454 pt` for office children.
The qualified 478.5 pt coded row is a semantic subset of the geometric
observations, not an additional non-overlapping geometric cluster.

### Program-code discriminator at the region indent

The approximately `479 pt` visual level is shared by region rows and coded
program/activity rows. It must not be assigned the semantic role `region` from
anchor distance alone.

Across the contiguous By-OU span, 128 main-label rows have a left-side
`code_candidate` retained in the row's `left_of_label_phrase_ids`:

| Evidence | Observed value |
| --- | ---: |
| Coded rows | 128 |
| Distance min–max | 457.39–503.28 pt |
| Distance median | 478.53 pt |
| Rows in rounded 476/480 pt bins | 119 |

Examples include codes such as `100000000000000` and `200000100018000` paired
with program/activity labels. The code is structural metadata and must remain
outside the label text.

Use this precedence when classifying a By-OU row near the shared parent indent:

1. a left-side `code_candidate` classifies the row as a coded
   program/activity row;
2. otherwise region-title evidence can classify it as a region row;
3. anchor distance assigns the shared visual indentation level but does not
   choose between those semantic row types.

Parent-stack behavior can still differ by row type even when the two rows share
the same indentation level. The table stage must therefore retain both
`indent_level` and `row_kind` instead of encoding semantic role directly into
the indent number.

The first two centers have very tight central ranges despite broad min–max
ranges. Their largest negative extremes occur on page 77 and represent a local
formatting displacement, not ordinary phrase jitter. The sparsely supported
far-left centers also contain transition/semantic effects and require review.

Page 77 has an approximately `9 pt` local layout displacement even after
right-anchor normalization. Fit centers per table or formatting regime rather
than comparing every page to one document-wide constant.

Pages around 107–108 transition toward By-Year formatting. They require a
separate table classification before being used as By-OU hierarchy evidence.

## PAP profile

| Center | N | Pages | Min | Max | Full range | P05–P95 | MAD | Max deviation | Typical labels | Interpretation |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 104.7 | 26 | 3 | 103.68 | 105.66 | 1.98 | 104.43–105.23 | 0.10 | 1.02 | `GOP` | funding metadata; excluded from hierarchy |
| 140.5 | 21 | 3 | 139.91 | 146.79 | 6.88 | 140.05–141.03 | 0.30 | 6.29 | `Loan Proceeds` | funding metadata; excluded from hierarchy |
| 391.3 | 11,763 | 522 | 387.72 | 397.08 | 9.36 | 390.02–392.44 | 0.59 | 5.78 | individual projects, roads, locations | leaf |
| 409.0 | 1,980 | 192 | 403.92 | 413.66 | 9.74 | 405.36–410.40 | 0.72 | 5.08 | district offices/intermediate labels | immediate parent |
| 426.6 | 2,073 | 400 | 423.67 | 432.30 | 8.63 | 425.52–428.04 | 0.63 | 5.70 | district engineering offices | parent |
| 448.6 | 465 | 210 | 443.70 | 453.37 | 9.67 | 447.21–449.32 | 0.36 | 4.90 | regions and major subprograms | higher parent |
| 464.8 | 69 | 47 | 461.07 | 467.64 | 6.57 | 463.10–466.56 | 0.64 | 3.73 | road-work categories | higher parent |
| 482.7 | 20 | 15 | 478.68 | 484.56 | 5.88 | 480.59–484.22 | 1.28 | 4.02 | programs | program/root candidate |
| 499.5 | 9 | 8 | 491.74 | 501.84 | 10.10 | 493.67–501.55 | 1.55 | 7.76 | outcomes and major support programs | root candidate |
| 514.6 | 10 | 5 | 513.12 | 516.60 | 3.48 | 513.55–516.07 | 0.54 | 2.00 | expense/support classes | root candidate |

The first four PAP centers have enough support for initial deterministic table
assembly. Farther-left centers should retain review flags until their semantic
roles are confirmed.

PAP's common levels also have narrow robust ranges. Extreme values near pages
507, 678, and 688 should be treated as potential formatting/table transitions
or semantic-class exceptions until reviewed, rather than widening every bin.

## Excluded semantic classes

These aligned labels must not automatically become hierarchy levels:

- `Sub-total` rows: semantic aggregation rows;
- `GOP` and `Loan Proceeds`: funding metadata, observed near 104 and 140 pt;
- page chrome and page numbers: excluded by the 45 pt table top gutter;
- By-Year rows in the pages 107–108 transition.

The phrases remain preserved as geometry evidence when excluded from ordinary
hierarchy inference.

## Table-local hierarchy procedure

1. Determine the table type and formatting regime.
2. Select main label candidates belonging to table body rows.
3. Exclude page chrome, funding metadata, and subtotal semantic rows.
4. Fit local distance centers using the calibrated profile as initialization.
5. Assign each row to its nearest center within `±4 pt`.
6. Rank accepted centers from largest to smallest distance as root to leaf.
7. Build parents using row order and an active parent stack.
8. Carry the active stack across pages until an explicit root reset or table end.
9. Flag unmatched distances, weak centers, illegal hierarchy jumps, and missing
   carry context.

Distance establishes an indentation level. It does not alone prove a semantic
role or parent; those require table type, row order, and carried context.

## Initial table-output requirements

Each output row should retain:

- source page, row section, cell section, phrase, and token IDs;
- table type and table instance ID;
- raw and corrected anchor distance;
- assigned local center and delta;
- provisional indentation level and confidence;
- row kind and its evidence, including a separated program code when present;
- parent row ID and whether the parent was carried from a previous page;
- semantic exclusions such as subtotal or funding metadata;
- associated flag IDs.

This keeps every semantic row traceable to its geometry evidence.

## Implementation

Stage `etl/002.30-by-ou-tree.py` implements this procedure for reviewed By-OU
pages. It consumes stage-002.20 row/cell sections and repaired stage-002.11 phrase
evidence, then writes:

- `002.30-by-ou-tree/tree.json`, the complete tree for the requested page set;
- `002.30-by-ou-tree/pages/page-NNNN.json`, compact page slices; and
- `002.30-by-ou-tree/qa/summary.json`, including page-local centers and flags.

The first viewer smoke uses pages 13–32. The stage also supports the complete
reviewed By-OU span (pages 13–108) without changing the output contract.
The React viewer's **Tree** tab renders `tree.json` as a searchable,
collapsible table and links nodes back to their source PDF row sections.

Stage `etl/002.40-pap-tree.py` applies the PAP profile to the reviewed
pages 115–690. Its deterministic rules add three PAP-specific details:

- the eight common levels are fitted from page-local clusters, anchored to the
  calibrated bottom level, so compressed far-left levels on page 688 remain
  distinct without widening the global bins;
- `MAINTENANCE AND OTHER OPERATING EXPENSES` and `CAPITAL OUTLAYS` reset the
  expense branch, while same-indent GAS, STO, and Operations rows nest below it;
- `GOP` and `Loan Proceeds` remain traceable funding children but never modify
  the active parent stack.

The stage writes the same whole-tree, page-slice, and QA contract under
`002.40-pap-tree/`. The viewer's **PAP** tab loads that artifact independently
of the **Tree** tab used by By-OU. The retained PAP smoke set is pages 115–134;
the complete 576-page span is covered by the same stage and was used to validate
cross-page carry and the formatting transitions on pages 195, 347, 404, 678,
688, and 690.
