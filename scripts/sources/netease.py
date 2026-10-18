# -*- coding: utf-8 -*-
"""网易云音乐公开元数据源（主源）。

只读取专辑名、发行日期、曲目名、演唱者等公开元数据，不涉及音频。
接口为非官方公开端点，可能随时变更；变更时由 sources/__init__.py 降级到备源。
"""

import json
import time
import urllib.parse
import urllib.request

from .base import Source, SourceError, pick_artist

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")
API = "https://music.163.com/api"

TYPE_MAP = {"专辑": "专辑", "ep": "EP", "single": "Single", "精选集": "精选集"}


class NeteaseSource(Source):
    name = "netease"
    degraded = False

    def __init__(self, timeout=30, retries=3, delay=0.3):
        self.timeout = timeout
        self.retries = retries
        self.delay = delay
        self._headers = {"User-Agent": UA, "Referer": "https://music.163.com/"}

    # ---- 基础设施 ----
    def _get(self, url):
        last = None
        for i in range(self.retries):
            try:
                req = urllib.request.Request(url, headers=self._headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read().decode("utf-8", "replace"))
            except Exception as e:                    # noqa: BLE001
                last = e
                time.sleep(1.2 * (i + 1))
        raise SourceError(f"请求失败: {url}\n{last}")

    # ---- 接口实现 ----
    def search_artist(self, name):
        d = self._get(f"{API}/search/get?s={urllib.parse.quote(name)}&type=100&limit=10")
        arts = (d.get("result") or {}).get("artists") or []
        if not arts:
            raise SourceError(f"没搜到歌手：{name}")
        cands = [{"name": a.get("name"), "id": a.get("id"),
                  "musicSize": a.get("musicSize") or 0,
                  "albumSize": a.get("albumSize") or 0} for a in arts]
        pick = pick_artist(name, cands)
        return pick["id"], pick["name"], cands

    def list_albums(self, artist_id, max_pages=25):
        out, seen, offset, step = [], set(), 0, 100
        for _ in range(max_pages):
            d = self._get(f"{API}/artist/albums/{artist_id}?limit={step}&offset={offset}")
            batch = d.get("hotAlbums") or []
            new = 0
            for a in batch:
                key = ((a.get("name") or "").strip().lower(), a.get("publishTime") or 0)
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "id": a.get("id"),
                    "name": a.get("name") or "",
                    "type": TYPE_MAP.get((a.get("type") or "").strip().lower(),
                                         a.get("type") or ""),
                    "size": a.get("size") or 0,
                    "publishTime": a.get("publishTime") or 0,
                })
                new += 1
            if not d.get("more") or new == 0:
                break
            offset += step
            time.sleep(self.delay)
        return out

    def album_tracks(self, album_id):
        d = self._get(f"{API}/v1/album/{album_id}")
        rows = []
        for s in (d.get("songs") or []):
            rows.append({
                "no": s.get("no") or 0,
                "name": (s.get("name") or "").strip(),
                "artists": [x.get("name", "") for x in (s.get("ar") or []) if x.get("name")],
            })
        rows.sort(key=lambda x: x["no"] or 999)
        return rows
