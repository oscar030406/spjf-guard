# accoding

`parse_sql.py` turns the six SQL dumps of the ACcoding dataset into the parquet tables
that `evidence/accoding_v2/` reads. It is the only file kept from the first ACcoding
study, which `accoding_v2` superseded; no number in the paper comes from that study.

Input: the `*.sql` files under `data/accoding/raw/` (see `data/README.md`).
Output: `data/accoding/parquet/`. Set `<repo-root>` in the two paths at the top of the
script to the package root, then run `python evidence/accoding/parse_sql.py`.
