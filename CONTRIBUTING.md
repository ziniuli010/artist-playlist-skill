# 贡献指南

感谢愿意改进这个工具。改动前请先读 `references/rules.md`，规则的每一条都有编号（S/D/O/U），提交信息请带上编号。

## 本地准备

```bash
git clone https://github.com/ziniuli010/artist-playlist-skill.git
cd artist-playlist-skill
pip install -e ".[dev]"
```

零第三方运行时依赖，`dev` 只装 pytest 和 ruff。

## 提交前自检

```bash
ruff check .
python scripts/validate_skill.py
python -m pytest -q
```

三条全绿再提交，CI 会跑同样的命令。

## 改规则的正确姿势

改判定逻辑时**必须同时**做三件事，否则 CI 或后续维护会出问题：

1. **改代码**：`scripts/build_discography.py` 里的常量或 `build_records()`。
2. **改文档**：`references/rules.md` 对应编号章节；若影响输入输出，同步 `SKILL.md`。
3. **加测试**：`tests/test_rules.py` 至少一条正例 + 一条反例。
   - 收紧规则（多排除）要加「不应被排除」的反例
   - 放宽规则（少排除）要加「仍应被排除」的反例
   - 涉及整条链路时，扩展 `tests/fixtures/mini_artist.json`

### 例：新增一个排除关键词

```python
# 1. 代码：DEFAULT_EXCLUDE 追加（注意不要用会误伤正式专辑的宽泛词）
DEFAULT_EXCLUDE = ("...", "Demo")

# 2. 文档：references/rules.md 的 S2 词表同步

# 3. 测试
def test_demo_excluded(self):
    self.assertTrue(bd.is_hit_by_keywords("XXX (Demo)"))

def test_album_named_demo_not_excluded(self):
    # 反例：正式专辑名里含 Demo 的情况要能被 --keep-all 放行
    ...
```

### 黑名单词的取舍原则

**不要**把 `Vision`、`Gold`、`Legends`、`Collection`、`Live` 这类常见词直接加进黑名单——它们会杀掉《Night Visions》《Gold》这类正式专辑。这类个案请走 `--xalbum`，并在 `references/troubleshooting.md` 记一条案例。

## 新增数据源

实现 `scripts/sources/base.py` 的 `Source` 三个方法，在 `scripts/sources/__init__.py` 的 `_SOURCES` 注册，然后：

- 在 `--source` 的 `choices` 里加上名字
- 若字段不全，设 `degraded = True`，输出会自动加降级提示
- 若名字体系与曲目署名不一致（如繁体/罗马字），设 `lenient_artists = True`

## 提交信息

```
<type>: <一句话说明>

- 规则编号或影响范围
- 为什么这么改（贴反例更好）
```

`type` 用 `feat` / `fix` / `docs` / `test` / `chore`。

## 不要提交

- 任何密钥、令牌、Cookie、`.env`
- 本机绝对路径、个人账号信息
- 生成的 `歌单/` 目录与 `logs/`（已在 `.gitignore`）

## 关于数据来源

本项目只读取**公开的专辑与曲目元数据**（歌名、专辑名、发行日期、曲序、演唱者），不下载、不转码、不分发音频。新增数据源时请确保其服务条款允许此类只读访问。
