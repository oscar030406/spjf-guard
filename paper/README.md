# paper

论文稿件（英文，LaTeX）。`sections/` 下每节一个 `.tex`，文件名前缀为节号（`01_introduction.tex`…）；`main.tex` 只做拼接。题录只从 `../docs/related_work/refs.bib` 取，不在这里另建 bib。数字只从 `../prechecks/` 的输出文件取，封存学期结果出来前表格里的数字标注为 development。新的一节放进 `sections/`，并在 `main.tex` 里加一行 `\input`。插图放 `figures/`，规则见 `figures/README.md`。

两个入口共用同一套 `sections/`：`main.tex` 是投稿版，走 MDPI 的 `Definitions/mdpi.cls`；`main_article.tex` 是不依赖期刊类的备用版，走标准 `article`。改任何一节，两边都要能编过。编译（在 `paper/` 下跑，需要联网取宏包时设 `HTTPS_PROXY=http://127.0.0.1:7897`）：

```
"D:/environment/tools/tectonic/tectonic.exe" main.tex
"D:/environment/tools/tectonic/tectonic.exe" main_article.tex
```

`Definitions/` 是 MDPI 官方模板目录，2026-09-20 从 res.mdpi.com 下载的 `MDPI_template_ACS.zip` 里原样解出，未作任何修改（模板自带的 `template.tex` / `template.pdf` 没有放进来）。唯一的例外是我们加的 `Definitions/logo-mdpi.pdf`：XeTeX 不能直接嵌 EPS，所以把 MDPI 自己的 `logo-mdpi.eps` 转了一份 PDF 放在旁边，`main.tex` 里的重定向只认这个文件名，`mdpi.cls` 一个字没动。重新生成：

```
epstopdf --outfile=Definitions/logo-mdpi.pdf Definitions/logo-mdpi.eps
```
