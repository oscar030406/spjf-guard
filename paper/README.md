# paper

The manuscript (English, LaTeX). `sections/` holds one `.tex` file per main-text section, named with the section number as prefix (`01_introduction.tex`, ...), plus `S_theory_additions.tex`, which the supplement inputs, and `A_proofs.tex`, a stub that records where the former appendix went and is no longer input. `main.tex` holds the class settings, the front and back matter and the list of supplementary items, and inputs the sections. Bibliography entries come only from `../docs/related_work/refs.bib`; no separate bib file is kept here. Every number in the text comes from an output file: the package's tables under `../outputs/`, which the commands in `../README.md` regenerate and which are not committed, or a study under `../evidence/` (the public copy of the working folder `prechecks/` that the source comments name; see `../evidence/PATHS.md` for the path mapping). Numbers from the development terms are wrapped in `\devnum{}` and numbers from the sealed terms in `\sealednum{}`; `../scripts/check_paper_numbers.py` checks both against their sources. A new section goes into `sections/`, with one `\input` line added to `main.tex`. Figures go into `figures/`; the rules are in `figures/README.md`.

Two entry points share the same `sections/`: `main.tex` is the submission version and uses MDPI's `Definitions/mdpi.cls`; `main_article.tex` is a fallback that does not depend on the journal class and uses the standard `article` class. After changing any section, both must still compile. The supplementary material `supplementary.tex` is a separate PDF. It uses `xr` to read `main.aux` so that it can refer to section, table and theorem numbers of the main text (written as `\ref*{M-label}`), so `main.tex` must be compiled first and its intermediate files kept. Build with tectonic, run in `paper/` in this order (tectonic downloads the LaTeX packages it needs on first use, so the first build needs network access):

```
tectonic --keep-intermediates --keep-logs main.tex
tectonic --keep-intermediates --keep-logs supplementary.tex
tectonic main_article.tex
```

References from the main text to the supplementary material ("Supplementary Table S6") are written out by hand, because when MDPI compiles the main text it does not have the supplementary material's aux file. After a table or section is added to the supplementary material, list the title of each S number (for example from the `\newlabel` entries in `supplementary.aux`) and update the main text and the `\supplementary{}` list in `main.tex` against it.

`Definitions/` is MDPI's official template directory, extracted unchanged from `MDPI_template_ACS.zip` downloaded from res.mdpi.com on 2026-09-20 (the `template.tex` / `template.pdf` shipped with the template are not included). The one exception is `Definitions/logo-mdpi.pdf`, which we added: XeTeX cannot embed EPS directly, so MDPI's own `logo-mdpi.eps` was converted to a PDF placed next to it. The redirect in `main.tex` recognises only this file name, and `mdpi.cls` is not changed in any way. To regenerate it:

```
epstopdf --outfile=Definitions/logo-mdpi.pdf Definitions/logo-mdpi.eps
```

The second exception is `Definitions/mathematics-logo.png`, the journal logo, taken from MDPI's Word template `mathematics-template.dot` (2025 version, `word/media/image3.png`). In the `submit` state `mdpi.cls` prints only the MDPI logo at the top right, and prints the journal logo only in the `accept` state; the Word template puts the MDPI logo on the left and the journal logo on the right in both states. A line in `main.tex` rewrites the title macro with `\patchcmd` so that the submission version looks the same way, and the class file is still unchanged. Removing that patch restores the class file's original behaviour.
