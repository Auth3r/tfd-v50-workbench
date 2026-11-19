# -*- coding: utf-8 -*-
"""v18：用真实的类 M1UILogin / M1UIGameStartMenu 在控件池里找“页面宿主”，
       找到后（在账号已装载之后）调用 showLogin(host, ticket) 把页面切到 3。"""
import io, sys

ROOT = r"E:\第二后裔\TFD发布端V50\TFD发布端V50"
SRC = ROOT + r"\offset_rework\old_bridge_v17_page_host.js"
DST = ROOT + r"\offset_rework\old_bridge_v18_page_switch.js"
START = "// __POOL_PROBE__"

NEW = r"""// __POOL_PROBE__
(function(){
 var fLogin=new NativeFunction(base.add(0x394d560),'pointer',[]);
 var fMenu=new NativeFunction(base.add(0x3913f80),'pointer',[]);
 var kLogin=null,kMenu=null;
 try{kLogin=fLogin();}catch(e){send({event:'v18_class_err',d:'login:'+String(e)});}
 try{kMenu=fMenu();}catch(e){send({event:'v18_class_err',d:'menu:'+String(e)});}
 try{
  if(kLogin){send({event:'v18_class',login:kLogin.toString(),ld:kLogin.add(0x38).readS32(),
                   menu:kMenu?kMenu.toString():'null',md:kMenu?kMenu.add(0x38).readS32():-1});}
 }catch(e){send({event:'v18_class_err',d:'dump:'+String(e)});}
 function matches(w,klass){
  try{
   if(!klass||w.isNull())return false;
   var t=w.add(0x10).readPointer();
   if(t.isNull())return false;
   var td=t.add(0x38).readS32();
   var kd=klass.add(0x38).readS32();
   if(kd<0||kd>td)return false;
   var sup=t.add(0x30).readPointer();
   if(sup.isNull())return false;
   var kp=klass.add(0x30).readPointer();
   return sup.add(kd*8).readPointer().equals(kp);
  }catch(e){return false;}
 }
 var scans=0;
 function scan(){
  scans++;
  var cnt=0,chunks=null;
  try{cnt=base.add(0xb89c294).readS32();chunks=base.add(0xb89c280).readPointer();}catch(e){return null;}
  if(cnt<1||chunks.isNull())return null;
  var limit=Math.min(cnt,320000);
  var host=null,cands=0,hostsWithLogin=0;
  for(var i=0;i<limit;i++){
   try{
    var ch=chunks.add((i>>>16)*8).readPointer();
    if(ch.isNull())continue;
    var obj=ch.add((i&65535)*24).readPointer();
    if(obj.isNull())continue;
    if((obj.add(8).readU32()&0x60000030))continue;
    var cont=obj.add(0x720).readPointer();
    if(cont.isNull())continue;
    var n=cont.add(0x728).readS32();
    if(n<1||n>64)continue;
    var arr=cont.add(0x720).readPointer();
    if(arr.isNull())continue;
    cands++;
    var hasLogin=false,hasMenu=false;
    for(var j=0;j<n;j++){
     var wpt=arr.add(j*48+0x10).readPointer();
     if(wpt.isNull())continue;
     if(!hasMenu&&matches(wpt,kMenu))hasMenu=true;
     if(!hasLogin&&matches(wpt,kLogin))hasLogin=true;
    }
    if(hasLogin){
     hostsWithLogin++;
     if(!host){
      host=obj;
      send({event:'v18_host',a:obj.toString(),cont:cont.toString(),page:obj.add(0x738).readS32(),
            n:n,hasMenu:hasMenu,scan:scans,limit:limit,pool:cnt});
     }
    }
   }catch(e){}
  }
  send({event:'v18_scan_done',scan:scans,pool:cnt,cands:cands,hostsWithLogin:hostsWithLogin});
  return host;
 }
 var timer=setInterval(function(){
  try{
   if(Date.now()-born<50000)return;
   if(globalThis.__v18done)return;
   if(scans>=6){clearInterval(timer);send({event:'v18_giveup',scans:scans});return;}
   var host=globalThis.__v18host||scan();
   if(!host)return;
   globalThis.__v18host=host;
   globalThis.__v18done=1;
   clearInterval(timer);
   var page=host.add(0x738).readS32();
   send({event:'v18_acting',a:host.toString(),page:page});
   if(page!==3){
    try{
     showLogin(host,ticket);
     send({event:'v18_showlogin_called',page:host.add(0x738).readS32()});
    }catch(e){send({event:'v18_showlogin_err',d:String(e)});}
   }
  }catch(e){send({event:'v18_tick_err',d:String(e)});}
 },2500);
})();
"""

text = io.open(SRC, 'r', encoding='utf-8').read()
i = text.find(START)
if i < 0:
    print('POOL MARKER NOT FOUND')
    sys.exit(1)
text = text[:i] + NEW
io.open(DST, 'w', encoding='utf-8', newline='\n').write(text)
print('written', DST, len(text))
