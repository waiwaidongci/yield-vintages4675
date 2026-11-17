import time,traceback
from pathlib import Path
import redis
from src.config.database import Base,engine,Session
from src.config.settings import REDIS_URL
from src.models import identity,source,run,ingest
from src.models.run import Run
from src.models.ingest import JobQueue,IngestPacket
from src.services.calculation import calculate
from src.services.delivery import tick
from src.services.ingest import apply_packet
from src.services.recompute import run_recompute

STALE_RUN_SECONDS=60
MAX_ATTEMPTS=5

def recover_stalled(db,now):
    """中断恢复：心跳超时的 running 作业回到 queued，领取时状态机保证不重复计入。"""
    stalled=db.query(JobQueue).filter(JobQueue.status=='running',
                                      JobQueue.heartbeat<=now-STALE_RUN_SECONDS).all()
    for j in stalled:
        j.status='queued';j.updated=now
    # 回收实体层面的僵尸重算任务（进程在落盘 running 后、队列复位前崩溃）
    from src.models.ingest import RecomputeJob
    zombies=db.query(RecomputeJob).filter(
        RecomputeJob.status=='running',
        RecomputeJob.heartbeat<=now-STALE_RUN_SECONDS).all()
    for rj in zombies:
        rj.status='queued';rj.updated=now
        q=db.query(JobQueue).filter_by(kind='recompute',ref_id=rj.id).filter(
            JobQueue.status.in_(('queued','running'))).first()
        if not q:
            db.add(JobQueue(kind='recompute',ref_id=rj.id,status='queued',created=now,updated=now))
        elif q.status=='running':
            q.status='queued'
    if stalled or zombies: db.commit()

def _ref_alive(db,kind,ref_id):
    """引用实体是否仍需该队列行驱动；已终结实体的遗留队列行应立即回收。"""
    if kind=='packet':
        packet=db.get(IngestPacket,ref_id)
        return packet is not None and packet.status not in ('applied','rejected')
    from src.models.ingest import RecomputeJob
    rj=db.get(RecomputeJob,ref_id)
    return rj is not None and rj.status not in ('completed','expired','failed')

def claim_next(db,now):
    # 跳过并终结引用已结束的僵尸队列行，避免它们阻塞后续作业领取
    while True:
        job=db.query(JobQueue).filter(JobQueue.status=='queued').order_by(JobQueue.id).first()
        if not job: return None
        if _ref_alive(db,job.kind,job.ref_id): break
        job.status='done';job.updated=now
    job.status='running';job.attempts+=1;job.heartbeat=now;job.updated=now
    db.commit();return job

def dispatch(job):
    if job.kind=='packet':
        with Session() as db:
            packet=db.get(IngestPacket,job.ref_id)
            packet_id=packet.packet_id if packet else None
        return apply_packet(packet_id) if packet_id else {'skipped':'数据包不存在'}
    if job.kind=='recompute':
        return run_recompute(job.ref_id)
    return {'skipped':f'未知作业类型 {job.kind}'}

def process_legacy_redis(r):
    """兼容原有 Redis 报告队列与定时交付。"""
    item=r.lpop('report-jobs')
    if item:
        with Session() as db:
            report=db.get(Run,int(item))
            if report and report.status=='queued':
                report.status='running';db.commit()
                try:
                    report.result=calculate(report.snapshot['sources'],report.snapshot['policy'])
                    report.status='completed'
                except Exception as exc:
                    report.status='failed';report.error=str(exc);traceback.print_exc()
                db.commit()
    with Session() as db: tick(db)

def process_once(r):
    now=time.time()
    with Session() as db:
        recover_stalled(db,now)
        job=claim_next(db,now)
    if not job:
        process_legacy_redis(r);return
    try:
        dispatch(job)
    except Exception:
        traceback.print_exc()
    # 依据引用实体的最终状态决定队列行去留，保证重试不丢、终态不重复
    with Session() as db:
        q=db.get(JobQueue,job.id)
        if not q or q.status!='running': return
        terminal=False;requeue=False
        if job.kind=='packet':
            packet=db.get(IngestPacket,job.ref_id)
            terminal=packet is None or packet.status in ('applied','rejected')
        else:
            from src.models.ingest import RecomputeJob
            rj=db.get(RecomputeJob,job.ref_id)
            terminal=rj is None or rj.status in ('completed','expired','failed')
            requeue=rj is not None and rj.status in ('queued','stale')
        if terminal: q.status='done'
        elif requeue: q.status='queued'
        else:
            if q.attempts>=MAX_ATTEMPTS: q.status='failed';q.last_error='连续失败，见服务日志'
            else: q.status='queued'
        q.updated=time.time();db.commit()

def main():
    Base.metadata.create_all(engine)
    r=redis.Redis.from_url(REDIS_URL)
    while True:
        Path('/tmp/worker-heartbeat').write_text(str(time.time()))
        try: process_once(r)
        except Exception: traceback.print_exc()
        time.sleep(1)

if __name__=='__main__':
    main()
