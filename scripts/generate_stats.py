#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PR Contribution Observatory — 静态资源生成器

从 GitHub REST API 抓取指定用户的全部 Pull Request，生成两张可直接嵌入
GitHub README 的 SVG 卡片，并把统计表格回写进 README.md 的标记区间。

用法：
    python scripts/generate_stats.py                 # 本地（走 gh CLI 鉴权）
    GITHUB_TOKEN=xxx python scripts/generate_stats.py # CI（Actions 自动注入）

只依赖标准库，无需 pip install。
"""

from __future__ import annotations

import calendar as _calendar
import json
import math
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

USER = "sjr666666"
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
README = ROOT / "README.md"

# ---------------------------------------------------------------- 主题色
C = {
    "bg0": "#0B0F17", "bg1": "#111A29", "border": "#1E2836",
    "text": "#E8EDF5", "text2": "#98A4B8", "text3": "#66738A",
    "accent": "#8B7CFF", "accent2": "#22D3EE",
    "merged": "#34D399", "open": "#60A5FA", "closed": "#FB7185",
    "grid": "#1B2434", "empty": "#182130",
}
FONT = ("-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',"
        "'Hiragino Sans GB','Microsoft YaHei',sans-serif")
MONO = "ui-monospace,'SF Mono',Menlo,Consolas,monospace"
STATUS_CN = {"merged": "已合并", "open": "待审核", "closed": "已关闭"}
# 固定按 UTC+8 统计「日 / 小时」口径，保证本地与 CI 跑出的结果一致
TZ_LOCAL = timezone(timedelta(hours=8))


# ---------------------------------------------------------------- 取数
def gh_api(path: str) -> dict:
    """CI 走 urllib + GITHUB_TOKEN；本地走 gh CLI。"""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req = urllib.request.Request(
            "https://api.github.com" + path,
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "pr-observatory",
            },
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


def parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def collect(user: str) -> tuple[list[dict], dict]:
    """返回 (prs, repos_meta)。离线模式直接读 assets/stats.json 缓存。"""
    cache = ASSETS / "stats.json"
    if "--offline" in sys.argv and cache.exists():
        print(f"  [offline] 读取缓存 {cache.relative_to(ROOT)}")
        return json.loads(cache.read_text(encoding="utf-8"))["prs"], {}

    raw = search_prs(user)
    repos: dict[str, dict] = {}
    prs: list[dict] = []

    for it in raw:
        repo_api = it["repository_url"].split("/repos/")[-1]
        owner, name = repo_api.split("/")
        if repo_api not in repos:
            try:
                d = gh_api(f"/repos/{repo_api}")
                repos[repo_api] = {
                    "full_name": d.get("full_name") or repo_api,
                    "description": d.get("description") or "",
                    "language": d.get("language") or "Other",
                    "stars": d.get("stargazers_count") or 0,
                    "forks": d.get("forks_count") or 0,
                    "license": (d.get("license") or {}).get("spdx_id") or "",
                    "url": d.get("html_url") or f"https://github.com/{repo_api}",
                }
            except Exception as e:  # 单个仓库失败不阻断整体
                print(f"  ! repo {repo_api}: {e}", file=sys.stderr)
                repos[repo_api] = {"full_name": repo_api, "description": "",
                                   "language": "Other", "stars": 0, "forks": 0,
                                   "license": "", "url": f"https://github.com/{repo_api}"}

        pr = gh_api(f"/repos/{repo_api}/pulls/{it['number']}")
        merged_at = pr.get("merged_at")
        status = "merged" if merged_at else ("open" if pr.get("state") == "open" else "closed")
        created = parse_ts(pr.get("created_at"))
        end = parse_ts(merged_at or pr.get("closed_at"))
        title = pr.get("title") or it.get("title") or ""
        typ = "other"
        if ":" in title:
            head = title.split(":", 1)[0].strip().lower()
            for k in ("fix", "feat", "docs", "test", "chore", "perf",
                      "build", "refactor", "ci"):
                if head == k or head.startswith(k + "("):
                    typ = k
                    break

        prs.append({
            "repo": repo_api,
            "number": it["number"],
            "title": title,
            "status": status,
            "type": typ,
            "draft": bool(pr.get("draft")),
            "created": pr.get("created_at"),
            "local_day": created.astimezone(TZ_LOCAL).strftime("%Y-%m-%d") if created else "",
            "local_hour": created.astimezone(TZ_LOCAL).hour if created else 0,
            "additions": pr.get("additions") or 0,
            "deletions": pr.get("deletions") or 0,
            "changed_files": pr.get("changed_files") or 0,
            "commits": pr.get("commits") or 0,
            "labels": [l["name"] for l in (pr.get("labels") or [])],
            "url": pr.get("html_url") or f"https://github.com/{repo_api}/pull/{it['number']}",
            "hours": round((end - created).total_seconds() / 3600, 2) if (end and created) else None,
            "stars": repos[repo_api]["stars"],
            "lang": repos[repo_api]["language"],
            "date": created.astimezone(TZ_LOCAL).strftime("%Y-%m-%d") if created else "",
        })

    prs.sort(key=lambda p: p["created"] or "")
    return prs, repos


# ---------------------------------------------------------------- 工具
def esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def fmt_int(n: int) -> str:
    return f"{n:,}"


def fmt_compact(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}".rstrip("0").rstrip(".") + "k"
    return str(n)


def fmt_dur(h: float | None) -> str:
    if h is None:
        return "—"
    if h < 1:
        return f"{max(1, round(h * 60))} 分"
    if h < 24:
        return f"{h:.1f}".rstrip("0").rstrip(".") + " 时"
    d = h / 24
    return (f"{d:.1f}".rstrip("0").rstrip(".") if d < 10 else str(round(d))) + " 天"


def nice_step(raw: float) -> float:
    mag = 10 ** int(math.floor(math.log10(max(raw, 1))))
    for m in (1, 2, 2.5, 5, 10):
        if m * mag >= raw:
            return m * mag
    return mag * 10


def svg_shell(w: int, h: int, body: str, gid: str = "g") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="PR Contribution Observatory">\n'
        f'<defs>\n'
        f'<linearGradient id="{gid}bg" x1="0" y1="0" x2="1" y2="1">\n'
        f'<stop offset="0%" stop-color="{C["bg0"]}"/>\n'
        f'<stop offset="100%" stop-color="{C["bg1"]}"/>\n'
        f'</linearGradient>\n'
        f'<linearGradient id="{gid}bar" x1="0" y1="0" x2="1" y2="0">\n'
        f'<stop offset="0%" stop-color="{C["accent"]}"/>\n'
        f'<stop offset="100%" stop-color="{C["accent2"]}"/>\n'
        f'</linearGradient>\n'
        f'<linearGradient id="{gid}hl" x1="0" y1="0" x2="0" y2="1">\n'
        f'<stop offset="0%" stop-color="{C["accent"]}" stop-opacity="0.16"/>\n'
        f'<stop offset="100%" stop-color="{C["accent"]}" stop-opacity="0"/>\n'
        f'</linearGradient>\n'
        f'</defs>\n'
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="16" '
        f'fill="url(#{gid}bg)" stroke="{C["border"]}"/>\n'
        f'<rect x="0" y="0" width="{w}" height="3" rx="1.5" fill="url(#{gid}bar)"/>\n'
        f'{body}\n</svg>\n'
    )


def tx(x, y, s, size=12, fill=None, weight="normal", anchor="start",
       family=None, opacity=None, ls=None):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    o = f' opacity="{opacity}"' if opacity is not None else ""
    l = f' letter-spacing="{ls}"' if ls is not None else ""
    return (f'<text x="{x}" y="{y}" font-family="{family or FONT}" '
            f'font-size="{size}" fill="{fill or C["text2"]}" '
            f'font-weight="{weight}"{a}{o}{l}>{esc(s)}</text>')


# ---------------------------------------------------------------- 卡片 1：总览
def card_overview(prs: list[dict], repos: dict, styles: str) -> str:
    """960 × 430：标题 / KPI / 仓库分布 / 状态环 / 页脚"""
    W, H = 960, 462
    total = len(prs)
    merged = sum(1 for p in prs if p["status"] == "merged")
    open_ = sum(1 for p in prs if p["status"] == "open")
    closed = sum(1 for p in prs if p["status"] == "closed")
    add = sum(p["additions"] for p in prs)
    dele = sum(p["deletions"] for p in prs)
    files = sum(p["changed_files"] for p in prs)
    commits = sum(p["commits"] for p in prs)
    n_repos = len({p["repo"] for p in prs})
    rate = round(merged / total * 100) if total else 0
    big = len({p["repo"] for p in prs if p["stars"] >= 10000})
    days = sorted(p["created"] for p in prs if p["created"])
    d0 = days[0][:10].replace("-", ".") if days else "—"
    d1 = days[-1][:10].replace("-", ".") if days else "—"

    b = [styles]
    b.append(f'<line x1="28" y1="92" x2="{W - 28}" y2="92" stroke="{C["border"]}"/>')
    b.append(tx(28, 46, "PR Contribution Observatory", 21, C["text"], "700", ls="-0.4"))
    b.append(tx(28, 70, f"Pull Request 贡献总览 · {d0} — {d1}", 12.5, C["text3"]))
    b.append(tx(W - 28, 44, "@" + USER, 14, C["accent"], "600", "end", MONO))
    b.append(tx(W - 28, 68, "github.com/" + USER, 12, C["text3"], "normal", "end", MONO))

    # ---- KPI 行
    kpis = [
        ("PULL REQUEST", fmt_int(total), f"{n_repos} 个仓库 · {fmt_int(commits)} 个提交", C["accent"]),
        ("已合并", f"{merged} / {total}", f"合并率 {rate}% · 待审 {open_} · 关闭 {closed}", C["merged"]),
        ("代码变更", f"{fmt_compact(add + dele)}", f"+{fmt_compact(add)} / −{fmt_compact(dele)} 行 · {files} 文件", C["accent2"]),
        ("上游仓库", fmt_int(n_repos), f"其中 {big} 个万星项目", C["open"]),
    ]
    colw = (W - 56) / 4
    for i, (lab, val, note, col) in enumerate(kpis):
        x = 28 + i * colw
        if i:
            b.append(f'<line x1="{x - 14:.0f}" y1="116" x2="{x - 14:.0f}" y2="176" '
                     f'stroke="{C["border"]}"/>')
        b.append(f'<rect x="{x:.0f}" y="118" width="3" height="14" rx="1.5" fill="{col}"/>')
        b.append(tx(x + 11, 129, lab, 11, C["text3"], "600", ls="0.6"))
        b.append(tx(x, 166, val, 30, C["text"], "700", family=MONO, ls="-1"))
        b.append(tx(x, 187, note, 11.5, C["text3"]))
    b.append(f'<line x1="28" y1="208" x2="{W - 28}" y2="208" stroke="{C["border"]}"/>')

    # ---- 左：仓库分布
    agg: dict[str, dict] = {}
    for p in prs:
        a = agg.setdefault(p["repo"], {"merged": 0, "open": 0, "closed": 0, "size": 0,
                                       "stars": p["stars"]})
        a[p["status"]] += 1
        a["size"] += p["additions"] + p["deletions"]
    top = sorted(agg.items(), key=lambda kv: (-(kv[1]["merged"] + kv[1]["open"] + kv[1]["closed"]),
                                              -kv[1]["size"]))[:6]
    mx = max((sum(v[k] for k in ("merged", "open", "closed")) for _, v in top), default=1)
    b.append(tx(28, 234, "仓库分布", 13, C["text"], "600"))
    b.append(tx(92, 234, "按 PR 数量", 11, C["text3"]))
    bx, bw = 232, 268
    for i, (repo, v) in enumerate(top):
        n = v["merged"] + v["open"] + v["closed"]
        y = 254 + i * 25
        name = repo.split("/")[1]
        if len(name) > 17:
            name = name[:16] + "…"
        b.append(tx(28, y + 11, name, 12, C["text2"], family=MONO))
        b.append(f'<rect x="{bx}" y="{y + 2}" width="{bw}" height="14" rx="7" fill="{C["empty"]}"/>')
        run = bx
        for k in ("merged", "open", "closed"):
            if not v[k]:
                continue
            seg = bw * (v[k] / mx)
            b.append(f'<rect x="{run:.1f}" y="{y + 2}" width="{max(seg, 2):.1f}" height="14" '
                     f'rx="7" fill="{C[k]}" fill-opacity="0.92"/>')
            run += seg
        b.append(tx(bx + bw + 12, y + 13, f"{n}", 12.5, C["text"], "600", family=MONO))

    # ---- 右：状态环
    cx, cy, r, sw = 726, 302, 54, 20
    circ = 2 * 3.141592653589793 * r
    b.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{C["empty"]}" stroke-width="{sw}"/>')
    off = 0.0
    for k in ("merged", "open", "closed"):
        val = {"merged": merged, "open": open_, "closed": closed}[k]
        if not val:
            continue
        length = circ * val / total
        gap = 3 if total > 1 else 0
        b.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{C[k]}" '
                 f'stroke-width="{sw}" stroke-linecap="round" '
                 f'stroke-dasharray="{max(length - gap, 0.6):.2f} {circ - length + gap:.2f}" '
                 f'stroke-dashoffset="{-off:.2f}" '
                 f'transform="rotate(-90 {cx} {cy})"/>')
        off += length
    b.append(tx(cx, cy + 4, str(total), 26, C["text"], "700", "middle", MONO, ls="-1"))
    b.append(tx(cx, cy + 22, "PRs", 10.5, C["text3"], "normal", "middle", MONO, ls="1"))
    b.append(tx(804, 268, "状态构成", 12.5, C["text"], "600"))
    for i, k in enumerate(("merged", "open", "closed")):
        val = {"merged": merged, "open": open_, "closed": closed}[k]
        y = 292 + i * 24
        b.append(f'<rect x="804" y="{y}" width="9" height="9" rx="2.5" fill="{C[k]}"/>')
        b.append(tx(821, y + 8.5, STATUS_CN[k], 12, C["text2"]))
        b.append(tx(876, y + 8.5, f"{(val / total * 100):.0f}%", 11, C["text3"], "normal", "start", MONO))
        b.append(tx(W - 28, y + 8.5, str(val), 12.5, C["text"], "600", "end", MONO))

    # ---- 页脚
    b.append(f'<line x1="28" y1="{H - 42}" x2="{W - 28}" y2="{H - 42}" stroke="{C["border"]}"/>')
    b.append(tx(28, H - 22, "数据来源 GitHub REST API · 由 scripts/generate_stats.py 自动生成",
                11, C["text3"]))
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    b.append(tx(W - 28, H - 22, f"更新于 {stamp}", 11, C["text3"], "normal", "end", MONO))
    return svg_shell(W, H, "\n".join(b), "ov")


# ---------------------------------------------------------------- 卡片 2：日历 + 节律
def card_calendar(prs: list[dict], styles: str) -> str:
    """960 × 300：双月日历 + 提交节律"""
    W, H = 960, 350
    counts: dict[str, int] = {}
    hours = [0] * 24
    for p in prs:
        counts[p["local_day"]] = counts.get(p["local_day"], 0) + 1
        hours[p["local_hour"]] += 1
    days = sorted(p["created"] for p in prs if p["created"])
    t0 = datetime.strptime(days[0][:10], "%Y-%m-%d") if days else datetime.now()
    t1 = datetime.strptime(days[-1][:10], "%Y-%m-%d") if days else datetime.now()
    today = datetime.now().strftime("%Y-%m-%d")

    b = [styles]
    b.append(f'<line x1="28" y1="72" x2="{W - 28}" y2="72" stroke="{C["border"]}"/>')
    b.append(tx(28, 42, "贡献日历", 16, C["text"], "700", ls="-0.3"))
    b.append(tx(96, 42, "每个方块 = 一天，颜色越深当日创建的 PR 越多", 11.5, C["text3"]))

    cell, gap = 24, 4
    grid_w = 7 * cell + 6 * gap
    lead0, x0 = 28, 28
    months = []
    cur = datetime(t0.year, t0.month, 1)
    stop = datetime(t1.year, t1.month, 1)
    while cur <= stop:
        months.append(cur)
        cur = datetime(cur.year + (cur.month == 12), (cur.month % 12) + 1, 1)

    for mi, m in enumerate(months):
        mx0 = x0 + mi * (grid_w + 46)
        ndays = _calendar.monthrange(m.year, m.month)[1]
        lead = datetime(m.year, m.month, 1).weekday()
        rows = -(-(lead + ndays) // 7)
        msum = sum(counts.get(f"{m.year}-{m.month:02d}-{d:02d}", 0) for d in range(1, ndays + 1))
        b.append(tx(mx0, 100, f"{m.year} 年 {m.month} 月", 12.5, C["text"], "600"))
        b.append(tx(mx0 + grid_w, 100, f"{msum} 个 PR", 11, C["text3"], "normal", "end", MONO))
        for wd, lab in enumerate("一二三四五六日"):
            b.append(tx(mx0 + wd * (cell + gap) + cell / 2, 119, lab, 10,
                        C["text3"], "normal", "middle", MONO))
        for i in range(rows * 7):
            dn = i - lead + 1
            gx = mx0 + (i % 7) * (cell + gap)
            gy = 128 + (i // 7) * (cell + gap)
            if dn < 1 or dn > ndays:
                continue
            key = f"{m.year}-{m.month:02d}-{dn:02d}"
            c = counts.get(key, 0)
            if c == 0:
                fill, op = C["empty"], "1"
            elif c == 1:
                fill, op = "#3B3486", "1"
            elif c == 2:
                fill, op = "#5B52D8", "1"
            elif c == 3:
                fill, op = "#8B7CFF", "1"
            else:
                fill, op = "#B9AEFF", "1"
            if key > today:
                op = "0.3"
            b.append(f'<rect x="{gx}" y="{gy}" width="{cell}" height="{cell}" rx="7" '
                     f'fill="{fill}" fill-opacity="{op}"><title>{key} · '
                     f'{c if c else "无"} PR</title></rect>')

    # ---- 右侧：提交节律
    rx = x0 + len(months) * (grid_w + 46) + 24
    rw = W - 28 - rx
    b.append(tx(rx, 100, "提交节律", 12.5, C["text"], "600"))
    b.append(tx(rx + rw, 100, "本地时间", 11, C["text3"], "normal", "end", MONO))
    bh, base = 110, 262
    mx = max(hours) or 1
    bw = rw / 24 - 3
    for i, v in enumerate(hours):
        h = max(3, bh * v / mx) if v else 3
        bx = rx + i * (bw + 3)
        col = f"url(#calbar)" if v else C["empty"]
        b.append(f'<rect x="{bx:.1f}" y="{base - h:.1f}" width="{bw:.1f}" height="{h:.1f}" '
                 f'rx="{min(3, bw / 2):.1f}" fill="{col}"><title>{i:02d}:00 · {v} 个 PR</title></rect>')
    b.append(f'<line x1="{rx}" y1="{base + 1}" x2="{W - 28}" y2="{base + 1}" stroke="{C["border"]}"/>')
    for i, lab in ((0, "00"), (6, "06"), (12, "12"), (18, "18"), (23, "23")):
        anchor = "start" if i == 0 else ("end" if i == 23 else "middle")
        b.append(tx(rx + i * (bw + 3) + bw / 2, base + 17, lab, 10, C["text3"], "normal",
                    anchor, MONO))
    active = len(counts)
    peak = hours.index(mx)
    b.append(tx(rx, 306, f"活跃 {active} 天 · 高峰 {peak:02d}:00 前后", 11.5, C["text2"]))
    b.append(tx(rx, 326, "颜色越深 = 当天创建的 PR 越多", 10.5, C["text3"]))

    b.append(tx(28, 326, "少", 10.5, C["text3"], "normal", "start", MONO))
    for i, fill in enumerate((C["empty"], "#3B3486", "#5B52D8", "#8B7CFF", "#B9AEFF")):
        b.append(f'<rect x="{44 + i * 20}" y="317" width="13" height="13" rx="4" fill="{fill}"/>')
    b.append(tx(150, 326, "多", 10.5, C["text3"], "normal", "start", MONO))
    return svg_shell(W, H, "\n".join(b), "cal")


# ---------------------------------------------------------------- README 表格
def pr_table(prs: list[dict]) -> str:
    rows = ["| 仓库 | PR | 标题 | 变更 | 文件 | 耗时 | 状态 | 创建 |",
            "|:--|--:|:--|--:|--:|--:|:--|--:|"]
    for p in sorted(prs, key=lambda x: x["created"] or "", reverse=True):
        name = p["repo"]
        title = p["title"]
        if len(title) > 62:
            title = title[:61] + "…"
        rows.append(
            f'| [{name}](https://github.com/{name}) | [#{p["number"]}]({p["url"]}) '
            f'| {title} '
            f'| +{fmt_int(p["additions"])} −{fmt_int(p["deletions"])} '
            f'| {p["changed_files"]} | {fmt_dur(p["hours"])} '
            f'| {STATUS_CN[p["status"]]} | {p["date"]} |'
        )
    return "\n".join(rows)


def portrait(prs: list[dict]) -> str:
    """自动生成的「贡献画像」区块 —— 所有数字均由数据推导，避免手工维护后与卡片打架。"""
    total = len(prs)
    merged = sum(1 for p in prs if p["status"] == "merged")
    open_ = sum(1 for p in prs if p["status"] == "open")
    upstream = [p for p in prs if p["repo"].split("/")[0] != USER]
    big = len({p["repo"] for p in prs if p["stars"] >= 10000})
    fix = sum(1 for p in prs if p["type"] == "fix")
    feat = sum(1 for p in prs if p["type"] == "feat")
    s_bucket = sum(1 for p in prs
                   if 20 <= p["additions"] + p["deletions"] < 100)
    small_files = sum(1 for p in prs if p["changed_files"] <= 3)
    biggest = max(prs, key=lambda p: p["additions"] + p["deletions"])

    agg: dict[str, int] = {}
    for p in prs:
        agg[p["repo"]] = agg.get(p["repo"], 0) + 1
    top = sorted(agg.items(), key=lambda kv: (-kv[1], kv[0]))
    dist = " · ".join(f"`{r.split('/')[1]}` {n}" for r, n in top)

    return (
        "<!-- PORTRAIT:BEGIN -->\n"
        "<table>\n"
        '<tr><td width="50%" valign="top">\n\n'
        f"**我最常做的事是「修边界」**\n\n"
        f"在 {total} 个 PR 里，`fix` {fix} 个、`feat` {feat} 个。`fix` 集中在三类高频区："
        f"参数校验的静默失败、并发读改写丢数据、跨平台（Windows / 容器）行为不一致。\n\n"
        "</td><td width=\"50%\" valign=\"top\">\n\n"
        f"**小步提交，便于审查与回滚**\n\n"
        f"变更规模落在 S 档（20–100 行）的有 {s_bucket} 个；{small_files} 个 PR 只碰不超过 3 个文件。"
        f"单笔最大变更来自 `{biggest['repo'].split('/')[1]} #{biggest['number']}`"
        f"（{biggest['changed_files']} 个文件、{fmt_compact(biggest['additions'] + biggest['deletions'])} 行）。\n\n"
        "</td></tr>\n"
        '<tr><td valign="top">\n\n'
        f"**向上游提出，而不是只写自己的仓库**\n\n"
        f"{total} 个 PR 中有 {len(upstream)} 个提给非本人仓库，覆盖 Agent 运行时、前端框架、"
        f"测试框架与企业级工具链，其中 {big} 个是万星以上项目。\n\n"
        "</td><td valign=\"top\">\n\n"
        f"**按仓库的贡献分布**\n\n{dist}\n\n"
        "</td></tr>\n"
        "</table>\n"
        "<!-- PORTRAIT:END -->"
    )


def sync_badges(md: str, prs: list[dict]) -> str:
    """同步顶部 shields.io 徽章里的数字，避免与卡片/表格不一致。"""
    total = len(prs)
    merged = sum(1 for p in prs if p["status"] == "merged")
    nrepo = len({p["repo"] for p in prs})
    md = re.sub(r"(Pull%20Requests-)\d+(-)", rf"\g<1>{total}\g<2>", md)
    md = re.sub(r"(badge/Merged-)\d+(-)", rf"\g<1>{merged}\g<2>", md)
    md = re.sub(r"(Upstream%20Repos-)\d+(-)", rf"\g<1>{nrepo}\g<2>", md)
    return md


def inject_readme(prs: list[dict]) -> None:
    if not README.exists():
        return
    md = README.read_text(encoding="utf-8")
    tbl = pr_table(prs)
    total, merged = len(prs), sum(1 for p in prs if p["status"] == "merged")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    block = (f"<!-- STATS:BEGIN -->\n"
             f"**{total}** 个 Pull Request · **{merged}** 个已合并 · "
             f"覆盖 **{len({p['repo'] for p in prs})}** 个仓库\n\n"
             f"{tbl}\n\n"
             f"<sub>最后更新 {stamp} · 由 `scripts/generate_stats.py` 自动生成</sub>\n"
             f"<!-- STATS:END -->")
    md = re.sub(r"<!-- STATS:BEGIN -->.*?<!-- STATS:END -->", block, md, flags=re.S)

    if "<!-- PORTRAIT:BEGIN -->" in md:
        md = re.sub(r"<!-- PORTRAIT:BEGIN -->.*?<!-- PORTRAIT:END -->",
                    portrait(prs), md, flags=re.S)
    md = sync_badges(md, prs)

    README.write_text(md, encoding="utf-8")
    print("  README.md 统计区间 / 画像 / 徽章已更新")


# ---------------------------------------------------------------- main
def main() -> int:
    ASSETS.mkdir(exist_ok=True)
    print(f"抓取 @{USER} 的 Pull Request ...")
    prs, repos = collect(USER)
    print(f"  共 {len(prs)} 个 PR · {len(repos)} 个仓库")

    styles = (f'<style>text{{font-variant-numeric:tabular-nums}}</style>\n'
              f'<linearGradient id="calbar" x1="0" y1="1" x2="0" y2="0">'
              f'<stop offset="0%" stop-color="{C["accent"]}"/>'
              f'<stop offset="100%" stop-color="{C["accent2"]}"/></linearGradient>')

    (ASSETS / "pr-overview.svg").write_text(card_overview(prs, repos, styles), encoding="utf-8")
    (ASSETS / "pr-calendar.svg").write_text(card_calendar(prs, styles), encoding="utf-8")
    print("  assets/pr-overview.svg")
    print("  assets/pr-calendar.svg")

    inject_readme(prs)

    if "--offline" not in sys.argv:
        (ASSETS / "stats.json").write_text(
            json.dumps({"generated_at": datetime.now(timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "user": USER, "prs": prs},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        print("  assets/stats.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
