import {heading} from '../components/common/header.js';
import {table} from '../components/common/table.js';
import {esc,time} from '../utils/format.js';
import {RECOMPUTE_STATUSES} from '../constants/enums.js';

const rstatus=s=>`<span class="status ${esc(s)}">${esc(RECOMPUTE_STATUSES[s]||s)}</span>`;

export function recompute(c,d){
 const versionOf=id=>d.policies.find(p=>p.id===id)?.version||id;
 return heading('RECOMPUTE & RELEASE / 06','受影响期间重算与版本发布','数据包生效后仅重算受影响期间的选定口径；底稿快照与加权结果作为同一版本、同一校验值发布。计算期间可继续收包，旧计算晚到不覆盖新结果。')
 +`<form id="recompute-form" class="inline-form">
  <label>选定口径<select name="policy_id">${d.policies.map(p=>`<option value="${p.id}">${esc(p.version)}</option>`).join('')}</select></label>
  <label>受影响期间<select name="period"><option>全部</option>${d.periods.map(p=>`<option>${esc(p.name)}</option>`).join('')}</select></label>
  <button>发起重算</button>
 </form>`
 +`<h2>重算任务（接收→发布状态与失败原因）</h2>`
 +table(d.recompute_jobs.map(j=>({
   编号:j.id,期间:j.period,口径:versionOf(j.policy_id),状态:rstatus(j.status),
   水位:j.watermark,发布版本:j.published_version?('v'+j.published_version):'—',
   尝试:j.attempts,更新:time(j.updated),说明:j.reason||'—'
 })))
 +`<h2>发布版本（同版本快照 + 加权结果 + SHA256）</h2>`
 +table(d.publications.map(p=>({
   编号:p.id,期间:p.period,口径:versionOf(p.policy_id),版本:'v'+p.version_no,
   状态:p.status,批次数:p.snapshot.lots.length,加权良率:(p.result.summary['加权良率']*100).toFixed(2)+'%',
   水位:p.watermark,校验:p.checksum.slice(0,16)+'…',发布时间:time(p.created)
 })))
 +`<div>${d.publications.map(p=>`<button class="pub-export" data-id="${p.id}">下载 v${p.version_no} CSV（${esc(p.period)}）</button>`).join('')}</div>`
 +`<h2>持久化作业队列</h2>`
 +table(d.jobs_queue.map(q=>({编号:q.id,类型:q.kind,引用:q.ref_id,状态:q.status,尝试:q.attempts,更新:time(q.updated),错误:q.last_error||'—'})));
}
