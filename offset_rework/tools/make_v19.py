# -*- coding: utf-8 -*-
"""v19：读 M1UILogin / M1UIGameStartMenu 的类缓存指针（不调用取值函数），
       统计“页面宿主”候选的页号分布 + 抽样，仍为只读。"""
import io, sys

ROOT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50"
SRC = ROOT + r"\offset_rework\old_bridge_v18_page_switch.js"
DST = ROOT + r"\offset_rework\old_bridge_v19_host_stat.js"
START = "// __POOL_PROBE__"

NEW = r"""// __POOL_PROBE__
(function(){
 var kLogin=null,kMenu=null;
 try{kLogin=base.add(0xbcd1e58).readPointer();}catch(e){send({event:'v19_err',d:'login_cache:'+String(e)});}
 try{kMenu=base.add(0xbccf978).readPointer();}catch(e){send({event:'v19_err',d:'menu_cache:'+String(e)});}
 var okL=false,okM=false;
 try{okL=!!kLogin&&!kLogin.isNull();okM=!!kMenu&&!kMenu.isNull();}catch(e){}
 if(okL){try{send({event:'v19_class_cache',login:kLogin.toString(),ld:kLogin.add(0x38).readS32(),menu:okM?kMenu.toString():'null',md:okM?kMenu.add(0x38).readS32():-1});}catch(e){send({event:'v19_err',d:'dump:'+String(e)});}}
 else{send({event:'v19_class_cache',login:'NULL',menu:okM?kMenu.toString():'NULL'});}
 function matchDepth(w,klass){
  try{
   if(!klass||w.isNull())return -1;
   var t=w.add(0x10).readPointer();if(t.isNull())return -1;
   var td=t.add(0x38).readS32();var kd=klass.add(0x38).readS32();
   if(kd<0||kd>td)return -1;
   var sup=t.add(0x30).readPointer();if(sup.isNull())return -1;
   var kp=klass.add(0x30).readPointer();
   return sup.add(kd*8).readPointer().equals(kp)?kd:-1;
  }catch(e){return -1;}
 }
 var scans=0;
 function scan(){
  scans++;
  var cnt=0,chunks=null;
  try{cnt=base.add(0xb89c294).readS32();chunks=base.add(0xb89c280).readPointer();}catch(e){return;}
  if(cnt<1||chunks.isNull())return;
  var limit=Math.min(cnt,320000);
  var hist={},nHist={},samples=[],hostCands=0,maxN=0;
  for(var i=0;i<limit;i++){
   try{
    var ch=chunks.add((i>>>16)*8).readPointer();if(ch.isNull())continue;
    var obj=ch.add((i&65535)*24).readPointer();if(obj.isNull())continue;
    if((obj.add(8).readU32()&0x60000030))continue;
    var cont=obj.add(0x720).readPointer();if(cont.isNull())continue;
    var n=cont.add(0x728).readS32();if(n<1||n>64)continue;
    var arr=cont.add(0x720).readPointer();if(arr.isNull())continue;
    hostCands++;
    if(n>maxN)maxN=n;
    nHist['n'+n]=(nHist['n'+n]||0)+1;
    var page=obj.add(0x738).readS32();
    hist['p'+page]=(hist['p'+page]||0)+1;
    if(page>=-1&&page<=8&&samples.length<40){
     var kd5=0,slots=[];
     for(var j=0;j<n;j++){
      var wpt=arr.add(j*48+0x10).readPointer();
      if(wpt.isNull()){slots.push('null');continue;}
      var t=wpt.add(0x10).readPointer();
      var d=t.isNull()?-1:t.add(0x38).readS32();
      var isL=matchDepth(wpt,okL?kLogin:null);
      var isM=matchDepth(wpt,okM?kMenu:null);
      slots.push({d:d,l:isL,m:isM,a:wpt.toString()});
     }
     samples.push({a:obj.toString(),page:page,n:n,cont:cont.toString(),slots:slots});
    }
   }catch(e){}
  }
  send({event:'v19_stat',scan:scans,pool:cnt,hostCands:hostCands,maxN:maxN,nHist:nHist,hist:hist,samples:samples});
 }
 var timer=setInterval(function(){
  try{
   if(Date.now()-born<48000)return;
   if(scans>=2){clearInterval(timer);return;}
   scan();
  }catch(e){send({event:'v19_tick_err',d:String(e)});}
 },4000);
})();
"""

text = io.open(SRC, 'r', encoding='utf-8').read()
i = text.find(START)
if i < 0:
    print('POOL MARKER NOT FOUND'); sys.exit(1)
text = text[:i] + NEW
io.open(DST, 'w', encoding='utf-8', newline='\n').write(text)
print('written', DST, len(text))
