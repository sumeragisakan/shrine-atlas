# 神祇地理志 · Shrine Atlas

以可追溯出处整理日本神社、所在地、祭神与历史线索的地图项目。

当前版本 **v0.2**：日本47个都道府县地图，鸟取县首批 **12座神社、13处地点**。大神山神社的本社和奥宫属于一条神社记录，分别标记位置。其他地区尚未收录；样本并非全县普查。

## 下载后查看

1. 在本仓库点击 **Code → Download ZIP**，然后解压。
2. 双击打开 [offline/tottori-shrine-atlas.html](offline/tottori-shrine-atlas.html)。

离线快照内嵌所需页面、地图和资料，不需要安装依赖。访问原始来源或外部地图时需要联网。在GitHub中点击HTML文件会显示源代码，请下载后用浏览器打开。

## 使用资料分离版

在项目目录运行：

```bash
python -m http.server 8000 --bind 127.0.0.1
```

然后用浏览器访问 `http://127.0.0.1:8000/`。Windows也可以使用 `py -m http.server 8000 --bind 127.0.0.1`。

主页面从独立JSON文件读取资料。直接双击根目录的 `index.html` 时，浏览器通常会限制本地JSON读取；这时使用上面的本地服务器或离线快照即可。

## 项目结构

| 路径 | 用途 |
| --- | --- |
| `index.html` | 页面结构，不内嵌神社或地图资料 |
| `web/atlas.css`、`web/atlas.js` | 样式与地图交互 |
| `data/catalog.json` | 资料集清单及地图路径 |
| `data/shrines/tottori.json` | 鸟取县神社资料；保留逐项引用和不同记载 |
| `data/maps/prefectures.json` | 用于展示的都道府县轮廓及边界范围 |
| `database/schema.sql` | SQLite关系表、引用关系与媒体元数据结构 |
| `database/catalog.sqlite` | 由资料文件生成、可直接查询的SQLite数据库 |
| `scripts/build.py` | 验证资料、重建数据库与离线快照 |
| `offline/tottori-shrine-atlas.html` | 可直接打开的单文件离线快照 |
| `media/images/`、`media/models/` | 后续图片和3D模型的文件目录 |
| `docs/DATA_MODEL.md` | 数据模型与编辑规则 |
| `docs/SOURCES_AND_RIGHTS.md` | 来源、地图精度与第三方权利说明 |

## 数据库与编辑

目前以 `data/catalog.json` 列出的JSON资料集为版本管理的源数据，SQLite数据库与离线HTML是生成产物。这样可以在GitHub中查看资料的具体修改，而不用手工比较二进制数据库。

修改JSON后运行：

```bash
python scripts/build.py
```

构建仅使用Python标准库，不需要 `pip install`。需要支持 `STRICT` 表的SQLite 3.37及以上版本（可用 `python -c "import sqlite3; print(sqlite3.sqlite_version)"` 检查）。构建会检查引用、坐标、标识符、媒体文件与数据库外键，并核对祭神原文名单在导入后未被改变。

SQLite已包含神社、地点、祭神原文分组、历史说明、来源和媒体元数据表。**当前网页仍读取JSON，尚未通过后端API直接查询SQLite。** 后续需要编辑界面、检索服务或多人使用时，可在这一数据库上增加API；无需将图片或模型塞进HTML或数据库BLOB。

例如使用SQLite命令行查询赤猪岩神社的两份祭神表：

```sql
SELECT role_text, name_verbatim
FROM deity_occurrences
WHERE shrine_id = 'akaiiwa'
ORDER BY group_id, ordinal;
```

## 资料原则

- 当前奉祀、社传、机构引述史料及学术说明分别标明。
- 未明确区分主配时，保留原资料的“祭神”分类。
- 不把神话中的出场人物自动当作神社的祭神。
- 祭神名单或地址有差异时保留不同记载及来源，例如赤猪岩神社、仓吉賀茂神社。
- 神名先作为原文记录，不自动认定异名属于同一神格；也不据原文项目数量推算“独立神祇数”。

## 图片与3D模型

本版尚未添加图片或3D模型，也尚未实现模型查看器。已预留独立文件目录及 `media_assets` 关系表，记录所属神社／地点、文件路径、作者、来源、许可和校验值。新增文件前请核实使用与公开分发权，详见 [media/README.md](media/README.md)。较大的模型宜使用Git LFS、Release附件或对象存储，避免持续扩大普通Git历史。

## 来源与权利

每座神社的资料内均包含出处链接和2026-10-29的查阅日期。原资料发表日期与本项目查阅日期分开记录。

地图依据国土地理院“地球地図日本”的 `dataofjapan/land` 转换版加工，并作展示简化；不是最新行政界或测量、导航成果。详见 [来源及权利说明](docs/SOURCES_AND_RIGHTS.md)。公开仓库不表示第三方网页、照片、模型或地图被重新授予统一许可。
