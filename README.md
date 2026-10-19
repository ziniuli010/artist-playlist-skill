# artist-playlist

[![CI](https://github.com/ziniuli010/artist-playlist-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/ziniuli010/artist-playlist-skill/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](pyproject.toml)

把一个歌手的**全部专辑曲目**按**发行时间**整理成独立歌单文件——Markdown 表格 + CSV + 可直接粘贴到音乐平台的文字清单。

零运行时依赖，自动完成专辑筛选、跨专辑去重、版本择优、时间排序与增量更新。既可作为命令行工具，也可作为 Agent Skill 使用。

<sub>Turn an artist's entire discography into a chronologically ordered playlist file. Zero dependencies, Python 3.9+, CLI or Agent Skill.</sub>

## 为什么做这个

音乐平台没有「某歌手全部专辑 → 一个歌单」的功能。歌手页的「添加到歌单」加的是**热门歌曲**，不是专辑曲目；手动逐张专辑添加，20 张就要点 20 遍。

这个工具把「找专辑 → 滤掉现场版/精选集 → 去重 → 按时间排序 → 生成可导入清单」一次做完。

## 安装

三种方式，任选一种。

```bash
# 1) 直接跑，无需安装（推荐先试）
git clone https://github.com/ziniuli010/artist-playlist-skill.git
cd artist-playlist-skill
python3 scripts/build_discography.py "陈奕迅"

# 2) 装成命令（需要 pipx 或 venv）
pipx install git+https://github.com/ziniuli010/artist-playlist-skill.git
artist-playlist "陈奕迅"

# 3) 作为 Agent Skill
cp -r artist-playlist-skill ~/.workbuddy/skills/artist-playlist
# 之后在对话里说「用 artist-playlist 整理某某的歌单」即可触发
```

要求：Python 3.9+，可访问 `music.163.com`（只读元数据，不下载音频）。

## 快速开始

```bash
artist-playlist "陈奕迅"
```

输出：

```
歌单/陈奕迅/
├── 陈奕迅_歌单.md     # 概览 + 筛选依据 + 曲目表格
├── 陈奕迅_歌单.csv    # Excel 可开
└── 陈奕迅_导入.txt    # 复制到平台「文字导入」
```

## 常用参数

```bash
artist-playlist "方大同" --types 专辑,EP          # 纳入 EP
artist-playlist "五月天" --keep-all               # 连现场/精选一起收
artist-playlist "薛之谦" --no-dedupe              # 每张专辑都要完整
artist-playlist "邓紫棋" --since 2024-01-01       # 只补新专辑
artist-playlist "BIGBANG" --xalbum "BEST SELECTION,ASIA BEST"   # 精确剔除脏数据
artist-playlist "The Weeknd" --source musicbrainz  # 指定备源
```

完整参数见 `artist-playlist --help`。

## 规则速览

| 环节 | 做法 |
|---|---|
| 筛选 | 只收 `专辑` 类型；排除巡演/现场/精选/合辑/伴奏/改版/**电影原声带**/**短序曲** |
| 演唱者 | 只保留本人演唱/参与，剔除合作合辑里别人唱的歌 |
| 去重 | 同专辑多条目合并；跨专辑同名歌留最早版本；重制版让位正式版 |
| 排序 | 专辑按发行日期升序，专辑内按原始曲序 |
| 更新 | 重跑即幂等覆盖；`--since` 支持增量 |

细则见 [`references/rules.md`](references/rules.md)，字段定义见 [`references/fields.md`](references/fields.md)。

## 数据源

| 源 | 角色 | 说明 |
|---|---|---|
| 网易云公开元数据 | 主源 | 专辑类型、发行日期、曲序完整 |
| MusicBrainz 开放数据 | 备源 | 主源不可用时自动降级，字段较少，输出文件会标注降级 |

降级时演唱者过滤会自动放宽（跨语种源的名字可能与曲目署名不一致），并在歌单顶部写明原因。

## 导入到音乐平台

导入依赖平台的「导入外部歌单 → 文字导入」，把 `<歌手>_导入.txt` 全文粘进去即可。

| 平台 | 入口 | 可用性 |
|---|---|---|
| 手机 App（iOS / Android） | 我的 → 右上角菜单 → 导入外部歌单；或 我的 → 自建歌单 → 导入外部歌单 | ✅ 支持文字导入 |
| Windows 客户端 | 我的音乐 → 自建歌单区 → 导入歌单 | ✅ 支持 |
| **macOS 客户端** | **无此功能** | ❌ 见下 |

> **macOS 客户端没有文字导入入口。** 已实测 QQ 音乐 Mac 版 11.10.5：客户端资源中存在「歌单」字符串，但不存在「导入」「导入歌单」「文字导入」「匹配歌曲」——即该功能未在 Mac 版实现。

### macOS 用户的推荐做法

1. 在 Mac 上打开 `_导入.txt`，全选复制（`⌘A` `⌘C`）
2. 通过「通用剪贴板」在 iPhone 上直接粘贴（同一 Apple ID，无需第三方工具）
3. iPhone 打开 QQ 音乐：我的 → 右上角菜单 → 导入外部歌单 → 粘贴文字 → 一键导入
4. Mac 端登录同一账号，歌单自动同步显示

几百首的清单建议分 2–3 次粘贴，每次 150 行以内更稳。导入后若顺序看着乱，把歌单排序切成「添加顺序」。

## 文档

| 文件 | 内容 |
|---|---|
| [`SKILL.md`](SKILL.md) | 能力说明、输入输出、目录结构、用法、规则总纲、示例 |
| [`references/fields.md`](references/fields.md) | 每个字段的类型、取值与设计理由 |
| [`references/rules.md`](references/rules.md) | 筛选/去重/排序/更新的完整判定规则（S/D/O/U 编号） |
| [`references/troubleshooting.md`](references/troubleshooting.md) | 匹配错人、空专辑、导入失败等 9 类问题排查 |
| [`schema/playlist.schema.json`](schema/playlist.schema.json) | 曲目记录字段 Schema |
| [`CHANGELOG.md`](CHANGELOG.md) | 版本记录 |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | 改规则的正确姿势、提交流程 |

## 开发

```bash
pip install -e ".[dev]"

ruff check .                     # 语法与未定义名
python scripts/validate_skill.py # SKILL 元数据与包完整性
python -m pytest -q              # 26 个离线用例，不联网
```

测试用 `tests/fixtures/mini_artist.json` 里的固定样本，覆盖类型过滤、同专辑合并、正式版优先、Live 排除、精选排除、拼盘判定、原声带豁免、跨专辑去重与时间排序。

## 已知限制

1. 匹配率受平台版权影响，无版权曲目导入时会失败。
2. 巡演专辑若名字本身不含任何现场标记，会被当作录音室专辑收录。
3. 曲库元数据随上下架变化，同一歌手不同日期运行结果可能略有差异。
4. 只读取公开元数据，不下载、不转码、不分发音频。

## License

[MIT](LICENSE)
