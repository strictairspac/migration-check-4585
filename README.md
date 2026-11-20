# 见山 · 检验结果迁移核对站

见山质量档案组13人用源批次、字段映射、后台对账运行完成旧字段检验结果的有证据交接。

## 场景与业务
上游实验室交付旧字段JSON检验记录；过去人工改字段名、复制到新表并凭总行数判断成功。痛点：非法数值默默丢失、重复委托号覆盖、备份无法证明能恢复。本站登记原始行，字段映射规定类型和必填，Python逐块转换并保留拒绝原行，真实PG目标表一次提交。下游质量复核人下载对账凭据，管理员用JSON逻辑备份恢复本次运行目标并核验。

四业务页：源批次、字段映射、迁移执行（可取消）、差异核对（拒绝区/目标行/备份）；管理员另有审计和回传恢复。三核心实体batches/mappings/runs，另target_rows持久化目标行。全部实体按模型/schema/service/controller/routes/前端api/store/page贯穿。

## 启动与账号
```sh
cp .env.example .env
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```
前端 http://localhost:18248 ，后端 http://localhost:19248/docs ，PostgreSQL localhost:17748（migrate / migratepass / migrationcheck）。结束docker compose down -v --remove-orphans会清除本地数据。

| 角色 | 账号 | 权限 / 页面 | 典型动作 |
|---|---|---|---|
| admin | admin@migration.local | 全部、审计、恢复 | 回传备份恢复目标并校验 |
| operator | operator@migration.local | 创建/编辑/执行/取消/导出 | 配置映射并迁移 |
| viewer | viewer@migration.local | 只读、下载凭据/备份 | 复核拒绝区和真实目标表 |

密码统一Migrate2026!；PBKDF2密码与8小时JWT。本地演示凭据与JWT密钥，部署前更换。

## 一天的交接剧本
1. 09:00 operator签入，查看见山日班检验结果14条多单位记录（MPa/kPa/J/kJ）。
2. 09:05 登记lab-results-20261117.json，委托号JS-20261117-001结果420.1MPa。
3. 09:10 新建shift-20261117批次，复制旧字段。
4. 09:15 字段映射：委托号→sample_code、检测项→test_name、结果→result_value、单位→unit、时间→measured_at，每块4行；同页配置检测项换算规则（如kPa×0.001→MPa，精度3位；kJ×1000→J，精度2位，含目标值区间）。
5. 09:20 提交shift-20261117对账，或运行旧字段异常样本查看缺规则/非有限数字/越界/超精度/单位不允许/重复/空值/缺列逐行拒绝。
6. 09:25 查看接受/拒绝与分块证据，在核对页按原单位、目标单位或拒绝原因筛选，读取真实PG目标表的统一值并对照原值原单位。
7. 09:30 下载reconciliation-<id>.json与backup-<id>.json(v2，含冻结换算规则)，viewer复核。
8. 10:00 admin回传该备份，恢复并核对摘要，确认统一值与来源同一，查看审计完成事件。

seed含三账号、三批次（多单位正常/异常/空输入）、三映射（均带换算规则）。固定数值、自然键upsert式补缺，不覆盖用户编辑；连续执行不新增。

同一检测项会以不同单位从多家实验室送来。字段映射之外，映射可按检测项声明**单位换算规则** `unit_rules`：允许的原单位 `allowed_units`、目标单位 `target_unit`、精度 `precision`（0~12位小数）、线性系数 `factors`（目标值=原值×系数，目标单位系数必须为1）与按目标单位声明的允许区间 `min_value/max_value`。换算规则在运行受理时随映射快照冻结：之后修改规则只影响新运行，已完成结果、目标行与备份均不改变。

## 迁移、校验、取消与恢复
字段类型为text/decimal/datetime。decimal使用Decimal精确转换，范围±1e9；无穷/NaN拒绝。空值/空串按required隔离（只有unit可非必填）；缺源字段隔离。时间统一UTC，无时区按Asia/Shanghai(+08:00)解释。基础转换通过后执行单位换算：缺换算规则(`unit_rule_missing`)、原单位不在允许列表(`source_unit_not_allowed`)、非有限值(`invalid_decimal`)、统一值越界(`value_out_of_range`)、换算后超过目标精度(`precision_loss`)均**逐行拒绝并保留原行与原因**，其他行照常提交。自然键sample_code+test_name按规范JSON SHA-256计算；同次运行重复键(`duplicate_natural_key`)只接受首条合法记录。每行与全部接受行用排序key/紧凑JSON/UTF-8算SHA-256。拒绝行保存原行、原因代码与中文说明。

目标行在原五字段外增加 `original_value`/`original_unit` 原值原单位证据，`result_value`+`unit` 为统一目标值。差异核对页可按**原单位、目标单位、拒绝原因**三维筛选，对照展示“原值/原单位 → 统一值/目标单位”，后端 `GET /runs/{id}/review` 提供同源分页数据。

最多2000源行、每行20列、单元格500字符；每块1-500行。逐块更新进度；取消在块间检查，最终提交前锁定run再次检查，成功目标一次提交；取消/异常没有部分目标数据。后台任务使用简单Redis单消费者；worker在取任务与最终提交两处检查目标行是否已存在，重复队列消息/重试提交不会重复写入，冲突时整次回滚。换算、落库与备份恢复可并发：恢复在run行锁内事务性替换并回读核验，读取始终只看到完整的旧集合或新集合。

下载备份为本工具目标行的逻辑JSON快照(**version2**)，含run_id/冻结的unit_rules/rows（含原值原单位）/row_hashes/checksum，不是pg_dump或物理备份，不含WAL/索引/权限。管理员恢复只允许该运行已保存checksum完全匹配的备份；先核验版本、逐行/总体摘要、schema（七字段含原值证据）和自然键，再事务性替换该运行target_rows，回读重新计算摘要并保存recovery记录。篡改、错运行、未完成运行拒绝，恢复事务回滚；恢复旧备份得到的统一目标值与行来源与备份完全一致；不能用任意新数据覆盖目标。

受控场景演示旧字段到新目标结构的逻辑迁移，数据库真实保存源/映射/目标/对账。不能连接远端数据库，不宣称生产异构迁移或灾备能力。

## 工程与开发
Python3.11/FastAPI/SQLAlchemy/psycopg/Redis/PostgreSQL16，原生HTML/CSS/JS，nginx1.27。exact五服务frontend/backend/worker/db/redis均healthcheck，数据库/Redis/共享产物命名卷；依赖健康后启动。请求追踪、全局错误、JWT授权和业务审计横切。

backend/src按models/schemas/services/controllers/routes/middlewares/config/constants/utils；backend/scripts/seed_demo.py；backend/migrations记录元数据版本。frontend/src按api/stores/pages/components/common/hooks/router/types/constants/utils；共享table/status/feedback；forms/poll hooks。角色/状态/类型枚举在backend/src/constants/enums.py与frontend/src/constants/enums.js。墨绿邮政凭单视觉，Noto Sans SC/Space Mono双字体来自Google Fonts，离线回退；桌面/平板/手机响应。

.env.example定义COMPOSE_PROJECT_NAME/三端口/JWT_SECRET/SEED_DEMO；DATABASE_URL/REDIS_URL由Compose注入。启动SEED_DEMO失败只记日志。本地开发pip install -r backend/requirements.txt，设数据库/Redis/JWT环境变量，在backend运行uvicorn src.main:app --reload；前端需/api代理，不能file://。测试/截图/日志放批次test-artifacts/gb-4109，源码不混入。MIT License。
