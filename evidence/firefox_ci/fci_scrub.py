"""Delete unreadable raw pages so the collector refetches them.

    uv run --with requests python fci_scrub.py

Pages written before writes became atomic (fci_common.write_jsonl_gz) could be truncated
if the process was killed mid-write.  This walks every .gz under data/mozilla_firefox_ci
/raw, tries to read it to the end, and removes the ones that fail; the matching stage of
fci_collect.py then refetches exactly those.  Also removes any leftover .part file.
"""
import os
import sys

sys.dont_write_bytecode = True

import fci_common as C


def main():
    bad, ok, parts = [], 0, 0
    for root, _dirs, files in os.walk(C.RAW):
        for fn in files:
            p = os.path.join(root, fn)
            if fn.endswith(".part"):
                os.remove(p)
                parts += 1
                continue
            if not fn.endswith(".gz"):
                continue
            try:
                for _ in C.read_jsonl_gz(p):
                    pass
                ok += 1
            except Exception as e:                                    # noqa: BLE001
                bad.append((p, repr(e)[:80]))
    for p, e in bad:
        print("  removing", os.path.relpath(p, C.RAW), e)
        os.remove(p)
    print(f"scrub: {ok} pages readable, {len(bad)} removed, {parts} .part files removed")
    with open(os.path.join(C.HERE, "out_scrub.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"{ok} pages readable, {len(bad)} unreadable pages removed, "
                 f"{parts} .part files removed\n")
        for p, e in bad:
            fh.write(f"  {os.path.relpath(p, C.RAW)}  {e}\n")


if __name__ == "__main__":
    main()
