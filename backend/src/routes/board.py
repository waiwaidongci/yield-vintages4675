from fastapi import APIRouter,Depends
from src.config.database import database
from src.controllers.auth import current
from src.models.source import Source,Policy,Period
from src.models.run import Run,Schedule,Delivery
from src.models.identity import Audit
from src.models.ingest import IngestPacket,LotEvent,RecomputeJob,JobQueue,Publication
from src.services.ingest import project_lots
from src.utils.serialize import row
router=APIRouter()

@router.get('/board')
def board(db=Depends(database),u=Depends(current)):
    """页面总览聚合：一次请求取齐所有集合，避免高频轮询触发限流。"""
    return {
      'sources':[row(x) for x in db.query(Source).order_by(Source.id).all()],
      'periods':[{'id':i+1,'name':n,'description':'当前来源期间'} for i,n in enumerate(sorted({x.data['period'] for x in db.query(Source).all()}))],
      'policies':[row(x) for x in db.query(Policy).order_by(Policy.id).all()],
      'runs':[row(x) for x in db.query(Run).order_by(Run.id.desc()).all()],
      'schedules':[row(x) for x in db.query(Schedule).all()],
      'deliveries':[row(x) for x in db.query(Delivery).order_by(Delivery.id.desc()).limit(100).all()],
      'audits':[row(x) for x in db.query(Audit).order_by(Audit.id.desc()).limit(200).all()],
      'packets':[row(x) for x in db.query(IngestPacket).order_by(IngestPacket.id.desc()).limit(200).all()],
      'lot_events':[row(x) for x in db.query(LotEvent).order_by(LotEvent.id.desc()).limit(500).all()],
      'lots_current':project_lots(db),
      'recompute_jobs':[row(x) for x in db.query(RecomputeJob).order_by(RecomputeJob.id.desc()).limit(200).all()],
      'jobs_queue':[row(x) for x in db.query(JobQueue).order_by(JobQueue.id.desc()).limit(200).all()],
      'publications':[row(x) for x in db.query(Publication).order_by(Publication.id.desc()).limit(200).all()],
    }
