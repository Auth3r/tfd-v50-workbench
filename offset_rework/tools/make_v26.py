# -*- coding: utf-8 -*-
"""v26：游戏线程里先 showLogin，再直接调 0x4850220(container, 页号) 逐页尝试，并读回 getPage"""
import io, sys

ROOT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50"
SRC = ROOT + r"\offset_rework\old_bridge_v25_page_trace.js"
DST = ROOT + r"\offset_rework\old_bridge_v26_force_page.js"
START = "// __POOL_PROBE__"

NEW = r"""// __POOL_PROBE__
(function(){
 var cont=null,wantAt=0,scanDone=false,acted=false;
 var showPageFn=new NativeFunction(base.add(0x4850220),'void',['pointer','int']);
 var getPageFn=new NativeFunction(base.add(0x4850bb0),'pointer',['pointer']);
 attachSafe(base.add(0x4850bb0),{
  onEnter(a){ this.c=a[0]; if(!cont){cont=this.c;} }
 });
 attachSafe(base.add(0x4850220),{
  onEnter(a){ try{ send({event:'v26_showpage',cont:a[0].toString(),idx:a[1].toInt32()}); }catch(e){send({event:'v26_showpage_odd',d:String(e)});} }
 });
 function state(tag){
  try{
   if(!cont){send({event:'v26_state',tag:tag,cont:'null'});return;}
   var cur='?';
   try{ cur=getPageFn(cont).toString(); }catch(e){ cur='ERR:'+String(e); }
   send({event:'v26_state',tag:tag,cont:cont.toString(),n:cont.add(0x728).readS32(),
    idx:cont.add(0x7b8).readS32(),ser:cont.add(0x7bc).readS32(),cur:cur});
  }catch(e){send({event:'v26_state_err',tag:tag,d:String(e)});}
 }
 attachSafe(base.add(0x449d540),{
  onLeave(){
   try{
    if(acted||!cont){return;}
    if(!globalThis.__v26at||Date.now()-globalThis.__v26at<1500){return;}
    acted=true;
    send({event:'v26_gamethread_call'});
    state('before');
    try{ showLogin(ptr(globalThis.__v26host),ticket); send({event:'v26_login_ok'}); }
    catch(e){ send({event:'v26_login_err',d:String(e)}); }
    state('afterLogin');
    for(var pg=3;pg<=4;pg++){
     try{ showPageFn(cont,pg); send({event:'v26_force_ok',pg:pg}); }
     catch(e){ send({event:'v26_force_err',pg:pg,d:String(e)}); }
     state('afterForce'+pg);
    }
   }catch(e){send({event:'v26_call_err',d:String(e)});}
  }
 });
 globalThis.__v26mark=function(){wantAt=Date.now();};
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
   send({event:'v26_scan',cont:cont?cont.toString():'null',hosts:hosts});
   globalThis.__v26host=hosts.length?hosts[0].a:'0x0';
   globalThis.__v26at=Date.now();
   send({event:'v26_armed',a:globalThis.__v26host,n:hosts.length});
  }catch(e){send({event:'v26_err',d:String(e)});}
 },3000);
})();
"""

text = io.open(SRC, 'r', encoding='utf-8').read()
i = text.find(START)
if i < 0:
    print('POOL MARKER NOT FOUND'); sys.exit(1)
text = text[:i] + NEW
old = "try{if(globalThis.__v25mark){globalThis.__v25mark();}}catch(e){}"
new = "try{if(globalThis.__v26mark){globalThis.__v26mark();}}catch(e){}"
if old in text:
    text = text.replace(old, new, 1)
    print('mark switched to v26')
else:
    print('WARN: v25 mark anchor not found')
io.open(DST, 'w', encoding='utf-8', newline='\n').write(text)
print('written', DST, len(text))
