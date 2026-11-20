import time,logging,redis
from pathlib import Path
from src.config.settings import REDIS_URL
from src.config.database import Session
from src.models.batch import Batch
from src.models.mapping import Mapping
from src.models.run import Run,TargetRow
from src.services.migration import migrate,make_backup,key_digest,Cancelled
from src.services.audit import log
q=redis.Redis.from_url(REDIS_URL)
def progress(run_id,info):
 Path('/tmp/worker-heartbeat').touch()
 with Session() as s:
  r=s.get(Run,run_id)
  if r.cancel_requested or r.status=='cancelled':raise Cancelled()
  r.progress=info;s.commit()
while True:
 Path('/tmp/worker-heartbeat').touch()
 try:
  item=q.blpop('migration-runs',timeout=2)
  if not item:continue
  run_id=int(item[1])
  with Session() as s:
   r=s.query(Run).filter_by(id=run_id).with_for_update().first()
   if not r or r.status!='queued':continue
   # 重试去重：已存在目标行的运行不允许再次写入
   if s.query(TargetRow).filter_by(run_id=run_id).count():
    r.status='failed';r.error='该运行已存在目标行，拒绝重复写入';s.commit();continue
   r.status='running';snapshot=r.snapshot;s.commit()
  try:
   mapping_snapshot=snapshot['mapping']
   result=migrate(snapshot['batch']['rows'],mapping_snapshot['rules'],mapping_snapshot['chunk_size'],mapping_snapshot.get('unit_rules',[]),lambda info:progress(run_id,info))
   result['backup']=make_backup(result,run_id,snapshot['batch']['name'],mapping_snapshot.get('unit_rules',[]))
   with Session() as s:
    r=s.query(Run).filter_by(id=run_id).with_for_update().first()
    if r.cancel_requested:raise Cancelled()
    # 提交前二次去重：并发/重试场景下整次回滚，不重复写入
    if s.query(TargetRow).filter_by(run_id=run_id).count():
     r.status='failed';r.error='目标行已存在，重试提交被拒绝';s.commit();continue
    for i,row in enumerate(result['accepted_rows']):s.add(TargetRow(run_id=run_id,ordinal=i,key_digest=key_digest(row),payload=row))
    r.result=result;r.status='completed';s.commit()
   log('worker','run.completed',str(run_id))
  except Cancelled:
   with Session() as s:r=s.get(Run,run_id);r.status='cancelled';r.error='用户取消，未提交目标行';s.commit()
   log('worker','run.cancelled',str(run_id))
  except Exception as exc:
   logging.exception('migration failed')
   with Session() as s:r=s.get(Run,run_id);r.status='failed';r.error=str(exc)[:1000];s.commit()
 except Exception:logging.exception('worker loop');time.sleep(2)
