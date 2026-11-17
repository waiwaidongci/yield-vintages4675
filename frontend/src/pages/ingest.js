import {heading} from '../components/common/header.js';
import {table} from '../components/common/table.js';
import {esc,time} from '../utils/format.js';
import {PACKET_STATUSES,LOT_OPS} from '../constants/enums.js';

const pstatus=s=>`<span class="status ${esc(s)}">${esc(PACKET_STATUSES[s]||s)}</span>`;

export function ingest(c,d){
 const fields=c.fields;
 const rowTpl=JSON.stringify({lot_no:'LOT-001',revision:1,op:'report',data:c.example},null,2);
 return heading('PACKET INTAKE / 02','批次数据包接收','按批号、修订号接收整包：同修订内容冲突整包拒绝，迟到修订不覆盖较新修订；每包全部生效后仅重算受影响期间。')
 +`<details open><summary>提交数据包（JSON：packet_id + items）</summary>
 <form id="packet-form">
 <label>数据包标识 packet_id<input name="packet_id" value="PKG-20261117-01" required></label>
 <label>批次记录 items（每条含 lot_no / revision / op / data）<textarea name="items" rows="10" required>${esc(rowTpl)}</textarea></label>
 <p class="method">op 取值：<b>report</b> 补报、<b>correct</b> 更正、<b>withdraw</b> 撤销（撤销不带 data）。修订号 revision 为不小于 1 的整数，包内同批号修订号不可重复。</p>
 <button>接收数据包</button>
 </form></details>`
 +`<h2>接收状态（含失败原因）</h2>`
 +table(d.packets.map(p=>({
   编号:p.id,数据包:p.packet_id,状态:pstatus(p.status),批次数:p.lot_count,最高修订:p.revision_max,
   提交人:p.actor,接收时间:time(p.created),生效时间:p.applied_at?time(p.applied_at):'—',
   失败原因:p.reason||'—'
 })))
 +`<h2>整包拒绝/失败重试</h2><p class="method">已生效包重试幂等不重复计入；被拒包修正数据后可用同一 packet_id 重新提交，或对原包点重试。</p>`
 +(d.packets.filter(p=>['rejected','failed'].includes(p.status)).length
   ? `<div>${d.packets.filter(p=>['rejected','failed'].includes(p.status)).map(p=>`<button class="retry-packet" data-id="${esc(p.packet_id)}">重试 ${esc(p.packet_id)}（${esc(p.reason)}）</button>`).join('')}</div>`
   : '<p class="empty">暂无被拒绝或失败的数据包。</p>');
}
