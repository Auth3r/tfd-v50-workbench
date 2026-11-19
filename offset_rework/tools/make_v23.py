# -*- coding: utf-8 -*-
"""v23：从 0x4850BB0 抓到真正的页面容器，反查宿主(obj+0x720==容器)，
       打印容器/宿主细节，然后（延时 4 秒）尝试 showLogin 切到登录页。"""
import io, sys

ROOT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50"
SRC = ROOT + r"\offset_rework\old_bridge_v22_page_hooks.js"
DST = ROOT + r"\offset_rework\old_bridge_v23_cont_host.js"
START = "// __POOL_PROBE__"

NEW = r"""// __POOL_PROBE__
(function(){
 var cont=null;
 attachSafe(base.add(0x4850bb0),{
  onEnter(a){ this.c=a[0]; if(!cont){cont=this.c;} },
  onLeave(r){
   try{
    if(globalThis.__v23fp){return;}
    globalThis.__v23fp=1;
    send({event:'v23_getpage',cont:this.c.toString(),ret:r.toString()});
   }catch(e){}
  }
 });
 var wantAt=0,scans=0,acted=false;
 globalThis.__v23mark=function(){wantAt=Date.now();};
 function dumpCont(c){
  try{
   var n=c.add(0x728).readS32();
   var arr=c.add(0x720).readPointer();
   var idx=c.add(0x7b8).readS32();
   var ser=c.add(0x7bc).readS32();
   var slots=[];
   if(!arr.isNull()){
    for(var j=0;j<Math.min(n,8);j++){
     var w=arr.add(j*48+0x10).readPointer();
     slots.push(w.isNull()?'null':w.toString());
    }
   }
   return {n:n,arr:arr.toString(),idx:idx,ser:ser,slots:slots};
  }catch(e){return {err:String(e)};}
 }
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
    if(p.isNull()){continue;}
    if(!p.equals(cont)){continue;}
    hits.push({a:obj.toString(),page:obj.add(0x738).readS32()});
    if(hits.length>=6){break;}
   }catch(e){}
  }
  return hits;
 }
 var timer=setInterval(function(){
  try{
   if(acted||!wantAt){return;}
   if(Date.now()-wantAt<7000){return;}
   acted=true;
   scans++;
   var st=cont?dumpCont(cont):{err:'no container'};
   var hosts=findHost();
   send({event:'v23_scan',cont:cont?cont.toString():'null',contState:st,hosts:hosts});
   if(!hosts.length){clearInterval(timer);send({event:'v23_no_host'});return;}
   clearInterval(timer);
   setTimeout(function(){
    try{
     var h=hosts[0];
     send({event:'v23_acting',a:h.a,page:h.page,pageGate:(function(){try{return ptr(h.a).add(0x738).readS32();}catch(e){return -99;}})()});
     showLogin(ptr(h.a),ticket);
     send({event:'v23_call_done'});
    }catch(e){send({event:'v23_call_err',d:String(e)});}
   },4000);
  }catch(e){send({event:'v23_err',d:String(e)});}
 },3000);
})();
"""

text = io.open(SRC, 'r', encoding='utf-8').read()
i = text.find(START)
if i < 0:
    print('POOL MARKER NOT FOUND'); sys.exit(1)
text = text[:i] + NEW
old = "try{if(globalThis.__v22mark){globalThis.__v22mark();}}catch(e){}"
new = "try{if(globalThis.__v23mark){globalThis.__v23mark();}}catch(e){}"
if old in text:
    text = text.replace(old, new, 1)
    print('mark switched to v23')
else:
    print('WARN: v22 mark anchor not found')
io.open(DST, 'w', encoding='utf-8', newline='\n').write(text)
print('written', DST, len(text))
