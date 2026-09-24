# paper

论文稿件（英文，LaTeX）。`sections/` 下每节一个 `.tex`，文件名前缀为节号（`01_introduction.tex`…）；`main.tex` 只做拼接。题录只从 `../docs/related_work/refs.bib` 取，不在这里另建 bib。数字只从 `../prechecks/` 的输出文件取，封存学期结果出来前表格里的数字标注为 development。新的一节放进 `sections/`，并在 `main.tex` 里加一行 `\input`。插图放 `figures/`，规则见 `figures/README.md`。

两个入口共用同一套 `sections/`：`main.tex` 是投稿版，走 MDPI 的 `Definitions/mdpi.cls`；`main_article.tex` 是不依赖期刊类的备用版，走标准 `article`。改任何一节，两边都要能编过。补充材料 `supplementary.tex` 单独成 PDF，用 `xr` 读 `main.aux` 引用正文的节、表、定理编号（写作 `\ref*{M-标签}`），所以必须先编 `main.tex` 并保留中间文件。编译（在 `paper/` 下按顺序跑，需要联网取宏包时设 `HTTPS_PROXY=http://127.0.0.1:7897`）：

```
"D:/environment/tools/tectonic/tectonic.exe" --keep-intermediates --keep-logs main.tex
"D:/environment/tools/tectonic/tectonic.exe" --keep-intermediates --keep-logs supplementary.tex
"D:/environment/tools/tectonic/tectonic.exe" main_article.tex
```

正文里指向补充材料的编号（"Supplementary Table S6"）是写死的，因为 MDPI 编译正文时拿不到补充材料的 aux。补充材料加表或加节后，用 `python ../local_tools/supp_list_0924.py` 列出每个 S 编号的标题，对照正文和 `main.tex` 的 `\supplementary{}` 清单改。

`Definitions/` 是 MDPI 官方模板目录，2026-09-20 从 res.mdpi.com 下载的 `MDPI_template_ACS.zip` 里原样解出，未作任何修改（模板自带的 `template.tex` / `template.pdf` 没有放进来）。唯一的例外是我们加的 `Definitions/logo-mdpi.pdf`：XeTeX 不能直接嵌 EPS，所以把 MDPI 自己的 `logo-mdpi.eps` 转了一份 PDF 放在旁边，`main.tex` 里的重定向只认这个文件名，`mdpi.cls` 一个字没动。重新生成：

```
epstopdf --outfile=Definitions/logo-mdpi.pdf Definitions/logo-mdpi.eps
```

第二个例外是 `Definitions/mathematics-logo.png`，期刊 logo，从 MDPI 的 Word 模板 `mathematics-template.dot`（2025 版，`word/media/image3.png`）里取出。`mdpi.cls` 在 `submit` 状态下只印右上角的 MDPI logo，`accept` 状态才印期刊 logo；Word 模板则两个状态都是左 MDPI、右期刊。`main.tex` 里用 `\patchcmd` 改写标题宏的那一行，让投稿版也是这个样子，类文件仍然没动。删掉那段 patch 就回到类文件原样。
