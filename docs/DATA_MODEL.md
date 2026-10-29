# 数据模型与维护

## 源数据与生成产物

资料来源是 `data/catalog.json` 列出的JSON集合。鸟取县分为 `data/shrines/tottori/` 下19个市町村集合，清单由 catalog 指定。每条记录使用稳定的 `id`，并有 `prefecture_code`；新增地区应使用不会与现有记录冲突的标识符，例如 `32-izumo-taisha`。

`database/catalog.sqlite` 和 `offline/tottori-shrine-atlas.html` 由 `python scripts/build.py` 生成。不要只修改SQLite并将它视为已同步JSON；重建会以JSON重新生成数据库。未来转为数据库直接写入时，应先确定唯一写入入口及JSON导出流程。

地图轮廓单独保存在 `data/maps/prefectures.json`。SQLite的 `prefectures` 表保存代码和名称，不保存展示用SVG路径。

## 主要对应

| JSON字段 | SQLite表 | 说明 |
| --- | --- | --- |
| `id`, `name`, `kana`, `prefecture_code` 等 | `shrines` | 神社基本记录；`intro` 对应 `introduction` |
| `aliases`, `tags` | `aliases`, `tags` | 原顺序保留 |
| `sources` | `sources`, `shrine_sources` | 按URL去重；保留各神社的局部引用序号 |
| `locations` | `locations`, `location_sources` | 一座神社可有多个地点；有独立稳定地点ID |
| `kami[].role` | `deity_groups` | 记录来源中的分类和列表身份 |
| `kami[].names` | `deity_mentions` | 原文神名项目，不等于统一神格实体 |
| `kami[].sources` | `deity_group_sources` | 每份名单的证据来源 |
| `facts` | `historical_notes`, `historical_note_sources` | 社传、沿革和史料引述分开记录性质 |
| `note`, `noteSources` | `shrines.research_note`, `research_note_sources` | 差异说明及其引用 |
| `media` | `media_assets` | 图片／模型的元数据；文件另存 |

## 引用与日期

JSON各字段的 `sources: [0, 1]` 指向同条神社记录的来源数组。界面显示为 `[1]`、`[2]`。调整来源数组顺序时必须同步更新引用；构建会检查越界，但无法判断一个合法序号是否指向了错误文章，仍需人工核对。

每份来源记录含 `checked` 查阅日期、可空的 `published` 发表日期。没有发表时间时不推测。`kind` 指资料性质，不是自动生成的概率置信度。

## 祭神与历史

同一神社可以有多组祭神，例如大神山神社的本社与奥宫，以及赤猪岩神社的两份异记。每组保留原文角色说明、名字次序与来源。不要将不同名单直接拼成一张“最终正确名单”。

目前未建立异名统一的 `deities` 主表。后续如需比较神格，应另建受证据约束的对应关系，保留匹配理由与争议状态，再与 `deity_mentions` 关联。

创立传说、最早文献、建筑年代、迁座、合祀为不同事件。机构页面引述古代史料，不等于本项目已经核验了原典。全县目录中的缺失和不同祭神分类仍需核对，不能将目录项目数直接解释为信仰比例。

## 媒体

文件放在 `media/images/` 或 `media/models/`。关联某一地点时使用该条记录中已有的 `locations[].id`。SQLite外键阻止将甲神社的媒体绑定到乙神社的地点。

`media` 项目至少提供：

```json
{
  "id": "31-example-photo-001",
  "kind": "image",
  "location_id": "example:1",
  "path": "media/images/example.jpg",
  "caption": "说明文字",
  "source_url": "https://来源页面",
  "creator": "作者或机构",
  "license": "已核实的许可名称或书面授权说明",
  "license_url": "https://许可说明页面",
  "checked_at": "YYYY-MM-DD"
}
```

示例仅说明结构，不是本版真实媒体记录。`location_id` 和 `license_url` 可以为空；新增文件须真实存在，构建会计算SHA-256。如提供 `sha256`，构建会核对一致性。大文件和外部对象存储的具体导入流程待后续确定。

## v0.3名录、缺失字段与法人资料

| JSON字段 | SQLite表 | 含义 |
| --- | --- | --- |
| `directory` | `directory_entries` | 稳定目录编号、名称、名录所在地、原链接、修正链接、详情匹配状态及源页SHA-256 |
| `record_status`, `availability`, `source_fields` | `record_quality` | 首批研究／目录导入，祭神及由绪可用状态，祭神原栏、旧社格 |
| `locations[].map_status` | `locations.map_status` | `mapped`、`not_published`、`outside_prefecture_needs_review` |
| `entity_registry` | `entity_registry` | 政府法人编号、登记关闭日期、登记地址与来源；不代表现场状态 |

新条目ID为 `tottori-####`（原目录号），既有12条ID保持不变。`no` 是显示次序，`directory.number` 是原目录编号，不能混用。一个名录条目对应一条神社记录；大神山神社仍有两个地点。

未公布祭神时 `kami: []`，并明确 `availability.kami: "not_published"`。坐标只允许成对为null，缺失时不得用0、县城中心或地址估算点替代。来源坐标落在县界外时保留原值但暂不绘制；详情注明异常。

`source_fields.kami_verbatim` 保留原栏文本。界面按原分隔符拆分显示，原文中的错位或疑似连字另标“原表需辨读”，不擅自修补为确定的神名。

`data/coverage-tottori.json` 是这一采集批次的核对报告，包含22个目录各自的条数、19市町村统计、缺失字段及链接修正。更新资料时同步核对报告；改变收录范围时应另建批次或更新范围说明。

## v0.4探索的统计口径

市町村入口依 `municipality`（名录归属）分组，保留未定位记录；入口位置只取该组已定位记录的分布中心作浏览示意。没有新增市町村行政界数据，不将这些入口解释为政府所在地或行政中心。

地图范围筛选使用点击时的投影范围快照。一条神社任一 `mapped` 地点落在范围内即计入一次；有本社和奥宫的大神山神社不会因此重复计数。缺失坐标及隔离待核坐标均不参加范围判定，地址记录仍在全县／市町村目录保留。

祭神分类使用 `kami[].names` 的原文项目，按神社ID去重计数，保留每个不同写法；不是统一神格统计。旧社格使用 `source_fields.former_rank` 原文，排除空栏和纯横线占位，不推测缺失值，也不作为现今排名。研究起点直接使用现有12条 `research_enriched` 记录与简介，不新增无出处的神话分类。

## v0.5全国地区索引

`data/catalog.json` 的 `regions` 列出47个都道府县及每地区的集合、覆盖报告、SQLite和离线文件路径。主页面只加载URL参数 `?pref=NN` 对应地区；全国页只读取索引，不一次读取全国神社。JSON分为每批150条的机构／历史记录文本，稳定ID独立于文件顺序。

`record_status: historical_directory` 是未可靠连接到机构同址记录的研究会条目；它可能与机构记录重复，不代表现今实存实体。`provenance.identity_match: unique_name_address` 只说明同名同址的唯一对应，不证明祭祀现况。不同来源的祭神表分别保留，历史表在角色说明与卡片中标记。

`source_retrievals` 保存地区检索的POST参数及采集方式；`record_provenance` 保存来源ID、对应方式、原始字段版本和字段异常。`locations` 新增地址状态与旧址字段。目录号改为文本，避免不同机构的原始标识被错误当作全局数字键。

来源若只提供地图视窗中心，点位状态为 `source_map_viewport`，原值保留但不绘制。未知祭神占位词保留原栏，不作为已命名神祇分组。

各新地区数据库以 `.sqlite.gz` 无损封装；解开gzip后是经验证的标准SQLite。鸟取仍保留原有 `database/catalog.sqlite` 路径。离线页面压缩内嵌一地区的资料，切换时通过全国离线索引跳转，便于每地区独立提交。
