import {request} from './client.js';
export const loadAll=async()=>request('/board');
export const saveSource=(data,id)=>request('/sources'+(id?'/'+id:''),id?'PUT':'POST',{data});
export const savePolicy=data=>request('/policies','POST',{data});
export const submitRun=data=>request('/runs','POST',data);
export const approveRun=(id,note)=>request('/runs/'+id+'/approve','POST',{note});
export const submitPacket=data=>request('/packets','POST',data);
export const retryPacket=packet_id=>request('/packets/'+encodeURIComponent(packet_id)+'/retry','POST',{});
export const requestRecompute=data=>request('/recompute-jobs','POST',data);
