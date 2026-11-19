# -*- coding: utf-8 -*-
"""v22：只读。挂 0x4850BB0(取当前页) / 0x4850220(切页)，并用池句柄校验页面容器；
       不做任何 native 调用（避免 widgetOwner 崩进程）。"""
import io, sys

ROOT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50"
SRC = ROOT + r"\offset_rework\old_bridge_v21_hb_switch.js"
DST = ROOT + r"\offset_rework\old_bridge_v22_page_hooks.js"
START = "// __POOL_PROBE__"

NEW = r"""// __POOL_PROBE__
(function(){
 var gpCount=0,spCount=0,gpSeen={},spSeen={};
 attachSafe(base.add(0x4850bb0),{
  onEnter(a){this.c=a[0];},
  onLeave(r){
   try{
    if(gpCount>=24){return;}
    var key=this.c.toString();
    if(gpSeen[key]){return;}
    gpSeen[key]=1;gpCount++;
    send({event:'v22_getpage',cont:key,obj:r.toString()});
   }catch(e){}
  }
 });
 attachSafe(base.add(0x4850220),{
  onEnter(a){this.c=a[0];this.p=a[1].toInt32();},
  onLeave(){
   try{
    if(spCount>=24){return;}
    var key=this.c.toString()+':'+this.p;
    if(spSeen[key]){return;}
    spSeen[key]=1;spCount++;
    send({event:'v22_showpage',cont:this.c.toString(),page:this.p});
   }catch(e){}
  }
 });
 var wantAt=0,scans=0,acted=false;
 globalThis.__v22mark=function(){wantAt=Date.now();};
 function validate(cont){
  var cnt=0,chunks=null;
  try{cnt=base.add(0xb89c294).readS32();chunks=base.add(0xb89c280).readPointer();}catch(e){return null;}
  if(cnt<1||chunks.isNull()){return null;}
  var idx=cont.add(0x7b8).readS32();
  var ser=cont.add(0x7bc).readS32();
  if(idx<0||idx>=cnt||ser===0){return null;}
  var ch=chunks.add((idx>>>16)*8).readPointer();
  if(ch.isNull()){return null;}
  var entry=ch.add((idx&65535)*24);
  if(entry.add(0x10).readS32()!==ser){return null;}
  var obj=entry.readPointer();
  if(obj.isNull()){return null;}
  var t=obj.add(0x10).readPointer();
  var d=t.isNull()?-1:t.add(0x38).readS32();
  return {obj:obj, d:d, idx:idx, ser:ser};
 }
 function scan(){
  scans++;
  var cnt=0,chunks=null,hosts=[],cands=0,valid=0;
  try{cnt=base.add(0xb89c294).readS32();chunks=base.add(0xb89c280).readPointer();}catch(e){return [];}
  if(cnt<1||chunks.isNull()){return [];}
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
    var v=validate(cont);
    if(!v){continue;}
    valid++;
    hosts.push({a:obj.toString(),page:obj.add(0x738).readS32(),n:n,cur:v.obj.toString(),d:v.d});
    if(hosts.length>=14){break;}
   }catch(e){}
  }
  send({event:'v22_scan',scan:scans,pool:cnt,cands:cands,valid:valid,hosts:hosts,
        getpage:gpCount,showpage:spCount});
  return hosts;
 }
 var timer=setInterval(function(){
  try{
   if(acted){return;}
   if(!wantAt){return;}
   if(Date.now()-wantAt<7000){return;}
   acted=true;
   scan();
   clearInterval(timer);
  }catch(e){send({event:'v22_err',d:String(e)});}
 },3000);
})();
"""

text = io.open(SRC, 'r', encoding='utf-8').read()
i = text.find(START)
if i < 0:
    print('POOL MARKER NOT FOUND'); sys.exit(1)
text = text[:i] + NEW
if "globalThis.__v22mark" in text:
    pass
old = "try{if(globalThis.__v21mark){globalThis.__v21mark();}}catch(e){}"
new = "try{if(globalThis.__v22mark){globalThis.__v22mark();}}catch(e){}"
if old in text:
    text = text.replace(old, new, 1)
    print('mark switched to v22')
else:
    print('WARN: v21 mark anchor not found')
io.open(DST, 'w', encoding='utf-8', newline='\n').write(text)
print('written', DST, len(text))
