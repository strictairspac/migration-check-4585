import json,hashlib
from decimal import Decimal,InvalidOperation,localcontext
from datetime import datetime,timezone,timedelta
from src.constants.enums import TYPES,REJECT_REASONS
class Cancelled(Exception):pass
MAX_ABS=Decimal('1000000000')
MAX_PLACES=12
BACKUP_VERSION=2
TARGET_FIELDS=set(TYPES)|{'original_value','original_unit'}
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def key_digest(row):return digest([row['sample_code'],row['test_name']])
def _fail(code,detail=''):
 e=ValueError(code);e.args=(code,detail);return e
def validate_rules(rules):
 if not isinstance(rules,list) or len(rules)!=5:raise ValueError('必须为五个目标字段各配置一条映射')
 targets=[]
 for rule in rules:
  if not isinstance(rule,dict) or set(rule)!={'source','target','type','required'}:raise ValueError('映射须包含source/target/type/required')
  target=rule['target']
  if not isinstance(target,str) or target not in TYPES or rule['type']!=TYPES[target]:raise ValueError('目标字段或类型不匹配')
  if not isinstance(rule['source'],str) or not 1<=len(rule['source'])<=60:raise ValueError('源字段名无效')
  if not isinstance(rule['required'],bool) or (target!='unit' and not rule['required']):raise ValueError('除unit外均为必填目标字段')
  targets.append(target)
 if len(set(targets))!=5:raise ValueError('目标字段不可重复')
 return rules
def _as_decimal(value,code='invalid_decimal'):
 if isinstance(value,bool):raise ValueError(code)
 try:d=Decimal(str(value))
 except (InvalidOperation,ValueError,TypeError):raise ValueError(code)
 if not d.is_finite():raise ValueError(code)
 return d
def validate_unit_rules(unit_rules):
 """检测项 -> 允许原单位/目标单位/精度/线性系数/目标值区间。factor 语义：目标值=原值*factor。"""
 if unit_rules is None:return []
 if not isinstance(unit_rules,list) or len(unit_rules)>100:raise ValueError('换算规则须为不少于0条、不超过100条的列表')
 normalized=[];seen=set()
 required={'test_name','target_unit','precision','allowed_units','factors','min_value','max_value'}
 for item in unit_rules:
  if not isinstance(item,dict) or set(item)!=required:raise ValueError('换算规则须包含test_name/target_unit/precision/allowed_units/factors/min_value/max_value')
  test_name=item['test_name'];target_unit=item['target_unit']
  if not isinstance(test_name,str) or not 1<=len(test_name)<=160:raise ValueError('换算规则检测项名称无效')
  if test_name in seen:raise ValueError('检测项 %s 的换算规则重复'%test_name)
  if not isinstance(target_unit,str) or not 1<=len(target_unit)<=40:raise ValueError('目标单位无效')
  precision=item['precision']
  if not isinstance(precision,int) or isinstance(precision,bool) or not 0<=precision<=MAX_PLACES:raise ValueError('精度须为0~%d位小数'%MAX_PLACES)
  allowed=item['allowed_units']
  if not isinstance(allowed,list) or not allowed or len(allowed)>50:raise ValueError('允许原单位须为非空列表')
  if any(not isinstance(u,str) or not 1<=len(u)<=40 for u in allowed) or len(set(allowed))!=len(allowed):raise ValueError('允许原单位名称无效或重复')
  if target_unit not in allowed:raise ValueError('目标单位必须在允许原单位列表内')
  factors=item['factors']
  if not isinstance(factors,dict) or set(factors)!=set(allowed):raise ValueError('每个允许原单位都必须提供换算系数')
  clean_factors={}
  for unit,raw in factors.items():
   f=_as_decimal(raw,'换算系数无效')
   if f<=0:raise ValueError('换算系数必须为正数')
   clean_factors[unit]=str(f)
  if Decimal(clean_factors[target_unit])!=1:raise ValueError('目标单位的换算系数必须为1')
  lo=_as_decimal(item['min_value'],'范围下限无效');hi=_as_decimal(item['max_value'],'范围上限无效')
  if lo>hi:raise ValueError('换算范围下限不能大于上限')
  seen.add(test_name)
  normalized.append({'test_name':test_name,'target_unit':target_unit,'precision':precision,'allowed_units':list(allowed),'factors':clean_factors,'min_value':str(lo),'max_value':str(hi)})
 return normalized
def convert(value,kind,required):
 if value is None or (isinstance(value,str) and not value.strip()):
  if required:raise ValueError('null_required')
  return None
 if kind=='text':
  v=str(value).strip()
  if len(v)>160:raise ValueError('text_too_long')
  return v
 if kind=='decimal':
  d=_as_decimal(value)
  if abs(d)>MAX_ABS:raise ValueError('invalid_decimal')
  return str(d)
 if kind=='datetime':
  try:
   dt=datetime.fromisoformat(str(value))
   if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone(timedelta(hours=8)))
   return dt.astimezone(timezone.utc).isoformat(timespec='seconds')
  except (ValueError,TypeError):raise ValueError('invalid_datetime')
 raise ValueError('invalid_type')
def _unify(target,unit_index):
 """在基础字段转换完成后做单位换算，失败抛携带 (reason, detail) 的 ValueError。"""
 test_name=target['test_name']
 spec=unit_index.get(test_name)
 if spec is None:raise _fail('unit_rule_missing','检测项 %s 缺少换算规则'%test_name)
 original_unit=target['unit']
 if original_unit is None or original_unit not in spec['allowed_units']:
  raise _fail('source_unit_not_allowed',"原单位 %r 不在允许列表 %s"%(original_unit,'/'.join(spec['allowed_units'])))
 original_value=target['result_value']
 d=Decimal(original_value)
 factor=Decimal(spec['factors'][original_unit])
 with localcontext() as ctx:
  ctx.prec=40
  unified=d*factor
 if not unified.is_finite() or abs(unified)>MAX_ABS:
  raise _fail('value_out_of_range','换算值超出全局范围 ±1e9')
 lo=Decimal(spec['min_value']);hi=Decimal(spec['max_value'])
 if not lo<=unified<=hi:
  raise _fail('value_out_of_range','统一值 %s %s 越界，允许区间 [%s, %s]'%(str(unified),spec['target_unit'],str(lo),str(hi)))
 places=spec['precision'];step=Decimal(1).scaleb(-places)
 if unified.quantize(step)!=unified:
  raise _fail('precision_loss','统一值 %s 超过目标精度 %d 位小数'%(str(unified),places))
 target['original_value']=original_value
 target['original_unit']=original_unit
 target['result_value']=str(unified.quantize(step))
 target['unit']=spec['target_unit']
def migrate(rows,rules,chunk_size,unit_rules=None,progress=lambda p:None):
 validate_rules(rules)
 unit_specs=validate_unit_rules(unit_rules)
 unit_index={s['test_name']:s for s in unit_specs}
 if not 1<=chunk_size<=500 or len(rows)>2000:raise ValueError('迁移配额超限')
 accepted=[];rejected=[];seen=set();chunks=[]
 for start in range(0,len(rows),chunk_size):
  chunk=rows[start:start+chunk_size]
  for offset,source in enumerate(chunk):
   try:
    target={}
    for rule in rules:
     if rule['source'] not in source:raise ValueError('missing_column:'+rule['source'])
     try:target[rule['target']]=convert(source[rule['source']],rule['type'],rule['required'])
     except ValueError as e:raise ValueError(rule['target']+':'+str(e))
    _unify(target,unit_index)
    key=key_digest(target)
    if key in seen:raise _fail('duplicate_natural_key','sample_code+test_name 重复')
    seen.add(key);accepted.append(target)
   except (ValueError,TypeError) as e:
    reason=e.args[0] if e.args else 'invalid_row'
    detail=e.args[1] if len(e.args)>1 else ''
    if ':' in reason:
     head,_,tail=reason.partition(':')
     if head in REJECT_REASONS:
      reason=head
      if not detail:detail=tail
     elif tail in REJECT_REASONS:
      reason=tail
      if not detail:detail=head
    if reason not in REJECT_REASONS:reason,detail='invalid_row',str(e)
    rejected.append({'row_number':start+offset+1,'reason':reason,'detail':detail,'source':source})
  item={'chunk':len(chunks)+1,'processed':start+len(chunk),'accepted':len(accepted),'rejected':len(rejected)}
  chunks.append(item);progress(item)
 if not rows:progress({'chunk':0,'processed':0,'accepted':0,'rejected':0})
 return {'accepted_rows':accepted,'rejected_rows':rejected,'row_hashes':[digest(r) for r in accepted],'checksum':digest(accepted),'chunks':chunks,'source_count':len(rows),'accepted_count':len(accepted),'rejected_count':len(rejected)}
def make_backup(result,run_id,batch_name,unit_rules):
 return {'version':BACKUP_VERSION,'run_id':run_id,'batch_name':batch_name,'unit_rules':unit_rules,'rows':result['accepted_rows'],'row_hashes':result['row_hashes'],'checksum':result['checksum'],'kind':'logical-json-snapshot'}
def validate_backup(backup,expected,run_id):
 if not isinstance(backup,dict) or backup.get('version')!=BACKUP_VERSION or backup.get('run_id')!=run_id or backup.get('kind')!='logical-json-snapshot':raise ValueError('备份版本或运行编号不一致')
 rows=backup.get('rows')
 if not isinstance(rows,list) or len(rows)>2000:raise ValueError('备份行数无效')
 if backup.get('checksum')!=digest(rows) or backup.get('checksum')!=expected:raise ValueError('备份checksum不匹配，拒绝恢复')
 if backup.get('row_hashes')!=[digest(r) for r in rows]:raise ValueError('逐行摘要不匹配')
 if any(not isinstance(r,dict) or set(r)!=TARGET_FIELDS for r in rows):raise ValueError('目标schema不一致')
 if any(not isinstance(r.get('original_value'),str) or not isinstance(r.get('original_unit'),str) for r in rows):raise ValueError('原值原单位证据缺失')
 if len({key_digest(r) for r in rows})!=len(rows):raise ValueError('备份自然键重复')
 return rows
