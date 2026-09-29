"""Print the Crossref fields a BibTeX entry rests on, for each DOI given on the command line.

Usage: python crossref_check.py <doi> [<doi> ...]  (writes nothing; prints one block per DOI)
"""

import json
import sys
import urllib.request

FIELDS = ("type", "title", "container-title", "volume", "issue", "page", "publisher", "ISBN")


def record(doi: str) -> dict:
    request = urllib.request.Request(
        f"https://api.crossref.org/works/{doi}", headers={"User-Agent": "envelope-bound-check"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)["message"]


def main() -> None:
    for doi in sys.argv[1:]:
        msg = record(doi)
        print(f"== {doi}")
        for key in FIELDS:
            if key in msg:
                print(f"  {key}: {msg[key]}")
        authors = [f"{a.get('family')}, {a.get('given')}" for a in msg.get("author", [])]
        editors = [f"{a.get('family')}, {a.get('given')}" for a in msg.get("editor", [])]
        print(f"  authors: {authors}")
        if editors:
            print(f"  editors: {editors}")
        for key in ("published-print", "published-online", "issued"):
            if key in msg:
                print(f"  {key}: {msg[key]['date-parts']}")
        if "event" in msg:
            print(f"  event: {msg['event']}")


if __name__ == "__main__":
    main()
