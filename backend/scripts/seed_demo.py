from src.config.database import Base,engine,Session
from src.models.identity import User,Audit
from src.models.batch import Batch
from src.models.mapping import Mapping
from src.models.run import Run,TargetRow
from src.utils.security import hash_password
RULES=[{'source':a,'target':b,'type':c,'required':True} for a,b,c in [('委托号','sample_code','text'),('检测项','test_name','text'),('结果','result_value','decimal'),('单位','unit','text'),('时间','measured_at','datetime')]]
# 受理时冻结的单位换算规则：目标值 = 原值 * factor；区间与精度均按目标单位声明
UNIT_RULES=[
 {'test_name':'拉伸强度','target_unit':'MPa','precision':3,'allowed_units':['MPa','kPa'],'factors':{'MPa':'1','kPa':'0.001'},'min_value':'0','max_value':'2000'},
 {'test_name':'冲击吸收能量','target_unit':'J','precision':2,'allowed_units':['J','kJ'],'factors':{'J':'1','kJ':'1000'},'min_value':'0','max_value':'1000'},
]
TS='2026-11-17T09:00:00+08:00'
def row(code,name,value,unit):return {'委托号':code,'检测项':name,'结果':value,'单位':unit,'时间':TS}
def seed():
 Base.metadata.create_all(engine)
 with Session() as s:
  for role in ('admin','operator','viewer'):
   if not s.query(User).filter_by(email=role+'@migration.local').first():s.add(User(email=role+'@migration.local',role=role,password=hash_password('Migrate2026!')))
  good=[row(f'JS-20261117-{i:03d}','拉伸强度',str(420+i/10),'MPa') for i in range(1,9)]
  good+=[row(f'JS-20261117-{i:03d}','拉伸强度',str(421000+i*100),'kPa') for i in range(9,12)]
  good+=[row(f'JS-20261117-{i:03d}','冲击吸收能量','78.5','J') for i in range(12,14)]
  good+=[row(f'JS-20261117-{i:03d}','冲击吸收能量','0.08','kJ') for i in range(14,15)]
  # 异常样本：覆盖单位换算四类逐行拒绝 + 非有限值/缺列/重复键
  bad=[
   row('JS-BAD-01','拉伸强度','NaN','MPa'),                      # 非有限值 invalid_decimal
   row('JS-BAD-02','拉伸强度','9999','MPa'),                     # 越界 value_out_of_range
   row('JS-BAD-03','拉伸强度','420.1235','MPa'),                 # 换算后超精度 precision_loss
   row('JS-BAD-04','拉伸强度','420.5','psi'),                     # 原单位不允许 source_unit_not_allowed
   row('JS-BAD-05','未登记检测项','10','MPa'),                    # 缺少换算规则 unit_rule_missing
   row('JS-BAD-06','冲击吸收能量','1.5','kJ'),                    # 1500J 越界
   {'委托号':'JS-BAD-07','检测项':'拉伸强度','单位':'MPa','时间':TS},  # 缺源字段 missing_column
   dict(good[0]),                                                # 重复自然键 duplicate_natural_key
  ]
  seeds=[('见山日班检验结果',good,'lab-results-20261117.json','14条多单位记录，MPa/kPa/J/kJ统一换算'),('旧字段异常样本',good[:2]+bad,'legacy-edge-20261117.json','缺规则/非有限值/越界/超精度/单位不允许逐行隔离'),('空批次验收',[],'empty-results.json','空输入可完成备份与恢复')]
  for name,rows,file,desc in seeds:
   if not s.query(Batch).filter_by(name=name).first():s.add(Batch(name=name,rows=rows,source_file=file,description=desc))
  s.flush()
  for i,(name,_,_,_) in enumerate(seeds):
   mname=['检验结果标准映射','异常隔离复核映射','空批次映射'][i]
   if not s.query(Mapping).filter_by(name=mname).first():s.add(Mapping(name=mname,batch_id=s.query(Batch).filter_by(name=name).one().id,rules=RULES,unit_rules=UNIT_RULES,chunk_size=4,note='受理时冻结单位换算：目标值=原值×系数，结果页保留原值原单位'))
  s.commit();counts={m.__tablename__:s.query(m).count() for m in (User,Batch,Mapping,Run,TargetRow)};print(counts);return counts
if __name__=='__main__':seed()
