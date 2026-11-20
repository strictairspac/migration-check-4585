#!/usr/bin/env python3
"""端到端验收：登录→映射换算规则→迁移→逐行拒绝→备份恢复→规则冻结→并发/重试。
运行：backend/ 下 python3 -I ../test-artifacts/gb-4109/e2e_check.py
"""
import json,sys,time,urllib.request,urllib.error
BASE='http://localhost:19248'
def call(method,path,token=None,body=None):
 data=json.dumps(body).encode() if body is not None else None
 req=urllib.request.Request(BASE+path,data=data,method=method,headers={'Content-Type':'application/json'})
 if token:req.add_header('Authorization','Bearer '+token)
 try:
  with urllib.request.urlopen(req) as r:return r.status,json.loads(r.read() or b'null')
 except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
def wait_run(token,rid,timeout=30):
 deadline=time.time()+timeout
 while time.time()<deadline:
  _,r=call('GET',f'/runs/{rid}',token)
  if r['status'] not in ('queued','running'):return r
  time.sleep(0.3)
 raise AssertionError('run timeout')
def main():
 failures=[]
 def check(name,cond,extra=''):
  print(('PASS' if cond else 'FAIL'),name,extra)
  if not cond:failures.append(name)
 # 1. 登录
 _,login=call('POST','/auth/login',body={'email':'operator@migration.local','password':'Migrate2026!'})
 op=login['token']
 _,alogin=call('POST','/auth/login',body={'email':'admin@migration.local','password':'Migrate2026!'})
 admin=alogin['token']
 # 2. 读取种子映射与批次
 _,mappings=call('GET','/mappings',op)
 _,batches=call('GET','/batches',op)
 bad_batch=next(b for b in batches if b['name']=='旧字段异常样本')
 good_batch=next(b for b in batches if b['name']=='见山日班检验结果')
 m=next(x for x in mappings if x['name']=='异常隔离复核映射')
 check('映射含换算规则',len(m['unit_rules'])==2,str([u['test_name'] for u in m['unit_rules']]))
 # 3. 非法换算规则必须被拒绝（精度超界 / 目标单位系数非1 / 缺系数）
 bad_rules=json.loads(json.dumps(m['unit_rules']))
 bad_rules[0]['precision']=99
 st,_=call('POST','/mappings',op,{'name':'非法精度映射','batch_id':bad_batch['id'],'rules':m['rules'],'unit_rules':bad_rules,'chunk_size':4})
 check('非法精度拒绝',st==422,str(st))
 bad_rules=json.loads(json.dumps(m['unit_rules']));bad_rules[0]['factors']['MPa']='2'
 st,_=call('POST','/mappings',op,{'name':'非法系数映射','batch_id':bad_batch['id'],'rules':m['rules'],'unit_rules':bad_rules,'chunk_size':4})
 check('目标单位系数非1拒绝',st==422,str(st))
 bad_rules=json.loads(json.dumps(m['unit_rules']));del bad_rules[1]['factors']['kJ']
 st,_=call('POST','/mappings',op,{'name':'缺系数映射','batch_id':bad_batch['id'],'rules':m['rules'],'unit_rules':bad_rules,'chunk_size':4})
 check('缺换算系数拒绝',st==422,str(st))
 # 4. 执行异常批次迁移
 _,run=call('POST','/runs',op,{'name':'e2e-异常批次-1','mapping_id':m['id']})
 r=wait_run(op,run['id'])
 check('异常批次完成',r['status']=='completed',r.get('error',''))
 res=r['result']
 reasons={x['reason'] for x in res['rejected_rows']}
 for code in ('unit_rule_missing','invalid_decimal','value_out_of_range','precision_loss','source_unit_not_allowed','missing_column','duplicate_natural_key'):
  check('拒绝原因覆盖 '+code,code in reasons,str(sorted(reasons)))
 check('其他行仍可提交',res['accepted_count']>=2 and res['accepted_count']+res['rejected_count']==res['source_count'])
 # 5. 统一值/原值证据
 acc=res['accepted_rows'][0]
 check('目标行含原值原单位',all(k in acc for k in ('original_value','original_unit','result_value','unit')))
 kpa=[x for x in res['accepted_rows'] if x['original_unit']=='kPa']
 check('kPa→MPa 换算',all(x['unit']=='MPa' and abs(float(x['result_value'])-float(x['original_value'])*0.001)<1e-9 for x in kpa),json.dumps(kpa[:2],ensure_ascii=False))
 kj=[x for x in res['accepted_rows'] if x['original_unit']=='kJ']
 check('kJ→J 换算与精度',all(x['unit']=='J' and x['result_value']=='80.00' for x in kj),json.dumps(kj,ensure_ascii=False))
 # 6. 真实目标表与运行摘要一致
 _,targets=call('GET',f"/runs/{run['id']}/targets",op)
 check('目标表行数=接受数',targets['count']==res['accepted_count'])
 check('目标表checksum一致',targets['checksum']==res['checksum'])
 # 7. review 筛选：原单位/目标单位/拒绝原因
 _,rv=call('GET',f"/runs/{run['id']}/review?source_unit=kPa",op)
 check('按原单位筛选',rv['accepted_total']==len(kpa) and all(x['original_unit']=='kPa' for x in rv['accepted_rows']))
 _,rv=call('GET',f"/runs/{run['id']}/review?target_unit=MPa",op)
 check('按目标单位筛选',all(x['unit']=='MPa' for x in rv['accepted_rows']) and rv['accepted_total']>0)
 _,rv=call('GET',f"/runs/{run['id']}/review?reason=precision_loss",op)
 check('按拒绝原因筛选',rv['rejected_total']>=1 and all(x['reason']=='precision_loss' for x in rv['rejected_rows']))
 check('筛选项字典完整',{o['code'] for o in rv['reasons']}<={x['reason'] for x in res['rejected_rows']} and all('label' in o for o in rv['reasons']))
 # 8. 备份下载与恢复（admin）
 st,backup=call('GET',f"/runs/{run['id']}/backup",admin)
 check('备份v2含换算规则',st==200 and backup['version']==2 and len(backup['unit_rules'])==2)
 _,proof=call('POST',f"/runs/{run['id']}/restore",admin,{'backup':backup})
 check('恢复校验一致',proof['verified'] and proof['restored_count']==res['accepted_count'],json.dumps(proof))
 _,targets2=call('GET',f"/runs/{run['id']}/targets",op)
 check('恢复后目标值与来源同一',targets2['checksum']==res['checksum'] and [x['original_value'] for x in targets2['rows']]==[x['original_value'] for x in res['accepted_rows']])
 # 9. 篡改/错运行备份拒绝
 tampered=json.loads(json.dumps(backup));tampered['rows'][0]['result_value']='1.000'
 st,_=call('POST',f"/runs/{run['id']}/restore",admin,{'backup':tampered})
 check('篡改备份拒绝',st==422)
 # 10. 规则改动不改变已完成结果（冻结性）
 updated=json.loads(json.dumps(m))
 updated['unit_rules'][0]['factors']['kPa']='0.01'  # 改系数
 st,_=call('PUT',f"/mappings/{m['id']}",op,updated)
 check('规则可更新',st==200,str(st))
 _,run2=call('POST','/runs',op,{'name':'e2e-规则改动后新运行','mapping_id':m['id']})
 r2=wait_run(op,run2['id'])
 check('新运行按新规则换算',r2['status']=='completed')
 new_kpa=[x for x in r2['result']['accepted_rows'] if x['original_unit']=='kPa']
 check('新运行采用新系数',all(abs(float(x['result_value'])-float(x['original_value'])*0.01)<1e-9 for x in new_kpa))
 _,r1_again=call('GET',f"/runs/{run['id']}",op)
 old_kpa=[x for x in r1_again['result']['accepted_rows'] if x['original_unit']=='kPa']
 check('历史运行结果不随规则改动',all(abs(float(x['result_value'])-float(x['original_value'])*0.001)<1e-9 for x in old_kpa))
 check('历史备份checksum不变',r1_again['result']['checksum']==res['checksum'])
 # 11. 正常批次全量迁移 + 重试不重复写入
 gm=next(x for x in mappings if x['name']=='检验结果标准映射')
 _,run3=call('POST','/runs',op,{'name':'e2e-正常批次','mapping_id':gm['id']})
 r3=wait_run(op,run3['id'])
 check('正常批次全接受',r3['status']=='completed' and r3['result']['rejected_count']==0 and r3['result']['accepted_count']==len(good_batch['rows']))
 _,t3=call('GET',f"/runs/{run3['id']}/targets",op)
 check('重试提交不重复写入（再次排队被去重）',t3['count']==r3['result']['accepted_count'])
 # 直接再推一次同一run到队列模拟重复消息
 import redis as rlib
 rq=rlib.Redis.from_url('redis://localhost:16379/0');rq.rpush('migration-runs',str(run3['id']))
 time.sleep(2)
 _,t3b=call('GET',f"/runs/{run3['id']}/targets",op)
 _,r3b=call('GET',f"/runs/{run3['id']}",op)
 check('重复队列消息不产生重复目标行',t3b['count']==r3['result']['accepted_count'] and r3b['status']=='completed')
 # 12. 空批次
 em=next(x for x in mappings if x['name']=='空批次映射')
 _,run4=call('POST','/runs',op,{'name':'e2e-空批次','mapping_id':em['id']})
 r4=wait_run(op,run4['id'])
 check('空批次可完成并备份',r4['status']=='completed' and r4['result']['accepted_count']==0)
 st,bk4=call('GET',f"/runs/{run4['id']}/backup",admin)
 _,proof4=call('POST',f"/runs/{run4['id']}/restore",admin,{'backup':bk4})
 check('空备份可恢复核验',proof4['verified'] and proof4['restored_count']==0)
 print('\n结果:', '全部通过' if not failures else f'{len(failures)} 项失败: {failures}')
 sys.exit(1 if failures else 0)
if __name__=='__main__':main()
