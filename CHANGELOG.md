# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.2.0] - 2026-10-19

### Changed
- **电影/电视原声带默认整张排除**（S5）。原行为是「本人曲目占比 ≥30% 即保留」，但原声带里大量是几十秒的过场配乐，混进歌单后听感割裂。新增 `--keep-interludes` 可恢复旧行为。
- **短序曲默认排除**（S5.1）：曲目整名仅为 `Intro/Outro/Interlude/Prelude/序曲/前奏/开场/间奏`（可带编号）的，视为过场音轨剔除。

### 实测影响
- 周杰伦：233 首 → **175 首**（《不能说的秘密》24 首 +《天台》33 首整张排除）
- 陈奕迅：402 首，无原声带，不受影响

### Tests
- 新增 `test_ost_excluded_by_default` / `test_ost_kept_with_flag`，测试总数 27。

## [1.2.0] - 2026-10-19

### Changed
- **电影/电视原声带默认整张排除**（S5）。原行为是「本人曲目占比 ≥30% 即保留」，但原声带里大量是几十秒的过场配乐，混进歌单后听感割裂。新增 `--keep-interludes` 可恢复旧行为。
- **短序曲默认排除**（S5.1）：曲目整名仅为 `Intro/Outro/Interlude/Prelude/序曲/前奏/开场/间奏`（可带编号）的，视为过场音轨剔除。

### 实测影响
- 周杰伦：233 首 → **175 首**（《不能说的秘密》24 首 +《天台》33 首整张排除）
- 陈奕迅：402 首，无原声带，不受影响

### Tests
- 新增 `test_ost_excluded_by_default` / `test_ost_kept_with_flag`，测试总数 27。

## [1.1.0] - 2026-10-18

### Added
- `sources/` 数据源适配层：主源（网易云公开元数据）不可用时自动降级到 MusicBrainz，输出文件标注「数据源降级」。
- `tests/` 离线回归测试：26 个用例覆盖归一化、Live 判定、版本判定、艺人选择与整条处理链。
- `tests/fixtures/mini_artist.json`：覆盖 9 类规则的固定样本。
- `schema/playlist.schema.json`：曲目记录字段 Schema。
- `scripts/validate_skill.py`：SKILL 元数据与包完整性检查（CI 中执行）。
- `pyproject.toml` + `artist_playlist.py`：支持 `pip install .` 后用 `artist-playlist` 命令调用。
- GitHub Actions CI：Python 3.9 / 3.12 双版本，跑 ruff、元数据检查、单测、CLI 冒烟。
- `--source {auto,netease,musicbrainz}` 参数。
- `CHANGELOG.md`、`CONTRIBUTING.md`。

### Changed
- 核心逻辑抽成纯函数 `build_records()`，网络请求由注入的 `fetch_tracks` 提供，便于离线测试。
- 输出前增加字段自检 `validate_records()`，异常字段在控制台提示。
- 演唱者匹配规则统一到 `sources.base.pick_artist()`。

### Fixed
- 类型过滤提前到「同专辑条目合并」之前，修复同名单曲版挤掉专辑版导致整张丢失（The Weeknd《Kiss Land》）。
- 合并同专辑条目时按「非现场 > 非版本 > 曲目多」排序，修复 Live 版挤掉正式版（《After Hours》）。
- Live 判定改为前后非字母的词边界匹配，兼容中文紧邻写法且不误伤 `ALIVE` / `Deliver`。
- 移除误伤正式专辑的黑名单词（`Vision` / `Gold` / `Legends` / `Collection`），改由 `--xalbum` 精确处理（`Night Visions` 曾因此丢失）。

## [1.0.0] - 2026-10-18

### Added
- 首个可用版本：按歌手抓取全部专辑，筛选、去重、按发行时间排序，输出 Markdown / CSV / 导入清单三件套。
- 规则：类型过滤、关键词排除、演唱者过滤、原声带占比判定、跨专辑去重、正式版优先、时间排序。
- 参数：`--types` `--min-tracks` `--exclude` `--keep-all` `--no-dedupe` `--singers` `--include-featured` `--since` `--xalbum`。
- 文档：`SKILL.md`、`references/{fields,rules,troubleshooting}.md`、`examples/`。
