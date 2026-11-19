# -*- coding: utf-8 -*-
"""v17：页面字段改 0x738（新版真实偏移），并把控件池普查换成“找页面宿主 + 页面号直方图”（只读）"""
import io, sys, re

ROOT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50"
SRC = ROOT + r"\offset_rework\old_bridge_v16_class_scan.js"
DST = ROOT + r"\offset_rework\old_bridge_v17_page_host.js"
START = "// __POOL_PROBE__"

NEW = r"""// __POOL_PROBE__
(function(){
 var batch=0,scanFrom=0,maxBatch=14,perBatch=20000;
 var hist={},hostTotal=0,samples=[];
 try{
  var k1=lobbyClass();
  send({event:'probe_cls_lobby',ptr:k1.toString(),depth:k1.add(0x38).readS32(),k30:k1.add(0x30).readPointer().toString(),self:k1.toString()});
 }catch(e){send({event:'probe_cls_err',d:'lobby:'+String(e)});}
 var timer=setInterval(function(){
  if(batch>=maxBatch){clearInterval(timer);send({event:'probe_host_summary',hostTotal:hostTotal,hist:hist,samples:samples});return;}
  var cnt=0,chunksp=null;
  try{cnt=base.add(0xb89c294).readS32();chunksp=base.add(0xb89c280).readPointer();}
  catch(e){send({event:'probe_host_error',d:String(e)});clearInterval(timer);return;}
  if(chunksp.isNull()||cnt<1){return;}
  var start=scanFrom,stop=Math.min(scanFrom+perBatch,cnt);
  var hosts=0;
  for(var i=start;i<stop;i++){
   try{
    var chunk=chunksp.add((i>>>16)*8).readPointer();
    if(chunk.isNull()){continue;}
    var obj=chunk.add((i&65535)*24).readPointer();
    if(obj.isNull()){continue;}
    if((obj.add(8).readU32()&0x60000030)){continue;}
    var t=obj.add(0x10).readPointer();
    if(t.isNull()){continue;}
    var d=t.add(0x38).readS32();
    if(d<0||d>64){continue;}
    var p720=obj.add(0x720).readPointer();
    if(p720.isNull()){continue;}
    var page=obj.add(0x738).readS32();
    hosts++;hostTotal++;
    var key='p'+page;
    hist[key]=(hist[key]||0)+1;
    if(hosts<=5&&samples.length<48){
     var dw=[];
     for(var o=0x700;o<=0x7fc;o+=4){try{dw.push(obj.add(o).readS32());}catch(e){dw.push(-1);}}
     samples.push({a:obj.toString(),page:page,d:d,p720:p720.toString(),dw:dw});
    }
   }catch(e){}
  }
  scanFrom=stop;batch++;
  send({event:'probe_host_batch',batch:batch,from:start,to:stop,count:cnt,hosts:hosts,hist:hist});
 },2500);
})();
"""

text = io.open(SRC, 'r', encoding='utf-8').read()
i = text.find(START)
if i < 0:
    print('POOL MARKER NOT FOUND')
    sys.exit(1)
text = text[:i] + NEW
# 0x748 -> 0x738 (new page field)
n = text.count('0x748')
text = text.replace('0x748', '0x738')
io.open(DST, 'w', encoding='utf-8', newline='\n').write(text)
print('written', DST, len(text), 'replaced 0x748 x', n)
