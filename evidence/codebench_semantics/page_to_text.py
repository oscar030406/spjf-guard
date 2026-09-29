"""Convert the saved official dataset page (sources/dataset_page.html) to plain text (sources/dataset_page.txt).

Source: https://codebench.icomp.ufam.edu.br/dataset/ fetched with curl on 2026-09-18.
The other two snapshots in sources/ are https://codebench.icomp.ufam.edu.br/index.php?r=site%2Fabout
and ...?r=site%2Fcontact, fetched the same day.
Regenerate: uv run python page_to_text.py
"""
import html
import os
import re

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources")
raw = open(os.path.join(HERE, "dataset_page.html"), encoding="utf-8", errors="replace").read()
raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
raw = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</tr>|</div>|</pre>", "\n", raw)
raw = re.sub(r"(?i)<li[^>]*>", "\n* ", raw)
txt = html.unescape(re.sub(r"<[^>]+>", " ", raw))
lines = [re.sub(r"[ \t]+", " ", l).strip() for l in txt.splitlines()]
out, blank = [], 0
for l in lines:
    if not l:
        blank += 1
        if blank > 1:
            continue
    else:
        blank = 0
    out.append(l)
open(os.path.join(HERE, "dataset_page.txt"), "w", encoding="utf-8").write("\n".join(out))
print(len(out), "lines")
