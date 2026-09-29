#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Merged PR Observatory — 静态资源生成器

只统计**已合并**的 Pull Request，生成一张可直接嵌入 GitHub README 的 SVG 卡片，
并把明细表格回写进 README.md 的标记区间。

设计原则：一个页面只讲一件事 —— 「有 7 个 PR 被合并了」。不做饼图、环形图、
热力图等装饰性图表，避免稀释重点。

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

# ---------------------------------------------------------------- 主题色
C = {
    "bg0": "#0A0E16", "bg1": "#101828", "border": "#1D2636",
    "text": "#EDF1F8", "text2": "#A8B3C6", "text3": "#63708A",
    "accent": "#8B7CFF", "accent2": "#22D3EE",
    "merged": "#34D399", "hair": "#1B2434",
}
FONT = ("-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',"
        "'Hiragino Sans GB','Microsoft YaHei',sans-serif")
MONO = "ui-monospace,'SF Mono',Menlo,Consolas,monospace"


# ---------------------------------------------------------------- 取数
def gh_api(path: str) -> dict:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req = urllib.request.Request(
            "https://api.github.com" + path,
            headers={"Authorization": "Bearer " + token,
                     "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28",
                     "User-Agent": "merged-pr-observatory"},
        )
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
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def collect(user: str):
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
                repos[repo_api] = {
                    "description": d.get("description") or "",
                    "language": d.get("language") or "Other",
                    "stars": d.get("stargazers_count") or 0,
                    "license": (d.get("license") or {}).get("spdx_id") or "",
                }
            except Exception as e:
                print(f"  ! repo {repo_api}: {e}", file=sys.stderr)
                repos[repo_api] = {"description": "", "language": "Other",
                                   "stars": 0, "license": ""}

        pr = gh_api(f"/repos/{repo_api}/pulls/{it['number']}")
        merged_at = pr.get("merged_at")
        created = parse_ts(pr.get("created_at"))
        closed = parse_ts(pr.get("closed_at"))
        end = parse_ts(merged_at) if merged_at else closed
        if merged_at:
            status = "merged"
        elif pr.get("state") == "open":
            status = "open"
        else:
            status = "closed"

        title = pr.get("title") or it.get("title") or ""
        owner, name = repo_api.split("/")
        prs.append({
            "repo": repo_api, "owner": owner, "name": name,
            "number": it["number"], "title": title, "status": status,
            "created": pr.get("created_at"), "merged_at": merged_at,
            "date": created.astimezone(TZ8).strftime("%Y-%m-%d") if created else "",
            "merged_date": parse_ts(merged_at).astimezone(TZ8).strftime("%Y-%m-%d") if merged_at else "",
            "additions": pr.get("additions") or 0,
            "deletions": pr.get("deletions") or 0,
            "changed_files": pr.get("changed_files") or 0,
            "commits": pr.get("commits") or 0,
            "labels": [l["name"] for l in (pr.get("labels") or [])],
            "url": pr.get("html_url") or f"https://github.com/{repo_api}/pull/{it['number']}",
            "hours": round((end - created).total_seconds() / 3600, 2) if (end and created) else None,
            "stars": repos[repo_api]["stars"],
            "lang": repos[repo_api]["language"],
        })

    prs.sort(key=lambda p: p["created"] or "")
    return prs


# ---------------------------------------------------------------- 工具
def esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def cut(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


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


def tx(x, y, s, size=12, fill=None, weight="normal", anchor="start",
       family=None, opacity=None, ls=None):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    o = f' opacity="{opacity}"' if opacity is not None else ""
    l = f' letter-spacing="{ls}"' if ls is not None else ""
    return (f'<text x="{x}" y="{y}" font-family="{family or FONT}" '
            f'font-size="{size}" fill="{fill or C["text2"]}" '
            f'font-weight="{weight}"{a}{o}{l}>{esc(s)}</text>')


def hairline(x1, y, x2):
    return (f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" '
            f'stroke="{C["hair"]}" stroke-width="1"/>')


# ---------------------------------------------------------------- 卡片
def common_theme(items: list[dict]) -> str:
    """从一组 PR 标题里提取共同主题词（小写比对，按首次出现顺序），避免写死文案。"""
    STOP = {"add", "the", "for", "and", "with", "into", "from", "when", "that",
            "not", "use", "make", "keep", "only", "new", "all", "fix", "feat",
            "docs", "test", "chore", "refactor", "perf", "build", "ci"}

    def body(t: str) -> str:
        if "):" in t:
            return t.split("):", 1)[1]
        if ":" in t:
            return t.split(":", 1)[1]
        return t

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
    common = [sets[0][k] for k in sets[0] if all(k in s2 for s2 in sets[1:])]
    return " ".join(common[:3])


def card_merged(prs: list[dict]) -> str:
    """单张卡片：一个焦点数字 + 上游合并故事 + 明细行。高度随内容自适应。"""
    W = 960
    L, R = 40, W - 40

    merged = [p for p in prs if p["status"] == "merged"]
    upstream = [p for p in merged if p["owner"] != USER]
    own = [p for p in merged if p["owner"] == USER]
    hours = sorted(p["hours"] for p in merged if p["hours"] is not None)
    median = hours[len(hours) // 2] if hours else None

    # 上游按仓库分组：同一个项目里的一组相关 PR 讲成一个故事
    groups: dict[str, list[dict]] = {}
    for p in upstream:
        groups.setdefault(p["repo"], []).append(p)
    groups = dict(sorted(groups.items(), key=lambda kv: -len(kv[1])))
    shown = list(groups.items())[:2]

    body: list[str] = []
    body.append(f'<circle cx="{L + 4}" cy="49" r="3" fill="{C["accent"]}"/>')
    body.append(tx(L + 15, 53, "MERGED PULL REQUESTS", 11, C["accent"], "700", ls="2.4"))
    body.append(tx(R, 53, f"github.com/{USER}", 11, C["text3"], "normal", "end", MONO))

    # 焦点数字
    n = str(len(merged))
    body.append(tx(L - 4, 138, n, 76, C["text"], "700", family=MONO, ls="-3"))
    body.append(tx(L + 46 * len(n) + 18, 138, "个 PR 已被合并", 17, C["text2"], "600", ls="-0.2"))
    sub = (f"{len(upstream)} 个提给他人仓库 · {len(own)} 个自有项目"
           + (f" · 中位交付 {fmt_dur(median)}" if median else ""))
    body.append(tx(L, 164, sub, 12.5, C["text3"]))
    body.append(hairline(L, 192, R))

    # 上游分组明细
    y, bottom = 220, 220
    for repo, items in shown:
        g_add = sum(p["additions"] for p in items)
        g_del = sum(p["deletions"] for p in items)
        g_files = sum(p["changed_files"] for p in items)
        body.append(tx(L, y, repo.upper(), 12.5, C["text"], "700", family=MONO, ls="0.6"))
        body.append(tx(R, y, f"{len(items)} 个 PR · +{fmt_int(g_add)} / −{fmt_int(g_del)} 行 · {g_files} 文件",
                        11.5, C["text3"], "normal", "end", MONO))
        theme = common_theme(items)
        if theme:
            body.append(tx(L, y + 19, f"共同主题：{theme} · {len(items)} 个相关联的 PR",
                            11.5, C["text3"]))
        first = y + 38
        for i, p in enumerate(sorted(items, key=lambda x: x["number"])):
            rb = first + i * 26
            body.append(tx(L + 2, rb, f"#{p['number']}", 11, C["text3"], "normal", "start", MONO))
            body.append(tx(L + 48, rb, cut(p["title"], 74), 12.5, C["text2"]))
            body.append(tx(R, rb, f"+{fmt_int(p['additions'])}", 12.5, C["merged"], "600", "end", MONO))
            bottom = rb
        y = first + (len(items) - 1) * 26 + 30

    if len(groups) > len(shown):
        rest = len(groups) - len(shown)
        body.append(tx(L, y, f"另有 {rest} 个他人仓库的合并 PR，见下表", 11.5, C["text3"]))
        bottom = y

    H = int(bottom + 26 + 44)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    head = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}" role="img" aria-label="已合并的 Pull Request">',
            '<defs>',
            f'<linearGradient id="cardbg" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0%" stop-color="{C["bg0"]}"/>'
            f'<stop offset="100%" stop-color="{C["bg1"]}"/></linearGradient>',
            f'<linearGradient id="topbar" x1="0" y1="0" x2="1" y2="0">'
            f'<stop offset="0%" stop-color="{C["accent"]}"/>'
            f'<stop offset="100%" stop-color="{C["accent2"]}"/></linearGradient>',
            f'<radialGradient id="glow" cx="0.10" cy="0.42" r="0.42">'
            f'<stop offset="0%" stop-color="{C["accent"]}" stop-opacity="0.20"/>'
            f'<stop offset="100%" stop-color="{C["accent"]}" stop-opacity="0"/></radialGradient>',
            '</defs>',
            f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="18" '
            f'fill="url(#cardbg)" stroke="{C["border"]}"/>',
            f'<rect x="0" y="0" width="{W}" height="200" fill="url(#glow)"/>',
            f'<rect x="0" y="0" width="{W}" height="3" rx="1.5" fill="url(#topbar)"/>']

    tail = [hairline(L, H - 42, R),
            tx(L, H - 19, "数据来源 GitHub REST API · 每日自动刷新", 11, C["text3"]),
            tx(R, H - 19, f"更新于 {stamp}", 11, C["text3"], "normal", "end", MONO),
            '</svg>']

    return "\n".join(head + body + tail) + "\n"


# ---------------------------------------------------------------- README
def pr_table(merged: list[dict]) -> str:
    rows = ["| 仓库 | PR | 标题 | 变更 | 文件 | 交付周期 | 合并日期 |",
            "|:--|--:|:--|--:|--:|--:|--:|"]
    for p in sorted(merged, key=lambda x: x["merged_at"] or "", reverse=True):
        # 标题里结尾的 (#NN) 与右侧 PR 列重复，去掉
        title = re.sub(r"\s*\(#\d+\)\s*$", "", p["title"])
        rows.append(
            f'| [`{p["name"]}`](https://github.com/{p["repo"]}) '
            f'| [#{p["number"]}]({p["url"]}) '
            f'| {cut(title, 72)} '
            f'| `+{fmt_int(p["additions"])}` `−{fmt_int(p["deletions"])}` '
            f'| {p["changed_files"]} | {fmt_dur(p["hours"])} | {p["merged_date"]} |'
        )
    return "\n".join(rows)


def sync(md: str, prs: list[dict]) -> str:
    merged = [p for p in prs if p["status"] == "merged"]
    up = [p for p in merged if p["owner"] != USER]
    own = [p for p in merged if p["owner"] == USER]
    up_repos = sorted({p["repo"] for p in up})
    n_all_repo = len({p["repo"] for p in prs})

    md = re.sub(r"(badge/Merged%20PRs-)\d+(-)", rf"\g<1>{len(merged)}\g<2>", md)
    md = re.sub(r"(badge/Upstream%20repos-)\d+(-)", rf"\g<1>{n_all_repo}\g<2>", md)

    lines = [f"<!-- STATS:BEGIN -->", f"**{len(merged)}** 个 PR 已被合并", ""]
    if up:
        links = "、".join(f"[`{r}`](https://github.com/{r})" for r in up_repos)
        lines.append(
            f"- **{len(up)}** 个提给他人仓库（{links}）· 合计 "
            f"**+{fmt_int(sum(p['additions'] for p in up))} / "
            f"−{fmt_int(sum(p['deletions'] for p in up))}** 行 · "
            f"{sum(p['changed_files'] for p in up)} 个文件")
    if own:
        names = "、".join(sorted({p["name"] for p in own}))
        lines.append(f"- **{len(own)}** 个自有项目（`{names}`）的发布与加固 PR")
    lines += ["", pr_table(merged), "",
              f"<sub>由 [`scripts/generate_stats.py`](./scripts/generate_stats.py) "
              f"直连 GitHub REST API 生成，经 GitHub Actions 每日自动刷新 · 最后更新 "
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

    (ASSETS / "merged-prs.svg").write_text(card_merged(prs), encoding="utf-8")
    print("  assets/merged-prs.svg")

    for stale in ("pr-overview.svg", "pr-calendar.svg"):
        f = ASSETS / stale
        if f.exists():
            f.unlink()
            print(f"  已移除旧卡片 assets/{stale}")

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
