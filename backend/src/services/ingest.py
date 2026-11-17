import time
from fastapi import HTTPException
from sqlalchemy import func
from src.config.database import Session
from src.models.ingest import IngestPacket,LotEvent,RecomputeJob,JobQueue
from src.models.source import Policy,Period
from src.services.validation import validate_packet
from src.services.audit import log

def enqueue(db,kind,ref_id):
    """同一引用只允许一个未结束的作业，中断恢复时不重复入队。"""
    busy=db.query(JobQueue).filter(JobQueue.kind==kind,JobQueue.ref_id==ref_id,
                                   JobQueue.status.in_(('queued','running'))).first()
    if busy: return busy
    now=time.time()
    job=JobQueue(kind=kind,ref_id=ref_id,status='queued',created=now,updated=now)
    db.add(job);db.flush();return job

def accept_packet(db,user,payload):
    """接收数据包：结构校验通过即登记并排队生效；重复提交幂等返回原包。"""
    parsed=validate_packet(payload)
    existing=db.query(IngestPacket).filter_by(packet_id=parsed['packet_id']).first()
    if existing:
        return existing,False
    now=time.time()
    packet=IngestPacket(packet_id=parsed['packet_id'],payload=parsed,status='received',
                        revision_max=max(x['revision'] for x in parsed['items']),
                        lot_count=len(parsed['items']),created=now,actor=user.email)
    db.add(packet);db.flush()
    enqueue(db,'packet',packet.id)
    log(db,user.email,'packet.accept',packet.packet_id)
    db.commit();db.refresh(packet)
    return packet,True

def _current_events(db,lot_nos):
    rows=db.query(LotEvent).filter(LotEvent.lot_no.in_(lot_nos)).order_by(LotEvent.id).all()
    latest={}
    for e in rows: latest[e.lot_no]=e
    return latest

def _active_periods(db,lot_nos):
    """受影响期间 = 事件涉及批号的当前生效数据期间（含撤销前旧期间与新期间）。"""
    if not lot_nos: return set()
    latest=_current_events(db,lot_nos);periods=set()
    for e in latest.values():
        if e.op!='withdraw' and e.data: periods.add(e.data['period'])
    return periods

def apply_packet(packet_id):
    """worker 调用：整包事务内冲突校验，全部通过才追加事件并安排重算。"""
    with Session() as db:
        packet=db.query(IngestPacket).filter_by(packet_id=packet_id).first()
        if not packet: return {'packet_id':packet_id,'skipped':'数据包不存在'}
        if packet.status in ('applied',): return {'packet_id':packet_id,'skipped':'已生效，幂等跳过'}
        if packet.status=='rejected': return {'packet_id':packet_id,'skipped':'此前已整包拒绝'}
        now=time.time()
        try:
            items=sorted(packet.payload['items'],key=lambda x:(x['lot_no'],x['revision']))
            lot_nos=sorted({x['lot_no'] for x in items})
            latest=_current_events(db,lot_nos)
            # 1) 整包冲突预检：任一记录冲突则整包拒绝，不写入任何事件
            for item in items:
                lot,rev,op=item['lot_no'],item['revision'],item['op']
                cur=latest.get(lot)
                if cur and rev<cur.revision:
                    raise ValueError(f'{lot} 修订号 {rev} 迟到：已存在更新修订 r{cur.revision}，迟到记录不覆盖')
                if cur and rev==cur.revision:
                    raise ValueError(f'{lot} 修订号 {rev} 与已生效修订内容冲突，整包拒绝')
                if op=='report' and cur and cur.op!='withdraw':
                    raise ValueError(f'{lot} r{rev} 批号已有生效记录，补报须使用更正(correct)')
                if op in ('correct','withdraw') and (not cur or cur.op=='withdraw'):
                    raise ValueError(f'{lot} r{rev} 批号无生效记录，无法{ "更正" if op=="correct" else "撤销" }')
            affected=set(_active_periods(db,lot_nos))
            # 2) 全部通过：追加只增事件流
            for item in items:
                db.add(LotEvent(lot_no=item['lot_no'],revision=item['revision'],op=item['op'],
                                data=item.get('data'),packet_id=packet.packet_id,created=now))
                if item['data']: affected.add(item['data']['period'])
            db.flush()
            watermark=db.query(func.max(LotEvent.id)).scalar() or 0
            packet.status='applied';packet.applied_at=now;packet.reason=''
            # 3) 仅对受影响期间的既有口径安排重算；同期间同口径合并为一个待执行任务
            for period in sorted(affected):
                if not db.query(Period).filter_by(name=period).first():
                    db.add(Period(name=period,description='批次数据包自动登记期间'))
                for policy in db.query(Policy).order_by(Policy.id).all():
                    _schedule_recompute(db,period,policy.id,watermark,now,
                                        f'数据包 {packet.packet_id} 生效触发')
            log(db,'worker','packet.apply',f'{packet.packet_id} events={len(items)} periods={sorted(affected)}')
            db.commit()
            return {'packet_id':packet_id,'status':'applied','events':len(items),'periods':sorted(affected)}
        except Exception as exc:
            db.rollback()
            with Session() as fail_db:
                p=fail_db.query(IngestPacket).filter_by(packet_id=packet_id).first()
                if p and p.status not in ('applied','rejected'):
                    p.status='rejected';p.reason=str(exc)
                    log(fail_db,'worker','packet.reject',f'{packet_id}: {exc}')
                    fail_db.commit()
            return {'packet_id':packet_id,'status':'rejected','reason':str(exc)}

def _schedule_recompute(db,period,policy_id,watermark,now,reason):
    queued=db.query(RecomputeJob).filter(
        RecomputeJob.period==period,RecomputeJob.policy_id==policy_id,
        RecomputeJob.status=='queued').first()
    if queued:
        # 计算期间仍可接收新包：排队中任务抬升水位并合并，不重复建任务
        queued.watermark=max(queued.watermark,watermark)
        queued.updated=now;queued.reason=reason
        return queued
    running=db.query(RecomputeJob).filter(
        RecomputeJob.period==period,RecomputeJob.policy_id==policy_id,
        RecomputeJob.status=='running').first()
    if running:
        # 计算进行中：在算任务水位冻结，另立下一代任务；旧任务发布前自检过期
        job=RecomputeJob(period=period,policy_id=policy_id,status='queued',watermark=watermark,
                         reason=reason,created=now,updated=now)
        db.add(job);db.flush();enqueue(db,'recompute',job.id);return job
    job=RecomputeJob(period=period,policy_id=policy_id,status='queued',watermark=watermark,
                     reason=reason,created=now,updated=now)
    db.add(job);db.flush();enqueue(db,'recompute',job.id);return job

def manual_recompute(db,user,period,policy_id):
    policy=db.get(Policy,policy_id)
    if not policy: raise HTTPException(404,'口径版本不存在')
    if period!='全部' and not _period_has_lots(db,period):
        raise HTTPException(422,'所选期间当前没有生效批次数据')
    now=time.time();watermark=db.query(func.max(LotEvent.id)).scalar() or 0
    periods=[period] if period!='全部' else sorted(_all_lot_periods(db))
    if not periods: raise HTTPException(422,'尚无批次数据可重算')
    jobs=[]
    for p in periods:
        job=_schedule_recompute(db,p,policy_id,watermark,now,f'{user.email} 手动发起重算')
        jobs.append(job)
    log(db,user.email,'recompute.request',f'policy={policy_id} periods={periods}')
    db.commit()
    return jobs

def project_lots(db,period=None):
    """事件流投影：每批号取最大修订号；撤销的批号不参与计算。"""
    rows=db.query(LotEvent).order_by(LotEvent.id).all()
    latest={}
    for e in rows: latest[e.lot_no]=e
    out=[]
    for lot_no,e in sorted(latest.items()):
        if e.op=='withdraw' or not e.data: continue
        if period and e.data['period']!=period: continue
        out.append({'lot_no':lot_no,'revision':e.revision,'data':e.data})
    return out

def period_watermark(db,period):
    """该期间相关批号在事件流中的最大事件 id。

    相关批号 = 当前数据在该期间的批号 ∪ 历史上曾在该期间出现的批号，
    因此批号迁出、撤销产生的新事件也会抬升水位，触发在算任务过期自检。
    """
    rows=db.query(LotEvent).order_by(LotEvent.id).all()
    latest={};ever=set();wm=0
    for e in rows:
        latest[e.lot_no]=e
        if e.data and e.data.get('period')==period:
            ever.add(e.lot_no);wm=max(wm,e.id)
    for lot_no,e in latest.items():
        if lot_no in ever: wm=max(wm,e.id)
    return wm

def _period_has_lots(db,period): return bool(project_lots(db,period))
def _all_lot_periods(db): return {x['data']['period'] for x in project_lots(db)}
