import redis
from datetime import datetime,timezone
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from src.config.database import Session
from src.config.settings import REDIS_URL
from src.models.batch import Batch
from src.models.mapping import Mapping
from src.models.run import Run,TargetRow
from src.utils.serialization import record
from src.services.migration import digest,key_digest,validate_backup
from src.constants.enums import REJECT_REASON_LABELS
queue=redis.Redis.from_url(REDIS_URL)
def list_items():
 with Session() as s:return [record(r) for r in s.query(Run).order_by(Run.id.desc()).limit(100).all()]
def detail(item_id):
 with Session() as s:
  r=s.get(Run,item_id)
  if not r:raise HTTPException(404,'未找到对账运行')
  return record(r)
def create(data):
 with Session() as s:
  m=s.get(Mapping,data.mapping_id)
  if not m:raise HTTPException(404,'未找到字段映射')
  b=s.get(Batch,m.batch_id)
  r=Run(name=data.name,batch_id=b.id,mapping_id=m.id,status='queued',snapshot={'batch':record(b),'mapping':record(m)})
  s.add(r);s.commit();s.refresh(r);result=record(r)
 try:queue.rpush('migration-runs',result['id'])
 except redis.RedisError:
  with Session() as s:r=s.get(Run,result['id']);r.status='failed';r.error='队列不可用，请创建新任务';s.commit()
  raise HTTPException(503,'队列不可用，请稍后重试')
 return result
def cancel(item_id):
 with Session() as s:
  r=s.query(Run).filter_by(id=item_id).with_for_update().first()
  if not r:raise HTTPException(404,'未找到对账运行')
  if r.status not in ('queued','running'):raise HTTPException(409,'运行已终止，无法取消')
  r.cancel_requested=True
  if r.status=='queued':r.status='cancelled'
  s.commit();return record(r)
def targets(item_id):
 detail(item_id)
 with Session() as s:rows=[r.payload for r in s.query(TargetRow).filter_by(run_id=item_id).order_by(TargetRow.ordinal)]
 return {'rows':rows,'count':len(rows),'checksum':digest(rows)}
def review(item_id,source_unit=None,target_unit=None,reason=None,limit=200,offset=0):
 """差异核对：按原单位/目标单位/拒绝原因过滤；接受行与拒绝行可独立分页核对。"""
 r=detail(item_id)
 result=r.get('result')
 if not result:raise HTTPException(409,'运行尚未完成，暂无核对数据')
 mapping=r.get('snapshot',{}).get('mapping',{})
 rules=mapping.get('rules',[])
 unit_source=next((x['source'] for x in rules if x.get('target')=='unit'),'单位')
 accepted=result.get('accepted_rows',[]);rejected=result.get('rejected_rows',[])
 def reject_unit(row):
  v=row.get('source',{}).get(unit_source)
  return str(v) if v not in (None,'') else None
 if source_unit:
  accepted=[x for x in accepted if x.get('original_unit')==source_unit]
  rejected=[x for x in rejected if reject_unit(x)==source_unit]
 if target_unit:
  accepted=[x for x in accepted if x.get('unit')==target_unit]
 if reason:
  rejected=[x for x in rejected if x.get('reason')==reason]
 total_a=len(accepted);total_r=len(rejected)
 accepted_page=accepted[offset:offset+limit]
 rejected_page=rejected[offset:offset+limit]
 source_units=sorted({x.get('original_unit') for x in result.get('accepted_rows',[]) if x.get('original_unit')}|{reject_unit(x) for x in result.get('rejected_rows',[]) if reject_unit(x)})
 target_units=sorted({x.get('unit') for x in result.get('accepted_rows',[]) if x.get('unit')})
 reasons=sorted({x.get('reason') for x in result.get('rejected_rows',[]) if x.get('reason')})
 return {
  'run_id':item_id,'filters':{'source_unit':source_unit,'target_unit':target_unit,'reason':reason},
  'accepted_rows':accepted_page,'accepted_total':total_a,
  'rejected_rows':rejected_page,'rejected_total':total_r,
  'source_units':source_units,'target_units':target_units,
  'reasons':[{'code':c,'label':REJECT_REASON_LABELS.get(c,c)} for c in reasons],
  'limit':limit,'offset':offset,
 }
def backup(item_id):
 r=detail(item_id)
 if r['status']!='completed':raise HTTPException(409,'仅完成运行可以备份')
 return r['result']['backup']
def restore(item_id,data):
 with Session() as s:
  r=s.query(Run).filter_by(id=item_id).with_for_update().first()
  if not r:raise HTTPException(404,'未找到对账运行')
  if r.status!='completed':raise HTTPException(409,'仅完成运行可以恢复')
  try:rows=validate_backup(data.backup,r.result['checksum'],item_id)
  except ValueError as e:raise HTTPException(422,str(e))
  before=s.query(TargetRow).filter_by(run_id=item_id).count()
  s.query(TargetRow).filter_by(run_id=item_id).delete()
  try:
   for i,row in enumerate(rows):s.add(TargetRow(run_id=item_id,ordinal=i,key_digest=key_digest(row),payload=row))
   s.flush()
  except IntegrityError:
   s.rollback()
   raise HTTPException(409,'恢复写入冲突，整次回滚')
  actual=[x.payload for x in s.query(TargetRow).filter_by(run_id=item_id).order_by(TargetRow.ordinal)]
  proof={'restored_at':datetime.now(timezone.utc).isoformat(),'previous_count':before,'restored_count':len(actual),'checksum':digest(actual),'verified':digest(actual)==r.result['checksum']}
  if not proof['verified']:raise HTTPException(409,'恢复后校验失败，已回滚')
  r.recovery=(r.recovery or [])+[proof];s.commit();return proof
