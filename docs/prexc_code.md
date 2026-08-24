DBM's **PREXC code** is the **15-digit enhanced UACS P/A/P code**.

For NEP Volume 2B By-OU rows (DPWH), the digit layout that matches observed
codes and rollups is:

```text
X X X X X X X XXXXX XXX
1 2-3 4-5 6 7 8-12  13-15
```

| Digits | Field | Meaning |
| --- | --- | --- |
| 1 | **Cost structure / purpose** | `1` GAS, `2` STO, `3` Operations, `4` SPFs |
| 2–3 | **Organizational outcome** | Outcome under which the program contributes |
| 4–5 | **Program** | Program identifier |
| 6 | **Sub-program** | Narrow sub-program field (with digit 1–6 used as the program prefix in ETL) |
| 7 | **Identifier** | `1` Activity, `2` Locally Funded Project, `3` Foreign-Assisted Project |
| 8–12 | **Lowest-level activity / project** | Specific activity/project identifier |
| 13–15 | **Reserved** | Completes the 15-digit code |

Example:

```text
310101100238000
││ │ │││└────┴── activity/project + reserved
││ │ ││└──────── identifier = Activity
││ │ │└───────── sub-program
││ │ └────────── program
││ └──────────── organizational outcome
└─────────────── Operations
```

Machine-readable form:

```json
{
  "prexc_code": "310101100238000",
  "cost_structure": "3",
  "organizational_outcome": "10",
  "program": "10",
  "subprogram": "1",
  "identifier": "1",
  "activity_project": "00238",
  "reserved": "000"
}
```

## By-OU hierarchy

Stage `002.30` builds layout nesting first (so region/office stay under the
open coded row), then **reparents coded nodes by PREXC**: each coded row's
parent is the longest proper zero-padded ancestor that exists (synthesizing
missing intermediate shells when needed). Uncoded children keep their layout
parent.

## Amount rollups (`002.50`)

Parent total should equal the sum of **immediate additive** children, excluding:

- `subtotal` / `grand_total` (explicit aggregates)
- `funding` (Loan/GOP breakdowns already inside the office/parent total)
- PREXC project siblings with identifier `2` or `3` (program lines total the
  regular activity stream only)

## References

DBM still calls this the enhanced 15-digit PREXC code (2017 COA-DBM-DOF Joint
Circular). Booklet graphics sometimes look like 16 digits if reserved is misread
as three trailing zeros plus an extra column; NEP By-OU codes in this repo are
consistently 15 digits.

[DBM PREXC page](https://www.dbm.gov.ph/index.php/program-expenditure-classification-prexc) ·
[2017 COA-DBM-DOF Joint Circular No. 1](https://www.dbm.gov.ph/index.php/central-office?catid=61&id=3239&view=article)
