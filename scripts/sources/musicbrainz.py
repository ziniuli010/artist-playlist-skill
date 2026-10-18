# -*- coding: utf-8 -*-
"""MusicBrainz 开放数据源（备源）。

用途：主源不可用（接口改版、限流、断网）时仍能产出歌单。
代价：字段不全、中文歌手名多为繁体、曲名可能是罗马字，匹配率明显低于主源。
因此 degraded=True，输出文件会标注来源与降级说明。

遵守 MusicBrainz 限速：每秒最多 1 次请求（官方要求），本实现默认 1.1 秒。
"""

import json
import time
import urllib.parse
import urllib.request

from .base import Source, SourceError

WS = "https://musicbrainz.org/ws/2"
UA = "artist-playlist/1.1 ( https://github.com/ziniuli010/artist-playlist-skill )"

TYPE_MAP = {"album": "专辑", "ep": "EP", "single": "Single", "other": "其他"}


class MusicBrainzSource(Source):
    name = "musicbrainz"
    degraded = True
    lenient_artists = True        # 名字简繁不一，收紧过滤会误杀全部曲目

    def __init__(self, timeout=30, retries=3, delay=1.1):
        self.timeout = timeout
        self.retries = retries
        self.delay = delay
        self._headers = {"User-Agent": UA, "Accept": "application/json"}
        self._last = 0.0

    def _get(self, url):
        # 全局限速
        wait = self.delay - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        last = None
        for i in range(self.retries):
            try:
                req = urllib.request.Request(url, headers=self._headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    self._last = time.time()
                    return json.loads(r.read().decode("utf-8", "replace"))
            except Exception as e:                    # noqa: BLE001
                last = e
                self._last = time.time()
                time.sleep(2.0 * (i + 1))
        raise SourceError(f"MusicBrainz 请求失败: {url}\n{last}")

    def search_artist(self, name):
        q = urllib.parse.quote(f'artist:"{name}"')
        d = self._get(f"{WS}/artist/?query={q}&fmt=json&limit=10")
        arts = d.get("artists") or []
        if not arts:
            raise SourceError(f"MusicBrainz 没搜到歌手：{name}")
        cands = [{"name": a.get("name"), "id": a.get("id"),
                  # MB 没有播放量，用 release-group 数近似作品量
                  "musicSize": 0, "albumSize": 0,
                  "_score": a.get("score") or 0} for a in arts]
        # 优先取评分最高者（MB 的 score 即匹配度）
        pick = max(cands, key=lambda a: a["_score"])
        return pick["id"], pick["name"], cands

    def list_albums(self, artist_id, max_pages=6):
        out, offset, step = [], 0, 100
        for _ in range(max_pages):
            d = self._get(f"{WS}/release-group?artist={artist_id}"
                          f"&type=album&limit={step}&offset={offset}&fmt=json")
            batch = d.get("release-groups") or []
            for rg in batch:
                date = rg.get("first-release-date") or ""
                out.append({
                    "id": rg.get("id"),
                    "name": rg.get("title") or "",
                    # MB 到 release-group 粒度只有 primary-type，没有「精选集」概念
                    "type": TYPE_MAP.get((rg.get("primary-type") or "").lower(), "其他"),
                    # MB 的 release-group 不含曲目数，置 None 表示「未知」，
                    # 不能用 0 —— 会被上层 size>0 的过滤整批误删
                    "size": None,
                    "publishTime": _date_to_ms(date),
                })
            if len(batch) < step:
                break
            offset += step
        return out

    def album_tracks(self, album_id):
        d = self._get(f"{WS}/release?release-group={album_id}"
                      f"&inc=recordings+artist-credits&limit=1&fmt=json")
        releases = d.get("releases") or []
        if not releases:
            return []
        rel = releases[0]
        rel_credit = _credit_names(rel)
        rows, no = [], 0
        for medium in rel.get("media") or []:
            for t in medium.get("tracks") or []:
                no += 1
                rows.append({
                    "no": t.get("position") or no,
                    "name": (t.get("title") or "").strip(),
                    # 单曲级 artist-credit 优先，缺失时退回专辑级署名
                    "artists": _credit_names(t) or rel_credit,
                })
        rows.sort(key=lambda x: x["no"] or 999)
        return rows


def _credit_names(obj):
    """从 MB 的 artist-credit 数组里取名字。

    MB 的结构是 {"name": "A feat. B", "joinphrase": ..., "artist": {"name": "A"}}，
    不同接口层级字段可能只给 artist.name，两种都兼容。
    """
    out = []
    for ac in (obj.get("artist-credit") or []):
        if isinstance(ac, dict):
            n = ac.get("name") or (ac.get("artist") or {}).get("name")
            if n:
                out.append(n)
    return out


def _date_to_ms(s):
    """'2003-07-31' / '2003-07' / '2003' → 毫秒时间戳，失败返回 0"""
    if not s:
        return 0
    parts = (s.split("-") + ["1", "1"])[:3]
    try:
        t = time.strptime("-".join(parts), "%Y-%m-%d")
        return int(time.mktime(t) * 1000)
    except Exception:                                 # noqa: BLE001
        return 0
