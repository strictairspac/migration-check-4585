#!/usr/bin/env python3
"""并发与回滚专项：恢复与读取并发、取消不留部分数据、逐行拒绝不影响其他行提交。"""
import json,time,threading,urllib.request,urllib.error,sys
BASE='http://localhost:19248'
def call(method,path,token=None,body=None):
 data=json.dumps(body).encode() if body is not None else None
 req=urllib.request.Request(BASE+path,data=data,method=method,headers={'Content-Type':'application/json'})
 if token:req.add_header('Authorization','Bearer '+token)
 try:
  with urllib.request.urlopen(req,timeout=20) as r:return r.status,json.loads(r.read() or b'null')
 except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
def wait_run(token,rid,timeout=30):
 end=time.time()+timeout
 while time.time()<end:
  _,r=call('GET',f'/runs/{rid}',token)
  if r['status'] not in ('queued','running'):return r
  time.sleep(0.2)
 raise AssertionError('timeout')
fails=[]
def check(n,c,extra=''):
 print(('PASS' if c else 'FAIL'),n,extra)
 if not c:fails.append(n)
_,op=call('POST','/auth/login',body={'email':'operator@migration.local','password':'Migrate2026!'})
op=op['token']
_,ad=call('POST','/auth/login',body={'email':'admin@migration.local','password':'Migrate2026!'})
ad=ad['token']
_,mappings=call('GET','/mappings',op);_,batches=call('GET','/batches',op)
gm=next(x for x in mappings if x['name']=='检验结果标准映射')
_,run=call('POST','/runs',op,{'name':'并发-正常批次','mapping_id':gm['id']})
r=wait_run(op,run['id'])
check('迁移完成',r['status']=='completed',r.get('error',''))
_,backup=call('GET',f"/runs/{run['id']}/backup",ad)
errors=[];results=[]
def restore_loop(n):
 try:
  for _ in range(n):
   st,proof=call('POST',f"/runs/{run['id']}/restore",ad,{'backup':backup})
   if st!=200 or not proof.get('verified'):errors.append((st,proof))
   results.append(proof.get('restored_count'))
 except Exception as e:errors.append(str(e))
def read_loop(n):
 try:
  for _ in range(n):
   st,t=call('GET',f"/runs/{run['id']}/targets",op)
   if st!=200:errors.append(('read',st))
   results.append(('count',t['count'],t['checksum']==r['result']['checksum']))
 except Exception as e:errors.append(str(e))
t1=threading.Thread(target=restore_loop,args=(6,));t2=threading.Thread(target=read_loop,args=(8,))
t1.start();t2.start();t1.join();t2.join()
check('并发恢复/读取无错误',not errors,str(errors[:3]))
check('每次恢复计数与checksum恒定',all(x==r['result']['accepted_count'] for x in results if isinstance(x,int)))
check('并发读取始终一致',all(x[1]==r['result']['accepted_count'] and x[2] for x in results if isinstance(x,tuple)))
# 取消：排队即取消，目标表零残留
_,run2=call('POST','/runs',op,{'name':'并发-取消运行','mapping_id':gm['id']})
st,_=call('POST',f"/runs/{run2['id']}/cancel",op)
r2=wait_run(op,run2['id'])
_,t2rows=call('GET',f"/runs/{run2['id']}/targets",op)
check('取消运行无目标残留',r2['status'] in ('cancelled',) and t2rows['count']==0,r2['status'])
# 逐行原子性：异常批次接受+拒绝=源行数，且接受行全部具备统一值与原值
bm=next(x for x in mappings if x['name']=='异常隔离复核映射')
_,run3=call('POST','/runs',op,{'name':'并发-异常原子性','mapping_id':bm['id']})
r3=wait_run(op,run3['id'])
res=r3['result']
check('逐行隔离总数守恒',res['accepted_count']+res['rejected_count']==res['source_count'])
check('接受行均含统一值与原值证据',all(set(('original_value','original_unit','result_value','unit'))<=set(x) for x in res['accepted_rows']))
# 非有限值（Infinity）经批次接口入站后逐行拒绝
bad_batch=next(b for b in batches if b['name']=='旧字段异常样本')
rows=bad_batch['rows']+[{'委托号':'JS-INF','检测项':'拉伸强度','结果':'Infinity','单位':'MPa','时间':'2026-11-17T09:00:00+08:00'}]
st,nb=call('POST','/batches',op,{'name':'并发-无穷值批次','source_file':'inf.json','rows':rows})
check('无穷字符串可入源批次',st==200,str(st))
_,m4=call('POST','/mappings',op,{'name':'并发-无穷值映射','batch_id':nb['id'],'rules':bm['rules'],'unit_rules':bm['unit_rules'],'chunk_size':4})
_,run4=call('POST','/runs',op,{'name':'并发-无穷值运行','mapping_id':m4['id']})
r4=wait_run(op,run4['id'])
inf_rej=[x for x in r4['result']['rejected_rows'] if x['reason']=='invalid_decimal']
check('Infinity 按非有限值逐行拒绝',bool(inf_rej),json.dumps(inf_rej,ensure_ascii=False))
print('\n并发专项:','全部通过' if not fails else f'失败 {fails}')
sys.exit(1 if fails else 0)
