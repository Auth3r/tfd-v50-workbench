# -*- coding: utf-8 -*-
"""v25：游戏线程调 showLogin，钩住 0x4850220/0x4850BB0 观察页号，失败则直接调 showPage(cont,3)"""
import io, sys

ROOT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50"
SRC = ROOT + r"\offset_rework\old_bridge_v24_gamethread.js"
DST = ROOT + r"\offset_rework\old_bridge_v25_page_trace.js"
START = "// __POOL_PROBE__"

NEW = r"""// __POOL_PROBE__
(function(){
 var cont=null,wantAt=0,scanDone=false,acted=false,stage=0;
 attachSafe(base.add(0x4850bb0),{
  onEnter(a){ this.c=a[0]; if(!cont){cont=this.c;} },
  onLeave(ret){ try{ if(this.c&&this.c.equals(cont)){send({event:'v25_getpage',cont:this.c.toString(),ret:ret.toString()});} }catch(e){} }
 });
 attachSafe(base.add(0x4850220),{
  onEnter(a){ try{ send({event:'v25_showpage',cont:a[0].toString(),idx:a[1].toInt32()}); }catch(e){send({event:'v25_showpage_odd',d:String(e)});} }
 });
 function dumpCont(tag){
  try{
   if(!cont){send({event:'v25_contstate',tag:tag,cont:'null'});return;}
   send({event:'v25_contstate',tag:tag,cont:cont.toString(),
    n:cont.add(0x728).readS32(),
    idx:cont.add(0x7b8).readS32(),
    ser:cont.add(0x7bc).readS32()});
  }catch(e){send({event:'v25_contstate_err',tag:tag,d:String(e)});}
 }
 attachSafe(base.add(0x449d540),{
  onLeave(){
   try{
    if(acted||!cont){return;}
    if(!globalThis.__v25at||Date.now()-globalThis.__v25at<1500){return;}
    acted=true;
    send({event:'v25_gamethread_call'});
    dumpCont('before');
    try{ showLogin(ptr(globalThis.__v25host),ticket); send({event:'v25_login_ok'}); }
    catch(e){ send({event:'v25_login_err',d:String(e)}); }
    dumpCont('afterLogin');
    try{ showPage(ptr(cont),3); send({event:'v25_showpage_direct_ok'}); }
    catch(e){ send({event:'v25_showpage_direct_err',d:String(e)}); }
    dumpCont('afterShowPage');
   }catch(e){send({event:'v25_call_err',d:String(e)});}
  }
 });
 globalThis.__v25mark=function(){wantAt=Date.now();};
 function findHost(){
  var cnt=0,chunks=null,hits=[];
  try{cnt=base.add(0xb89c294).readS32();chunks=base.add(0xb89c280).readPointer();}catch(e){return hits;}
  if(cnt<1||chunks.isNull()||!cont){return hits;}
  var limit=Math.min(cnt,320000);
  for(var i=0;i<limit;i++){
   try{
    var ch=chunks.add((i>>>16)*8).readPointer();
    if(ch.isNull()){continue;}
    var obj=ch.add((i&65535)*24).readPointer();
    if(obj.isNull()){continue;}
    if((obj.add(8).readU32()&0x60000030)){continue;}
    var p=obj.add(0x720).readPointer();
    if(p.isNull()||!p.equals(cont)){continue;}
    hits.push({a:obj.toString(),page:obj.add(0x738).readS32()});
    if(hits.length>=6){break;}
   }catch(e){}
  }
  return hits;
 }
 var timer=setInterval(function(){
  try{
   if(scanDone||!wantAt){return;}
   if(Date.now()-wantAt<7000){return;}
   scanDone=true;
   var hosts=findHost();
   send({event:'v25_scan',cont:cont?cont.toString():'null',hosts:hosts});
   if(!hosts.length){
    // 没有宿主也要能自己切页
    globalThis.__v25host=hosts.length?hosts[0].a:'0x0';
    globalThis.__v25at=Date.now();
    send({event:'v25_armed_nohost'});
    return;
   }
   globalThis.__v25host=hosts[0].a;
   globalThis.__v25at=Date.now();
   send({event:'v25_armed',a:hosts[0].a,page:hosts[0].page});
  }catch(e){send({event:'v25_err',d:String(e)});}
 },3000);
})();
"""

text = io.open(SRC, 'r', encoding='utf-8').read()
i = text.find(START)
if i < 0:
    print('POOL MARKER NOT FOUND'); sys.exit(1)
text = text[:i] + NEW
old = "try{if(globalThis.__v24mark){globalThis.__v24mark();}}catch(e){}"
new = "try{if(globalThis.__v25mark){globalThis.__v25mark();}}catch(e){}"
if old in text:
    text = text.replace(old, new, 1)
    print('mark switched to v25')
else:
    print('WARN: v24 mark anchor not found')
io.open(DST, 'w', encoding='utf-8', newline='\n').write(text)
print('written', DST, len(text))
