# 神祇地理志 · Shrine Atlas

以逐项出处整理日本神社、所在地、祭神与历史线索的地图项目。

当前版本 **v0.4** 收录鳥取縣神社廳22个公开地域目录的 **824条记录**，覆盖鸟取县全部19个市町村。814条有祭神资料，792处地点可标图，33条记录尚无可用地图位置；保留首批12条多来源研究记录及大神山神社本社、奥宫两个地点。

**“全县”指上述公开目录完整收录，不等于已经穷尽每一处小祠、境内末社或未列名设施。** 新增记录以目录事实为基础，由绪尚未逐社完成独立历史考证。查阅日期：2026-10-29。核对范围、链接修正与缺失名单见 [本次核对报告](docs/TOTTORI_AUDIT.md)。

## 下载后查看

1. 点击 **Code → Download ZIP**，解压下载的文件。
2. 双击打开 [offline/tottori-shrine-atlas.html](offline/tottori-shrine-atlas.html)。

单文件快照内嵌页面、地图和全县资料，可以离线查看；打开外部出处或地图时需要联网。在GitHub中点击HTML文件会显示源码，请下载后用浏览器打开。

## 不知道神社名，也可以开始探索

- **先选地点**：全县地图显示19个有名称的市町村入口及名录条数。点击入口，地图聚焦并筛选目录；入口位置是浏览示意，不是行政中心或市町村边界。
- **预览一个聚合点**：在市町村或局部地图点击数字，先看最多4条神社的名称、地址与祭神，再选择“放大这个区域”或“浏览这组全部记录”。
- **浏览眼前区域**：拖动／缩放地图后点击“浏览当前地图范围”。侧栏只在按按钮时更新；地图移动后会提示再次更新。取消“地图范围”条件即可回到目录，包括未定位条目。
- **按分类发现**：侧栏“不知道社名？从这里探索”提供市町村、祭神原文、旧社格及首批12条研究记录。祭神数量按神社记录去重，不把不同写法自动合并为同一神。
- **阅读卡片再决定**：目录列出地址、祭神与已有的简介／旧社格线索，适合逐条浏览。名称、位置、祭神和沿革的出处仍在详情中。

目录保留每页50条、东中西部分区、资料状态筛选和搜索；选择“祭神暂缺”“未定位”“待核对”可以检查缺失项。编号对应神社庁原目录；同名神社保持独立。地图聚合数字表示地点数，市町村入口数字表示名录条数，两者在图例中分别说明。

交互的具体规则与验证方法见 [EXPLORATION.md](docs/EXPLORATION.md)。

## 使用资料分离版

在项目目录运行：

```bash
python -m http.server 8000 --bind 127.0.0.1
```

浏览器访问 `http://127.0.0.1:8000/`。Windows也可以使用 `py -m http.server 8000 --bind 127.0.0.1`。直接双击根目录的 `index.html` 时，浏览器通常会限制本地JSON读取；这时使用服务器或离线快照。

## 项目结构

| 路径 | 用途 |
| --- | --- |
| `index.html`, `web/` | 页面结构、样式、交互及可独立测试的探索规则，不内嵌神社资料 |
| `data/catalog.json` | 资料集清单和地图路径 |
| `data/shrines/tottori/*.json` | 按19个市町村拆分的事实与逐项引用 |
| `data/coverage-tottori.json` | 收录统计、22个目录、链接修正及缺失项 |
| `data/research/tottori-registry.json` | 已核实的7条法人登记关闭证据 |
| `data/maps/prefectures.json` | 47个都道府县展示轮廓 |
| `database/schema.sql`, `database/catalog.sqlite` | 关系表结构与生成的SQLite数据库 |
| `scripts/build.py` | 验证资料，重建数据库与离线快照 |
| `scripts/collect_tottori.py`, `scripts/import_tottori.py` | 公开目录采集与保守导入；原始网页不提交 |
| `offline/tottori-shrine-atlas.html` | 可直接打开的单文件快照 |
| `media/images/`, `media/models/` | 后续图片和3D模型文件目录 |
| `docs/` | 数据模型、核对报告、来源与权利说明 |

## 数据库与编辑

JSON是版本管理的源数据；SQLite和离线HTML由其生成。修改JSON后运行：

```bash
python scripts/build.py
```

仅使用Python标准库，需要SQLite 3.37以上版本以支持 `STRICT` 表。构建检查稳定ID、来源引用、成对空坐标、47个行政区划、824条名录对应关系、数据库外键和完整性，并核对祭神原文分组导入后未改变。

**当前网页仍读取JSON，尚未通过后端API查询SQLite。** 数据库已经分开保存神社、地点、原文祭神表、出处、历史线索、目录对应、字段状态、法人登记及媒体元数据。例：

```sql
-- 查看尚无可标图地点的记录，不把缺失坐标写成0,0。
SELECT s.id, s.name_ja, s.municipality
FROM shrines s
WHERE NOT EXISTS (
  SELECT 1 FROM locations l
  WHERE l.shrine_id = s.id AND l.map_status = 'mapped'
);

-- 赤猪岩神社的两份祭神原表分别保留。
SELECT role_text, name_verbatim
FROM deity_occurrences
WHERE shrine_id = 'akaiiwa'
ORDER BY group_id, ordinal;
```

### 重新采集

```bash
python scripts/collect_tottori.py /绝对路径/私有缓存目录
python scripts/import_tottori.py /绝对路径/私有缓存目录 /绝对路径/japan.geojson
python scripts/build.py
```

采集器仅访问网站公开普通目录页，限速并缓存。导入器从公开导航中寻找错链的替代页，核对社名和所在地，不猜测页面编号。现有12条研究资料使用稳定ID保留。完整县界GeoJSON为可选第二参数；省略时不能完成新来源坐标的县界检查，应保留现有坐标审核或自行核实后提交。原始网页可能含第三方文字及地图嵌入参数，缓存须放在仓库外，不上传。

页面交互规则另有使用真实目录的测试（需Node.js）：

```bash
node --test tests/explore-core.test.js
```

## 资料原则

- 未公布祭神就留空，不根据社名推定主神；没有明确主配分类就保留“祭神”。
- 目录、详情、机构引述、社传与历史考证分别说明；提及古籍不等于已核验原卷。
- 没有可核实坐标时保留地址，不估算参考点；县界外的来源点暂不标图。
- 原文神名不自动统一为神格实体，名单项目数不能当作独立神祇数。
- 法人登记关闭不等于神社建筑消失或祭祀停止；相关记录不从名录中删除。
- 法人登记所在地独立注明，不能直接当作现场神社坐标。

## 图片与3D模型

本版尚未添加图片、3D模型或模型查看器。已预留文件目录和 `media_assets` 表，记录神社／地点、来源、作者、许可、文件路径和校验值。详见 [media/README.md](media/README.md)。大文件宜使用Git LFS、Release或对象存储。

来源与旧版底图的精度、再利用条件见 [SOURCES_AND_RIGHTS.md](docs/SOURCES_AND_RIGHTS.md)。公开仓库不代表第三方网页、地图和媒体已被重新授予统一许可。
