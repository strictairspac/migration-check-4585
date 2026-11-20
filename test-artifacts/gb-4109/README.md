# GB-4109 单位换算迁移验收

本目录存放单位统一换算需求的端到端验收脚本，不混入应用源码。

## 前置（本地无 docker 时的等价环境）
- PostgreSQL 16 监听 17748，库 `migrationcheck`，用户 `migrate`（trust）
- Redis 7 监听 16379
- 后端依赖已安装（`pip install -r backend/requirements.txt`）
- 在 `backend/` 目录启动：
  - `python3 -m uvicorn src.main:app --port 19248`（环境变量 DATABASE_URL / REDIS_URL / JWT_SECRET / SEED_DEMO=false）
  - `python3 -m src.worker`
- 静态站可用任意 http 服务托管 `frontend/`，并将 `/api/` 反代到 19248（等价 frontend/nginx.conf）

## 用例
- `e2e_check.py`：换算规则校验、四类逐行拒绝、原值/统一值、review 三维筛选、备份 v2 恢复、规则冻结、重试去重、空批次。
- `concurrency_check.py`：恢复与读取并发、取消零残留、逐行原子性、Infinity/NaN 非有限值拒绝。
- DOM 冒烟（jsdom，见会话记录）：结果页渲染、原单位/目标单位/原因筛选、中文拒绝标签、原值→统一值对照。

账号沿用 seed：operator/admin/viewer，密码 `Migrate2026!`。
