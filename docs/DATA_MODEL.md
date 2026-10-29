# 数据模型与维护

## 源数据与生成产物

资料来源是 `data/catalog.json` 列出的JSON集合。初始集合是 `data/shrines/tottori.json`。每条记录使用稳定的 `id`，并有 `prefecture_code`；新增地区应使用不会与现有记录冲突的标识符，例如 `32-izumo-taisha`。

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

创立传说、最早文献、建筑年代、迁座、合祀为不同事件。机构页面引述古代史料，不等于本项目已经核验了原典。现有12社也不足以统计全县信仰比例。

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
