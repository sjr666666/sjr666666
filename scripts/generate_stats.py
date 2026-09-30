#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Merged PR Observatory — 静态资源生成器

只统计**已合并**的 Pull Request，生成 **亮 / 暗两版** SVG 卡片（供 README 用
<picture> + prefers-color-scheme 按 GitHub 主题自动切换），并把明细表格回写进
README.md 的标记区间。

设计依据（2025-2026 业内实践）：
- GitHub 官方推荐用 <picture> + prefers-color-scheme 做主题自适应；
  旧的 #gh-dark-mode-only 片段已废弃。
- 配色直接采用 GitHub Primer 原生色值，卡片与站点视觉同源，不显突兀。
- 已合并到他人大仓库的 PR 是 GitHub 上最强的可信凭证，必须显性展示。

用法：
    python scripts/generate_stats.py                  # 本地（走 gh CLI 鉴权）
    GITHUB_TOKEN=xxx python scripts/generate_stats.py # CI（Actions 自动注入）
    python scripts/generate_stats.py --offline        # 读 assets/stats.json 缓存

只依赖标准库，无需 pip install。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

USER = "sjr666666"
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
README = ROOT / "README.md"
TZ8 = timezone(timedelta(hours=8))

# ---------------------------------------------------------------- GitHub Primer 色值
# 亮色（GitHub light default）
LIGHT = {
    "bg": "#FFFFFF", "border": "#D1D9E0", "hair": "#EAEEF2", "chip": "#F6F8FA",
    "text": "#1F2328", "text2": "#59636E", "text3": "#818B98",
    "accent": "#8250DF",   # GitHub 的 merged 紫
    "add": "#1A7F37",      # GitHub 的 additions 绿
}
# 暗色（GitHub dark default）
DARK = {
    "bg": "#0D1117", "border": "#30363D", "hair": "#21262D", "chip": "#161B22",
    "text": "#F0F6FC", "text2": "#9198A1", "text3": "#6E7681",
    "accent": "#A371F7",
    "add": "#3FB950",
}
FONT = ("-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',"
        "'Hiragino Sans GB','Microsoft YaHei',sans-serif")
MONO = "ui-monospace,'SF Mono',Menlo,Consolas,monospace"
# GitHub 官方 octicon: git-merge（16×16，MIT）
MERGE_ICON = ("M5 3.25a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Zm0 2.122a2.25 2.25 0 1 0-1.5 0v.878A2.25 "
              "2.25 0 0 0 5.75 8.5h1.5v2.128a2.251 2.251 0 1 0 1.5 0V8.5h1.5a2.25 2.25 0 0 0 2.25-2.25v-.878"
              "a2.25 2.25 0 1 0-1.5 0v.878a.75.75 0 0 1-.75.75h-4.5A.75.75 0 0 1 5 6.25v-.878Zm3.75 "
              "7.378a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Zm3-8.75a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Z")


# ---------------------------------------------------------------- 取数
def gh_api(path: str) -> dict:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req = urllib.request.Request(
            "https://api.github.com" + path,
            headers={"Authorization": "Bearer " + token,
                     "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28",
                     "User-Agent": "merged-pr-observatory"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True,
                         encoding="utf-8", check=True)
    return json.loads(out.stdout)


def search_prs(user: str) -> list[dict]:
    items, page = [], 1
    while True:
        data = gh_api(f"/search/issues?q=author:{user}+type:pr"
                      f"&per_page=100&page={page}&sort=created&order=desc")
        batch = data.get("items", [])
        items.extend(batch)
        if len(batch) < 100 or page >= 10:
            break
        page += 1
    return items


def parse_ts(s):
    return (datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if s else None)


def collect(user: str) -> list[dict]:
    cache = ASSETS / "stats.json"
    if "--offline" in sys.argv and cache.exists():
        print(f"  [offline] 读取缓存 {cache.relative_to(ROOT)}")
        return json.loads(cache.read_text(encoding="utf-8"))["prs"]

    raw = search_prs(user)
    repos: dict[str, dict] = {}
    prs: list[dict] = []

    for it in raw:
        repo_api = it["repository_url"].split("/repos/")[-1]
        if repo_api not in repos:
            try:
                d = gh_api(f"/repos/{repo_api}")
                repos[repo_api] = {"language": d.get("language") or "Other",
                                   "stars": d.get("stargazers_count") or 0}
            except Exception as e:
                print(f"  ! repo {repo_api}: {e}", file=sys.stderr)
                repos[repo_api] = {"language": "Other", "stars": 0}

        pr = gh_api(f"/repos/{repo_api}/pulls/{it['number']}")
        merged_at = pr.get("merged_at")
        created = parse_ts(pr.get("created_at"))
        end = parse_ts(merged_at) if merged_at else parse_ts(pr.get("closed_at"))
        status = "merged" if merged_at else ("open" if pr.get("state") == "open" else "closed")
        merged_dt = parse_ts(merged_at)
        owner, name = repo_api.split("/")

        prs.append({
            "repo": repo_api, "owner": owner, "name": name,
            "number": it["number"],
            "title": pr.get("title") or it.get("title") or "",
            "status": status,
            "created": pr.get("created_at"), "merged_at": merged_at,
            "merged_date": merged_dt.astimezone(TZ8).strftime("%m-%d") if merged_dt else "",
            "merged_year": merged_dt.astimezone(TZ8).strftime("%Y") if merged_dt else "",
            "additions": pr.get("additions") or 0,
            "deletions": pr.get("deletions") or 0,
            "changed_files": pr.get("changed_files") or 0,
            "url": pr.get("html_url") or f"https://github.com/{repo_api}/pull/{it['number']}",
            "hours": round((end - created).total_seconds() / 3600, 2) if (end and created) else None,
        })

    prs.sort(key=lambda p: p["created"] or "")
    return prs


# ---------------------------------------------------------------- 工具
def esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def cut(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


# 全角字符区间（CJK / 假名 / 全角标点等）
_WIDE = ((0x1100, 0x115F), (0x2E80, 0xA4CF), (0xAC00, 0xD7A3),
         (0xF900, 0xFAFF), (0xFE30, 0xFE6F), (0xFF00, 0xFF60), (0xFFE0, 0xFFE6))
# 实测：13.5px 下比例字体约 6.3px/字符（0.467 em），全角按 1 em 计
_ASCII_RATIO = 0.467


def _char_px(ch: str, size: float) -> float:
    o = ord(ch)
    for a, b in _WIDE:
        if a <= o <= b:
            return size
    return size * (_ASCII_RATIO if o < 0x0250 else 0.52)


def cut_px(s: str, max_px: float, size: float = 13.5) -> str:
    """按渲染宽度截断，中英文混排都不会溢出。"""
    w, out = 0.0, []
    for ch in s:
        cw = _char_px(ch, size)
        if w + cw > max_px:
            return "".join(out).rstrip() + "…"
        out.append(ch)
        w += cw
    return s


def fmt_int(n: int) -> str:
    return f"{n:,}"


def fmt_dur(h):
    if h is None:
        return "—"
    if h < 1:
        return f"{max(1, round(h * 60))} 分钟"
    if h < 24:
        return f"{h:.1f}".rstrip("0").rstrip(".") + " 小时"
    d = h / 24
    return (f"{d:.1f}".rstrip("0").rstrip(".") if d < 10 else str(round(d))) + " 天"


def common_theme(items: list[dict]) -> str:
    """从一组 PR 标题里提取共同主题词（小写比对，按首次出现顺序），避免写死文案。"""
    STOP = {"add", "the", "for", "and", "with", "into", "from", "when", "that",
            "not", "use", "make", "keep", "only", "new", "all", "fix", "feat",
            "docs", "test", "chore", "refactor", "perf", "build", "ci"}

    def body(t: str) -> str:
        if "):" in t:
            return t.split("):", 1)[1]
        return t.split(":", 1)[1] if ":" in t else t

    if not items:
        return ""
    sets = []
    for p in items:
        seen, order = set(), {}
        for w in re.split(r"[^0-9A-Za-z]+", body(p["title"])):
            lw = w.lower()
            if len(lw) >= 3 and lw.isascii() and lw not in STOP and lw not in seen:
                seen.add(lw)
                order[lw] = w
        sets.append(order)
    return " ".join([sets[0][k] for k in sets[0] if all(k in s2 for s2 in sets[1:])][:3])


def tx(x, y, s, size=12, fill="#000", weight="normal", anchor="start",
       family=None, ls=None):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    l = f' letter-spacing="{ls}"' if ls is not None else ""
    return (f'<text x="{x}" y="{y}" font-family="{family or FONT}" '
            f'font-size="{size}" fill="{fill}" font-weight="{weight}"{a}{l}>{esc(s)}</text>')


def merge_glyph(x, y, color, scale=0.78) -> str:
    return (f'<g transform="translate({x} {y}) scale({scale})">'
            f'<path d="{MERGE_ICON}" fill="{color}"/></g>')


# ---------------------------------------------------------------- 卡片
def card_merged(prs: list[dict], C: dict) -> str:
    """962 宽、高度自适应：一个焦点数字 + 上游合并故事 + 明细行。"""
    W = 962
    L, R = 40, W - 40

    merged = [p for p in prs if p["status"] == "merged"]
    upstream = [p for p in merged if p["owner"] != USER]
    own = [p for p in merged if p["owner"] == USER]
    hours = sorted(p["hours"] for p in merged if p["hours"] is not None)
    median = hours[len(hours) // 2] if hours else None

    groups: dict[str, list[dict]] = {}
    for p in upstream:
        groups.setdefault(p["repo"], []).append(p)
    groups = dict(sorted(groups.items(), key=lambda kv: -len(kv[1])))
    shown = list(groups.items())[:2]

    b: list[str] = []
    # 眉头
    b.append(f'<circle cx="{L + 4}" cy="50" r="3.2" fill="{C["accent"]}"/>')
    b.append(tx(L + 16, 54, "MERGED PULL REQUESTS", 12, C["accent"], "700", ls="2.4"))
    b.append(tx(R, 54, f"github.com/{USER}", 11.5, C["text3"], "normal", "end", MONO))

    # 焦点数字
    n = str(len(merged))
    b.append(tx(L - 5, 146, n, 84, C["text"], "700", family=MONO, ls="-3.5"))
    b.append(tx(L + 52 * len(n) + 16, 146, "个 PR 已合并进开源项目", 19, C["text2"], "600", ls="-0.2"))
    sub = (f"{len(upstream)} 个提给他人仓库 · {len(own)} 个自有项目"
           + (f" · 中位交付 {fmt_dur(median)}" if median else ""))
    b.append(tx(L, 174, sub, 13, C["text3"]))
    b.append(f'<line x1="{L}" y1="202" x2="{R}" y2="202" stroke="{C["hair"]}"/>')

    # 上游分组
    y, bottom = 230, 230
    for repo, items in shown:
        g_add = sum(p["additions"] for p in items)
        g_del = sum(p["deletions"] for p in items)
        g_files = sum(p["changed_files"] for p in items)
        b.append(tx(L, y, repo.upper(), 13.5, C["text"], "700", family=MONO, ls="0.6"))
        b.append(tx(R, y, f"{len(items)} 个 PR · +{fmt_int(g_add)} / −{fmt_int(g_del)} 行 · "
                          f"{g_files} 文件", 12, C["text3"], "normal", "end", MONO))
        theme = common_theme(items)
        if theme:
            b.append(tx(L, y + 21, f"共同主题：{theme}", 12.5, C["text3"]))
        first = y + 48
        for i, p in enumerate(sorted(items, key=lambda x: x["number"])):
            rb = first + i * 30
            b.append(merge_glyph(L + 1, rb - 12, C["accent"]))
            b.append(tx(L + 27, rb, f"#{p['number']}", 12, C["text3"], "normal", "start", MONO))
            b.append(tx(L + 72, rb,
                        cut_px(re.sub(r"\s*\(#\d+\)\s*$", "", p["title"]), 740),
                        13.5, C["text2"]))
            b.append(tx(R, rb, f"+{fmt_int(p['additions'])}", 13.5, C["add"], "600", "end", MONO))
            bottom = rb
        y = first + (len(items) - 1) * 30 + 34

    if len(groups) > len(shown):
        b.append(tx(L, y, f"另有 {len(groups) - len(shown)} 个他人仓库的合并 PR，见下表",
                    12.5, C["text3"]))
        bottom = y

    H = int(bottom + 28 + 44)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    head = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}" role="img" aria-label="已合并的 Pull Request 总览">',
            f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" '
            f'fill="{C["bg"]}" stroke="{C["border"]}"/>',
            f'<rect x="0" y="0" width="{W}" height="3" rx="1.5" fill="{C["accent"]}" '
            f'fill-opacity="0.9"/>']
    tail = [f'<line x1="{L}" y1="{H - 44}" x2="{R}" y2="{H - 44}" stroke="{C["hair"]}"/>',
            tx(L, H - 20, "数据来源 GitHub REST API · 每日自动刷新", 11.5, C["text3"]),
            tx(R, H - 20, f"更新于 {stamp}", 11.5, C["text3"], "normal", "end", MONO),
            '</svg>']
    return "\n".join(head + b + tail) + "\n"


# ---------------------------------------------------------------- README
def pr_table(merged: list[dict]) -> str:
    rows = ["| 仓库 | PR | 变更内容 | 规模 | 交付周期 | 合并日期 |",
            "|:--|--:|:--|--:|--:|--:|"]
    for p in sorted(merged, key=lambda x: x["merged_at"] or "", reverse=True):
        title = re.sub(r"\s*\(#\d+\)\s*$", "", p["title"])   # 去掉与 PR 列重复的 (#NN)
        rows.append(
            f'| [`{p["name"]}`](https://github.com/{p["repo"]}) '
            f'| [#{p["number"]}]({p["url"]}) '
            f'| {cut_px(title, 470, 15)} '
            f'| `+{fmt_int(p["additions"])}`' + (f' `−{fmt_int(p["deletions"])}`' if p["deletions"] else '') + f' · {p["changed_files"]} 文件 '
            f'| {fmt_dur(p["hours"])} | {p["merged_date"]} |')
    return "\n".join(rows)


def sync(md: str, prs: list[dict]) -> str:
    merged = [p for p in prs if p["status"] == "merged"]
    up = [p for p in merged if p["owner"] != USER]
    own = [p for p in merged if p["owner"] == USER]
    n_all_repo = len({p["repo"] for p in prs})

    md = re.sub(r"(badge/Merged%20PRs-)\d+(-)", rf"\g<1>{len(merged)}\g<2>", md)
    md = re.sub(r"(badge/Upstream%20repos-)\d+(-)", rf"\g<1>{n_all_repo}\g<2>", md)

    years = sorted({p["merged_year"] for p in merged if p.get("merged_year")})
    yr = years[0] if len(years) == 1 else (f"{years[0]}–{years[-1]}" if years else "")
    lines = ["<!-- STATS:BEGIN -->",
             f"**{len(merged)}** 个 PR 已被合并" + (f"（{yr} 年）" if yr else ""), ""]
    if up:
        links = "、".join(f"[`{r}`](https://github.com/{r})"
                          for r in sorted({p["repo"] for p in up}))
        lines.append(
            f"- **{len(up)}** 个合并进他人仓库（{links}）· 合计 "
            f"**+{fmt_int(sum(p['additions'] for p in up))} / "
            f"−{fmt_int(sum(p['deletions'] for p in up))}** 行 · "
            f"{sum(p['changed_files'] for p in up)} 个文件")
    if own:
        names = "、".join(sorted({p["name"] for p in own}))
        lines.append(f"- **{len(own)}** 个自有项目（`{names}`）的发布与加固 PR")
    lines += ["", pr_table(merged), "",
              "<sub>由 [`scripts/generate_stats.py`](./scripts/generate_stats.py) "
              "直连 GitHub REST API 生成，经 GitHub Actions 每日自动刷新 · 最后更新 "
              f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</sub>",
              "<!-- STATS:END -->"]
    return re.sub(r"<!-- STATS:BEGIN -->.*?<!-- STATS:END -->", "\n".join(lines), md, flags=re.S)


# ---------------------------------------------------------------- main
def main() -> int:
    ASSETS.mkdir(exist_ok=True)
    print(f"抓取 @{USER} 的 Pull Request ...")
    prs = collect(USER)
    merged = [p for p in prs if p["status"] == "merged"]
    print(f"  共 {len(prs)} 个 PR，其中已合并 {len(merged)} 个")

    for name, palette in (("light", LIGHT), ("dark", DARK)):
        (ASSETS / f"merged-prs-{name}.svg").write_text(
            card_merged(prs, palette), encoding="utf-8")
        print(f"  assets/merged-prs-{name}.svg")

    for stale in ("merged-prs.svg", "pr-overview.svg", "pr-calendar.svg"):
        f = ASSETS / stale
        if f.exists():
            f.unlink()
            print(f"  已移除旧资源 assets/{stale}")

    if README.exists():
        README.write_text(sync(README.read_text(encoding="utf-8"), prs), encoding="utf-8")
        print("  README.md 统计区间 / 徽章已更新")

    if "--offline" not in sys.argv:
        (ASSETS / "stats.json").write_text(
            json.dumps({"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "user": USER, "prs": prs}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        print("  assets/stats.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
