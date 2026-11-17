import {heading} from '../components/common/header.js';
import {table} from '../components/common/table.js';
import {time} from '../utils/format.js';
import {LOT_OPS} from '../constants/enums.js';

export function lots(c,d){
 return heading('LOT LEDGER / 03','批次修订台账','事件流只追加不覆盖：每个批号保留全部补报/更正/撤销轨迹，当前状态取最新修订；撤销批号不参与核算。')
 +`<h2>当前生效批次（最新修订投影）</h2>`
 +table(d.lots_current.map(x=>({
   批号:x.lot_no,修订号:'r'+x.revision,
   日期:x.data.period,试制线:x.data.department,班次:x.data.shift,
   投入:x.data.input,一次通过:x.data.first_pass,返工合格:x.data.reworked_good,报废:x.data.scrap
 })))
 +`<h2>修订事件流（只追加，按时间倒序）</h2>`
 +table(d.lot_events.map(e=>({
   批号:e.lot_no,修订号:'r'+e.revision,动作:LOT_OPS[e.op]||e.op,
   来源包:e.packet_id,时间:time(e.created),
   数据:e.data?`${e.data.period} / ${e.data.department} / 投入${e.data.input}`:'—（撤销）'
 })));
}
