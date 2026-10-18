#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_discography.py —— 为单个歌手生成「按专辑发行时间排列」的独立歌单文件。

输出三份（每人一目录，互不合并）：
    <歌手>/<歌手>_歌单.md    表格：序号 | 歌曲 | 专辑 | 发行年份，附筛选依据
    <歌手>/<歌手>_歌单.csv   同内容，Excel 可开
    <歌手>/<歌手>_导入.txt   "歌名 - 歌手" 逐行，供音乐平台文字导入

用法：
    python3 build_discography.py "陈奕迅"
    python3 build_discography.py "The Weeknd" --types 专辑,EP
    python3 build_discography.py "五月天" --since 2024-01-01
    python3 build_discography.py "方大同" --source musicbrainz

设计说明：
    网络请求由 scripts/sources/* 提供，本文件的 build_records() 是纯逻辑
    （筛选 → 合并 → 去重 → 排序），可在无网络环境下用假数据做回归测试。
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

# 兼容「直接运行脚本」与「作为包安装」两种场景
try:
    from sources import get_source, SourceError
except ImportError:                                   # pragma: no cover
    from .sources import get_source, SourceError

VERSION = "1.1.0"

# 巡演/Live/精选/合辑/伴奏/翻唱等不属于「录音室专辑」的标记
DEFAULT_EXCLUDE = ("演唱会,音乐会,拉阔,现场,Concert,Tour,Dome,Unplugged,"
                   "精选,精选集,合辑,Greatest,Best of,Anthology,Essential,"
                   "Number Ones,Box set,Box Set,Ultimate,Definitive,"
                   "伴奏,Instrumental,Karaoke,翻唱,Tribute,Cover,Remix,Mix,Mixes,"
                   "Broadcast,FM Broadcast,Repackage,改版,原声带特辑,Highlights")

# "Live" 判定：前后不能是英文字母，这样能抓住「Live全纪录」「D.N.A LIVE」这类紧邻中文/标点的写法，
# 又不会误伤 ALIVE / Alive / Deliver。个别以 Live 开头的正式专辑放进白名单。
LIVE_PATTERN = r"(?<![a-z])live(?![a-z])"
LIVE_WHITELIST = ("live for today",)

# 版本修饰：不排除，只降级（撞歌时让正式版占位）
BAD_VER = ("remaster", "deluxe", "edited", "rough mix", "expanded", "bonus",
           "special edition", "anniversary", "complete edition", "重制", "纪念版")

# 原声带：本人占比达标的整张保留
OST_MARKS = ("原声带", "原声", "OST", "Soundtrack")
OST_MIN_RATIO = 0.3
COMPILATION_MIN_RATIO = 0.2      # 非原声带专辑：曲目≥8 且本人占比低于此值 → 视为拼盘
COMPILATION_MIN_TRACKS = 8

DEFAULTS = {
    "types": "专辑",
    "min_tracks": 0,
    "exclude": DEFAULT_EXCLUDE,
    "keep_all": False,
    "no_dedupe": False,
    "singers": "primary",
    "include_featured": False,
    "since": "",
    "xalbum": "",
    "lenient_artists": False,
}

PUNCT = re.compile(r"[\s\u3000·・,，.。!！?？'\"“”‘’()（）\[\]【】<>《》:：;；/\\|\-—–_~～&＋+*#@]")
VER = re.compile(r"[\(（\[【].*?[\)）\]】]")


# ---------------------------------------------------------------- 文本归一

def norm(title):
    """用于去重的宽松规范化：去版本后缀 + 去标点 + 全角转半角"""
    t = unicodedata.normalize("NFKC", title).lower()
    return PUNCT.sub("", VER.sub("", t))


def norm_album(name):
    """专辑名归一：去括号修饰、去版本词，用于识别同专辑的重复条目"""
    n = unicodedata.normalize("NFKC", name).lower()
    n = VER.sub("", n)
    n = re.sub(r"remaster(ed)?|deluxe|expanded|edition", "", n)
    return PUNCT.sub("", n)


def is_live_name(name):
    n = (name or "").lower()
    if any(w in n for w in LIVE_WHITELIST):
        return False
    return re.search(LIVE_PATTERN, n) is not None


def is_alt_name(name):
    n = (name or "").lower()
    return any(k in n for k in BAD_VER)


def fmt_date(ms):
    if not ms:
        return "", ""
    t = time.strftime("%Y-%m-%d", time.localtime(ms / 1000))
    return t, t[:4]


def _csv(v):
    """把逗号分隔参数切成列表，兼容中文逗号"""
    return [x.strip() for x in (v or "").replace("，", ",").split(",") if x.strip()]


# ---------------------------------------------------------------- 核心逻辑（纯函数）

def build_records(albums, fetch_tracks, aname, opts=None, log=None):
    """筛选 → 合并 → 去重 → 排序，返回 (records, dropped, zero_note, stats)。

    albums      : [{id,name,type,size,publishTime}]
    fetch_tracks: callable(album_id) -> [{no,name,artists[]}]
    aname       : 官方艺人名，用于演唱者过滤
    opts        : 覆盖 DEFAULTS 的字典
    log         : 可选的进度输出函数（None 表示静默）
    """
    o = dict(DEFAULTS)
    if opts:
        o.update({k: v for k, v in opts.items() if v is not None})
    say = log or (lambda *a, **k: None)
    raw_n = len(albums)

    # 1) 类型过滤。必须在合并之前：同名条目里常有「单曲版 1 首」与「专辑版 12 首」并存，
    #    先合并会选中单曲版，随后被类型过滤整组淘汰（曾导致 The Weeknd《Kiss Land》整张丢失）。
    want = {t.lower() for t in _csv(o["types"])}
    if "all" not in want:
        albums = [a for a in albums if (a.get("type") or "").strip().lower() in want]
    typed_n = len(albums)

    # 2) 同名专辑合并：优先「非现场 + 非版本修饰」，其次曲目最多的
    groups = collections.OrderedDict()
    for a in albums:
        groups.setdefault(norm_album(a.get("name") or ""), []).append(a)
    merged = []
    for _, grp in groups.items():
        grp.sort(key=lambda a: (is_live_name(a.get("name")), is_alt_name(a.get("name")),
                                -(a.get("size") or 0)))
        best = dict(grp[0])
        best["_dupe_ids"] = [g.get("id") for g in grp[1:]]
        merged.append(best)
    albums = merged

    if o["min_tracks"]:
        albums = [a for a in albums
                  if a.get("size") is None or (a.get("size") or 0) >= o["min_tracks"]]

    # 3) 关键词排除（含 Live 判定）
    kw = [] if o["keep_all"] else _csv(o["exclude"])
    dropped, kept = [], []
    for a in albums:
        name = a.get("name") or ""
        hit = next((k for k in kw if k.lower() in name.lower()), None)
        if not hit and not o["keep_all"] and is_live_name(name):
            hit = "Live 现场录音"
        (dropped.append((a, hit)) if hit else kept.append(a))
    albums = kept

    # 4) 精确排除（曲库脏数据）
    for x in _csv(o["xalbum"]):
        rest = []
        for a in albums:
            if x.lower() in (a.get("name") or "").lower():
                dropped.append((a, f"手动排除:{x}"))
            else:
                rest.append(a)
        albums = rest

    # size 未知（None）的源（如 MusicBrainz）不能按 0 处理，否则整批专辑会被误删
    albums = [a for a in albums if a.get("size") is None or (a.get("size") or 0) > 0]
    if o["since"]:
        cutoff = int(time.mktime(time.strptime(o["since"], "%Y-%m-%d")) * 1000)
        albums = [a for a in albums if (a.get("publishTime") or 0) >= cutoff]
    albums.sort(key=lambda a: (a.get("publishTime") or 0, a.get("name") or ""))

    # 5) 两轮抓曲目：正式版先占位，重制/混音版让位
    order = ([i for i, a in enumerate(albums) if not is_alt_name(a.get("name"))] +
             [i for i, a in enumerate(albums) if is_alt_name(a.get("name"))])

    records, seen, zero_note = [], set(), []
    for step, idx in enumerate(order, 1):
        al = albums[idx]
        date, year = fmt_date(al.get("publishTime"))
        try:
            tracks = fetch_tracks(al["id"])
        except Exception as e:                        # noqa: BLE001
            say(f"  ! 跳过《{al['name']}》：{e}")
            continue

        named = [t for t in tracks if t.get("artists")]
        self_cnt = sum(1 for t in named
                       if any(aname == n or aname in n or n in aname for n in t["artists"]))
        ratio = self_cnt / len(tracks) if tracks else 0
        is_ost = any(k.lower() in (al.get("name") or "").lower() for k in OST_MARKS)

        # 6) 拼盘判定（仅在源提供演唱者信息时可靠；降级源常缺该字段）
        if named and (
            (is_ost and ratio < OST_MIN_RATIO) or
            (len(tracks) >= COMPILATION_MIN_TRACKS and not is_ost
                and ratio < COMPILATION_MIN_RATIO)
        ):
            zero_note.append((al["name"],
                              f"{'原声带拼盘' if is_ost else '合辑拼盘'}，本人仅 {self_cnt}/{len(tracks)} 首"))
            say(f"  [{step:02d}/{len(albums)}] {date} {al['name'][:36]} (跳过：本人占比 {ratio:.0%})")
            continue

        kept_n = other = dup = 0
        for t in tracks:
            if not t.get("name"):
                continue
            names = t.get("artists") or []
            # 7) 演唱者过滤（原声带整张保留；降级源放宽）
            if names and not o["include_featured"] and not is_ost and not o["lenient_artists"]:
                if not any(aname == n or aname in n or n in aname for n in names):
                    other += 1
                    continue
            # 8) 跨专辑去重
            key = norm(t["name"])
            if not o["no_dedupe"] and key in seen:
                dup += 1
                continue
            seen.add(key)
            label = (names[0] if names else aname) if o["singers"] == "primary" \
                else "/".join(names or [aname])
            records.append({
                "title": t["name"], "album": al["name"], "date": date, "year": year,
                "atype": al.get("type") or "", "no": t.get("no") or 0, "singer": label,
                "_sort": (al.get("publishTime") or 0, idx, t.get("no") or 0),
            })
            kept_n += 1

        if kept_n == 0:
            zero_note.append((al["name"],
                              "整张非本人演唱" if other else "曲目与更早专辑重复"))
        note = f"，跳过他人演唱 {other} 首" if other else ""
        if dup:
            note += f"，{dup} 首已在前面的专辑出现过"
        say(f"  [{step:02d}/{len(albums)}] {date} {al['name'][:36]} ({kept_n}/{len(tracks)} 首{note})")

    # 9) 复原时间线（抓取顺序为「正式版优先」被打乱过）
    records.sort(key=lambda r: r["_sort"])
    stats = {
        "raw": raw_n, "typed": typed_n, "merged": len(groups),
        "selected": len(albums), "albums_used": len({r["album"] for r in records}),
    }
    return records, dropped, zero_note, stats


# ---------------------------------------------------------------- 输出

def _safe(name):
    return re.sub(r"[\\/:*?\"<>|]", "_", name)


def write_outputs(records, aname, opts, dropped, zero_note, stats, outdir,
                  source_name="", degraded=False, fallback_reason=""):
    o = dict(DEFAULTS)
    o.update({k: v for k, v in (opts or {}).items() if v is not None})
    base = _safe(aname)
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
            w.writerow([i, r["title"], r["album"], r["date"], r["year"],
                        r["atype"], r["no"], r["singer"]])

    years = [r["year"] for r in records if r["year"]]
    with open(md_p, "w", encoding="utf-8") as f:
        f.write(f"# {aname} · 专辑全曲歌单\n\n")
        if years:
            f.write(f"共 **{len(records)}** 首，来自 **{stats['albums_used']}** 张专辑，"
                    f"发行年份跨度 **{min(years)}–{max(years)}**。\n\n")
        else:
            f.write(f"共 **{len(records)}** 首，来自 **{stats['albums_used']}** 张专辑。\n\n")

        if degraded:
            if fallback_reason:
                f.write(f"> ⚠️ 数据源降级：主源不可用，已切换到 `{source_name}`。"
                        f"字段完整度与匹配率低于主源，建议核对后再使用。\n")
                f.write(f">\n> 主源错误：`{fallback_reason}`\n")
            else:
                f.write(f"> ℹ️ 本次使用备源 `{source_name}` 生成。"
                        f"字段完整度与匹配率低于主源，建议核对后再使用。\n")
            f.write("\n")

        f.write("## 筛选依据\n\n")
        f.write(f"1. **只取专辑曲目**：专辑类型筛选为 `{o['types']}`，"
                f"单曲（Single）、EP、精选集不进歌单。曲库共 {stats['raw']} 条记录，"
                f"类型命中 {stats['typed']} 张，合并同专辑重复条目后 {stats['merged']} 张。\n")
        f.write("2. **排除非录音室专辑**：专辑名命中 "
                f"`{'/'.join(_csv(o['exclude'])) if not o['keep_all'] else '（未启用）'}` 的整张跳过，"
                f"包括巡演、现场、精选、合辑、伴奏版等。\n")
        f.write("3. **只保留本人演唱/参与**：合作合辑中他人演唱的曲目剔除；"
                "电影原声带在本人占比达标时整张保留。\n")
        f.write("4. **跨专辑去重**：同一首歌在多张专辑出现时，只保留**最早**专辑中的版本；"
                "重制版、混音版撞歌时由正式版占位。\n")
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
            f.write(f"| {i} | {r['title'].replace('|', '／')} | {r['album'].replace('|', '／')} "
                    f"| {r['year'] or '—'} |\n")

    # 10) 字段 schema 自检（不引入额外依赖）
    problems = validate_records(records)
    return md_p, csv_p, txt_p, problems


def validate_records(records):
    """输出前的字段自检，返回问题列表（空表示通过）"""
    problems = []
    required = ("title", "album", "date", "year", "atype", "no", "singer")
    for i, r in enumerate(records, 1):
        miss = [k for k in required if k not in r]
        if miss:
            problems.append(f"第 {i} 条缺字段: {','.join(miss)}")
        if r.get("date") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["date"]):
            problems.append(f"第 {i} 条发行日期格式异常: {r['date']}")
        if r.get("year") and not re.fullmatch(r"\d{4}", str(r["year"])):
            problems.append(f"第 {i} 条年份异常: {r['year']}")
        if "|" in (r.get("title") or ""):
            problems.append(f"第 {i} 条歌名含竖线，已转义")
    return problems


# ---------------------------------------------------------------- CLI

def build_parser():
    ap = argparse.ArgumentParser(
        prog="artist-playlist",
        description="把一位歌手的全部专辑曲目按发行时间整理成独立歌单文件")
    ap.add_argument("artist", help="歌手名，中英文均可")
    ap.add_argument("--types", default=DEFAULTS["types"],
                    help="纳入的专辑类型，逗号分隔：专辑,EP；all=全部")
    ap.add_argument("--min-tracks", type=int, default=0, help="曲目数下限")
    ap.add_argument("--exclude", default=DEFAULT_EXCLUDE, help="专辑名命中即跳过，逗号分隔")
    ap.add_argument("--xalbum", default="", help="精确排除指定专辑（子串），逗号分隔")
    ap.add_argument("--keep-all", action="store_true", help="忽略 --exclude 与 Live 判定")
    ap.add_argument("--no-dedupe", action="store_true", help="关闭跨专辑去重")
    ap.add_argument("--singers", default="primary", choices=["primary", "full"])
    ap.add_argument("--include-featured", action="store_true", help="保留他人演唱曲目")
    ap.add_argument("--since", default="", help="增量：只处理该日期(YYYY-MM-DD)后的专辑")
    ap.add_argument("--source", default="auto", choices=["auto", "netease", "musicbrainz"],
                    help="数据源，默认自动选择并在失败时降级")
    ap.add_argument("--outdir", default="", help="输出根目录，默认 ./歌单")
    ap.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    outdir = args.outdir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "歌单")

    try:
        src = get_source(args.source)
        aid, aname, _ = src.search_artist(args.artist)
    except SourceError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2

    print(f"[{args.artist}] → {aname} (id={aid}, source={src.name})", flush=True)
    if getattr(src, "degraded", False):
        why = getattr(src, "fallback_reason", "")
        head = "主源不可用，已降级到备源" if why else "正在使用备源"
        print(f"  ⚠️ {head}，字段完整度与匹配率会下降", flush=True)

    albums = src.list_albums(aid)
    opts = vars(args).copy()
    opts["lenient_artists"] = getattr(src, "lenient_artists", False)
    records, dropped, zero_note, stats = build_records(
        albums, src.album_tracks, aname, opts, log=print)

    if not records:
        print("✗ 没有抓到任何曲目，检查歌手名或过滤条件", file=sys.stderr)
        return 1

    md_p, csv_p, txt_p, problems = write_outputs(
        records, aname, opts, dropped, zero_note, stats, outdir,
        source_name=src.name, degraded=getattr(src, "degraded", False),
        fallback_reason=getattr(src, "fallback_reason", ""))

    print(f"\n✅ 完成  曲目 {len(records)} 首 / 专辑 {stats['albums_used']} 张")
    if dropped:
        print(f"  · 排除 {len(dropped)} 张（Live/精选/合辑/手动）")
    if zero_note:
        print(f"  · {len(zero_note)} 张无曲目入选（整张重复或非本人演唱）")
    if problems:
        print(f"  ⚠️ 字段自检发现 {len(problems)} 处问题（前 3 条）：{problems[:3]}")
    print(f"  歌单：{md_p}")
    print(f"  导入：{txt_p}")
    print("\n下一步：把导入清单全文复制 → 音乐平台「导入外部歌单 → 文字导入」")
    return 0


if __name__ == "__main__":
    sys.exit(main())
