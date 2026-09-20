# NyaGallery 数据契约

## 统一 Asset

统一交换格式为 `nyagallery.asset.v1`。`asset_id` 是 `sha256:<64 位十六进制摘要>`；原图的 `blob.sha256` 必须与它一致。`blob.storage_key` 是人类可读的稳定路径，原图不可变，分类变化不能移动它。

```json
{
  "schema": "nyagallery.asset.v1",
  "asset_id": "sha256:<sha256>",
  "blob": {
    "sha256": "<sha256>",
    "size": 123,
    "mime": "image/jpeg",
    "width": 1920,
    "height": 1080,
    "storage_key": "original/pixiv_123.jpg",
    "original_filename": "123.jpg"
  },
  "metadata": {},
  "external_refs": [{"system": "lsky", "id": "123", "path": "uploads/123.jpg"}],
  "created_at": "2026-01-01T00:00:00Z"
}
```

## Primary 模式

`file` 模式以 JSON 元数据为真相源，数据库只允许作为可删除、可重建的索引；`database` 模式以 SQLite、PostgreSQL 或 MySQL 为真相源，JSON 只能作为导出侧车。应用不会在一次写入中双写两个 primary。

`nyagallery convert --from file|database --to file|database` 默认只做 dry-run；切换到 `file` 时需要 `--output <dir>`，加入 `--confirm` 后才会在目标旁边创建备份，写入临时目录，逐文件计算 SHA256，再原子切换。切换到 `database` 会校验原图 SHA256 后在一个事务内导入索引，并保存数据库侧车备份。源文件始终只读。

## 旧数据

`nyagallery.creator_metadata.v1` 由 `LegacyReader` 只读解析。启动和索引重建仍能读取旧的单资源 JSON 及 creator 分组 JSON，不自动覆盖旧文件。显式转换或 `migrate-metadata` 才会写新文件。

## 物理与虚拟层

物理层保存来源、创作者和作品 ID；虚拟文件夹保存 tag 查询（例如 `tag:type/ugoira`），位于 `storage/tags/virtual_folders.json`，不会移动原图。来源、画师、类型、相册和自建分类都应通过 tag/query 表达。

## 迁移与回滚

Importer 先读取源、转换 Asset、只读校验 SHA256，再复制或硬链接原图，保留 `external_refs`。目标写入失败时不修改源；目标目录可使用转换命令生成的备份恢复。Lsky importer 重新计算 SHA256，不把源数据库表直接复制到目标库。
