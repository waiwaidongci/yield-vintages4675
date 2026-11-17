ROLES=('admin','analyst','viewer')
STATUSES=('queued','running','completed','failed')
# 数据包接收状态机
PACKET_STATUSES=('received','queued','applied','rejected','failed')
# 重算任务状态机：stale=计算期间数据已更新，需重算；expired=计算晚到未发布
RECOMPUTE_STATUSES=('queued','running','completed','failed','stale','expired')
# 批次事件动作：补报 / 更正 / 撤销
LOT_OPS=('report','correct','withdraw')
