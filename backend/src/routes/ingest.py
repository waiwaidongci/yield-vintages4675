from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import Response
from src.config.database import database
from src.controllers.auth import current,editor
from src.models.ingest import IngestPacket,LotEvent,RecomputeJob,JobQueue,Publication
from src.schemas.requests import PacketInput,RecomputeInput
from src.services.ingest import accept_packet,manual_recompute,project_lots,enqueue
from src.services.export import csv_text
from src.services.audit import log
from src.utils.serialize import row
router=APIRouter()

# ---------- 数据包接收 ----------
@router.get('/packets')
def packets(db=Depends(database),u=Depends(current)):
    return [row(x) for x in db.query(IngestPacket).order_by(IngestPacket.id.desc()).limit(200).all()]

@router.post('/packets')
def submit_packet(b:PacketInput,db=Depends(database),u=Depends(editor)):
    packet,created=accept_packet(db,u,b.model_dump())
    return {**row(packet),'accepted':created}

@router.get('/packets/{packet_id}')
def packet_detail(packet_id:str,db=Depends(database),u=Depends(current)):
    obj=db.query(IngestPacket).filter_by(packet_id=packet_id).first()
    if not obj: raise HTTPException(404,'数据包不存在')
    return row(obj)

@router.post('/packets/{packet_id}/retry')
def retry_packet(packet_id:str,db=Depends(database),u=Depends(editor)):
    """拒绝/失败后的人工重试：重新排队，已生效包幂等不重复计入。"""
    obj=db.query(IngestPacket).filter_by(packet_id=packet_id).first()
    if not obj: raise HTTPException(404,'数据包不存在')
    if obj.status=='applied': return {**row(obj),'skipped':'已生效，无需重试'}
    obj.status='received';obj.reason=''
    q=enqueue(db,'packet',obj.id)
    log(db,u.email,'packet.retry',packet_id);db.commit()
    return {**row(obj),'queue_id':q.id}

# ---------- 批次事件流（只追加，页面可查看修订轨迹） ----------
@router.get('/lot-events')
def lot_events(db=Depends(database),u=Depends(current)):
    return [row(x) for x in db.query(LotEvent).order_by(LotEvent.id.desc()).limit(500).all()]

@router.get('/lots/current')
def lots_current(period:str='',db=Depends(database),u=Depends(current)):
    return project_lots(db,period or None)

# ---------- 重算任务与发布版本 ----------
@router.get('/recompute-jobs')
def recompute_jobs(db=Depends(database),u=Depends(current)):
    return [row(x) for x in db.query(RecomputeJob).order_by(RecomputeJob.id.desc()).limit(200).all()]

@router.post('/recompute-jobs')
def request_recompute(b:RecomputeInput,db=Depends(database),u=Depends(editor)):
    jobs=manual_recompute(db,u,b.period,b.policy_id)
    return [row(x) for x in jobs]

@router.get('/jobs/queue')
def queue(db=Depends(database),u=Depends(current)):
    return [row(x) for x in db.query(JobQueue).order_by(JobQueue.id.desc()).limit(200).all()]

@router.get('/publications')
def publications(db=Depends(database),u=Depends(current)):
    return [row(x) for x in db.query(Publication).order_by(Publication.id.desc()).limit(200).all()]

@router.get('/publications/{pid}')
def publication_detail(pid:int,db=Depends(database),u=Depends(current)):
    obj=db.get(Publication,pid)
    if not obj: raise HTTPException(404,'发布版本不存在')
    return row(obj)

@router.get('/publications/{pid}/csv')
def publication_csv(pid:int,db=Depends(database),u=Depends(current)):
    obj=db.get(Publication,pid)
    if not obj: raise HTTPException(404,'发布版本不存在')
    if obj.status!='published': raise HTTPException(409,'该版本未发布')
    return Response(csv_text(obj.result),media_type='text/csv',
                    headers={'Content-Disposition':f'attachment; filename="publication-{pid}-v{obj.version_no}.csv"'})
