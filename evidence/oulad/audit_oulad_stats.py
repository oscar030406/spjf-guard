# Independent recomputation of the OULAD input-statistics table.
# READ-ONLY on <repo-root>\data\
import math
import pandas as pd

DATA = r"<repo-root>\data"
MODULES = ["AAA", "BBB", "DDD", "EEE", "FFF", "GGG"]
TARGET_TYPES = {"resource", "oucontent", "page"}

CLAIM_N = {"AAA": 156, "BBB": 232, "DDD": 177, "EEE": 64, "FFF": 230, "GGG": 93}
CLAIM_SLOTS = {"AAA": 15, "BBB": 23, "DDD": 17, "EEE": 6, "FFF": 23, "GGG": 9}
CLAIM_PIN = {"AAA": 7, "BBB": 11, "DDD": 8, "EEE": 3, "FFF": 11, "GGG": 4}
CLAIM_PRE = {"AAA": 1, "BBB": 2, "DDD": 1, "EEE": 1, "FFF": 2, "GGG": 1}
CLAIM_REQ = {"AAA": 188515, "BBB": 750799, "DDD": 186696,
             "EEE": 509978, "FFF": 1659455, "GGG": 141918}


def main():
    vle = pd.read_csv(f"{DATA}/vle.csv",
                      usecols=["id_site", "code_module", "code_presentation", "activity_type"])
    vle = vle[vle.code_module.isin(MODULES)]
    tgt = vle[vle.activity_type.isin(TARGET_TYPES)]
    tgt_keys = set(zip(tgt.code_module, tgt.code_presentation, tgt.id_site))
    print("vle rows (6 modules):", len(vle), "| target-type rows:", len(tgt))
    print("activity_type counts (6 modules):")
    print(vle.activity_type.value_counts().to_string())

    sv = pd.read_csv(f"{DATA}/studentVle.csv",
                     dtype={"code_module": "category", "code_presentation": "category",
                            "id_student": "int32", "id_site": "int32",
                            "date": "int16", "sum_click": "int32"})
    sv = sv[sv.code_module.isin(MODULES)]
    sv["code_module"] = sv.code_module.astype(str)
    sv["code_presentation"] = sv.code_presentation.astype(str)
    print("\nstudentVle rows (6 modules):", len(sv))

    keys = pd.MultiIndex.from_arrays([sv.code_module, sv.code_presentation, sv.id_site])
    sv["is_target"] = keys.isin(tgt_keys)
    print("target-type rows:", int(sv.is_target.sum()),
          "| non-target rows:", int((~sv.is_target).sum()))

    # ---- item 4: presentations present + date ranges ----
    print("\n=== item 4: presentations per module, date min/max ===")
    g = sv.groupby(["code_module", "code_presentation"], observed=True).agg(
        rows=("date", "size"), date_min=("date", "min"), date_max=("date", "max"),
        students=("id_student", "nunique"))
    print(g.to_string())

    # ---- item 1/2 ----
    print("\n=== item 1+2: N (2013J, 0<=date<=140, target types) ===")
    hdr = f"{'mod':<4} {'N':>5} {'clm':>5} {'ok':>3} {'slots':>5} {'clm':>4} {'pin':>4} {'clm':>4} {'pre':>4} {'clm':>4}"
    print(hdr)
    for m in MODULES:
        sub = sv[(sv.code_module == m) & (sv.code_presentation == "2013J") &
                 (sv.date >= 0) & (sv.date <= 140) & sv.is_target]
        N = sub.id_site.nunique()
        slots = max(2, math.floor(0.10 * N))
        pin = math.floor(slots / 2)
        pre = min(pin, max(1, math.floor(0.1 * slots)))
        print(f"{m:<4} {N:>5} {CLAIM_N[m]:>5} {str(N==CLAIM_N[m]):>5} "
              f"{slots:>5} {CLAIM_SLOTS[m]:>4} {pin:>4} {CLAIM_PIN[m]:>4} {pre:>4} {CLAIM_PRE[m]:>4}")
        # unfiltered comparison
        sub2 = sv[(sv.code_module == m) & (sv.code_presentation == "2013J") &
                  (sv.date >= 0) & (sv.date <= 140)]
        print(f"     [no type filter N={sub2.id_site.nunique()}; "
              f"no date filter N={sv[(sv.code_module==m)&(sv.code_presentation=='2013J')&sv.is_target].id_site.nunique()}]")

    # ---- item 3: test request counts, several definitions ----
    print("\n=== item 3: 2014J request counts under several definitions ===")
    defs = []
    for lo, hi in [(14, 220), (0, 220), (14, 269), (0, 269), (-25, 269)]:
        for filt in [True, False]:
            defs.append((lo, hi, filt))
    rows = []
    for lo, hi, filt in defs:
        base = sv[(sv.code_presentation == "2014J") & (sv.date >= lo) & (sv.date <= hi)]
        if filt:
            base = base[base.is_target]
        agg = base.groupby("code_module", observed=True).agg(
            clicks=("sum_click", "sum"), nrows=("sum_click", "size"))
        for kind in ["clicks", "nrows"]:
            vals = {m: int(agg[kind].get(m, 0)) for m in MODULES}
            ok = all(vals[m] == CLAIM_REQ[m] for m in MODULES)
            rows.append({"range": f"{lo}..{hi}", "typefilt": filt, "metric": kind,
                         **vals, "total": sum(vals.values()), "ALL_MATCH": ok})
    res = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(res.to_string(index=False))
    print("\nclaimed:", CLAIM_REQ, "total", sum(CLAIM_REQ.values()))
    matches = res[res.ALL_MATCH]
    print("\nDefinitions reproducing ALL six claimed request counts:",
          matches[["range", "typefilt", "metric"]].to_dict("records") or "NONE")
    # per-module near-misses on the primary definition
    prim = res[(res["range"] == "14..220") & (res.typefilt) & (res.metric == "clicks")].iloc[0]
    print("\nprimary def (14..220, filtered, sum_click) per-module vs claim:")
    for m in MODULES:
        print(f"  {m}: mine={prim[m]:>9} claim={CLAIM_REQ[m]:>9} "
              f"diff={prim[m]-CLAIM_REQ[m]:>+9} ratio={prim[m]/CLAIM_REQ[m]:.4f}")

    # ---- item 5 ----
    print("\n=== item 5a: distinct target-type id_site touched in 2014J (full presentation) ===")
    for m in MODULES:
        s = sv[(sv.code_module == m) & (sv.code_presentation == "2014J") & sv.is_target]
        s2 = s[(s.date >= 14) & (s.date <= 220)]
        print(f"  {m}: all-dates={s.id_site.nunique():>5}  within 14..220={s2.id_site.nunique():>5}"
              f"  vle-declared target sites={len(tgt[(tgt.code_module==m)&(tgt.code_presentation=='2014J')])}")

    print("\n=== item 5b: 'unseen resource' share in 2014J test window (14..220, target types) ===")
    print("  first-observed day per id_site computed over the FULL 2014J presentation (all dates)")
    for m in MODULES:
        full = sv[(sv.code_module == m) & (sv.code_presentation == "2014J") & sv.is_target]
        first = full.groupby("id_site", observed=True).date.min()
        win = full[(full.date >= 14) & (full.date <= 220)].copy()
        win["first_day"] = win.id_site.map(first)
        m_rows = win.date == win.first_day
        # also: first day computed within the window itself
        first_w = win.groupby("id_site", observed=True).date.min()
        m_rows_w = win.date == win.id_site.map(first_w)
        print(f"  {m}: by rows={m_rows.mean():.4%} by clicks="
              f"{win.loc[m_rows,'sum_click'].sum()/win.sum_click.sum():.4%} "
              f"| window-local first day: rows={m_rows_w.mean():.4%} "
              f"clicks={win.loc[m_rows_w,'sum_click'].sum()/win.sum_click.sum():.4%}")

    print("\n=== item 5c: enrollments (distinct id_student) per module-presentation ===")
    reg = pd.read_csv(f"{DATA}/studentRegistration.csv")
    reg = reg[reg.code_module.isin(MODULES)]
    rr = reg.groupby(["code_module", "code_presentation"]).id_student.nunique()
    print(rr.to_string())

    print("\n=== courses.csv (6 modules) ===")
    co = pd.read_csv(f"{DATA}/courses.csv")
    print(co[co.code_module.isin(MODULES)].to_string(index=False))


if __name__ == "__main__":
    main()
