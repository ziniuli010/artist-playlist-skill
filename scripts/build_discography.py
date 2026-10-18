#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_discography.py —— 为单个歌手生成「按专辑发行时间排列」的独立歌单文件。

输出三份（每人一目录，互不合并）：
    <歌手>/<歌手>_歌单.md    表格：序号 | 歌曲 | 专辑 | 发行年份，附筛选依据
    <歌手>/<歌手>_歌单.csv   同内容，Excel 可开
    <歌手>/<歌手>_导入.txt   "歌名 - 歌手" 逐行，供 QQ 音乐文字导入

用法：
    python3 build_discography.py "陈奕迅"
    python3 build_discography.py "The Weeknd" --types 专辑,EP
    python3 build_discography.py "Michael Jackson" --keep-all
"""

import argparse
import collections
import csv
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Referer": "https://music.163.com/"}
API = "https://music.163.com/api"

# 巡演/Live/精选/合辑/伴奏/翻唱等不属于「录音室专辑」的标记
DEFAULT_EXCLUDE = ("演唱会,音乐会,拉阔,现场,Concert,Tour,Dome,Unplugged,"
                   "精选,精选集,合辑,Greatest,Best of,Anthology,Collection,Essential,"
                   "Number Ones,Gold,Box set,Box Set,Vision,Ultimate,Definitive,Legends,"
                   "伴奏,Instrumental,Karaoke,翻唱,Tribute,Cover,Remix,Mix,Mixes,"
                   "Broadcast,FM Broadcast,Repackage,改版,原声带特辑,Highlights")
# "Live" 不能当子串匹配（会误杀《Live For Today》这类正式专辑），只在明确是现场录音时才算
LIVE_PATTERNS = (r"\(live\)", r"\[live\]", r"\blive\s+(in|at)\b", r"\blive\s+\d{4}\b",
                 r"-\s*live\b", r"\blive\s*$", r"\blive\s+(tour|session|version|album|ep|cd|show)\b")
# 版本修饰（不排除，只降级：撞歌时让正式版占位）
BAD_VER = ("remaster", "deluxe", "edited", "rough mix", "expanded", "bonus",
           "special edition", "anniversary", "complete edition", "重制", "纪念版")


def http_json(url, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"请求失败: {url}\n{last}")


def search_artist(name):
    d = http_json(f"{API}/search/get?s={urllib.parse.quote(name)}&type=100&limit=10")
    arts = (d.get("result") or {}).get("artists") or []
    if not arts:
        raise SystemExit(f"没搜到歌手：{name}")
    q = name.strip().lower()
    # 只考虑名字相关的候选，滤掉完全无关的推荐结果
    related = [a for a in arts if q in (a.get("name") or "").lower() or (a.get("name") or "").lower() in q]
    pool = related or arts
    top = max(pool, key=lambda a: a.get("musicSize") or 0)
    exact = [a for a in pool if (a.get("name") or "").strip().lower() == q]
    if exact:
        best = max(exact, key=lambda a: a.get("musicSize") or 0)
        # 同名的"粉丝号/山寨号"作品量远小于真正的艺人号，此时改用作品最多的候选
        pick = best if (best.get("musicSize") or 0) >= 0.5 * (top.get("musicSize") or 0) else top
    else:
        pick = top
    return pick["id"], pick["name"], arts


def list_albums(artist_id, max_pages=25):
    out, seen, offset, step = [], set(), 0, 100
    for _ in range(max_pages):
        d = http_json(f"{API}/artist/albums/{artist_id}?limit={step}&offset={offset}")
        batch = d.get("hotAlbums") or []
        new = 0
        for a in batch:
            key = ((a.get("name") or "").strip().lower(), a.get("publishTime") or 0)
            if key in seen:
                continue
            seen.add(key)
            out.append(a)
            new += 1
        if not d.get("more") or new == 0:
            break
        offset += step
        time.sleep(0.3)
    return out


def album_tracks(album_id):
    d = http_json(f"{API}/v1/album/{album_id}")
    rows = []
    for s in (d.get("songs") or []):
        rows.append({
            "no": s.get("no") or 0,
            "name": (s.get("name") or "").strip(),
            "artists": [x.get("name", "") for x in (s.get("ar") or []) if x.get("name")],
        })
    rows.sort(key=lambda x: x["no"] or 999)
    return rows


PUNCT = re.compile(r"[\s\u3000·・,，.。!！?？'\"“”‘’()（）\[\]【】<>《》:：;；/\\|\-—–_~～&＋+*#@]")
VER = re.compile(r"[\(（\[【].*?[\)）\]】]")


def norm(title):
    t = unicodedata.normalize("NFKC", title).lower()
    return PUNCT.sub("", VER.sub("", t))


def norm_album(name):
    """专辑名归一：去括号修饰、去版权年份标记，用于识别同专辑重复条目"""
    n = unicodedata.normalize("NFKC", name).lower()
    n = VER.sub("", n)
    n = re.sub(r"remaster(ed)?|deluxe|expanded|edition", "", n)
    return PUNCT.sub("", n)


def fmt_date(ms):
    if not ms:
        return "", ""
    t = time.strftime("%Y-%m-%d", time.localtime(ms / 1000))
    return t, t[:4]


def is_live_name(name):
    n = (name or "").lower()
    return any(re.search(p, n) for p in LIVE_PATTERNS)


def is_alt_name(name):
    n = (name or "").lower()
    return any(k in n for k in BAD_VER)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artist")
    ap.add_argument("--types", default="专辑")
    ap.add_argument("--min-tracks", type=int, default=0)
    ap.add_argument("--exclude", default=DEFAULT_EXCLUDE)
    ap.add_argument("--keep-all", action="store_true")
    ap.add_argument("--no-dedupe", action="store_true")
    ap.add_argument("--singers", default="primary", choices=["primary", "full"])
    ap.add_argument("--include-featured", action="store_true")
    ap.add_argument("--outdir", default="")
    ap.add_argument("--since", default="",
                    help="增量模式：只保留该日期(YYYY-MM-DD)及之后发行的专辑，用于补新专辑")
    ap.add_argument("--xalbum", default="",
                    help="精确排除指定专辑（子串匹配），逗号分隔，用于剔除曲库脏数据/精选残留")
    args = ap.parse_args()

    outdir = args.outdir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "歌单")
    aid, aname, _ = search_artist(args.artist)
    print(f"[{args.artist}] → {aname} (id={aid})", flush=True)

    albums = list_albums(aid)
    raw_n = len(albums)

    # 同一张专辑在曲库里可能有多个条目（版本不同、曲目数不同）：按归一化名字合并，留曲目最多的
    groups = collections.OrderedDict()
    for a in albums:
        groups.setdefault(norm_album(a.get("name") or ""), []).append(a)
    merged = []
    for _, grp in groups.items():
        # 优先留「非现场 + 非版本修饰」的条目，其次留曲目最多的
        # 否则《After Hours (Live At SoFi Stadium)》31 首会把正式版 14 首挤掉，再被 Live 规则整张删掉
        grp.sort(key=lambda a: (is_live_name(a.get("name")), is_alt_name(a.get("name")),
                                -(a.get("size") or 0)))
        best = dict(grp[0])
        best["_dupe_ids"] = [g["id"] for g in grp[1:]]
        merged.append(best)
    albums = merged

    want = {t.strip().lower() for t in args.types.replace("，", ",").split(",") if t.strip()}
    if "all" not in want:
        albums = [a for a in albums if (a.get("type") or "").strip().lower() in want]
    if args.min_tracks > 0:
        albums = [a for a in albums if (a.get("size") or 0) >= args.min_tracks]

    kw = [] if args.keep_all else [k.strip() for k in args.exclude.replace("，", ",").split(",") if k.strip()]
    dropped, kept_al = [], []
    for a in albums:
        name = (a.get("name") or "")
        hit = next((k for k in kw if k.lower() in name.lower()), None)
        if not hit and not args.keep_all:
            m = next((p for p in LIVE_PATTERNS if re.search(p, name.lower())), None)
            if m:
                hit = "Live 现场录音"
        (dropped.append((a, hit)) if hit else kept_al.append(a))
    albums = [a for a in kept_al if (a.get("size") or 0) > 0]

    if args.xalbum.strip():
        xs = [x.strip() for x in args.xalbum.replace("，", ",").split(",") if x.strip()]
        manual = []
        for a in albums:
            hit = next((x for x in xs if x and x.lower() in (a.get("name") or "").lower()), None)
            if hit:
                manual.append((a, f"手动排除:{hit}"))
        albums = [a for a in albums if not any(x and x.lower() in (a.get("name") or "").lower() for x in xs)]
        dropped.extend(manual)
    if args.since:
        cutoff = int(time.mktime(time.strptime(args.since, "%Y-%m-%d")) * 1000)
        albums = [a for a in albums if (a.get("publishTime") or 0) >= cutoff]
    albums.sort(key=lambda a: (a.get("publishTime") or 0, a.get("name") or ""))

    print(f"[{args.artist}] 原始 {raw_n} 张 → 合并重复条目后 {len(groups)} 张 → 入选 {len(albums)} 张", flush=True)

    order = [i for i, a in enumerate(albums) if not is_alt_name(a.get("name"))] + \
            [i for i, a in enumerate(albums) if is_alt_name(a.get("name"))]

    records, seen, zero_note = [], set(), []
    for step, idx in enumerate(order, 1):
        al = albums[idx]
        date, year = fmt_date(al.get("publishTime"))
        try:
            tracks = album_tracks(al["id"])
        except Exception as e:                       # noqa: BLE001
            print(f"  ! 跳过《{al['name']}》：{e}", flush=True)
            continue
        is_ost = any(k.lower() in (al.get("name") or "").lower()
                     for k in ("原声带", "原声", "OST", "Soundtrack"))
        if is_ost:
            # 原声带分两类：本人主导的电影原声（整张保留）与多人拼盘（本人只占一两首，属合辑）
            named = [t for t in tracks if t["artists"]]
            self_cnt = sum(1 for t in named
                           if any(aname == n or aname in n or n in aname for n in t["artists"]))
            ratio = self_cnt / len(tracks) if tracks else 0
            if ratio < 0.3:
                zero_note.append((al["name"], f"原声带拼盘，本人仅 {self_cnt}/{len(tracks)} 首"))
                print(f"  [{step:02d}/{len(albums)}] {date} {al['name'][:36]} (跳过：本人占比 {ratio:.0%})", flush=True)
                time.sleep(0.3)
                continue
        kept = other = dup = 0
        for t in tracks:
            if not t["name"]:
                continue
            names = t["artists"]
            if names and not args.include_featured and not is_ost:
                if not any(aname == n or aname in n or n in aname for n in names):
                    other += 1
                    continue
            key = norm(t["name"])
            if not args.no_dedupe and key in seen:
                dup += 1
                continue
            seen.add(key)
            label = (names[0] if names else aname) if args.singers == "primary" else "/".join(names or [aname])
            records.append({
                "title": t["name"], "album": al["name"], "date": date, "year": year,
                "atype": al.get("type") or "", "no": t["no"], "singer": label,
                "_sort": (al.get("publishTime") or 0, idx, t["no"]),
            })
            kept += 1
        if kept == 0:
            zero_note.append((al["name"], "整张非本人演唱" if other else "曲目与更早专辑重复"))
        print(f"  [{step:02d}/{len(albums)}] {date} {al['name'][:36]} ({kept}/{len(tracks)})", flush=True)
        time.sleep(0.3)

    if not records:
        raise SystemExit(f"{aname} 没有抓到曲目")

    records.sort(key=lambda r: r["_sort"])
    years = [r["year"] for r in records if r["year"]]
    used_albums = len({r["album"] for r in records})

    base = re.sub(r"[\\/:*?\"<>|]", "_", aname)
    d = os.path.join(outdir, base)
    os.makedirs(d, exist_ok=True)
    md_p = os.path.join(d, f"{base}_歌单.md")
    csv_p = os.path.join(d, f"{base}_歌单.csv")
    txt_p = os.path.join(d, f"{base}_导入.txt")

    with open(txt_p, "w", encoding="utf-8") as f:
        for r in records:
            f.write(f"{r['title']} - {r['singer']}\n")

    with open(csv_p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["序号", "歌曲", "专辑", "发行日期", "发行年份", "类型", "专辑内曲序", "演唱者"])
        for i, r in enumerate(records, 1):
            w.writerow([i, r["title"], r["album"], r["date"], r["year"], r["atype"], r["no"], r["singer"]])

    with open(md_p, "w", encoding="utf-8") as f:
        f.write(f"# {aname} · 专辑全曲歌单\n\n")
        f.write(f"共 **{len(records)}** 首，来自 **{used_albums}** 张专辑，"
                f"发行年份跨度 **{min(years)}–{max(years)}**。" if years else
                f"共 **{len(records)}** 首，来自 **{used_albums}** 张专辑。")
        f.write("\n\n")

        f.write("## 筛选依据\n\n")
        f.write(f"1. **只取专辑曲目**：专辑类型筛选为 `{args.types}`，"
                f"单曲（Single）、EP、精选集不进歌单。曲库共 {raw_n} 条记录，"
                f"合并同专辑重复条目后 {len(groups)} 张。\n")
        f.write("2. **排除非录音室专辑**：专辑名命中 "
                f"`{'/'.join(kw) if kw else '（未启用）'}` 的整张跳过，"
                f"包括巡演、现场、精选、合辑、伴奏版等。\n")
        f.write("3. **只保留本人演唱/参与**：合作合辑中他人演唱的曲目剔除；"
                "电影原声带例外，整张保留（配乐与客串插曲同属该作品）。\n")
        f.write("4. **跨专辑去重**：同一首歌在多张专辑出现时，只保留**最早**专辑中的版本，"
                "避免按时间通听时重复；重制版、混音版撞歌时由正式版占位。\n")
        f.write("5. **排序**：先按专辑发行日期升序，专辑内按原始曲序，"
                "得到一条从出道到最新的时间线。\n\n")

        if dropped:
            f.write(f"**被排除的专辑（{len(dropped)} 张）**：" +
                    "、".join(f"《{a['name']}》" for a, _ in dropped) + "\n\n")
        if zero_note:
            f.write(f"**无曲目入选的专辑（{len(zero_note)} 张）**：" +
                    "；".join(f"《{n}》（{why}）" for n, why in zero_note) + "\n\n")

        f.write("## 曲目清单\n\n")
        f.write("| # | 歌曲 | 专辑 | 发行年份 |\n|---:|---|---|---|\n")
        for i, r in enumerate(records, 1):
            title = r["title"].replace("|", "／")
            album = r["album"].replace("|", "／")
            f.write(f"| {i} | {title} | {album} | {r['year'] or '—'} |\n")

    print(f"[{aname}] ✅ {len(records)} 首 / {used_albums} 张专辑 → {md_p}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
