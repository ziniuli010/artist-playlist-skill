# artist-playlist

把一个歌手的**全部专辑曲目**，按**发行时间**整理成独立歌单文件——Markdown 表格 + CSV + 可直接导入音乐平台的文字清单。

零依赖（Python 标准库），自动完成专辑筛选、跨专辑去重、版本择优、时间排序与增量更新。

## 为什么做这个

平台没有「某歌手全部专辑 → 一个歌单」的功能。歌手页的「添加到歌单」加的是**热门歌曲**，不是专辑曲目；手动逐张专辑添加，20 张就要点 20 遍。

这个工具把「找专辑 → 滤掉现场版/精选集 → 去重 → 按时间排序 → 生成可导入清单」一次做完。

## 快速开始

```bash
git clone <this-repo>
cd artist-playlist

python3 scripts/build_discography.py "陈奕迅"
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
# 纳入 EP
python3 scripts/build_discography.py "方大同" --types 专辑,EP

# 连现场/精选一起收
python3 scripts/build_discography.py "五月天" --keep-all

# 每张专辑都要完整（关闭跨专辑去重）
python3 scripts/build_discography.py "薛之谦" --no-dedupe

# 只补新专辑
python3 scripts/build_discography.py "邓紫棋" --since 2024-01-01 --outdir ./增量

# 批量
for a in "陈奕迅" "五月天" "The Weeknd"; do python3 scripts/build_discography.py "$a"; done
```

完整参数见 `python3 scripts/build_discography.py -h`。

## 规则速览

| 环节 | 做法 |
|---|---|
| 筛选 | 只收 `专辑` 类型；排除巡演/现场/精选/合辑/伴奏；原声带整张保留 |
| 演唱者 | 只保留本人演唱/参与，剔除合作合辑里别人唱的歌 |
| 去重 | 同专辑多条目合并；跨专辑同名歌留最早版本；重制版让位正式版 |
| 排序 | 专辑按发行日期升序，专辑内按原始曲序 |
| 更新 | 重跑即幂等覆盖；`--since` 支持增量 |

细则见 [`references/rules.md`](references/rules.md)，字段定义见 [`references/fields.md`](references/fields.md)。

## 文档

| 文件 | 内容 |
|---|---|
| [`SKILL.md`](SKILL.md) | 能力说明、输入输出、目录结构、用法、规则总纲、示例 |
| [`references/fields.md`](references/fields.md) | 歌单每个字段的类型、取值与设计理由 |
| [`references/rules.md`](references/rules.md) | 筛选/去重/排序/更新的完整判定规则（S/D/O/U 编号） |
| [`references/troubleshooting.md`](references/troubleshooting.md) | 匹配错人、空专辑、导入失败等 9 类问题排查 |

## 作为 Agent Skill 使用

```bash
cp -r artist-playlist ~/.workbuddy/skills/artist-playlist
```

之后在对话里说「用 artist-playlist 整理某某的歌单」即可触发。

## 环境

- Python 3.8+
- 可访问 `music.163.com`（只读取公开元数据）

## 免责声明

本项目仅处理**公开的专辑/曲目元数据**（歌名、专辑名、发行日期、曲序），不下载、不转码、不分发任何音频内容。请遵守所在地区法律与平台服务条款。

## License

MIT
