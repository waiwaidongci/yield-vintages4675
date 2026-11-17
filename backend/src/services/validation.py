import math
from src.config.settings import CONFIG
from src.constants.enums import LOT_OPS
def number(value,name,minimum=0,integer=False):
 if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<minimum or (integer and int(value)!=value): raise ValueError(name+'数值不合法')
 return value
def validate_source(d):
 if not isinstance(d,dict) or set(d)!=set(CONFIG['fields']): raise ValueError('底稿字段必须与业务字段一致')
 for key in ('period','department'):
  if not isinstance(d[key],str) or not 1<=len(d[key])<=100: raise ValueError(key+'不能为空或过长')
 for k in ('input','first_pass','reworked_good','scrap'):number(d[k],k,integer=True)
 if d['input']<=0 or d['first_pass']+d['reworked_good']+d['scrap']!=d['input']:raise ValueError('投入必须大于0且一次通过+返工合格+报废应等于投入')
 if not isinstance(d['shift'],str) or not d['shift']:raise ValueError('班次不能为空')
def validate_policy(d):
 if not isinstance(d,dict) or not isinstance(d.get('version'),str) or not 2<=len(d['version'])<=120: raise ValueError('口径版本名不合法')
 if d.get('numerator') not in ('first_pass','total_good') or d.get('denominator') not in ('input','non_scrap'):raise ValueError('分子分母口径无效')
 if not isinstance(d.get('description'),str):raise ValueError('必须填写口径说明')
def validate_packet(payload):
 """数据包结构校验；业务冲突（修订号/操作顺序）在生效事务内判定。"""
 if not isinstance(payload,dict): raise ValueError('数据包必须为对象')
 pid=payload.get('packet_id')
 if not isinstance(pid,str) or not 2<=len(pid)<=120: raise ValueError('数据包标识 packet_id 不合法')
 items=payload.get('items')
 if not isinstance(items,list) or not items: raise ValueError('数据包 items 至少包含一条批次记录')
 seen=set();parsed=[]
 for i,item in enumerate(items):
  if not isinstance(item,dict): raise ValueError(f'第{i+1}条记录格式不合法')
  lot=item.get('lot_no')
  if not isinstance(lot,str) or not 1<=len(lot)<=120: raise ValueError(f'第{i+1}条批号不合法')
  rev=item.get('revision')
  if isinstance(rev,bool) or not isinstance(rev,int) or rev<1: raise ValueError(f'{lot} 修订号必须为不小于1的整数')
  op=item.get('op')
  if op not in LOT_OPS: raise ValueError(f'{lot} r{rev} 动作必须为 report/correct/withdraw')
  data=item.get('data')
  if op in ('report','correct'):
   validate_source(data)
  elif data is not None:
   raise ValueError(f'{lot} r{rev} 撤销动作不得携带业务数据')
  key=(lot,rev)
  if key in seen: raise ValueError(f'数据包内 {lot} 修订号 {rev} 重复')
  seen.add(key);parsed.append({'lot_no':lot,'revision':rev,'op':op,'data':data})
 return {'packet_id':pid,'items':parsed}
