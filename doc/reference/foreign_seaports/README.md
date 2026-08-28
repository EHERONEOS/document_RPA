# 国外海港地点集合

本目录基于 UN/LOCODE 代码表生成，适用于英文地址或港口地点的初步匹配。

## 筛选规则

- `Function` 的第 1 位为 `1`，即 UN/LOCODE 定义的 Maritime transport（海港/海运港口）。
- 排除中国大陆国家代码 `CN`。
- 保留香港 `HK`、澳门 `MO`、台湾 `TW`。
- 不以行政意义上的“城市”判断；集合包含 UN/LOCODE 标注为海运港口的地点、码头及港区。因此名称匹配后，应优先用国家代码或 UN/LOCODE 作二次确认。

## 文件

- `foreign_seaport_city_names.json`：16,385 个去重后的英文港口地点名，适合程序直接读取为集合。
- `foreign_seaport_city_names.txt`：同一集合，每行一个名称。
- `foreign_seaport_locations.csv`：16,831 条完整港口地点记录，包含国家代码、UN/LOCODE、原始名称、ASCII 名称、行政区及坐标。

## 数据来源

UN/LOCODE（United Nations Code for Trade and Transport Locations）公开代码表的镜像数据，仓库版本提交于 2026-07-27。UN/LOCODE 功能代码 `1` 的说明为 `Maritime transport (sea port or maritime port)`。

数据是港口地点名录，不等同于所有沿海城市；例如一个城市可能有多条港区记录，也可能有同名地点位于不同国家。
