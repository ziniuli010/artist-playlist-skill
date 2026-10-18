# -*- coding: utf-8 -*-
"""数据源抽象。

一个 Source 负责三件事：
    search_artist(name)  -> (artist_id, official_name, candidates)
    list_albums(aid)     -> [ {id, name, type, size, publishTime} ]
    album_tracks(aid)    -> [ {no, name, artists[]} ]

统一的 Album 字段约定：
    id           源内唯一标识（字符串或整数均可）
    name         专辑名
    type         专辑类型，统一映射为 专辑 / EP / Single / 精选集 / 其他
    size         曲目数（拿不到时为 None，调用方需容错）
    publishTime  发行时间，毫秒时间戳（拿不到时为 0，排序时置底）
"""


class SourceError(RuntimeError):
    """数据源不可用或返回异常。"""


class Source:
    name = "base"
    #: True 表示该源字段不全、匹配率低，输出时应标注「降级」
    degraded = False
    #: 是否放宽演唱者过滤（跨语种源的名字可能与曲目署名不一致）
    lenient_artists = False

    def search_artist(self, name):
        raise NotImplementedError

    def list_albums(self, artist_id):
        raise NotImplementedError

    def album_tracks(self, album_id):
        raise NotImplementedError

    def close(self):
        pass


def pick_artist(name, candidates):
    """从候选里挑出目标艺人：同名同作品量优先，否则取作品最多的。

    candidates 元素需含 name / musicSize 字段。
    这条规则解决两类脏数据：
      1. 粉丝号、后援会号与正主同名；
      2. 不同艺人的名字互为子串（"Big Bang" 与 "BIGBANG"）。
    """
    if not candidates:
        raise SourceError(f"没搜到歌手：{name}")
    q = name.strip().lower().replace(" ", "")
    related = [a for a in candidates
               if q in (a.get("name") or "").lower().replace(" ", "")
               or (a.get("name") or "").lower().replace(" ", "") in q]
    pool = related or candidates
    top = max(pool, key=lambda a: a.get("musicSize") or 0)
    exact = [a for a in pool if (a.get("name") or "").lower().replace(" ", "") == q]
    if exact:
        best = max(exact, key=lambda a: a.get("musicSize") or 0)
        # 同名的山寨号作品量通常远小于正主，此时改用作品最多的候选
        if (best.get("musicSize") or 0) >= 0.5 * (top.get("musicSize") or 0):
            return best
    return top
