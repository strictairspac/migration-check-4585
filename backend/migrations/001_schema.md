# Schema v1
SQLAlchemy metadata creates users/audits/batches/mappings/runs/target_rows. Unique natural names, foreign keys, and target unique(run_id,key_digest) enforce linkage. Successful workers atomically commit accepted target rows; cancelled/failed runs do not persist partial targets. Restore replaces a run's target set under a run row lock and checks the logical backup checksum before commit.

# Schema v2 (unit conversion)
mappings 增加 unit_rules JSON 列（非空，默认 []），按检测项声明 target_unit / precision / allowed_units / factors / min_value / max_value。新库由 metadata 直接创建；旧库需 `ALTER TABLE mappings ADD COLUMN unit_rules JSON NOT NULL DEFAULT '[]'`。
target_rows.payload 在 v1 五字段外增加 original_value / original_unit 原值原单位证据，result_value+unit 为统一目标值。逻辑备份升级为 version 2，内含 unit_rules，恢复仍按 run 内 checksum 与逐行 hash 核验。拒绝行带 reason(code) 与 detail(中文说明)，拒绝原因枚举见 src/constants/enums.py。
