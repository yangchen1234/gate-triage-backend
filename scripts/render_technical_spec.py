"""Render the standalone technical specification; requires Markdown>=3.7."""

from html import escape
from pathlib import Path
import re

import markdown


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/gate-triage-technical-specification.zh-CN.md"
OUTPUT = SOURCE.with_suffix(".html")


def slugify(value: str, separator: str) -> str:
    return re.sub(r"[^\w\u3400-\u9fff]+", separator, value.casefold()).strip(separator)


def main() -> None:
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
        extension_configs={"toc": {"toc_depth": "2-2", "slugify": slugify}},
    )
    body = md.convert(SOURCE.read_text(encoding="utf-8"))
    body = body.replace("<table>", '<div class="table-scroll"><table>').replace(
        "</table>", "</table></div>"
    )
    title = "Gate Triage 技术设计与全栈开发规范"
    template = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title><style>
:root{color-scheme:light;--ink:#182d3a;--muted:#536572;--line:#d9e2e5;--teal:#126b66;--paper:#fff;--canvas:#f3f6f6}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:28px}body{margin:0;background:var(--canvas);color:var(--ink);font:15px/1.85 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
a{color:var(--teal);text-underline-offset:3px}a:hover{text-decoration-thickness:2px}aside{position:fixed;inset:0 auto 0 0;width:270px;padding:30px 22px;background:#eaf0f0;border-right:1px solid var(--line);overflow:auto}aside .brand{font-size:20px;font-weight:750;letter-spacing:.02em}aside .sub{color:var(--muted);font-size:12px;margin:6px 0 20px}.toc ul{list-style:none;padding:0;margin:0}.toc a{display:block;padding:6px 7px;text-decoration:none;color:var(--ink);font-size:12px;border-radius:5px}.toc a:hover{background:#dae9e6;color:var(--teal)}
main{margin-left:270px;padding:36px 42px 80px;max-width:1570px}.toolbar{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:22px;font-size:12px}.tag{border:1px solid #a9c7c1;background:#e7f3ee;padding:3px 10px;color:#195549;border-radius:20px}.toolbar button{margin-left:auto;border:1px solid #b8c9cd;background:white;border-radius:6px;padding:7px 12px;color:var(--ink);cursor:pointer;font:inherit}article{background:var(--paper);padding:38px 46px 60px;border:1px solid var(--line);border-radius:10px;box-shadow:0 4px 22px #1e3a4310}h1{font-size:32px;line-height:1.4;letter-spacing:-.025em;margin:0 0 22px}h2{font-size:23px;line-height:1.5;margin:54px 0 18px;padding-top:16px;border-top:2px solid #dbe8e6}h3{font-size:17px;margin:30px 0 12px;color:#224d58}p{margin:14px 0}li{margin:6px 0}strong{font-weight:680}.table-scroll{overflow:auto;margin:20px 0;border:1px solid var(--line);border-radius:7px}table{border-collapse:collapse;width:100%;min-width:650px;font-size:12px;line-height:1.7}th,td{padding:11px 13px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line);overflow-wrap:anywhere}th{background:#eaf2f1;font-weight:650}tr:last-child td{border-bottom:0}td:first-child{min-width:100px}tr:nth-child(even)td{background:#f8faf9}code{font:12px/1.65 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:#eef3f3;padding:2px 4px;border-radius:3px;overflow-wrap:anywhere}pre{background:#142d39;color:#e3f1f0;overflow:auto;padding:22px;border-radius:7px;line-height:1.6}pre code{background:none;color:inherit;padding:0;overflow-wrap:normal}blockquote{border-left:4px solid #73a79f;margin:20px 0;padding:2px 20px;background:#f1f7f5}footer{font-size:12px;color:var(--muted);margin-top:24px}
@media(max-width:1000px){aside{position:static;width:auto;max-height:270px;border-bottom:1px solid var(--line)}main{margin:0;padding:22px 16px}article{padding:26px 22px}.toc ul{columns:2}h1{font-size:26px}}@media print{aside,.toolbar{display:none}body{background:white}main{margin:0;padding:0;max-width:none}article{padding:0;border:0;box-shadow:none}h2{break-before:auto;break-after:avoid}h3{break-after:avoid}pre{white-space:pre-wrap;background:#f2f4f4;color:black}pre code{color:black}table{min-width:0}tr{break-inside:avoid}a{color:inherit}}
</style></head><body><aside><div class="brand">Gate Triage</div><div class="sub">开发规范 · 1.0 · 2026-10-17<br>目录可点击；正文可用浏览器查找</div>__TOC__</aside><main><div class="toolbar"><span class="tag">技术规范 · 待实现产品</span><a href="gate-triage-technical-specification.zh-CN.md">Markdown 原稿</a><a href="gate-triage-development-brief.zip">开发文档包</a><button type="button" onclick="window.print()">打印或保存 PDF</button></div><article>__BODY__</article><footer>真实外部业务数据源为 Terminal49；运营资源与历史事件演练单独标明为模拟。所有技术与产品状态以正文及验收记录为准。</footer></main></body></html>"""
    template = template.replace("开发规范 · 1.0", "开发规范 · 1.1").replace("技术规范 · 待实现产品", "技术规范 · 实现状态见验收记录")
    html = template.replace("__TITLE__", escape(title)).replace("__TOC__", md.toc).replace(
        "__BODY__", body
    )
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Rendered {OUTPUT.name}: {len(html):,} characters")


if __name__ == "__main__":
    main()
