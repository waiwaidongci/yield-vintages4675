import time,traceback
from sqlalchemy import func
from src.config.database import Session
from src.models.ingest import RecomputeJob,JobQueue,Publication
from src.models.source import Policy
from src.services.calculation import calculate
from src.services.ingest import project_lots,period_watermark
from src.services.audit import log

MAX_ATTEMPTS=5

def run_recompute(job_id):
    """worker 调用：重算受影响期间的选定口径；过期结果不发布、不覆盖新版本。"""
    with Session() as db:
        job=db.get(RecomputeJob,job_id)
        if not job: return {'id':job_id,'skipped':'任务不存在'}
        if job.status=='completed': return {'id':job_id,'skipped':'已发布，幂等跳过'}
        if job.status not in ('queued','running','stale'):
            return {'id':job_id,'status':job.status,'skipped':'非可执行状态'}
        job.status='running';job.heartbeat=time.time()
        job.attempts+=1;job.updated=time.time()
        db.commit()
    try:
        with Session() as db:
            job=db.get(RecomputeJob,job_id)
            policy=db.get(Policy,job.policy_id)
            if not policy: raise ValueError('口径版本已不存在')
            lots=project_lots(db,job.period)
            if not lots:
                # 无生效批次（如全部撤销）：终态失败并保留原因，不做空版本、不空转重试
                job.status='failed';job.updated=time.time()
                job.reason=f"期间 {job.period} 当前没有生效批次（可能已全部撤销），不发布空版本"
                log(db,'worker','recompute.failed',f'job={job_id} {job.reason}')
                db.commit()
                return {'id':job_id,'status':'failed','reason':job.reason}
            # 发布前水位自检：计算期间收到新包且水位抬升时，本结果即过期
            current_wm=period_watermark(db,job.period)
            if current_wm>job.watermark:
                successor=db.query(RecomputeJob).filter(
                    RecomputeJob.period==job.period,RecomputeJob.policy_id==job.policy_id,
                    RecomputeJob.status=='queued').first()
                if successor:
                    # 下一代任务已在排队：本任务过期，旧计算晚到不发布、不覆盖新结果
                    job.status='expired';job.reason=(
                        f'计算期间数据已更新（水位 {job.watermark}→{current_wm}），'
                        f'旧计算晚到不发布，由任务#{successor.id} 承接')
                    for q in db.query(JobQueue).filter_by(kind='recompute',ref_id=job.id).all():
                        if q.status in ('queued','running'): q.status='done';q.updated=time.time()
                else:
                    # 无承接任务（如恢复场景）：回到排队等待包装层重新派发
                    job.status='stale';job.watermark=current_wm
                    job.reason=f'计算期间数据已更新（水位 {job.watermark}→{current_wm}），重新排队'
                job.updated=time.time()
                log(db,'worker','recompute.stale',f'job={job_id} wm {job.watermark}->{current_wm}')
                db.commit()
                return {'id':job_id,'status':job.status}
            sources=[dict(x['data']) for x in lots]
            result=calculate(sources,policy.data)
            snapshot={'period':job.period,'policy':policy.data,'policy_id':policy.id,
                      'lots':[{'lot_no':x['lot_no'],'revision':x['revision'],'data':x['data']} for x in lots],
                      'watermark':job.watermark}
            checksum=hashlib_sha(snapshot,result)
            last=db.query(func.max(Publication.version_no)).filter(
                Publication.period==job.period,Publication.policy_id==policy.id).scalar() or 0
            version_no=last+1
            # 同事务发布：底稿快照与加权结果作为同一版本、同一校验值落库
            pub=Publication(period=job.period,policy_id=policy.id,version_no=version_no,
                            status='published',snapshot=snapshot,result=result,checksum=checksum,
                            watermark=job.watermark,recompute_job_id=job.id,
                            reason=job.reason,created=time.time())
            db.add(pub);db.flush()
            job.status='completed';job.published_version=version_no;job.updated=time.time()
            log(db,'worker','publication.release',
                f'period={job.period} policy={policy.data["version"]} v{version_no} checksum={checksum[:12]}')
            db.commit()
            return {'id':job_id,'status':'completed','version_no':version_no,'checksum':checksum}
    except Exception as exc:
        traceback.print_exc()
        terminal=False
        with Session() as db:
            job=db.get(RecomputeJob,job_id)
            if job and job.status=='running':
                if job.attempts>=MAX_ATTEMPTS:
                    job.status='failed';job.reason=f'连续{job.attempts}次失败：{exc}'
                    log(db,'worker','recompute.failed',f'job={job_id} {exc}');terminal=True
                else:
                    # 回到排队，队列行由 worker 包装层负责复位
                    job.status='queued';job.reason=f'失败待重试（第{job.attempts}次）：{exc}'
                    log(db,'worker','recompute.retry',f'job={job_id} attempt={job.attempts} {exc}')
                job.updated=time.time();db.commit()
        return {'id':job_id,'status':'failed' if terminal else 'queued','reason':str(exc)}

def hashlib_sha(snapshot,result):
    import hashlib,json
    return hashlib.sha256(json.dumps(
        {'snapshot':snapshot,'result':result},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
