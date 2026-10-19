# -*- coding: utf-8 -*-
"""规则与管道的离线测试（无需网络）。

运行：
    python -m unittest discover -s tests -v
或：
    python -m pytest tests -q
"""

import json
import os
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import build_discography as bd                      # noqa: E402
from sources.base import pick_artist                # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "mini_artist.json")


def load_fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        raw = json.load(f)
    albums = []
    for a in raw["albums"]:
        t = time.strptime(a["date"], "%Y-%m-%d")
        albums.append({
            "id": a["id"], "name": a["name"], "type": a["type"],
            "size": a["size"], "publishTime": int(time.mktime(t) * 1000),
        })
    return raw["artist"], albums, raw["tracks"]


class TestNormalize(unittest.TestCase):
    def test_norm_strips_version_suffix(self):
        self.assertEqual(bd.norm("晴天"), "晴天")
        self.assertEqual(bd.norm("晴天 (Live)"), "晴天")
        self.assertEqual(bd.norm("晴天（伴奏）"), "晴天")

    def test_norm_unifies_case_and_width(self):
        self.assertEqual(bd.norm("Love Story"), bd.norm("love  story"))
        self.assertEqual(bd.norm("ＬＯＶＥ"), bd.norm("love"))

    def test_norm_album_merges_editions(self):
        base = bd.norm_album("Hurry Up Tomorrow")
        self.assertEqual(base, bd.norm_album("Hurry Up Tomorrow (Deluxe)"))
        self.assertEqual(base, bd.norm_album("Hurry Up Tomorrow (Remastered)"))
        self.assertNotEqual(base, bd.norm_album("Hurry Up Tomorrow Live"))


class TestLiveDetection(unittest.TestCase):
    def test_positive_cases(self):
        for name in ["Get A Life (Live)", "MOOV Live 2009 陈奕迅",
                     "Third Encounter Live", "D.N.A LIVE 创记录音",
                     "台北市立体育场Live全纪录", "Life Live 好友加班篇",
                     "Night Visions Live", "After Hours (Live At SoFi Stadium)"]:
            self.assertTrue(bd.is_live_name(name), f"应判为现场: {name}")

    def test_negative_cases(self):
        # ALIVE / Deliver 含 live 子串但不是现场；Live For Today 是正式专辑，走白名单
        for name in ["ALIVE", "Alive (Deluxe)", "Deliver", "Live For Today", "Believe"]:
            self.assertFalse(bd.is_live_name(name), f"不应判为现场: {name}")


class TestAltDetection(unittest.TestCase):
    def test_alt_versions(self):
        for name in ["Bad (Remastered)", "Kiss Land (Deluxe Edition)",
                     "上五楼的快活- EDITED ROUGH MIX", "Thriller 25th Anniversary"]:
            self.assertTrue(bd.is_alt_name(name))

    def test_plain_album(self):
        for name in ["叶惠美", "After Hours", "MADE"]:
            self.assertFalse(bd.is_alt_name(name))


class TestPickArtist(unittest.TestCase):
    def test_prefers_real_account_over_fan_account(self):
        cands = [{"name": "邓紫棋", "id": 1, "musicSize": 7},
                 {"name": "G.E.M.邓紫棋", "id": 2, "musicSize": 420}]
        self.assertEqual(pick_artist("邓紫棋", cands)["id"], 2)

    def test_equivalent_name_ignores_case_and_space(self):
        cands = [{"name": "Big Bang", "id": 1, "musicSize": 199},
                 {"name": "BIGBANG", "id": 2, "musicSize": 662}]
        self.assertEqual(pick_artist("Big Bang", cands)["id"], 2)

    def test_raises_on_empty(self):
        from sources.base import SourceError
        with self.assertRaises(SourceError):
            pick_artist("不存在", [])


class TestPipeline(unittest.TestCase):
    """用固定样本验证整条处理链的最终结果"""

    @classmethod
    def setUpClass(cls):
        cls.artist, cls.albums, cls.tracks = load_fixture()
        cls.records, cls.dropped, cls.zero, cls.stats = bd.build_records(
            cls.albums, lambda aid: cls.tracks.get(aid, []), cls.artist, {}, log=None)

    def test_total_count(self):
        # a1:3 + a5:2(甲被去重)；原声带 a7 默认整张排除
        self.assertEqual(len(self.records), 5)

    def test_deluxe_does_not_win_over_regular(self):
        # a1 与 a2 同专辑，正式版 3 首优先，Deluxe 独有的「丁」不进入
        titles = [r["title"] for r in self.records]
        self.assertNotIn("丁", titles)
        self.assertEqual(self.stats["albums_used"], 2)

    def test_live_album_excluded(self):
        titles = [r["title"] for r in self.records]
        self.assertNotIn("现场闲聊", titles)
        self.assertNotIn("乙 (Live)", titles)

    def test_compilation_type_excluded(self):
        self.assertNotIn("黄金精选集", [r["album"] for r in self.records])

    def test_single_type_excluded(self):
        self.assertNotIn("抢跑", [r["title"] for r in self.records])

    def test_cross_album_dedup(self):
        self.assertEqual([r["title"] for r in self.records].count("甲"), 1)

    def test_collab_compilation_skipped(self):
        # 8 首里本人仅 1 首（12.5% < 20%）→ 整张跳过
        self.assertNotIn("群星合作企划", [r["album"] for r in self.records])
        self.assertTrue(any("群星合作企划" == n for n, _ in self.zero))

    def test_ost_excluded_by_default(self):
        # 原声带默认整张排除（电影配乐多为过场短曲）
        albums = [r["album"] for r in self.records]
        self.assertNotIn("某电影原声带", albums)
        self.assertTrue(any(n == "某电影原声带" for n, _ in self.zero))

    def test_ost_kept_with_flag(self):
        # --keep-interludes 时恢复旧行为
        recs, _, _, _ = bd.build_records(
            self.albums, lambda aid: self.tracks.get(aid, []), self.artist,
            {"keep_interludes": True}, log=None)
        self.assertEqual([r["album"] for r in recs].count("某电影原声带"), 5)

    def test_ost_skipped_when_self_ratio_low(self):
        # 10 首里本人 1 首（10% < 30%）→ 整张跳过
        self.assertNotIn("另一部电视剧原声带", [r["album"] for r in self.records])

    def test_chronological_order(self):
        years = [r["year"] for r in self.records]
        self.assertEqual(years, sorted(years))
        self.assertEqual([r["title"] for r in self.records[:3]], ["甲", "乙", "丙"])

    def test_no_dedupe_switch(self):
        recs, _, _, _ = bd.build_records(
            self.albums, lambda aid: self.tracks.get(aid, []), self.artist,
            {"no_dedupe": True}, log=None)
        self.assertEqual([r["title"] for r in recs].count("甲"), 2)

    def test_min_tracks_switch(self):
        recs, _, _, stats = bd.build_records(
            self.albums, lambda aid: self.tracks.get(aid, []), self.artist,
            {"min_tracks": 5}, log=None)
        self.assertNotIn("首张专辑", [r["album"] for r in recs])
        self.assertLess(stats["selected"], self.stats["selected"])

    def test_xalbum_excludes(self):
        recs, dropped, _, _ = bd.build_records(
            self.albums, lambda aid: self.tracks.get(aid, []), self.artist,
            {"xalbum": "第二张"}, log=None)
        self.assertNotIn("第二张", [r["album"] for r in recs])
        self.assertTrue(any("第二张" == a["name"] for a, _ in dropped))

    def test_since_filters_old_albums(self):
        recs, _, _, _ = bd.build_records(
            self.albums, lambda aid: self.tracks.get(aid, []), self.artist,
            {"since": "2014-01-01"}, log=None)
        self.assertTrue(all(int(r["year"]) >= 2014 for r in recs))


class TestOutputs(unittest.TestCase):
    def test_validate_records_catches_bad_date(self):
        bad = [{"title": "x", "album": "y", "date": "2010/01/01", "year": "2010",
                "atype": "专辑", "no": 1, "singer": "z"}]
        problems = bd.validate_records(bad)
        self.assertTrue(any("发行日期格式异常" in p for p in problems))

    def test_write_outputs_creates_three_files(self):
        import tempfile
        artist, albums, tracks = load_fixture()
        recs, dropped, zero, stats = bd.build_records(
            albums, lambda aid: tracks.get(aid, []), artist, {}, log=None)
        with tempfile.TemporaryDirectory() as d:
            md, csv_p, txt, problems = bd.write_outputs(
                recs, artist, {}, dropped, zero, stats, d)
            for p in (md, csv_p, txt):
                self.assertTrue(os.path.exists(p))
            self.assertEqual(problems, [])
            with open(txt, encoding="utf-8") as f:
                lines = f.read().strip().split("\n")
            self.assertEqual(len(lines), len(recs))
            self.assertIn(" - ", lines[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
