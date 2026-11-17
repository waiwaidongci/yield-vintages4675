from sqlalchemy import Column,Integer,String,JSON,Float,Text,UniqueConstraint,Index
from src.config.database import Base

class IngestPacket(Base):
    """按批号、修订号接收的数据包；整包接收或整包拒绝。"""
    __tablename__='ingest_packets'
    id=Column(Integer,primary_key=True)
    packet_id=Column(String(120),unique=True,nullable=False)
    payload=Column(JSON,nullable=False)
    status=Column(String(20),nullable=False,default='received')
    reason=Column(Text,default='')
    revision_max=Column(Integer,nullable=False,default=0)
    lot_count=Column(Integer,nullable=False,default=0)
    created=Column(Float,nullable=False)
    applied_at=Column(Float)
    actor=Column(String(120))

class LotEvent(Base):
    """批次修订事件流，只追加不更新；当前状态由每批号最大修订号投影。"""
    __tablename__='lot_events'
    id=Column(Integer,primary_key=True)
    lot_no=Column(String(120),nullable=False)
    revision=Column(Integer,nullable=False)
    op=Column(String(20),nullable=False)
    data=Column(JSON)
    packet_id=Column(String(120),nullable=False)
    created=Column(Float,nullable=False)
    __table_args__=(UniqueConstraint('lot_no','revision',name='uq_lot_revision'),
                    Index('ix_lot_events_lot','lot_no','revision'))

class RecomputeJob(Base):
    """受影响期间×选定口径的重算任务；watermark 为排队时的批次事件水位。"""
    __tablename__='recompute_jobs'
    id=Column(Integer,primary_key=True)
    period=Column(String(120),nullable=False)
    policy_id=Column(Integer,nullable=False)
    status=Column(String(20),nullable=False,default='queued')
    watermark=Column(Integer,nullable=False,default=0)
    published_version=Column(Integer)
    attempts=Column(Integer,nullable=False,default=0)
    reason=Column(Text,default='')
    created=Column(Float,nullable=False)
    updated=Column(Float,nullable=False)
    heartbeat=Column(Float)
    __table_args__=(Index('ix_recompute_lookup','period','policy_id','status'),)

class JobQueue(Base):
    """持久化作业队列：packet 数据包生效 / recompute 受影响期间重算。"""
    __tablename__='job_queue'
    id=Column(Integer,primary_key=True)
    kind=Column(String(20),nullable=False)
    ref_id=Column(Integer,nullable=False)
    status=Column(String(20),nullable=False,default='queued')
    attempts=Column(Integer,nullable=False,default=0)
    last_error=Column(Text,default='')
    created=Column(Float,nullable=False)
    updated=Column(Float,nullable=False)
    heartbeat=Column(Float)
    __table_args__=(Index('ix_job_queue_pick','status','id'),)

class Publication(Base):
    """选定口径的发布版本：底稿快照与加权结果同一版本、同一校验值发布。"""
    __tablename__='yield_publications'
    id=Column(Integer,primary_key=True)
    period=Column(String(120),nullable=False)
    policy_id=Column(Integer,nullable=False)
    version_no=Column(Integer,nullable=False)
    status=Column(String(20),nullable=False,default='published')
    snapshot=Column(JSON,nullable=False)
    result=Column(JSON,nullable=False)
    checksum=Column(String(64),nullable=False)
    watermark=Column(Integer,nullable=False,default=0)
    recompute_job_id=Column(Integer)
    reason=Column(Text,default='')
    created=Column(Float,nullable=False)
    __table_args__=(UniqueConstraint('period','policy_id','version_no',name='uq_publication_version'),)
