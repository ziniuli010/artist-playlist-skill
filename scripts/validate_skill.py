#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skill 元数据与包完整性检查。

CI 与本地提交前均可运行：
    python scripts/validate_skill.py
退出码 0 表示通过，1 表示有问题（问题会逐条打印）。
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIRED_FILES = [
    "SKILL.md", "README.md", "LICENSE",
    "scripts/build_discography.py",
    "references/fields.md", "references/rules.md", "references/troubleshooting.md",
]
TRIGGER_HINTS = ("歌单", "专辑", "playlist", "discography")
MAX_DESC = 400
MIN_DESC = 40


def parse_frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    block = text[3:end]
    meta = {}
    for line in block.splitlines():
        if ":" in line and not line.strip().startswith("#"):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, text[end + 4:]


def main():
    problems, notes = [], []

    for rel in REQUIRED_FILES:
        if not os.path.exists(os.path.join(ROOT, rel)):
            problems.append(f"缺少必需文件：{rel}")

    skill_p = os.path.join(ROOT, "SKILL.md")
    if os.path.exists(skill_p):
        meta, body = parse_frontmatter(open(skill_p, encoding="utf-8").read())
        for key in ("name", "description"):
            if not meta.get(key):
                problems.append(f"SKILL.md frontmatter 缺 {key}")
        name = meta.get("name", "")
        if name and not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", name):
            problems.append(f"name 不合规（应小写字母/数字/连字符）：{name}")
        desc = meta.get("description", "")
        if desc:
            if len(desc) < MIN_DESC:
                problems.append(f"description 过短（{len(desc)} < {MIN_DESC}），会影响触发")
            if len(desc) > MAX_DESC:
                problems.append(f"description 过长（{len(desc)} > {MAX_DESC}），部分宿主会截断")
            if not any(h in desc for h in TRIGGER_HINTS):
                problems.append("description 未包含任何触发词（歌单/专辑/playlist/discography）")
        if not meta.get("version"):
            notes.append("建议补 version 字段，便于发布与缓存失效")
        # 正文引用的相对路径是否都存在
        for ref in set(re.findall(r"`((?:references|scripts|examples)/[\w\-./]+)`", body)):
            if not os.path.exists(os.path.join(ROOT, ref)):
                problems.append(f"SKILL.md 引用了不存在的路径：{ref}")

    # 脚本可编译
    import compileall
    if not compileall.compile_dir(os.path.join(ROOT, "scripts"), quiet=2, force=True):
        problems.append("scripts/ 存在语法错误，编译失败")

    # 测试存在性
    if not os.path.exists(os.path.join(ROOT, "tests", "test_rules.py")):
        problems.append("缺少 tests/test_rules.py，规则改动无回归保护")
    if not os.path.exists(os.path.join(ROOT, "tests", "fixtures", "mini_artist.json")):
        problems.append("缺少离线回归样本 tests/fixtures/mini_artist.json")

    print(f"检查目录：{ROOT}")
    for n in notes:
        print(f"  · 建议：{n}")
    if problems:
        print(f"\n✗ 发现 {len(problems)} 个问题：")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\n✓ 全部检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
