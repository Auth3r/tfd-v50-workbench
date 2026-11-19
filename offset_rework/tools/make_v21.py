# -*- coding: utf-8 -*-
"""v21：心跳定时器 + 账号装载后 8 秒触发扫描；用 owner->comp 找页面宿主并切页"""
import io, sys

ROOT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50"
SRC = ROOT + r"\offset_rework\old_bridge_v20_owner_switch.js"
DST = ROOT + r"\offset_rework\old_bridge_v21_hb_switch.js"
START = "// __POOL_PROBE__"

NEW = r"""// __POOL_PROBE__
(function(){
 var tick=0,scans=0,wantAt=0,acted=false;
 var hb=setInterval(function(){
  tick++;
  if(tick<=3){send({event:'v21_tick',n:tick,comp:String(globalThis.__comp||null),want:wantAt});}
 },2000);
 function scan(){
  scans++;
  var comp=globalThis.__comp||null;
  var cnt=0,chunks=null,hosts=[],cands=0;
  try{cnt=base.add(0xb89c294).readS32();chunks=base.add(0xb89c280).readPointer();}catch(e){send({event:'v21_err',d:'pool:'+String(e)});return hosts;}
  if(cnt<1||chunks.isNull()){return hosts;}
  var limit=Math.min(cnt,320000);
  for(var i=0;i<limit;i++){
   try{
    var ch=chunks.add((i>>>16)*8).readPointer();
    if(ch.isNull()){continue;}
    var obj=ch.add((i&65535)*24).readPointer();
    if(obj.isNull()){continue;}
    if((obj.add(8).readU32()&0x60000030)){continue;}
    var cont=obj.add(0x720).readPointer();
    if(cont.isNull()){continue;}
    var n=cont.add(0x728).readS32();
    if(n<2||n>64){continue;}
    cands++;
    var owner=null;
    try{owner=widgetOwner(obj);}catch(e){continue;}
    if(owner.isNull()){continue;}
    var par=owner.add(0x830).readPointer();
    if(par.isNull()){continue;}
    if(!comp||!par.equals(comp)){continue;}
    hosts.push({a:obj.toString(),page:obj.add(0x738).readS32(),n:n,cont:cont.toString()});
    if(hosts.length>=12){break;}
   }catch(e){}
  }
  send({event:'v21_scan',scan:scans,pool:cnt,cands:cands,hosts:hosts,comp:comp?comp.toString():'null'});
  return hosts;
 }
 var timer=setInterval(function(){
  try{
   if(acted){return;}
   if(!wantAt){return;}
   if(Date.now()-wantAt<8000){return;}
   if(scans>=3){acted=true;clearInterval(timer);clearInterval(hb);send({event:'v21_giveup'});return;}
   var hosts=scan();
   if(!hosts.length){return;}
   acted=true;
   clearInterval(timer);clearInterval(hb);
   var pick=hosts[0];
   for(var i=0;i<hosts.length;i++){if(hosts[i].page!==3&&hosts[i].page!==4){pick=hosts[i];break;}}
   send({event:'v21_acting',a:pick.a,page:pick.page,n:pick.n,all:hosts.length});
   try{
    showLogin(ptr(pick.a),ticket);
    send({event:'v21_call_done'});
   }catch(e){send({event:'v21_call_err',d:String(e)});}
  }catch(e){send({event:'v21_tick_err',d:String(e)});}
 },2500);
 globalThis.__v21mark=function(){wantAt=Date.now();};
})();
"""

text = io.open(SRC, 'r', encoding='utf-8').read()
i = text.find(START)
if i < 0:
    print('POOL MARKER NOT FOUND'); sys.exit(1)
text = text[:i] + NEW

# 账号装载后打一个“可以开始扫描”的标记
old = "report('native_account_loaded'"
new = "try{if(globalThis.__v21mark){globalThis.__v21mark();}}catch(e){}\n  report('native_account_loaded'"
if old in text:
    text = text.replace(old, new, 1)
    print('mark hooked into account_loaded')
else:
    print('WARN: account_loaded report anchor not found')

io.open(DST, 'w', encoding='utf-8', newline='\n').write(text)
print('written', DST, len(text))
