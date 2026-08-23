# Hidden Sheet in `xlsx/NEP-FY2027.xlsx` — Findings

**Date investigated:** 2026-08-23
**Scope:** `xlsx/NEP-FY2027.xlsx` (65.9 MB, 2 sheets), cross-checked against `xlsx/NEP-FY2026.xlsx` (70.1 MB, 1 sheet).

## TL;DR

The workbook contains a hidden sheet (`Sheet1`, `state="hidden"`) holding **the Oracle SQL query that generated the visible data**, left in the file accidentally. It confirms the NEP Excel is a **pre-aggregated object-code-level extract** — the sub-object (line-item) grain of DBM's source system is summed away on purpose, with a Tagalog code comment attributing the removal: `-- pina remove ng BTB for NEP EXCEL`.

## Extraction method

Plain `zipfile` + regex over the OOXML parts (no Excel/LibreOffice needed):

- `xl/workbook.xml` → sheet registry; second sheet has `state="hidden"`.
- `xl/worksheets/sheet2.xml` → 101 cells, single column (`A1:A101`), all shared strings.
- `xl/sharedStrings.xml` → resolved via the shared-string table (451,603 entries, shared with the visible sheet).

The full query text is reproduced in the Appendix below.

## Workbook structure

| File | Visible sheet | Hidden sheet | Data rows |
|---|---|---|---|
| `NEP-FY2027.xlsx` | `NEP 2027` | `Sheet1` (SQL query) | 756,628 |
| `NEP-FY2026.xlsx` | `Sheet 1` | none | 771,595 |

The hidden sheet is **unique to FY2027** — likely a developer pasted the query into a scratch sheet during generation and shipped it hidden instead of deleting it.

## What the query reveals

### 1. Source system

Oracle, two schemas:

- `EXPENDITURE` — fact/description tables: `cdsc_f_prexc`, `cexp_f_prexc` (branch 1), `SPF_DSC_f_PREXC`, `SPF_AMT_f_PREXC` (branch 2)
- `REFERENCE` — UACS lookup views: `sobj_view_uacs`, `operunit_UACS`, `VW_FUNDSOURCE`, `v_owner_uacs`, `region_UACS`

All joins are old-style Oracle outer joins (`(+)`), no ANSI syntax. Budget level is hardcoded `'F'` (F-FERB / NEP stage), with `sysdate l_update` captured then discarded before the Excel export.

### 2. Two UNION'd branches

| | Branch 1 (`sorder = 1`) | Branch 2 (`sorder = 2`) |
|---|---|---|
| Purpose | Department/agency detail | Special Purpose Funds ("F-FERB as NEP") |
| "Department" column | `uacs_dpt_id` | `uacs_auth_id` (appropriation authority) |
| "Agency" column | `uacs_agy_id` | `uacs_fundsubcat_id` (fund subcategory) |
| Operating unit | joined from `operunit_UACS` | `NULL` |
| Region description | joined | `NULL` |
| Filter | `amt <> 0` | `uacs_auth_id <> '05'` (excludes one fund authority) |

So in the visible sheet, SPF rows reuse the department/agency columns with fund-source semantics — worth remembering when parsing: **department/agency codes are overloaded across `SORDER` values**.

### 3. Grain of the visible data (the "collapsing" you suspected)

The final SELECT keeps 21 columns; everything below this grain is aggregated with `SUM(b.amt)`:

> department × agency × program (`prexc_fpap_id` + `prexc_level` + `dsc`) × operating unit × region × fund source (`fundcd`) × expense class (`uacs_exp_cd`) × **object code** (`uacs_obj_cd`)

Explicitly dropped from the output (commented out in the SQL):

- `uacs_sobj_cd` / `uacs_sobj_dsc` — **sub-object codes, i.e. the true line-item detail** — both branch select lists comment these out, with `-- pina remove ng BTB for NEP EXCEL` ("BTB had it removed for the NEP Excel")
- `budg_yr`, `budg_lvl` — single-year extract, constant anyway
- `uacs_prov_id/mun_id/brgy_id` + descriptions — province/municipality/barangay geography nulled to `NULL` and excluded from Excel; **region is the finest geographic grain published**
- `sysdate l_update` — load timestamp, dropped

Filters: `amt <> 0` (branch 1). Zero/negative-only line items never appear in the workbook.

### 4. FUNDCD composition

`FUNDCD` is not a lookup code — it's a concatenation:

```
fundcd = uacs_finance_id || uacs_auth_id || UACS_FUND_CLUST_CD || uacs_fundsubcat_id
```

e.g. `10101101`. Each 2-digit component carries meaning (financing source, appropriation authority, fund cluster, fund sub-category). Treat it as a composite key, not an atomic code.

### 5. Text sanitation

Every description column is wrapped in a triple `replace(..., chr(10)/chr(13)/chr(9), ' ')` chain — source descriptions contain CR/LF/tab characters that would otherwise corrupt row-per-line exports. Any pipeline comparing XLSX strings against PDF text should normalize whitespace the same way.

### 6. Sort order

`ORDER BY sorder, department, ..., replace(prexc_fpap_id,'_','2'), prexc_level, ...` — the `replace(prexc_fpap_id,'_','2')` hack forces program IDs containing `_` to sort after numeric-only ones ('2' > any digit), matching the printed volumes' ordering.

## Observable effects in the visible sheet

Verified directly against `NEP 2027` sheet XML:

- Header row maps 1:1, in order, to the query's 21 output columns (`SORDER` … `AMT`).
- 756,628 data rows; ~70% at `PREXC_LEVEL = 7` (leaf, carries `AMT`); levels 1–6 are hierarchy/title rows with **no AMT cell at all** (224,314 rows).
- Exactly **1 formula** exists in the whole sheet — subtotal rows are *implicit* (parent rows simply have no amount). Any roll-up must be computed by the consumer, e.g. group by `PREXC_LEVEL < 7` prefixes of `PREXC_FPAP_ID`.
- Leaf amounts are stored as literal `<v>` numbers, not formulas.

## Notable observations / gotchas

1. **Data-loss asymmetry vs the PDFs.** The printed NEP volumes show sub-object-level detail (e.g. `5010101000.01`-style line items under object codes); the XLSX intentionally collapses these. OCR-extracted PDF figures will therefore be *finer-grained* than the XLSX — reconciliation should aggregate PDF sub-objects up to object code before comparing, not the reverse.
2. **SPF rows pollute the department dimension.** Branch 2 reuses `DEPARTMENT`/`AGENCY` columns for fund authority/fund subcategory. Filter `SORDER = 1` for a clean agency-level dataset; `SORDER = 2` rows will not join to a department reference table.
3. **No zero rows, but signed amounts survive.** `amt <> 0` filters exact zeros only; negatives (e.g. deductions) remain and can make object-code totals smaller than the sum of visible sub-items in the PDF.
4. **One formula, 224k blank-AMT rows** — downstream tools that assume every row has an amount will mis-handle hierarchy rows; conversely, `dropna()` on AMT is actually the correct way to get leaf rows.
5. **Hardcoded join in branch 1:** division descriptions come from `operunit_uacs` restricted to `uacs_dpt_id = 07 and uacs_opertype = '08'`, outer-joined **only on `uacs_operdiv_id`** (not department-scoped). Division labels for other departments may be mis-joined if `uacs_operdiv_id` values collide across departments. Treat `UACS_DIV_DSC` as suspect.
6. **The hidden sheet itself is PII-free but operationally sensitive** — it exposes internal schema/table names and a workflow nickname ("BTB"). No action needed, but it's a fingerprint of DBM's internal tooling.
7. **FY2026 workbook lacks the hidden sheet**, so no equivalent ground truth for that year from this artifact.
8. `replace(prexc_fpap_id,'_','2')` in the ORDER BY means program-ID sort order in the XLSX is *not* plain lexicographic — replicate the transform if you need to reproduce row order.

## Relevance to this repo's pipeline

`xlsx/NEP-FY2027.xlsx` is the authoritative machine-readable counterpart of the PDFs being OCR'd here. The hidden query documents its exact semantics, making it the natural **reconciliation target** for the ETL: aggregate extracted sub-object amounts to object-code grain (per operating unit × region × fund), apply the same whitespace normalization, then diff against column `AMT` on `SORDER = 1` rows.

## Appendix — full hidden-sheet query text (rows 1–101)

```sql
select sorder, department, uacs_dpt_dsc, agency, uacs_agy_dsc, prexc_fpap_id, prexc_level, dsc, uacs_operdiv_id,
      uacs_div_dsc, operunit, uacs_oper_dsc,
      uacs_reg_id,   uacs_reg_dsc, fundcd, uacs_fundsubcat_dsc, uacs_exp_cd, uacs_exp_dsc,
      uacs_obj_cd,  uacs_obj_dsc,  --uacs_sobj_cd,  uacs_sobj_dsc,
      amt
--      budg_yr, budg_lvl, uacs_prov_id, uacs_mun_id, uacs_brgy_id,      uacs_prov_dsc, uacs_mun_dsc, uacs_brgy_dsc, sysdate l_update
FROM
(SELECT  distinct a.budg_yr, 'F' budg_lvl, 1 sorder, a.uacs_dpt_id department, f.uacs_dpt_dsc, a.uacs_agy_id agency,
       replace(replace(replace(f.uacs_agy_dsc, chr(10), ' '), chr(13), ' '), chr(9), ' ') uacs_agy_dsc,
       a.prexc_fpap_id, a.prexc_level,
       replace(replace(replace(dsc, chr(10), ' '), chr(13), ' '), chr(9), ' ') dsc,
       b.uacs_opertype||b.uacs_oper_id operunit,
       replace(replace(replace(d.uacs_oper_dsc, chr(10), ' '), chr(13), ' '), chr(9), ' ') uacs_oper_dsc ,
       b.uacs_reg_id, r.uacs_reg_dsc, g.uacs_operdiv_id, g.uacs_oper_dsc uacs_div_dsc,
       b.uacs_finance_id||b.uacs_auth_id||e.UACS_FUND_CLUST_CD||b.uacs_fundsubcat_id fundcd,
       replace(replace(replace(e.uacs_fundsubcat_dsc, chr(10), ' '), chr(13), ' '), chr(9), ' ') uacs_fundsubcat_dsc,
       c.uacs_exp_cd,  replace(replace(replace(c.uacs_exp_dsc, chr(10), ' '), chr(13), ' '), chr(9), ' ') uacs_exp_dsc,
       c.UACS_OBJ_CD, replace(replace(replace(c.UACS_OBJ_DSC, chr(10), ' '), chr(13), ' '), chr(9), ' ') UACS_OBJ_DSC,  -- inlais ko
       -- b.uacs_sobj_cd, replace(replace(replace(c.uacs_sobj_dsc, chr(10), ' '), chr(13), ' '), chr(9), ' ') uacs_sobj_dsc,
       sum(b.amt)  amt,
       b.uacs_prov_id, b.uacs_mun_id, b.uacs_brgy_id, null uacs_prov_dsc, NULL uacs_mun_dsc, NULL uacs_brgy_dsc
  FROM (select * from expenditure.cdsc_f_prexc  )  a,
       (select * from expenditure.cexp_f_prexc  )  b,
       REFERENCE.sobj_view_uacs c,
       REFERENCE.operunit_UACS d,
       (select distinct UACS_FUND_CLUST_CD, uacs_finance_id, uacs_auth_id, uacs_fundcat_id, uacs_fundsubcat_id, uacs_fundsubcat_dsc
        from REFERENCE.VW_FUNDSOURCE where uacs_auth_id in ('01','04')) e,
       reference.v_owner_uacs f ,
       (select uacs_operdiv_id, uacs_oper_dsc  from operunit_uacs where uacs_dpt_Id = 07 and uacs_opertype ='08') g,
       REFERENCE.REGION_UACS r
 WHERE a.uacs_dpt_id = b.uacs_dpt_id(+)
   AND a.uacs_agy_id = b.uacs_agy_id(+)
   and a.prexc_fpap_id = b.prexc_fpap_id(+) and amt <> 0
   AND b.uacs_sobj_cd = c.uacs_sobj_cd(+)
   and b.uacs_dpt_id = d.uacs_dpt_id(+)
   and b.uacs_agy_id = d.uacs_agy_id(+)
   and b.uacs_opertype = d.uacs_opertype(+)
   and b.uacs_oper_id  = d.uacs_oper_id(+)
   and b.uacs_finance_id = e.uacs_finance_id(+)
   and b.uacs_auth_id = e.uacs_auth_id(+)
   and b.uacs_fundcat_id = e.uacs_fundcat_id(+)
   and b.uacs_fundsubcat_id = e.uacs_fundsubcat_id(+)
   and a.uacs_dpt_id = f.uacs_dpt_id(+)
   AND a.uacs_agy_id = f.uacs_agy_id(+)
   and d.uacs_operdiv_id = g.uacs_operdiv_id(+)
   and b.uacs_reg_id  = r.uacs_reg_id(+)
group by a.budg_yr, a.uacs_dpt_id , f.uacs_dpt_dsc, a.uacs_agy_id ,
        replace(replace(replace(f.uacs_agy_dsc, chr(10), ' '), chr(13), ' '), chr(9), ' ') ,
        a.prexc_fpap_id, a.prexc_level,
        replace(replace(replace(dsc, chr(10), ' '), chr(13), ' '), chr(9), ' ') ,
       b.uacs_opertype||b.uacs_oper_id,
       replace(replace(replace(d.uacs_oper_dsc, chr(10), ' '), chr(13), ' '), chr(9), ' ') ,
       b.uacs_reg_id, r.uacs_reg_dsc,
       b.uacs_finance_id||b.uacs_auth_id||e.UACS_FUND_CLUST_CD||b.uacs_fundsubcat_id,
       replace(replace(replace(e.uacs_fundsubcat_dsc, chr(10), ' '), chr(13), ' '), chr(9), ' ') ,
       c.uacs_exp_cd, c.uacs_exp_dsc,
       c.UACS_OBJ_CD, replace(replace(replace(c.UACS_OBJ_DSC, chr(10), ' '), chr(13), ' '), chr(9), ' ') ,
      -- b.uacs_sobj_cd, c.uacs_sobj_dsc,  -- pina remove ng BTB for NEP EXCEL
      g.uacs_operdiv_id, g.uacs_oper_dsc,
      b.uacs_prov_id, b.uacs_mun_id, b.uacs_brgy_id
UNION ALL
--- F-FERB as NEP
SELECT a.budg_yr, 'F' budg_lvl, 2, a.uacs_auth_id department, e.uacs_auth_dsc, a.uacs_fundsubcat_id agency,
        replace(replace(replace(e.uacs_fundsubcat_dsc, chr(10), ' '), chr(13), ' '), chr(9), ' ') uacs_agy_dsc,
        a.prexc_fpap_id, a.prexc_level,
        replace(replace(replace(dsc, chr(10), ' '), chr(13), ' '), chr(9), ' ') dsc,   null ,  null uacs_oper_dsc ,
        b.uacs_reg_id, NULL, NULL, NULL,
        b.uacs_finance_id||b.uacs_auth_id||e.UACS_FUND_CLUST_CD||b.uacs_fundsubcat_id fundcd,
        replace(replace(replace(e.uacs_fundsubcat_dsc, chr(10), ' '), chr(13), ' '), chr(9), ' ') uacs_fundsubcat_dsc,
        c.uacs_exp_cd, replace(replace(replace(c.uacs_exp_dsc, chr(10), ' '), chr(13), ' '), chr(9), ' ') uacs_exp_dsc,
        c.UACS_OBJ_CD, replace(replace(replace(c.UACS_OBJ_DSC, chr(10), ' '), chr(13), ' '), chr(9), ' ') UACS_OBJ_DSC,
        -- b.uacs_sobj_cd,replace(replace(replace(c.uacs_sobj_dsc, chr(10), ' '), chr(13), ' '), chr(9), ' ') uacs_sobj_dsc,  -- pina remove ng BTB for NEP EXCEL
        sum(b.amt)amt,
        b.uacs_prov_id, b.uacs_mun_id, b.uacs_brgy_id, NUll uacs_prov_dsc, null uacs_mun_dsc, NULL uacs_brgy_dsc
  FROM (select * from EXPENDITURE.SPF_DSC_f_PREXC  where uacs_auth_id <> '05' )  a,
       (select * from expenditure.SPF_AMT_f_PREXC  where uacs_auth_id <> '05' )  b,
       REFERENCE.sobj_view_uacs c,
 --      REFERENCE.operunit_UACS d,
       (select distinct UACS_FUND_CLUST_CD, uacs_auth_id, uacs_auth_dsc, uacs_fundsubcat_id, uacs_fundsubcat_dsc from REFERENCE.VW_FUNDSOURCE) e
 WHERE a.uacs_auth_id = b.uacs_auth_id(+)
   AND a.uacs_fundsubcat_id = b.uacs_fundsubcat_id(+)
   and a.prexc_fpap_id = b.prexc_fpap_id(+)
   AND b.uacs_sobj_cd = c.uacs_sobj_cd(+)
   and b.uacs_auth_id = e.uacs_auth_id(+)
   and b.uacs_fundsubcat_id = e.uacs_fundsubcat_id(+)
group by  a.budg_yr, a.uacs_auth_id , e.uacs_auth_dsc, a.uacs_fundsubcat_id ,
        replace(replace(replace(e.uacs_fundsubcat_dsc, chr(10), ' '), chr(13), ' '), chr(9), ' ') ,
        a.prexc_fpap_id, a.prexc_level,
        replace(replace(replace(dsc, chr(10), ' '), chr(13), ' '), chr(9), ' ') ,
       b.uacs_reg_id,
       b.uacs_finance_id||b.uacs_auth_id||e.UACS_FUND_CLUST_CD||b.uacs_fundsubcat_id ,
       replace(replace(replace(e.uacs_fundsubcat_dsc, chr(10), ' '), chr(13), ' '), chr(9), ' ') ,
      c.uacs_exp_cd, c.uacs_exp_dsc,
      -- b.uacs_sobj_cd,replace(replace(replace(c.uacs_sobj_dsc, chr(10), ' '), chr(13), ' '), chr(9), ' '),  -- pina remove ng BTB for NEP EXCEL
       c.UACS_OBJ_CD, replace(replace(replace(c.UACS_OBJ_DSC, chr(10), ' '), chr(13), ' '), chr(9), ' ') ,
      b.uacs_prov_id, b.uacs_mun_id, b.uacs_brgy_id
 )
order by sorder, department, uacs_dpt_dsc, agency, uacs_agy_dsc, replace(prexc_fpap_id,'_','2'), prexc_level, dsc, uacs_operdiv_id,
      uacs_div_dsc, operunit, uacs_oper_dsc,
      uacs_reg_id,  fundcd, uacs_fundsubcat_dsc, uacs_exp_cd, uacs_exp_dsc,
      uacs_obj_cd,  uacs_obj_dsc
```
