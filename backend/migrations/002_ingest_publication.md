# 迁移 002：批次数据包接收与版本化发布

SQLAlchemy 启动自动创建以下新表，不改动既有表结构，旧报告（yield_runs）与交付（deliveries）继续按原快照读取：

- `ingest_packets`：按 packet_id 幂等接收的数据包，记录状态机 received/applied/rejected/failed 与整包拒绝原因。
- `lot_events`：批次修订事件流，只追加；唯一约束 (lot_no, revision) 保证同批号修订号不冲突，当前状态由每批号最大修订号投影。
- `recompute_jobs`：受影响期间×口径的重算任务，携带排队时事件水位 watermark；状态机 queued/running/completed/failed/stale/expired。
- `job_queue`：持久化作业队列（packet/recompute 两类），心跳与 attempts 支撑中断恢复，避免依赖易失的内存队列。
- `yield_publications`：发布版本，唯一约束 (period, policy_id, version_no)；底稿快照 snapshot 与加权结果 result、SHA256 checksum 在同一事务落库。

关键语义：
1. 数据包在单事务内做整包冲突预检，任一记录冲突则整包拒绝、不写任何事件。
2. 迟到修订（revision ≤ 已生效修订）不覆盖；撤销后只允许重新补报，不允许更正。
3. 数据包生效后仅对受影响期间的既有口径排重算；同期间同口径的排队任务合并，计算中的任务水位冻结，新包生成下一代任务。
4. 重算发布前做水位自检：期间相关批号出现更新事件时，在算任务判 expired 不发布，由下一代任务发布新版本，旧计算不覆盖新结果。
5. 中断恢复：worker 启动及每轮回收心跳超时的 running 队列行/僵尸任务回 queued；所有生效与发布均幂等，重试不重复计入、不漏算。

回滚：新表均为增量表，停用新功能后可保留；如需彻底回滚，按 job_queue → recompute_jobs → yield_publications → lot_events → ingest_packets 顺序 DROP，不影响 yield_lots / yield_runs / deliveries。
