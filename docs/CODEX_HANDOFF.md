# 本地 Codex 项目交接

更新日期：2026-10-30。此文档供在本地克隆仓库后直接接手开发，不依赖此前聊天记录。

## 目标与本次交接范围

项目名：神祇地理志 / Shrine Atlas。公开仓库：<https://github.com/sumeragisakan/shrine-atlas>。

研究用途是通过神社所在地、祭神原文和逐项出处，考察日本神话、奉祀分布及相关历史记载。用户希望把开发转到本地，便于以后管理地形数据、图片和简单的 AI 生成神社模型。

本次交接只补充开发说明和目标，不代表热度图、三维地形或 AI 建模功能已实现。下一步按 [路线图](ROADMAP.md) 实现三神祇热度对比；用户将定位补全列为未来独立方向。

## 现有基线

数据与功能基线提交：`0665eb2ef3b232238d2d4f6524e7cd749df19f99`，版本 v0.5、catalog schema 3。该提交之前有其余46地区各自的导入提交，随后完成全国地址分组和离线快照复核。以后新增提交应以实际最新分支为准。

| 项目 | 本次交接时的状态 |
| --- | --- |
| 地区 | 47个都道府县均有首轮来源资料 |
| 来源记录 | 102,039条；不等于独立实存神社数 |
| 有祭神资料的记录 | 83,585条；可含历史名单，不等于已确认当前祭祀 |
| 未可靠对应的历史条目 | 51,279条；可能与机构记录重复 |
| 有可绘制坐标的记录 | 14,838条，约14.5% |
| 可绘制地点 | 14,839处；一条鸟取记录有两个地点 |
| 有可绘制点位的地区 | 10个；其余37地区本批暂无可绘制点位 |
| 仅地图视窗中心 | 412处，保留但不绘制 |
| 县界外待核坐标 | 74处，保留但不绘制 |
| 鸟取县 | 原有824条记录、12条研究记录保留 |

统计以 [catalog](../data/catalog.json)、[全国进度](NATIONAL_PROGRESS.md) 和各地区覆盖 JSON 为准。基线验证见 [NATIONAL_VALIDATION.md](NATIONAL_VALIDATION.md)。

### 已实现

- 全国47地区 SVG 地图；选择地区后聚焦并按需加载该地区 JSON。全国初始页只读地区索引。
- 侧栏分页、社名／祭神／地点搜索，来源地域、祭神原文、旧社格及资料状态筛选。
- 地点聚合预览、放大、浏览整组、点击时地图范围快照筛选。
- 神社详情中的所在地、祭神分组、资料说明与逐项来源链接。
- 机构条目与历史待核条目区分；原始地址、邮编、原表附记及历史祭神名单保留。
- 标准 SQLite 导出、47地区离线快照及全国离线入口。

### 尚未实现

- 同时比较最多三位神祇的热度图、全国神祇空间索引、可审查的神名统一层。
- 主祭／配祀／合祀的统一筛选字段；目前角色主要是来源原文。
- 全国地址定位、系统的现址核对、统一定位精度与复核工作流。
- 三维地形、建筑模型查看器、照片画廊、AI 建模流程。
- 面向编辑的常驻数据库服务、媒体上传后台或资产管理界面。

## 本地启动

推荐用 Git 克隆以保留后续提交能力；ZIP 也能运行现有离线版。

```bash
git clone https://github.com/sumeragisakan/shrine-atlas.git
cd shrine-atlas
git switch -c feature/deity-heatmap
```

当前无 Node 包依赖、无前端打包器、无必须配置的 API 密钥。Python 构建仅依赖标准库；需要支持现有脚本语法的 Python 和 SQLite 3.37+（使用 STRICT 表）。前次构建使用 Python 3.12；Node 需支持内置 `node:test`。仓库尚未设置统一的运行时版本锁定文件，首次接手先检查版本并运行测试。

Windows PowerShell：

```powershell
$env:PYTHONUTF8 = "1"
py -3 --version
py -3 -c "import sqlite3; print(sqlite3.sqlite_version)"
node --version
py -3 -m http.server 8000 --bind 127.0.0.1
```

打开 <http://127.0.0.1:8000/>；例如 `/?pref=31` 为鸟取，`/?pref=28` 为兵库。停止服务器用 Ctrl+C。macOS/Linux 可使用 `python3 -m http.server 8000 --bind 127.0.0.1`。

直接离线阅读则打开 `offline/japan-shrine-atlas.html`，保留整个目录结构。地区页使用浏览器 `DecompressionStream` 解开内嵌 gzip；外部出处仍需联网。根目录 `index.html` 读取外部 JSON，直接双击通常受本地文件读取限制。

## 文件与维护入口

| 路径 | 作用 |
| --- | --- |
| `index.html`、`web/atlas.css` | 页面结构与样式 |
| `web/atlas.js` | 加载、地图、侧栏、详情和交互；`initializeAtlas`／`bootAtlas` 为入口 |
| `web/explore-core.js` | 无 DOM 的投影、筛选、分类和地域布局逻辑；既有 `project` 是展示变换，不是米制投影 |
| `data/catalog.json` | 47地区、集合路径和统计索引 |
| `data/shrines/` | 维护用 JSON：鸟取市町村集合、新地区每批150条的机构／历史集合 |
| `data/coverage-tottori.json`、`data/coverage/` | 范围、缺项、来源失败、对应关系和坐标隔离 |
| `data/maps/prefectures.json` | 当前二维展示轮廓；没有地形或高程 |
| `database/schema.sql` | 关系模型；祭神提及与神格实体尚未统一 |
| `database/catalog.sqlite` | 鸟取县生成数据库，不是全国总库 |
| `database/prefectures/*.sqlite.gz` | 其余地区生成数据库，先解 gzip 即为 SQLite |
| `scripts/build.py` | 校验、数据库与离线页生成、索引和地区报告更新 |
| `scripts/import_prefecture.py` | 机构／研究会资料的保守对应及导入；不做地址地理编码 |
| `scripts/collect_*.py` | 已提交的采集工具；不代表每个来源均有完整的本地刷新流程 |
| `tests/` | 现有探索逻辑及全国数据／数据库检查 |
| `media/` | 图片与模型预留位置；当前无真实媒体资产，见 [媒体说明](../media/README.md) |

JSON 是当前维护入口；SQLite 是派生产物，网页并不直接读 SQLite。直接修改数据库会在重建时被 JSON 覆盖。若以后转换写入入口，需要显式设计迁移和导出流程。

模型当前支持 `media` 元数据、独立文件路径及 `location_id` 绑定；生成数据库会校验文件存在、地点归属和 SHA-256。并未实现模型加载或地形。详见 [DATA_MODEL.md](DATA_MODEL.md)。

### 重建与检查

以下以 `python` 表示 Python 命令；Windows 设置 UTF-8 后可换成 `py -3`，macOS/Linux 可换成 `python3`。

```bash
# 读取现有 JSON 重建单地区数据库、该地区离线页、全国索引及报告
python scripts/build.py --prefecture 31

# 只刷新全国索引、报告和全国离线入口，不重建地区数据库／地区离线页
python scripts/build.py --registry-only

# 全部地区重建；会更新多个生成文件，完成后检查 git diff
python scripts/build.py

node --test tests/explore-core.test.js
python -m unittest discover -s tests -p 'test_*.py'
```

仅修改交接文档时无需重建数据。前端改动需要考虑内嵌脚本的离线版同步。`docs/NATIONAL_PROGRESS.md` 和 `docs/prefectures/*.md` 由构建生成，不适合作为手写开发笔记。

数据基线已有6项 Python 和9项 JavaScript检查；这是此快照的数量，不应成为以后固定的测试数目标。

## 必须了解的数据限制

1. **定位尚不完整。** `not_published` 表示本批未取得可用坐标，包括仅有地址、详情尚未取得等情况。不能解释成官网一定没有坐标，更不能把空白地区解读为信仰不存在。
2. **历史与机构记录可能重复。** 仅在规范化社名和地址能唯一对应时连接，不按同名强行合并。地址格式整理会去除分组用邮编，原栏仍保留。
3. **机构条目内也可能包含历史祭神组。** 热度筛选应检查 `kami` 分组及其来源、角色和版本，不能只看记录的 `record_status`。
4. **当前祭神分类是原文项目。** 一个项目可能含多个神名、注音或“外N柱”等描述，不可假设 `kami[].names` 已全部解析为单个统一神格。保持原文，另建可复核的解析／对应层。
5. **公开目录范围不同。** 有的覆盖机构全部名录，有的仅列本务神社、所属神社或精选介绍。千叶目录明确标示2003年版本，岩手青年会帖子标示2018年发布日期；这些日期不是现况核实。
6. **现有底图是加工旧版轮廓。** 不用于精确行政界、导航、面积或高程判断。地图地域入口是浏览示意，不能作为新增神社点位。
7. **采集暂存文件并未全部交付。** 云端原始 HTML、批次输入和原始完整行政界 GeoJSON 不随仓库完整分发。现有 JSON→SQLite／HTML 可离线重建；重新采集或调用导入器前，需要准备输入、核对接口与使用条件。不要依赖旧云端 `/workspace/...` 路径。

当前来源边界与权利处理见 [NATIONAL_METHOD.md](NATIONAL_METHOD.md)、[SOURCES_AND_RIGHTS.md](SOURCES_AND_RIGHTS.md) 和 [地区报告](prefectures/)。

## 交给本地 Codex 的起始任务

可以直接使用这段提示词：

> 请先读取 AGENTS.md、docs/CODEX_HANDOFF.md 和 docs/ROADMAP.md，检查当前分支、数据统计与已有测试。接下来实现 M1「最多三位神祇的热度对比」的最小可用版本，保留现有目录与出处功能。先建立可复核的神名对应、分组来源筛选及去重规则，用少量真实记录验证，再生成适合全国按需加载的空间索引。图例显示匹配、已定位和定位覆盖率；资料不足地区明确标注。定位补全、三维地形和 AI 建模是独立后续阶段，不把它们当作已有功能。按小批提交并说明验证和未解决口径。
