# -*- coding: utf-8 -*-
"""数据源选择与自动降级。"""

from .base import Source, SourceError, pick_artist
from .netease import NeteaseSource
from .musicbrainz import MusicBrainzSource

__all__ = ["Source", "SourceError", "pick_artist",
           "NeteaseSource", "MusicBrainzSource", "get_source"]

_SOURCES = {
    "netease": NeteaseSource,
    "musicbrainz": MusicBrainzSource,
}


def get_source(name="auto"):
    """name: auto / netease / musicbrainz

    auto 模式先探测主源可用性，失败则降级到备源，并在返回的实例上暴露 .fallback_reason。
    """
    if name in _SOURCES:
        return _SOURCES[name]()

    primary = NeteaseSource()
    try:
        # 轻量探测：一次搜索请求即可确认可用
        primary.search_artist("周杰伦")
        return primary
    except Exception as e:                            # noqa: BLE001
        fallback = MusicBrainzSource()
        fallback.fallback_reason = str(e)[:160]
        return fallback
