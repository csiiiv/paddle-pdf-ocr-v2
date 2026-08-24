# By-OU table structure and carry contract

**Status:** Reviewed development contract; geometric column, row, and cell
sections implemented; semantic row construction not implemented

This contract defines the first deterministic By-OU structure slice. It uses
the existing `002.10-token-geometry` objects as evidence and does not recreate
tokens, baseline bands, phrases, amount anchors, or fits.

The reviewed seed is
[`fixtures/by_ou_table_seeds.json`](../fixtures/by_ou_table_seeds.json). The
initial development pages are 13–15; the declared table continues through the
terminal row on page 108.

## Reviewed span

The first table begins on page 13:

- band 0: page header/chrome;
- band 1: table title;
- bands 2–6: grouped and leaf column headings;
- band 7 / phrase 13: reviewed hierarchy root, `A. REGULAR PROGRAMS`;
- bands 8–9: first wrapped, amount-anchored data row.

It ends on page 108 at band 9, `TOTAL NEW APPROPRIATIONS`. Band 10 begins the
next table, `Obligations, by Object of Expenditures`. An end boundary is a band
reference because tables can change within a page.

Page-header bands remain preserved upstream. They are excluded from table
cells but remain addressable as observed geometry.

## Column seed

Page 13 supplies four persistent roles through its recurring amount-column
candidates:

| Role | Page-13 column candidate |
|---|---:|
| PS | 0 |
| MOOE | 1 |
| CO | 2 |
| Total | 3 |

The carried template stores roles and Total-relative geometry, not absolute
page coordinates. Each continuation page monotonically aligns observed amount
anchors to these roles while permitting skipped roles. Three visible amount
tracks must never collapse the four-slot schema.

## Cell and row boundary

Stage `002.20` first emits a deliberately coarse, non-semantic grid:

- reviewed header sections for page chrome, table title, and grouped column
  headings, kept separate from the hierarchy root and body;
- one `Labels` section followed by one section per recurring amount-column
  candidate, using each skew-corrected amount-left edge as a boundary;
- row boundaries formed by consolidating all amount-column fit segments that
  share a label phrase;
- row sections from the reviewed root baseline to the first alignment fit,
  fit to fit, and the last fit to the page bottom.

Reviewed column seeds name the page-13 amount sections PS, MOOE, CO, and Total;
without such a mapping the geometry uses neutral amount roles. Each section
retains its polygon, bounding box, phrase IDs, and source token IDs. Intersecting
the column and row polygons creates cell sections with ordered line text and
flat text while preserving the underlying phrase/token evidence. These are
geometric content containers, not semantic rows. On page 13, three header
sections and five column sections accompany 20 logical alignment boundaries
consolidated from 65 raw fit segments, 21 row sections, and 105 cell sections.

Columns provide horizontal bounds. Consecutive Total-anchored terminal bands
provide vertical row evidence. Together they form cells for:

```text
program_code | label | PS | MOOE | CO | Total
```

`program_code` is optional metadata and is not label text. Missing amount roles
are explicit empty cells. Label cells retain ordered line objects plus flattened
text, phrase IDs, token IDs, and a union bounding box.

Cell text is sourced strictly from stage-002.10 phrases: `text_candidate`
phrases for the Labels section and `money_candidate` phrases for amount
sections. Stage 002.20 does not rebuild text from Paddle tokens. Token IDs remain
source provenance. Long numeric program-code prefixes are split upstream as
`code_candidate` phrases and retained on the row as left-of-label evidence.

An indent observation is eligible only when a descriptive label fragment is on
the Total-aligned terminal band and is the leftmost token on that band. A
program code, marker, amount, or any other token to its left makes the indent
ineligible. Wrapped lines above the terminal band remain label-cell content but
do not supply hierarchy indentation.

Cell assembly is geometric. It does not use hierarchy to decide phrase
ownership. Hierarchy consumes completed rows afterward.

## Per-page state

Every table-structure page artifact must expose three state blocks:

```json
{
  "page": 14,
  "sequence": {
    "table_id": "by-ou-001",
    "previous_page": 13,
    "contiguous": true
  },
  "carried_in": {
    "source_page": 13,
    "column_roles": ["PS", "MOOE", "CO", "Total"],
    "column_template": {},
    "hierarchy_context": [],
    "pending_row": null
  },
  "observed": {
    "page_header_band_ids": [0],
    "page_column_fits": [],
    "cells": [],
    "rows": []
  },
  "carried_out": {}
}
```

`carried_in` is never implicit. Page 13 uses `explicit_root`; pages 14–15 cite
the immediately preceding page. Starting mid-table must either walk forward
from the declared root or consume an explicit reviewed carried-in snapshot.

## Pending rows

When a page ends after label content but before its Total-aligned terminal
band, `carried_out.pending_row` retains page-qualified band, phrase, and token
references, accumulated label lines, and optional program-code metadata. Only
the next contiguous page may consume it. A page gap resets pending content and
requires review.

## Table close

Processing the declared page-108 terminal band closes `by-ou-001`, clears its
column and hierarchy carry, and prevents the following By-Year table from
inheriting By-OU roles. No page-wide end assumption is allowed.

## Scope boundary

This contract establishes reviewed inputs and state ownership only. It does not
yet implement cell extraction, semantic row typing, hierarchy inference, or
automatic table start/end discovery. Those transforms must reproduce this seed
before replacing it with inferred decisions.
