# -*- coding: utf-8 -*-
"""v20：用 widgetOwner(obj)+0x830 == comp 过滤页面宿主；命中且当前页 != 3 时调用 showLogin"""
import io, sys

ROOT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50"
SRC = ROOT + r"\offset_rework\old_bridge_v19_host_stat.js"
DST = ROOT + r"\offset_rework\old_bridge_v20_owner_switch.js"
START = "// __POOL_PROBE__"

NEW = r"""// __POOL_PROBE__
(function(){
 var comp=globalThis.__comp||null;
 if(!comp){send({event:'v20_no_comp'});}
 var scans=0;
 function scan(){
  scans++;
  var cnt=0,chunks=null,hosts=[],allCands=0;
  try{cnt=base.add(0xb89c294).readS32();chunks=base.add(0xb89c280).readPointer();}catch(e){send({event:'v20_err',d:'pool:'+String(e)});return;}
  if(cnt<1||chunks.isNull())return;
  var limit=Math.min(cnt,320000);
  for(var i=0;i<limit;i++){
   try{
    var ch=chunks.add((i>>>16)*8).readPointer();if(ch.isNull())continue;
    var obj=ch.add((i&65535)*24).readPointer();if(obj.isNull())continue;
    if((obj.add(8).readU32()&0x60000030))continue;
    var cont=obj.add(0x720).readPointer();if(cont.isNull())continue;
    var n=cont.add(0x728).readS32();if(n<2||n>64)continue;
    allCands++;
    var owner=null;
    try{owner=widgetOwner(obj);}catch(e){continue;}
    if(!owner||owner.isNull())continue;
    var par=null;
    try{par=owner.add(0x830).readPointer();}catch(e){continue;}
    if(!par||par.isNull()||!comp||!par.equals(comp))continue;
    hosts.push({a:obj.toString(),page:obj.add(0x738).readS32(),n:n,cont:cont.toString(),owner:owner.toString()});
    if(hosts.length>=12)break;
   }catch(e){}
  }
  send({event:'v20_scan',scan:scans,pool:cnt,cands:allCands,hosts:hosts});
  return hosts;
 }
 var timer=setInterval(function(){
  try{
   if(Date.now()-born<49000)return;
   if(globalThis.__v20done)return;
   if(scans>=4){clearInterval(timer);send({event:'v20_giveup'});return;}
   var hosts=scan();
   if(!hosts||!hosts.length)return;
   globalThis.__v20done=1;
   clearInterval(timer);
   var pick=null;
   for(var i=0;i<hosts.length;i++){if(hosts[i].page!==3&&hosts[i].page!==4){pick=hosts[i];break;}}
   if(!pick)pick=hosts[0];
   send({event:'v20_acting',a:pick.a,page:pick.page,n:pick.n});
   try{
    showLogin(ptr(pick.a), ticket);
    send({event:'v20_call_done',page_after:(function(){try{return ptr(pick.a).add(0x738).readS32();}catch(e){return -99;}})()});
   }catch(e){send({event:'v20_call_err',d:String(e)});}
  }catch(e){send({event:'v20_tick_err',d:String(e)});}
 },3000);
})();
"""

text = io.open(SRC, 'r', encoding='utf-8').read()
i = text.find(START)
if i < 0:
    print('POOL MARKER NOT FOUND'); sys.exit(1)
text = text[:i] + NEW
io.open(DST, 'w', encoding='utf-8', newline='\n').write(text)
print('written', DST, len(text))
