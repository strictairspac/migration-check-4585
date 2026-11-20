import {store} from '../stores/business.js';import {esc,json} from '../utils/html.js';import {status} from '../components/common/status.js';import {table} from '../components/common/table.js';import {runs} from '../api/business.js';import {REJECT_REASON_LABELS} from '../constants/enums.js';
// 核对筛选状态按运行保存，轮询刷新不丢失
export const reviewState=new Map();
function state(id){if(!reviewState.has(id))reviewState.set(id,{source_unit:'',target_unit:'',reason:'',offset:0});return reviewState.get(id);}
function optionList(values,picked,emptyLabel){return `<option value="">${esc(emptyLabel)}</option>`+values.map(v=>`<option value="${esc(v.code??v)}" ${v===picked||v.code===picked?'selected':''}>${esc(v.label??v)}</option>`).join('');}
export function resultsPage(id){
 let e=store.runs.find(x=>x.id===Number(id))||store.runs.find(x=>x.status==='completed')||store.runs[0];
 if(!e)return '<div class="empty"><h2>交接尚未开始</h2><p>登记源批次、配置字段映射（含单位换算规则），再提交一次迁移。空批次也可生成可复查备份。</p></div>';
 let r=e.result,st=state(e.id);
 return `<div class="result-head"><div><span class="eyebrow">RECEIPT #${e.id} / FROZEN INPUT</span><h2>${esc(e.name)} ${status(e.status)}</h2></div><button data-export="${e.id}">下载对账凭据 ↓</button></div>${e.error?`<div class="feedback error">${esc(e.error)}</div>`:''}${r?`<div class="metrics"><div><small>源记录</small><strong>${r.source_count}<em>行</em></strong></div><div><small>已交接 / 目标持久化</small><strong>${r.accepted_count}<em>行</em></strong></div><div><small>隔离待修复</small><strong>${r.rejected_count}<em>行</em></strong></div></div>
<div class="review-filters" data-review="${e.id}"><label>按原单位<select data-review-filter="source_unit">${optionList(extractUnits(r,true),st.source_unit,'全部原单位')}</select></label><label>按目标单位<select data-review-filter="target_unit">${optionList(extractUnits(r,false),st.target_unit,'全部目标单位')}</select></label><label>按拒绝原因<select data-review-filter="reason">${optionList(extractReasons(r),st.reason,'全部原因')}</select></label><button class="quiet" data-review-clear="${e.id}">清除筛选</button></div>
<div class="evidence"><section><h3>目标行核对 · 原值原单位 → 统一值</h3><div id="review-accepted">正在读取…</div><h3>拒绝区 · 原行保留</h3><div id="review-rejected">正在读取…</div><h3>分块校验</h3>${table(['块','已处理','接受','拒绝'],r.chunks.map(c=>[c.chunk,c.processed,c.accepted,c.rejected]))}</section><section><h3>交接摘要</h3><code class="checksum">${esc(r.checksum)}</code><div class="actions"><button data-backup="${e.id}">下载逻辑备份 ↓</button><button class="quiet" data-targets="${e.id}">读取真实目标表</button></div><pre id="target-data" hidden></pre><aside class="note">备份(v2)含受理时换算规则与原值原单位证据，是本工具目标行的JSON逻辑快照，不包含数据库WAL、索引或权限，不等同于pg_dump。换算规则之后改动不会改变本运行已冻结的结果与备份。</aside>${store.user.role==='admin'?`<h3>管理员 · 回传备份恢复</h3><p>恢复将用经原运行摘要校验的备份，原子替换本次运行目标行并核对，恢复后统一值与来源必须与备份完全一致。请先下载该运行备份。</p><input id="backup-file" type="file" accept=".json,application/json"><button data-restore="${e.id}">恢复并核验</button>`:'<p>管理员可以回传已下载的JSON备份，验证目标行恢复。</p>'}${e.recovery?.length?`<pre>${json(e.recovery)}</pre>`:''}<details><summary>完整对账记录 / 输入快照（含冻结换算规则）</summary><pre>${json(e)}</pre></details></section></div>`:'<div class="empty">本次运行尚未完成或已取消；取消/异常不提交目标行。页面会自动刷新。</div>'}`;
}
function extractUnits(r,source){
 let key=source?'original_unit':'unit';
 return [...new Set((r.accepted_rows||[]).map(x=>x[key]).filter(Boolean))].sort();
}
function extractReasons(r){return [...new Set((r.rejected_rows||[]).map(x=>x.reason).filter(Boolean))].sort().map(code=>({code,label:REJECT_REASON_LABELS[code]||code}));}
export async function loadReview(id){
 let boxA=document.getElementById('review-accepted'),boxR=document.getElementById('review-rejected');
 if(!boxA||!boxR)return;
 let st=state(id);
 try{
  let data=await runs.review(id,{source_unit:st.source_unit,target_unit:st.target_unit,reason:st.reason,limit:50,offset:st.offset});
  boxA.innerHTML=renderAccepted(data)+pager(id,data.accepted_total,st.offset,50,'a');
  boxR.innerHTML=renderRejected(data)+pager(id,data.rejected_total,st.offset,50,'r');
 }catch(e){boxA.innerHTML=`<div class="feedback error">${esc(e.message)}</div>`;boxR.innerHTML='';}
}
function renderAccepted(data){
 if(!data.accepted_rows.length)return '<div class=empty>没有符合筛选条件的目标行。</div>';
 return table(['委托号','检测项','原值 / 原单位','统一值 / 目标单位','测量时间(UTC)'],data.accepted_rows.map((x,i)=>[esc(x.sample_code),esc(x.test_name),`<b>${esc(x.original_value)}</b> <small>${esc(x.original_unit)}</small>`,`<b>${esc(x.result_value)}</b> <small>${esc(x.unit)}</small>`,esc(x.measured_at)]));
}
function renderRejected(data){
 if(!data.rejected_rows.length)return '<div class=empty>没有符合筛选条件的拒绝行。</div>';
 return table(['源行号','拒绝原因','说明 / 原始数据'],data.rejected_rows.map(x=>[x.row_number,esc(REJECT_REASON_LABELS[x.reason]||x.reason),`<small>${esc(x.detail||'')}</small><details><summary>展开原行</summary><pre>${json(x.source)}</pre></details>`]));
}
function pager(id,total,offset,limit,kind){
 if(total<=limit)return `<div class="pager-note">共 ${total} 行</div>`;
 let pages=[];
 for(let p=0;p<total;p+=limit)pages.push(p);
 return `<div class="pager-note">共 ${total} 行，第 ${Math.floor(offset/limit)+1}/${pages.length} 页</div><div class="pager">${pages.map(p=>`<button class="quiet ${p===offset?'active':''}" data-review-page="${id}" data-offset="${p}" data-kind="${kind}">${Math.floor(p/limit)+1}</button>`).join('')}</div>`;
}
export async function bindReview(){
 document.querySelectorAll('[data-review-filter]').forEach(sel=>sel.addEventListener('change',async()=>{
  let id=Number(sel.closest('[data-review]').dataset.review),st=state(id);
  st[sel.dataset.reviewFilter]=sel.value;st.offset=0;await loadReview(id);
 }));
 document.querySelectorAll('[data-review-clear]').forEach(b=>b.addEventListener('click',async()=>{
  let id=Number(b.dataset.reviewClear);reviewState.set(id,{source_unit:'',target_unit:'',reason:'',offset:0});
  document.querySelectorAll(`[data-review="${id}"] [data-review-filter]`).forEach(sel=>{sel.value='';});
  await loadReview(id);
 }));
 document.querySelectorAll('[data-review-page]').forEach(b=>b.addEventListener('click',async()=>{let id=Number(b.dataset.reviewPage);state(id).offset=Number(b.dataset.offset);await loadReview(id);}));
}
