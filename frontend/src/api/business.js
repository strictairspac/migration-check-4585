import {api,post} from './client.js';
export const batches={list:()=>api('/batches'),save:(d,id)=>post('/batches'+(id?'/'+id:''),d,id?'PUT':'POST')};
export const mappings={list:()=>api('/mappings'),save:(d,id)=>post('/mappings'+(id?'/'+id:''),d,id?'PUT':'POST')};
function reviewQuery(q){
 if(!q)return '';
 const params=new URLSearchParams();
 for(const [k,v] of Object.entries(q)){
  if(v!==null&&v!==undefined&&v!=='')params.append(k,String(v));
 }
 const qs=params.toString();
 return qs?('?'+qs):'';
}
export const runs={list:()=>api('/runs'),run:d=>post('/runs',d),cancel:id=>post('/runs/'+id+'/cancel',{}),targets:id=>api('/runs/'+id+'/targets'),review:(id,q)=>api('/runs/'+id+'/review'+reviewQuery(q)),restore:(id,backup)=>post('/runs/'+id+'/restore',{backup})};
