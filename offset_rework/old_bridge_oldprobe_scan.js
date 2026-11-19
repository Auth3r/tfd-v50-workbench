const LAUNCH = {"ticket": "DboLnXlmf-CjR3sdwPIcJ8L8Z6wHrHBQRk5gzPu5XSby4X75", "existing_character": true, "account_uid": "1", "run_id": "20261119T035039-93aa42", "field_boxes": [610000001, 610000002, 610000003, 610000004, 610000005, 610000006, 610000007, 610000008, 610000009, 610000010, 610000011, 610000012, 610000030, 610003001, 610003002, 610003003, 610003004, 610003005, 610003006, 610003007, 610003008]};
'use strict';
// Exact-build process-local bridge. Never supplies a character or edits game files.
const base = Process.mainModule.base;
const born = Date.now();
let requested = false;
let launcherAuthentication = false;
function report(event, fields = {}) { send({event, ...fields}); }
Interceptor.attach(base.add(0x3c3b910), {
  onEnter(a) { this.object = a[0]; },
  onLeave() { this.object.add(0xe0).writeU8(0); report('local_platform_config'); }
});
const ticketText = Memory.allocUtf16String(LAUNCH.ticket);
const ticket = Memory.alloc(16);
ticket.writePointer(ticketText);
ticket.add(8).writeS32(LAUNCH.ticket.length + 1);
ticket.add(12).writeS32(LAUNCH.ticket.length + 1);
// Native login screen callbacks 1449ca5f0 / 1449ca700 pass the visible ID
// to this same login entry. Keep every attempt bound to this launcher's ticket;
// never treat the visible ID as a password, new account, or character name.
Interceptor.attach(base.add(0x43ffcf0), {
  onEnter(a) {
    a[1] = ticket;
    requested = true;
    report('launcher_login_ticket_bound', {source: launcherAuthentication ? 'authenticated_launcher' : 'native_login_ui'});
  }
});
// The native login widget binds the account-loaded delegate in 1449d1420.
// Logging in before that widget exists loses the needs-creation transition.
// Reuse the launcher's authenticated account after the native login widget has
// bound its account-loaded delegates. Loading an account must not enter a map.
const lobbyClass = new NativeFunction(base.add(0x38ff0c0), 'pointer', []);
const widgetOwner = new NativeFunction(base.add(0x49f4ec0), 'pointer', ['pointer']);
const showLogin = new NativeFunction(base.add(0x49cd210), 'void', ['pointer', 'pointer']);
const login = new NativeFunction(base.add(0x43ffcf0), 'void', ['pointer', 'pointer']);
function authenticateLobby(widget, component) {
  if (requested || widget.add(0x738).readS32() !== 3) return false;
  // 14440549d broadcasts the account-loaded delegate at +430. Check its
  // actual bindings: an initialization hook can miss an earlier/inlined call.
  const delegates = component.add(0x430), count = delegates.add(8).readS32();
  if (delegates.readPointer().isNull() || count < 1 || count > 64) return false;
  if (widget.add(0x720).readPointer().isNull()) return false;
  if ([0x760, 0x768, 0x770, 0x778].some(offset => !widget.add(offset).readPointer().isNull())) return false;
  launcherAuthentication = true;
  try { login(component, ticket); }
  finally { launcherAuthentication = false; }
  report('native_launcher_account_login', {manual_start_required: true});
  return true;
}
let titlePrepared = false, titleOpening = false, titleScan = 0, nextTitleScan = 0;
function prepareTitle(component) {
  if (titlePrepared || requested || Date.now() < nextTitleScan) return;
  const count = base.add(0xb75c314).readS32();
  const chunks = base.add(0xb75c300).readPointer();
  if (count < 1 || count > 2000000 || chunks.isNull()) return;
  try{send({event:'probe_head',count:count,chunks:chunks.toString(),klass:lobbyClass().toString(),depth:lobbyClass().add(0x38).readS32(),klass30:lobbyClass().add(0x30).readPointer().toString()});}catch(e){send({event:'probe_head_err',d:String(e)});}
  const klass = lobbyClass(), depth = klass.add(0x38).readS32();
  if (depth < 0 || depth > 128) throw Error('Unexpected lobby class depth');
  const until = Math.min(titleScan + 4096, count);
  for (let index = titleScan; index < until; index++) {
    titleScan=index+1;
    if(titleScan>=count){titleScan=0;nextTitleScan=Date.now()+1000;}
    const chunk = chunks.add((index >>> 16) * 8).readPointer();
    if (chunk.isNull()) continue;
    const object = chunk.add((index & 65535) * 24).readPointer();
    if (object.isNull() || (object.add(8).readU32() & 0x60000030)) continue;
    const type = object.add(0x10).readPointer();
    if (type.isNull() || type.add(0x38).readS32() < depth) continue;
    const supers = type.add(0x30).readPointer();
    if (supers.isNull() || !supers.add(depth * 8).readPointer().equals(klass.add(0x30))) continue;
    try{const ow=widgetOwner(object);const f={};for(let o=0x700;o<=0x7c0;o+=8){const q=object.add(o).readU64();if(q.toString()!=='0x0')f['0x'+o.toString(16)]=q.toString();}send({event:'probe_cand',page:object.add(0x738).readS32(),owner:ow.toString(),owner830:ow.isNull()?'NULL':ow.add(0x830).readPointer().toString(),q:f});}catch(e){send({event:'probe_cand_err',d:String(e)});}
    const owner = widgetOwner(object);
    if (owner.isNull() || !owner.add(0x830).readPointer().equals(component)) continue;
    const page = object.add(0x738).readS32();
    if (page === 3) {
      if (authenticateLobby(object, component)) titlePrepared = true;
      return;
    }
    if (page >= 0) continue;
    if (page !== -1 || object.add(0x720).readPointer().isNull()) continue;
    if (Date.now() - born < 45000) return;
    // A logo, patch or platform dialog owns the UI until its native callback.
    if ([0x760, 0x768, 0x770, 0x778].some(offset => !object.add(offset).readPointer().isNull())) continue;
    if (titleOpening) return;
    titleOpening = true;
    showLogin(object, ticket);
    report('native_title_login_opened', {page: object.add(0x738).readS32(), manual_start_required: true});
    if (authenticateLobby(object, component)) titlePrepared = true;
    return;
  }
  if (titleScan >= count) { titleScan = 0; nextTitleScan = Date.now() + 1000; }
}
// 1449cdbf0 is the native lobby page transition. A return to page 3 starts
// a new title visit; the previous visit's one-shot latch must not suppress it.
Interceptor.attach(base.add(0x49cdbf0), {
  onEnter(a) { this.widget=a[0]; this.previous=a[0].add(0x738).readS32(); this.page=a[1].toInt32(); },
  onLeave() {
    try {
      if (this.page!==3 || this.previous===3 || this.widget.add(0x738).readS32()!==3 ||
          (this.widget.add(8).readU32()&0x60000030)) return;
      const owner=widgetOwner(this.widget);
      if (owner.isNull() || owner.add(0x830).readPointer().isNull()) return;
      requested=false; titlePrepared=false; titleOpening=false; titleScan=0; nextTitleScan=0;
      report('native_title_login_rearmed', {manual_start_required:true});
    } catch(e) { report('bridge_error', {description:String(e)}); }
  }
});
Interceptor.attach(base.add(0x4404fd0), {
  onEnter(a) { this.count = a[1].add(0x70).readS32(); },
  onLeave() {
    report('native_account_loaded', {character_count: this.count, creation_required: this.count === 0});
  }
});
Interceptor.attach(base.add(0x43fd5a0), {
  onEnter(a) { this.object = a[0]; },
  onLeave() {
    try {
      const obj = this.object;
      if ((obj.add(8).readU32() & 0x30) || obj.add(0x7a0).readPointer().isNull()) return;
      // Authenticate the launcher's account through the initialized native UI.
      // Every city/world request still comes from the player's Start Game click.
      prepareTitle(obj);
    } catch (e) { report('bridge_error', {description: String(e)}); }
  }
});
Interceptor.attach(base.add(0x4094990), {
  onEnter(a) { this.tid = a[1].toInt32(); },
  onLeave(r) { report('native_character_registered', {template_id: this.tid, result: r.toInt32()}); }
});
// Observe the actual version-failure branch; placeholder build text is not
// evidence of this notification. The observer never suppresses the dialog.
Interceptor.attach(base.add(0x3be07a0), {
  onEnter() { report('native_server_version_failure'); }
});
report('bridge_ready', {character_creation_bypassed: false, existing_character: LAUNCH.existing_character});

// Observe the original creation UI without choosing a character or invoking a
// button. These events distinguish a UI confirmation from a network request.
Interceptor.attach(base.add(0x4bd6f20), {
  onEnter() { report('native_creation_confirm_clicked'); },
  onLeave() { report('native_creation_confirm_returned'); }
});
Interceptor.attach(base.add(0x43ff750), {
  onLeave(row) {
    try { report('native_creation_default_set', {
      found: !row.isNull(), default_set_id: row.isNull() ? 0 : row.add(8).readS32()
    }); } catch(e) { report('creation_observer_error', {description: String(e)}); }
  }
});
Interceptor.attach(base.add(0x43feee0), {
  onEnter(a) {
    try {
      const row = a[0].add(0x108).readPointer();
      report('native_creation_submit', {default_set_id: row.isNull() ? 0 : row.add(8).readS32()});
    } catch(e) { report('creation_observer_error', {description: String(e)}); }
  }
});
Interceptor.attach(base.add(0x4dd1ad0), {
  onEnter(a) {
    try { report('native_creation_2006_send', {default_set_id:a[4].readS32()}); }
    catch(e) { report('creation_observer_error', {description: String(e)}); }
  }
});

// Complete the original account-loaded title callback when its platform readiness
// gate returns false. The native callback only changes the login widget state;
// selection, confirmation, character creation and Start Game remain native UI.
(()=>{'use strict';
const base=Process.mainModule.base,loads=new Map(),waits=new Map();
const platformOf=new NativeFunction(base.add(0x3c42b20),'pointer',[]);
const invoke=new NativeFunction(base.add(0x112d840),'void',['pointer']);
const live=p=>!p.isNull()&&!(p.add(8).readU32()&0x60000030);
function push(map,id,value){const rows=map.get(id)||[];rows.push(value);map.set(id,rows);}
function pop(map,id){const rows=map.get(id);if(rows){rows.pop();if(!rows.length)map.delete(id);}}
function top(map,id){const rows=map.get(id);return rows&&rows[rows.length-1];}
function safeDelegate(frame){
 const cb=frame.callback,w=frame.widget;
 if(!live(w)||!cb.readPointer().equals(base.add(0x4a05e90))||!cb.add(16).readPointer().isNull()||
    !cb.add(32).readPointer().equals(base.add(0x8fc0930)))return false;
 const index=cb.add(40).readS32(),serial=cb.add(44).readS32();
 const count=base.add(0xb75c314).readS32(),chunks=base.add(0xb75c300).readPointer();
 if(index<0||index>=count||count>2000000||serial<=0||chunks.isNull())return false;
 const chunk=chunks.add((index>>>16)*8).readPointer();if(chunk.isNull())return false;
 const item=chunk.add((index&65535)*24);
 return item.readPointer().equals(w)&&item.add(16).readS32()===serial&&
   !(item.add(8).readU32()&0x30200000)&&w.add(0xc).readS32()===index&&
   w.add(0x769).readU8()===1&&w.add(0x7a0).readU8()===frame.creation;
}
Interceptor.attach(base.add(0x4404fd0),{
 onEnter(a){
  const count=a[1].add(0x70).readS32();
  const authenticated=count>=0&&count<=10000&&a[1].readS64().toString()===String(LAUNCH.account_uid);
  // Original 144404fd0 also permits an explicit creation flag at component+130.
  const creation=Number(count===0||a[0].add(0x130).readU8()!==0);
  push(loads,this.threadId,{component:a[0],authenticated,creation});
 },onLeave(){pop(loads,this.threadId);}
});
Interceptor.attach(base.add(0x49d3e20),{
 onEnter(a){
  this.frame={widget:a[0],callback:a[1],blocked:false,gateSeen:false,invoked:false,eligible:false};
  push(waits,this.threadId,this.frame);
  try{
   const load=top(loads,this.threadId);
   if(!load||!load.authenticated||!live(a[0]))return;
   this.frame.creation=load.creation;
   this.frame.load=load;
   this.frame.candidate=safeDelegate(this.frame);
  }catch(e){send({event:'native_title_creation_error',description:String(e)});}
 },onLeave(){
  const frame=this.frame;pop(waits,this.threadId);
  if(!frame.eligible||!frame.gateSeen||frame.invoked)return;
  try{
   const platform=platformOf();
   if(platform.isNull()||platform.add(0xe0).readU8()!==0||!safeDelegate(frame))return;
   if(!frame.blocked&&!platform.add(0xf0).readPointer().isNull())return;
   // False readiness, or the absent offline platform service, returns without
   // invoking or queuing this callback (native wait function 1449d3e20).
   // Its stack-owned functor remains alive until our caller 1449d60c0 resumes.
   invoke(frame.callback);
   send({event:'native_title_creation_platform_released',creation_required:!!frame.creation,manual_start_required:true});
  }catch(e){send({event:'native_title_creation_error',description:String(e)});}
 }
});
// Observe the owner's original return. Calling this virtual getter again from
// the wait function's onEnter re-enters the UI while its dispatch is suspended.
Interceptor.attach(base.add(0x49f4ec0),{
 onEnter(a){const frame=top(waits,this.threadId);this.titleFrame=frame&&frame.candidate&&frame.widget.equals(a[0])?frame:null;},
 onLeave(owner){
  const frame=this.titleFrame;if(!frame)return;
  try{frame.eligible=live(owner)&&live(frame.load.component)&&owner.add(0x830).readPointer().equals(frame.load.component)&&safeDelegate(frame);}
  catch(e){send({event:'native_title_creation_error',description:String(e)});}
 }
});
Interceptor.attach(base.add(0x43e4760),{
 onLeave(result){const frame=top(waits,this.threadId);if(frame){frame.gateSeen=true;frame.blocked=(result.toInt32()&255)===0;}}
});
Interceptor.attach(base.add(0x112d840),{
 onEnter(a){const frame=top(waits,this.threadId);if(frame&&a[0].equals(frame.callback))frame.invoked=true;}
});
send({event:'native_title_creation_bridge_ready'});
})();

// Offline delivery of committed SQL character snapshots to the original
// ClientReceiveOwnedCharacters implementation. This is a local bridge, not
// an implementation of Unreal's dedicated-server RPC transport.
(() => {
 'use strict';
 const image=Process.mainModule.base;
 const accountOf=new NativeFunction(image.add(0x441f8a0),'pointer',['pointer']);
 const applyCharacters=new NativeFunction(image.add(0x441b2d0),'void',['pointer','pointer']);
 const rowBuffer=Memory.alloc(48),arrayBuffer=Memory.alloc(16);
 arrayBuffer.writePointer(rowBuffer);arrayBuffer.add(8).writeS32(1);arrayBuffer.add(12).writeS32(1);
 let readyKey=null,failed=false;const pending=new Map(),applied=new Map();
 const emit=(event,fields={})=>send({event,...fields});
 function unavailable(){if(readyKey!==null){readyKey=null;applied.clear();emit('native_character_progress_unavailable');}}
 function integer(value,low,high){return Number.isInteger(value)&&value>=low&&value<=high;}
 function receive(){recv('character-progress',message=>{
  try{
   const p=message.payload;
   if(p.account_uid!==LAUNCH.account_uid||!Array.isArray(p.characters)||p.characters.length>64)throw Error('Snapshot account/bounds mismatch');
   for(const s of p.characters){
    if(!/^[1-9][0-9]{0,18}$/.test(s.uid)||!/^[0-9]{1,19}$/.test(s.exp)||
       !integer(s.tid,1,2147483647)||!integer(s.level,1,40)||!integer(s.max,s.level,40)||
       !integer(s.reset,0,2147483647)||!integer(s.revision,0,Number.MAX_SAFE_INTEGER))throw Error('Invalid character snapshot');
    const old=pending.get(s.uid);if(!old||s.revision>=old.revision)pending.set(s.uid,s);
   }
  }catch(e){failed=true;unavailable();emit('native_character_progress_error',{error:String(e)});}
  receive();
 });}
 receive();
 Interceptor.attach(image.add(0x43fd5a0),{
  onEnter(args){this.self=args[0];},onLeave(){
   if(failed)return;
   try{
    const self=this.self;
    if((self.add(8).readU32()&0x30)||!self.readPointer().add(0x6c0).readPointer().equals(image.add(0x441b2c0))){unavailable();return;}
    const state=self.add(0x98).readPointer();
    if(state.isNull()||state.add(0x108).readU8()!==3){unavailable();return;}
    const account=accountOf(self);if(account.isNull()){unavailable();return;}
    const owned=account.add(0x2e0).readPointer();if(owned.isNull()){unavailable();return;}
    const uid=owned.add(0x30).readS64().toString(),tid=owned.add(0x38).readS32();
    if(uid==='0'||owned.add(0x78).readS32()<1){unavailable();return;}
    const key=self.toString()+':'+uid;
    if(key!==readyKey){readyKey=key;applied.clear();emit('native_character_progress_ready',{uid,tid});}
    const s=pending.get(uid);if(!s)return;
    if(s.tid!==tid)throw Error('Owned character template mismatch');
    if(s.revision<(applied.get(uid)??-1)){pending.delete(uid);return;}
    rowBuffer.writeByteArray(new Uint8Array(48));rowBuffer.writeS64(int64(s.uid));
    rowBuffer.add(8).writeS32(s.tid);rowBuffer.add(16).writeS64(int64(s.exp));
    rowBuffer.add(24).writeS32(s.level);rowBuffer.add(28).writeS32(s.max);rowBuffer.add(32).writeS32(s.reset);
    applyCharacters(self,arrayBuffer);
    if(owned.add(0x78).readS32()!==s.level||owned.add(0x80).readS64().toString()!==s.exp||
       owned.add(0xac).readS32()!==s.max||owned.add(0xa8).readS32()!==s.reset)throw Error('Native character refresh did not match committed snapshot');
    pending.delete(uid);applied.set(uid,s.revision);
    emit('native_character_progress_applied',{uid,tid,revision:s.revision,level:s.level,exp:s.exp,max:s.max,reset:s.reset});
   }catch(e){failed=true;unavailable();emit('native_character_progress_error',{error:String(e)});}
  }
 });
})();

// Apply committed equipment on the game thread; confirm the pawn's equipment,
// not merely the account cache that the stock handler updates first.
(() => {
 'use strict';const image=Process.mainModule.base;
 const accountOf=new NativeFunction(image.add(0x441f8a0),'pointer',['pointer']);
 const componentOf=new NativeFunction(image.add(0x3c3f670),'pointer',['pointer']);
 const wornAt=new NativeFunction(image.add(0x40a2290),'pointer',['pointer','uint8']);
 const findItem=new NativeFunction(image.add(0x40a0f90),'pointer',['pointer','uint8','int64']);
 const applyChanges=new NativeFunction(image.add(0x4445e80),'void',['pointer','pointer']);
 const playerInterfaceClass=new NativeFunction(image.add(0x3641950),'pointer',[]);
 const playerInterfaceOf=new NativeFunction(image.add(0x51f1100),'pointer',['pointer','pointer']);
 const reactorElement=new NativeFunction(image.add(0x4164dc0),'uint8',['pointer']);
 const slots=[0,1,2,9,10,11,12,13,90],componentSlots=[9,10,11,12,13];
 const rowBuffer=Memory.alloc(16*slots.length),notice=Memory.alloc(24);
 notice.writeS64(int64(LAUNCH.account_uid));notice.add(8).writePointer(rowBuffer);notice.add(20).writeS32(slots.length);
 let snapshot=null,pending=false,revision=-1,key=null,failed=false,initializePawn=true,lastAttempt=-Infinity;
 function receive(){recv('equipment-selection',m=>{try{
  const p=m.payload;if(!/^(0|[1-9][0-9]{0,18})$/.test(p.character_uid)||BigInt(p.character_uid)>9223372036854775807n)throw Error('Missing persisted character identity');if(p.account_uid!==LAUNCH.account_uid||!Number.isSafeInteger(p.revision)||p.revision<0||!Array.isArray(p.wearing)||p.wearing.length>slots.length)throw Error('Selection envelope mismatch');
  const seenSlots=new Set(),seenItems=new Set();
  for(const r of p.wearing){if(!slots.includes(r.slot)||!/^([1-9][0-9]{0,18})$/.test(r.uid)||BigInt(r.uid)>9223372036854775807n||seenSlots.has(r.slot)||seenItems.has(r.uid))throw Error('Invalid wearing snapshot');seenSlots.add(r.slot);seenItems.add(r.uid);}
  if(p.character_uid==='0'){
   // Before procedure 2006 the original prologue owns its temporary loadout.
   snapshot=null;pending=false;revision=-1;
   send({event:'native_equipment_selection_deferred',reason:'tutorial_character_not_committed'});
  }else if(p.revision>=revision){revision=p.revision;snapshot=p;pending=true;lastAttempt=-Infinity;}
 }catch(e){failed=true;send({event:'native_equipment_selection_error',error:String(e)});}receive();});}receive();
 function worn(inv,slot){const item=wornAt(inv,slot);return item.isNull()?'0':item.add(0x40).readS64().toString();}
 function pawnState(pawn){
  // IM1OnlineServicePlayerInterface can exist before the tutorial pawn is ready.
  // Its stock +0x30 handler returns immediately unless the pawn has authority.
  if(pawn.add(0x108).readU8()!==3)return null;
  const player=playerInterfaceOf(pawn,playerInterfaceClass());if(player.isNull())return null;
  if(!player.equals(pawn.add(0xd10))||!player.readPointer().add(0x30).readPointer().equals(image.add(0x3e8c490)))throw Error('Unexpected player equipment interface');
  const equipment=player.add(0x440).readPointer(),weapons=player.add(0x450).readPointer(),refresh=player.add(0x458).readPointer();
  if(equipment.isNull()||weapons.isNull()||refresh.isNull())return null;
  if(!equipment.add(0x98).readPointer().equals(pawn)||!weapons.add(0x4f0).readPointer().equals(pawn)||equipment.add(0xe8).readPointer().isNull())return null;
  const rows=equipment.add(0xd0).readPointer(),count=equipment.add(0xd8).readS32();
  if(rows.isNull()||count===0)return null;
  if(count<0||count>32)throw Error('Invalid player equipment slot count');
  const map=new Map();for(let i=0;i<count;i++){const row=rows.add(i*40),slot=row.add(32).readU8();if(map.has(slot))throw Error('Duplicate player equipment slot');map.set(slot,row);}
  if(componentSlots.some(s=>!map.has(s)))return null;
  return {equipment,rows:map};
 }
 function pawnMatches(state,desired,inv){
  for(const slot of componentSlots){
   const row=state.rows.get(slot),uid=desired.get(slot)||'0',tid=row.add(8).readS32();
   if(uid==='0'){if(tid!==0)return false;continue;}
   const item=findItem(inv,2,int64(uid));
   if(item.isNull()||row.readU64().toString()!==String(item.add(0xc).readU32())||tid!==item.add(0x48).readS32())return false;
   if(slot===9&&state.equipment.add(0xf8).readU8()!==reactorElement(item))return false;
  }
  return true;
 }
 Interceptor.attach(image.add(0x43fd5a0),{onEnter(a){this.self=a[0];},onLeave(){
  if(failed)return;
  try{
   const self=this.self,state=self.add(0x98).readPointer();
   if(state.isNull()||state.add(0x108).readU8()!==3){key=null;return;}
   const account=accountOf(self);if(account.isNull()||account.add(0x28).readS64().toString()!==LAUNCH.account_uid)return;
   const pc=self.add(0x7a0).readPointer();if(pc.isNull())return;const pawn=pc.add(0x298).readPointer();if(pawn.isNull())return;
   let inv=account.add(0x318).readPointer();if(inv.isNull())inv=account.add(0x310).readPointer();if(inv.isNull())return;
   const component=componentOf(self);if(component.isNull()||!component.readPointer().add(0x3e0).readPointer().equals(image.add(0x4445e70)))throw Error('Unexpected equipment component');
   const current=self.toString()+':'+inv.toString()+':'+pawn.toString();
   if(key!==current){key=current;snapshot=null;pending=false;initializePawn=true;lastAttempt=-Infinity;send({event:'native_equipment_selection_ready'});return;}
   if(snapshot===null)return;
   const p=snapshot,selected=account.add(0x2e0).readPointer();
   // A late response for a saved character must never overwrite a tutorial or
   // preview pawn, even when account and inventory pointers have not changed.
   if(selected.isNull()||selected.add(0x30).readS64().toString()!==p.character_uid)return;
   const desired=new Map(p.wearing.map(r=>[r.slot,r.uid]));
   for(const r of p.wearing)if(findItem(inv,2,int64(r.uid)).isNull())return;
   const actual=pawnState(pawn);if(actual===null)return;
   const accountMatches=slots.every(slot=>worn(inv,slot)===(desired.get(slot)||'0'));
   const actorMatches=pawnMatches(actual,desired,inv);
   if(!pending&&accountMatches&&actorMatches)return;
   // Wait for the new server snapshot during a player-initiated equipment swap.
   if(!pending&&!accountMatches)return;
   const now=Date.now();if(now-lastAttempt<500)return;
   const repair=initializePawn||!actorMatches,changes=[];
   for(const slot of slots){const uid=desired.get(slot)||'0';if(worn(inv,slot)!==uid||(repair&&uid!=='0'))changes.push({slot,uid});}
   // Retry a deferred stock application after component initialization/rebuild.
   if(changes.length){
    lastAttempt=now;rowBuffer.writeByteArray(new Uint8Array(16*slots.length));
    changes.forEach((r,i)=>{rowBuffer.add(i*16).writeS64(int64(r.uid));rowBuffer.add(i*16+8).writeU8(r.slot);});
    notice.add(16).writeS32(changes.length);applyChanges(component,notice);
   }
   const after=pawnState(pawn);
   if(after===null||slots.some(slot=>worn(inv,slot)!==(desired.get(slot)||'0'))||!pawnMatches(after,desired,inv)){pending=true;return;}
   pending=false;const initialized=initializePawn;initializePawn=false;
   send({event:'native_equipment_selection_applied',revision:p.revision,changes:changes.length,pawn_initialized:initialized,pawn_equipment_verified:true,reactor_uid:desired.get(9)||'0',wearing:p.wearing});
  }catch(e){failed=true;send({event:'native_equipment_selection_error',error:String(e)});}
 }});
})();

// Complete local inventory notifications whose stock RPC route requires a
// dedicated world. Call the original implementation only if it was not called
// synchronously by that route. SQL mutations remain owned by the local service.
(() => {
 'use strict';
 const image=Process.mainModule.base;
 const componentOf=new NativeFunction(image.add(0x44b9720),'pointer',['pointer']);
 const accountOf=new NativeFunction(image.add(0x441f8a0),'pointer',['pointer']);
 const netMode=new NativeFunction(image.add(0x6ddb820),'int',['pointer']);
 const runeVtable=image.add(0x9a86308),consumableVtable=image.add(0x9a64528);
 function local(self,vtable){
  if(self.isNull()||!self.readPointer().equals(vtable))return false;
  const component=componentOf(self);if(component.isNull())return false;
  const pc=component.add(0x98).readPointer();
  if(pc.isNull()||pc.add(0x108).readU8()!==3||netMode(pc)!==0)return false;
  const account=accountOf(component);
  return !account.isNull()&&account.add(0x28).readS64().toString()===LAUNCH.account_uid;
 }
 function array(p,max){
  const n=p.add(8).readS32();return n>=0&&n<=max&&(n===0||!p.readPointer().isNull());
 }
 function owner(p){
  return p.readS64().toString()===LAUNCH.account_uid&&[2,5].includes(p.add(8).readU8())&&
   p.add(12).readS32()>0&&array(p.add(0x18),64)&&array(p.add(0x28),64)&&array(p.add(0x38),256);
 }
 function install(name,wrapper,impl,observed,vtable,types,check){
  const active=new Map(),apply=new NativeFunction(image.add(impl),'void',types);
  for(const offset of observed)Interceptor.attach(image.add(offset),{onEnter(a){
   const stack=active.get(this.threadId)||[];
   for(const call of stack)if(call.args[0].equals(a[0]))call.delivered=true;
  }});
  Interceptor.attach(image.add(wrapper),{
   onEnter(a){
    this.call=null;
    try{
     if(!local(a[0],vtable)||!check(a))return;
     const args=types.map((type,i)=>type==='int'||type==='uint8'?a[i].toInt32():a[i]);
     this.call={args,delivered:false};
     const stack=active.get(this.threadId)||[];stack.push(this.call);active.set(this.threadId,stack);
    }catch(e){send({event:'native_inventory_bridge_error',operation:name,phase:'capture',error:String(e)});}
   },
   onLeave(){
    const call=this.call;if(!call)return;
    const stack=active.get(this.threadId)||[];stack.splice(stack.lastIndexOf(call),1);
    if(!stack.length)active.delete(this.threadId);
    try{
     if(!call.delivered&&local(call.args[0],vtable)){
      apply(...call.args);
      send({event:'native_inventory_reply_delivered',operation:name});
     }
    }catch(e){send({event:'native_inventory_bridge_error',operation:name,phase:'delivery',error:String(e)});}
   }
  });
 }
 install('rune_loadout',0x36efa30,0x44982e0,[0x44982e0],runeVtable,['pointer','pointer'],a=>owner(a[1]));
 install('rune_bundle',0x4497f10,0x4498c30,[0x4498c30],runeVtable,['pointer','pointer'],a=>{
  if(!array(a[1],1024))return false;
  const data=a[1].readPointer(),n=a[1].add(8).readS32();
  for(let i=0;i<n;i++)if(!owner(data.add(i*80)))return false;
  return true;
 });
 install('rune_selection',0x4498120,0x4498ca0,[0x4498ca0],runeVtable,['pointer','pointer'],a=>array(a[1],64));
 install('experience_item',0x4433990,0x4433b80,[0x4433b80,0x4433bd0],consumableVtable,
  ['pointer','pointer','int','uint8','pointer'],a=>
   a[1].readS32()>0&&a[2].toInt32()>0&&[2,5,12].includes(a[3].toInt32())&&array(a[4],64));

 // These notifications use ProcessEvent directly, rather than a separate RPC
 // wrapper. Its UFunction native entry (+0xd8) identifies the exact operation.
 // Complete a skipped local dispatch once, on the same thread and stack frame.
 const cosmeticVtable=image.add(0x9a60570),cosmeticActive=new Map();
 const accountPayload=p=>!p.isNull()&&p.readS64().toString()===LAUNCH.account_uid;
 const loadoutPayload=p=>accountPayload(p)&&p.add(8).readS32()>0&&
  p.add(12).readS32()>=0&&p.add(12).readS32()<p.add(16).readS32()&&p.add(16).readS32()<=64;
 const boundPayload=p=>accountPayload(p)&&p.add(8).readS32()>0&&array(p.add(16),4096)&&array(p.add(32),4096);
 const cosmetics=[
  ['character_cosmetic_loadout',0x36c0270,0x4440550,loadoutPayload],
  ['fellow_cosmetic_loadout',0x36c0180,0x4440880,loadoutPayload],
  ['skin_paints',0x36c0630,0x443f430,p=>accountPayload(p)&&[8,24,40,56,72,88,104].every(o=>array(p.add(o),4096))],
  ['character_paints',0x36c04d0,0x44412e0,p=>accountPayload(p)&&array(p.add(8),4096)],
  ['cosmetic_inventory',0x36c0360,0x44415d0,p=>accountPayload(p)&&[5,12,16].includes(p.add(8).readU8())&&p.add(12).readS32()>0&&array(p.add(16),4096)],
  ['skin_bound_dyes',0x36c0bf0,0x443f250,boundPayload],
  ['character_bound_dyes',0x36c0a90,0x443f370,boundPayload]
 ].map(([name,exec,impl,check])=>({name,exec:image.add(exec),impl,check,apply:new NativeFunction(image.add(impl),'void',['pointer','pointer'])}));
 for(const spec of cosmetics)Interceptor.attach(image.add(spec.impl),{onEnter(a){
  // UHT copies reflected structures onto its own stack. Match the innermost
  // operation and service; payload pointer identity is not preserved.
  const stack=cosmeticActive.get(this.threadId)||[];
  for(let i=stack.length-1;i>=0;i--)if(stack[i].spec===spec&&stack[i].self.equals(a[0])){
   stack[i].delivered=true;break;
  }
 }});
 Interceptor.attach(image.add(0x51d3f10),{
  onEnter(a){
   this.cosmeticCall=null;
   try{
    if(a[0].isNull()||!a[0].readPointer().equals(cosmeticVtable)||a[1].isNull())return;
    const entry=a[1].add(0xd8).readPointer(),spec=cosmetics.find(s=>s.exec.equals(entry));
    if(!spec||!local(a[0],cosmeticVtable)||!spec.check(a[2]))return;
    const call={self:a[0],payload:a[2],spec,delivered:false};this.cosmeticCall=call;
    const stack=cosmeticActive.get(this.threadId)||[];stack.push(call);cosmeticActive.set(this.threadId,stack);
   }catch(e){send({event:'native_inventory_bridge_error',operation:'cosmetics',phase:'capture',error:String(e)});}
  },
  onLeave(){
   const call=this.cosmeticCall;if(!call)return;
   const stack=cosmeticActive.get(this.threadId)||[];stack.splice(stack.lastIndexOf(call),1);
   if(!stack.length)cosmeticActive.delete(this.threadId);
   try{
    if(!call.delivered&&local(call.self,cosmeticVtable)){
     call.spec.apply(call.self,call.payload);
     send({event:'native_inventory_reply_delivered',operation:call.spec.name});
    }
   }catch(e){send({event:'native_inventory_bridge_error',operation:call.spec.name,phase:'delivery',error:String(e)});}
  }
 });
 send({event:'native_inventory_bridge_ready'});
})();

// Native M1BattleZoneWorldSettings::BeginPlay (143fd5050) assigns its
// VerticalLimitZ to the shared world's +2d4. In the local Standalone field,
// multiple zone levels are loaded together, so the last zone can lower the
// ceiling below another zone's normal terrain. Use the highest ceiling of the
// loaded zones. Original out-of-bounds volumes and countdown logic still run.
(() => {
 'use strict';const base=Process.mainModule.base;
 const worldOf=new NativeFunction(base.add(0x6dbfcf0),'pointer',['pointer']);
 const settingsOf=new NativeFunction(base.add(0x7939350),'pointer',['pointer','uint8']);
 const ceilings=new Map();
 Interceptor.attach(base.add(0x3fdc770),{
  onEnter(args){this.actor=args[0];},
  onLeave(){
   try{
    const actor=this.actor;
    if(!actor.readPointer().equals(base.add(0x9658ab0)))return;
    const limit=actor.add(0x258).readFloat();
    if(!Number.isFinite(limit)||Math.abs(limit)<=1e-8)return;
    const world=worldOf(actor);if(world.isNull())return;
    const settings=settingsOf(world,1);if(settings.isNull())return;
    const key=world.toString()+':'+world.add(0xc).readU32()+':'+settings.toString();
    const previous=ceilings.get(key),ceiling=previous===undefined?limit:Math.max(previous,limit);
    ceilings.set(key,ceiling);const nativeLimit=settings.add(0x2d4).readFloat();
    if(nativeLimit!==ceiling){
     settings.add(0x2d4).writeFloat(ceiling);
     send({event:'native_local_world_ceiling_corrected',zone_limit:limit,previous_world_limit:nativeLimit,world_limit:ceiling});
    }
   }catch(e){send({event:'native_local_world_ceiling_error',error:String(e)});}
  }
 });
})();

// Resume only an original mission-success callback discarded by the absent
// backend. SQL commits first; the original callback emits normal quest events.
// Build c0147688: 14422e8d0 -> 1444c1700 -> 14422f6f0 -> 14422ece0.
(() => {
 'use strict';
 const image=Process.mainModule.base;
 const finish=new NativeFunction(image.add(0x422f6f0),'void',['pointer','pointer']);
 const pending=new Map(),ready=[];
 function actor(index,serial){
  if(!Number.isInteger(index)||index<0||index>=image.add(0xb75c314).readS32()||!serial)return null;
  const chunks=image.add(0xb75c300).readPointer();if(chunks.isNull())return null;
  const chunk=chunks.add((index>>>16)*8).readPointer();if(chunk.isNull())return null;
  const entry=chunk.add((index&65535)*24);
  if(entry.add(16).readU32()!==serial||(entry.add(8).readU32()&0x30200000))return null;
  const value=entry.readPointer();return value.isNull()?null:value;
 }
 Interceptor.attach(image.add(0x44c1700),{onEnter(a){try{
  const backend=a[0].add(0x188).readPointer();if(backend.isNull()||!backend.add(0x30).readPointer().isNull())return;
  const d=a[2];
  if(!d.readPointer().equals(image.add(0x4236d90))||!d.add(16).readPointer().isNull()||
     !d.add(32).readPointer().equals(image.add(0x8fc0930)))return;
  const index=d.add(40).readS32(),serial=d.add(44).readU32(),owner=actor(index,serial);if(owner===null)return;
  const q=a[1],n=q.add(8).readS32(),accounts=q.readPointer();
  if(n!==1||accounts.isNull()||accounts.readS64().toString()!==LAUNCH.account_uid){
   send({event:'native_mission_settlement_rejected',reason:'Only the bound local player can settle this mission'});return;
  }
  const request={account_uid:LAUNCH.account_uid,mission_id:q.add(16).readS32(),clear_time_ms:q.add(20).readS32(),
   unique_entry_count:q.add(24).readU8(),clear_score:q.add(28).readS32(),grade:accounts.add(8).readS32()};
  const timer=owner.add(0x628).readU64().toString();
  const receipt=[LAUNCH.run_id,index,serial,request.mission_id,request.clear_time_ms,timer].join(':');
  if(pending.has(receipt))return;
  pending.set(receipt,{index,serial,request,timer,lastAttempt:Date.now(),attempts:1,retry:true});
  send({event:'native_mission_settlement_requested',receipt,request});
 }catch(e){send({event:'native_mission_settlement_error',phase:'capture',error:String(e)});}}});
 function receive(){recv('mission-settlement',m=>{try{
  const p=m.payload,entry=pending.get(p.receipt);
  if(p.account_uid!==LAUNCH.account_uid||!entry)return;
  if(p.ok){if(!entry.committed){entry.committed=true;ready.push(p.receipt);}}
  else{entry.retry=!!p.retry;entry.lastAttempt=Date.now();send({event:'native_mission_settlement_waiting',mission_id:entry.request.mission_id,reason:p.reason});}
 }catch(e){send({event:'native_mission_settlement_error',phase:'response',error:String(e)});}receive();});}receive();
 Interceptor.attach(image.add(0x43fd5a0),{onLeave(){
  for(const [receipt,e] of pending){
   // Keep receipts only while their actor and attempt are current. This also
   // releases completed entries after the original callback clears its timer.
   const owner=actor(e.index,e.serial);
   if(owner===null||owner.add(0x628).readU64().toString()!==e.timer){pending.delete(receipt);continue;}
   // Loading the progress bridge or a delayed response may exceed 30 seconds.
   // Retry the same idempotent SQL receipt with bounded backoff, not a new award.
   if(e.retry&&!e.committed&&Date.now()-e.lastAttempt>=Math.min(1000*e.attempts,8000)){
    e.lastAttempt=Date.now();e.attempts++;send({event:'native_mission_settlement_requested',receipt,request:e.request});
   }
  }
  while(ready.length){const receipt=ready.shift(),e=pending.get(receipt);if(!e||e.applied)continue;
   try{
    const owner=actor(e.index,e.serial);
    if(owner===null){pending.delete(receipt);send({event:'native_mission_settlement_stale',receipt});continue;}
    // A new mission attempt on the same actor cannot receive an old result.
    if(owner.add(0x628).readU64().toString()!==e.timer){pending.delete(receipt);send({event:'native_mission_settlement_stale',receipt});continue;}
    const weak=Memory.alloc(8),res=Memory.alloc(32),row=Memory.alloc(56);
    weak.writeS32(e.index);weak.add(4).writeU32(e.serial);res.writeByteArray(new Uint8Array(32));row.writeByteArray(new Uint8Array(56));
    row.writeS64(int64(LAUNCH.account_uid));res.writeS32(1);res.add(8).writePointer(row);res.add(16).writeS32(1);res.add(20).writeS32(1);
    e.applied=true;finish(weak,res);
    send({event:'native_mission_settlement_applied',receipt,mission_id:e.request.mission_id});
   }catch(err){send({event:'native_mission_settlement_error',phase:'callback',error:String(err)});}
  }
 }});
})();

// c0147688: an orphaned assassination goal can keep the Iron Heart task pending
// after every scheduled subtask succeeded. Reconcile that goal only; the native
// task scheduler, final interactions and SQL settlement continue normally.
(() => {
 'use strict';
 const base=Process.mainModule.base;
 const nameOf=new NativeFunction(base.add(0x5009ed0),'pointer',['pointer','pointer']);
 const freeString=new NativeFunction(base.add(0x110b460),'void',['pointer']);
 const enableTick=new NativeFunction(base.add(0x787d080),'void',['pointer','uint8']);
 function name(p){const s=Memory.alloc(16);nameOf(p,s);try{const n=s.add(8).readS32();return n>0&&n<128?s.readPointer().readUtf16String(n-1):'';}finally{freeString(s);}}
 function finalTask(task){
  if(task.isNull()||!task.readPointer().equals(base.add(0x98f78e8))||task.add(0x678).readS32()!==21)return false;
  const definition=task.add(0x670).readPointer();
  return !definition.isNull()&&name(definition.add(0x98))==='DestructionIronHeartD1_17';
 }
 function childrenSucceeded(task){
  const children=task.add(0xa08).readPointer(),count=task.add(0xa10).readS32();
  if(count!==4||children.isNull())return false;
  let bosses=0,occupations=0;
  for(let i=0;i<count;i++){
   const child=children.add(i*8).readPointer();
   if(child.isNull()||child.add(0x468).readU8()!==3||child.add(0x2a0).readU8()!==3)return false;
   const components=child.add(0x380).readPointer(),n=child.add(0x388).readS32();
   if(n!==1||components.isNull())return false;
   const component=components.readPointer();if(component.isNull())return false;
   if(component.readPointer().equals(base.add(0x99241f0))){
    const kills=component.add(0x190).readPointer();
    if(component.add(0x198).readS32()!==1||kills.isNull()||kills.add(8).readS32()!==520130016||kills.add(0x2c).readS32()!==1||kills.add(0x28).readS32()<1)return false;
    bosses++;
   }else{
    // Only successfully occupied sites count; no unfinished timer is changed.
    if(!component.add(0x188).readU8()||component.add(0x184).readFloat()<=0)return false;
    occupations++;
   }
  }
  return bosses===1&&occupations===3;
 }
 function reconciliable(goal){
  if(goal.add(0x278).readU8()||!goal.add(0x270).readPointer().isNull())return false;
  const task=goal.add(0x268).readPointer();
  return finalTask(task)&&task.add(0x468).readU8()===2&&childrenSucceeded(task);
 }
 Interceptor.attach(base.add(0x4315eb0),{onEnter(args){try{
  const goal=args[0];if(!reconciliable(goal))return;
  goal.add(0x278).writeU8(1);
  send({event:'native_fortress_orphan_goal_reconciled',mission_id:620510114,boss_id:520130016});
 }catch(error){send({event:'native_fortress_goal_error',error:String(error)});}}});
 // The Iron Heart override (430b1c0) disables ticking as soon as state becomes
 // Completed. The base completion function only queues its success phase AFTER
 // that override returns, so the following tick never drains the success event
 // and next-task delegates. Restore the original tick only for this completed
 // fight with a still-pending success phase; never mark an unfinished task won.
 Interceptor.attach(base.add(0x3fba2d0),{
  onEnter(args){this.task=args[0];},
  onLeave(){try{
   const task=this.task;
   if(!finalTask(task)||task.add(0x468).readU8()!==3||task.add(0x2a0).readU8()!==3||
      task.add(0x270).readU8()!==1||task.add(0x271).readU8()!==1||!childrenSucceeded(task))return;
   enableTick(task.add(0x28),1);
   send({event:'native_fortress_success_tick_restored',mission_id:620510114,boss_id:520130016});
  }catch(error){send({event:'native_fortress_goal_error',phase:'success_tick',error:String(error)});}}
 });
})();

// Exact build c0147688. Add the missing local material request after the native
// field-object trigger. Keep original spawn, collision, pickup and UI effects.
(() => {
 'use strict';
 const b=Process.mainModule.base,zero=ptr(0),boxes=new Set(LAUNCH.field_boxes||[]);
 const fn=(r,result,args)=>new NativeFunction(b.add(r),result,args);
 // Both the controller and the box are Actors, not ActorComponents.
 const worldOf=fn(0x6dbfcf0,'pointer',['pointer']),netMode=fn(0x6ddb820,'int',['pointer']);
 const gameState=fn(0x71eaea0,'pointer',['pointer']),accountOf=fn(0x441f8a0,'pointer',['pointer']);
 const stateClass=fn(0x34f34a0,'pointer',[]),dropClass=fn(0x34817d0,'pointer',[]);
 const serialFor=fn(0x51ec760,'uint',['pointer','int']);
 const makeContext=fn(0x43e2d40,'void',['pointer','pointer','pointer']);
 const spawn=fn(0x3dd8210,'void',['pointer','pointer','pointer']);
 const pending=new Map(),issued=new Map();let resumingOid=null;
 const report=(event,fields={})=>send({event,...fields});
 function isA(object,klass){
  if(object.isNull()||klass.isNull())return false;
  const type=object.add(0x10).readPointer(),depth=klass.add(0x38).readS32();
  return depth>=0&&depth<128&&!type.isNull()&&type.add(0x38).readS32()>=depth&&
   type.add(0x30).readPointer().add(depth*8).readPointer().equals(klass.add(0x30));
 }
 function entry(index){
  if(index<0||index>=b.add(0xb75c314).readS32())return null;
  const chunks=b.add(0xb75c300).readPointer();if(chunks.isNull())return null;
  const chunk=chunks.add((index>>>16)*8).readPointer();return chunk.isNull()?null:chunk.add((index&65535)*24);
 }
 function weak(object){
  if(object.isNull())throw Error('Missing native object');
  const index=object.add(12).readS32(),e=entry(index);
  if(e===null||!e.readPointer().equals(object)||(e.add(8).readU32()&0x30200000))throw Error('Invalid native object');
  return {index,serial:serialFor(zero,index)};
 }
 const key=w=>w.index+':'+w.serial;
 function resolve(w){
  const e=entry(w.index);
  if(e===null||!w.serial||e.add(16).readU32()!==w.serial||(e.add(8).readU32()&0x30200000))return null;
  const p=e.readPointer();return p.isNull()?null:p;
 }
 function local(pc){
  if(pc.isNull()||netMode(pc)!==0)return null;
  const component=pc.add(0x830).readPointer();if(component.isNull())return null;
  const account=accountOf(component);if(account.isNull()||account.add(0x28).readS64().toString()!==LAUNCH.account_uid)return null;
  const world=worldOf(pc);if(world.isNull())return null;
  const mode=world.add(0x158).readPointer();if(mode.isNull())return null;
  const service=mode.add(0x350).readPointer();if(service.isNull())return null;
  const backend=service.add(0x188).readPointer();
  // Standalone also constructs DedicatedToGS and its loopback proxy.
  // Account binding + native NetMode=Standalone identify this local world.
  return backend.isNull()?null:world;
 }
 function request(action,receipt,e){
  e.last=Date.now();e.attempts++;
  report(action==='drop'?'native_field_drop_requested':'native_field_pickup_requested',{
   receipt,request:{account_uid:LAUNCH.account_uid,world:key(e.world),...(action==='drop'?{field_tid:e.tid}:{})}});
 }
 Interceptor.attach(b.add(0x3dc2090),{onEnter(a){try{
  const pc=a[1],world=local(pc);if(world===null)return;
  const actor=a[0].add(0x98).readPointer();if(actor.isNull()||!worldOf(actor).equals(world))return;
  const tid=actor.add(0x458).readS32();if(!boxes.has(tid))return;
  const state=gameState(actor);if(!isA(state,stateClass()))return;
  const manager=state.add(0x3b8).readPointer();if(manager.isNull())return;
  const w=weak(world),f=weak(actor),receipt=[LAUNCH.run_id,key(w),key(f)].join(':');
  if(pending.has('drop:'+receipt))return;
  const context=Memory.alloc(88),empty=Memory.alloc(16);
  context.writeByteArray(new Uint8Array(88));empty.writeByteArray(new Uint8Array(16));
  makeContext(context,empty,actor);
  const e={action:'drop',tid,world:w,pc:weak(pc),manager:weak(manager),context,attempts:0,retry:true};
  pending.set('drop:'+receipt,e);request('drop',receipt,e);
 }catch(e){report('native_field_loot_error',{phase:'trigger',reason:String(e)});}}});
 // Only locally issued material/currency actors wait for durable SQL pickup.
 // Unknown drops and the native ammo/HP path keep their original behavior.
 let obtain;
 const obtainReplacement=new NativeCallback((actor,pc)=>{
  let ours=false;
  try{
   if(!isA(actor,dropClass()))return obtain(actor,pc);
   const oid=actor.add(0x670).readS64().toString(),d=issued.get(oid);
   if(!d)return obtain(actor,pc);ours=true;
   const world=local(pc);
   if(world===null||resolve(d.world)===null||!world.equals(resolve(d.world))||!pc.equals(resolve(d.pc)))return;
   if(d.applied||pending.has('pickup:'+oid))return;
   const e={action:'pickup',world:d.world,pc:d.pc,actor:weak(actor),attempts:0,retry:true};
   pending.set('pickup:'+oid,e);request('pickup',oid,e);
  }catch(e){report('native_field_loot_error',{phase:'pickup',reason:String(e)});if(!ours)return obtain(actor,pc);}
 },'void',['pointer','pointer']);
 obtain=new NativeFunction(Interceptor.replaceFast(b.add(0x3f97720),obtainReplacement),'void',['pointer','pointer']);
 // Native non-instant pickup reaches DedicatedToGS acquisition at 144443170.
 // That backend is absent here; SQL + inventory notices already fulfilled it.
 // Suppress only this exact invocation while resuming a committed local drop.
 let backendObtain;
 const backendReplacement=new NativeCallback((component,info)=>{
  const oid=info.add(24).readS64().toString();
  if(oid===resumingOid&&issued.get(oid)?.committed)return;
  return backendObtain(component,info);
 },'void',['pointer','pointer']);
 backendObtain=new NativeFunction(Interceptor.replaceFast(b.add(0x4443170),backendReplacement),'void',['pointer','pointer']);
 function receive(){recv('field-loot',m=>{try{
  const p=m.payload,e=pending.get(p.action+':'+p.receipt);
  if(!e||p.account_uid!==LAUNCH.account_uid||e.applied)return;
  if(p.ok){e.response=p;e.retry=false;}
  else{e.retry=!!p.retry;e.last=Date.now();report('native_field_loot_waiting',{action:p.action,reason:p.reason});}
 }catch(e){report('native_field_loot_error',{phase:'reply',reason:String(e)});}receive();});}receive();
 Interceptor.attach(b.add(0x43fd5a0),{onLeave(){
  for(const [id,e] of pending){try{
   const world=resolve(e.world),pc=resolve(e.pc);
   if(world===null||pc===null){pending.delete(id);continue;}
   const current=local(pc);if(current===null||!current.equals(world)){pending.delete(id);continue;}
   if(e.applied)continue;
   if(e.response){
    if(e.action==='drop'){
     const manager=resolve(e.manager),pawn=pc.add(0x298).readPointer(),rows=e.response.rows;
     if(manager===null||pawn.isNull())continue;
     if(!Array.isArray(rows)||rows.length>64)throw Error('Invalid native drop response');
     const array=Memory.alloc(16),items=Memory.alloc(Math.max(1,rows.length)*56);
     array.writeByteArray(new Uint8Array(16));items.writeByteArray(new Uint8Array(Math.max(1,rows.length)*56));
     for(let i=0;i<rows.length;i++){
      const r=rows[i];if(!/^[0-9]{1,19}$/.test(r.oid)||![1,3].includes(r.kind)||
       !Number.isInteger(r.tid)||r.tid<=0||!Number.isInteger(r.count)||r.count<=0||r.count>2147483647)throw Error('Invalid native drop row');
      const p=items.add(i*56);p.add(8).writePointer(pawn);p.add(20).writeS32(r.count);
      p.add(24).writeU8(r.kind);p.add(28).writeS32(r.tid);p.add(32).writeS64(int64(r.oid));
      p.add(40).writeS64(e.context.add(72).readS64());
     }
     for(const r of rows)issued.set(r.oid,{world:e.world,pc:e.pc,committed:false,applied:false});
     array.writePointer(items);array.add(8).writeS32(rows.length);array.add(12).writeS32(rows.length);
     e.applied=true;spawn(manager,e.context,array);
     e.context=null;report('native_field_drop_spawn_requested',{receipt:e.response.receipt,count:rows.length});
    }else{
     const actor=resolve(e.actor),oid=e.response.receipt,d=issued.get(oid);
     if(actor===null||!d){pending.delete(id);continue;}
     if(actor.add(0x670).readS64().toString()!==oid)throw Error('Pickup actor was recycled');
     e.applied=true;d.committed=true;d.applied=true;resumingOid=oid;
     try{obtain(actor,pc);}finally{resumingOid=null;}
     report('native_field_pickup_applied',{oid});
    }
   }else if(e.retry&&Date.now()-e.last>=Math.min(1000*e.attempts,8000))request(e.action,id.slice(e.action.length+1),e);
  }catch(err){e.retry=false;e.applied=true;report('native_field_loot_error',{phase:'apply',reason:String(err)});}}
  for(const [oid,d] of issued)if(resolve(d.world)===null)issued.delete(oid);
 }});
 report('native_field_loot_bridge_ready',{box_templates:boxes.size});
})();

// Observe mission end boundaries without completing objectives or changing state.
(() => {
 'use strict';
 const b=Process.mainModule.base;
 const missionId=new NativeFunction(b.add(0x421ac90),'pointer',['pointer','pointer']);
 const worldOf=new NativeFunction(b.add(0x6dbfcf0),'pointer',['pointer']);
 let reports=0;
 function emit(event,fields){if(reports++<500)send({event,...fields});}
 function state(p){
  const result={object_index:p.add(12).readS32(),timer:p.add(0x628).readU64().toString(),
   ended:p.add(0x371).readU8(),override_state:p.add(0x638).readU8(),override_set:p.add(0x639).readU8(),
   score:p.add(0x458).readS32(),initial_score:p.add(0x484).readS32()};
  const definition=p.add(0x298).readPointer();
  if(!definition.isNull()){const out=Memory.alloc(4);result.mission_id=missionId(definition,out).readS32();}
  const world=worldOf(p);
  if(!world.isNull()){
   const mode=world.add(0x158).readPointer();result.has_game_mode=!mode.isNull();
   if(!mode.isNull())result.has_game_service=!mode.add(0x350).readPointer().isNull();
  }
  return result;
 }
 for(const [offset,phase,indirect] of [[0x422e8d0,'success_timer',true],[0x422f390,'submit',false],
   [0x422e950,'end',false],[0x422e9d0,'failure',false],[0x422b250,'finish',false]]){
  Interceptor.attach(b.add(offset),{
   onEnter(a){try{this.owner=indirect?a[0].readPointer():a[0];
    emit('native_mission_phase',{phase,...state(this.owner),...(phase==='finish'?{finish_state:a[1].toInt32()&255}:{})});
   }catch(e){emit('native_mission_observer_error',{phase,error:String(e)});}},
   onLeave(r){if(phase==='submit')emit('native_mission_submit_returned',{submitted:!!(r.toInt32()&255)});}
  });
 }
 Interceptor.attach(b.add(0x44c1700),{onEnter(a){try{
  const d=a[2],q=a[1],backend=a[0].add(0x188).readPointer();
  emit('native_mission_backend_request',{mission_id:q.add(16).readS32(),account_count:q.add(8).readS32(),
   has_backend:!backend.isNull(),has_connection:!backend.isNull()&&!backend.add(0x30).readPointer().isNull(),
   callback:d.readPointer().sub(b).toString(),storage:d.add(32).readPointer().sub(b).toString(),
   indirect_storage:!d.add(16).readPointer().isNull(),object_index:d.add(40).readS32(),serial:d.add(44).readU32()});
 }catch(e){emit('native_mission_observer_error',{phase:'backend',error:String(e)});}}});
 // The recommendation preview uses NX HTTP, not a GameService rune RPC.
 // Observe its actual request and fallback without changing the player's build.
 const recommendations=new Map();
 Interceptor.attach(b.add(0x40d19a0),{
  onEnter(a){this.span={owner_type:a[1].toInt32()&255,owner_tid:a[2].toInt32(),json_ready:false,http_dispatched:false,missing_endpoint:false};
   this.thread=Process.getCurrentThreadId();
   if(!recommendations.has(this.thread))recommendations.set(this.thread,[]);
   recommendations.get(this.thread).push(this.span);
   emit('native_rune_recommendation_requested',{owner_type:this.span.owner_type,owner_tid:this.span.owner_tid});},
  onLeave(){emit('native_rune_recommendation_returned',this.span);
   const stack=recommendations.get(this.thread);if(stack){stack.pop();if(!stack.length)recommendations.delete(this.thread);}}
 });
 const recommendation=()=>{const s=recommendations.get(Process.getCurrentThreadId());return s&&s[s.length-1];};
 // Mid-function probes must be instruction listeners: a function listener can
 // corrupt an outer onLeave return address when its stack frame is still active.
 Interceptor.attach(b.add(0x40d242c),function(){try{
  const span=recommendation();if(!span)return;
  const value=this.context.rbp.add(0x40),count=value.add(8).readS32();
  if(count<1||count>524288)return;
  const json=JSON.parse(value.readPointer().readUtf16String(count-1));
  span.json_ready=true;
  emit('native_rune_recommendation_input',{owner_type:span.owner_type,owner_tid:span.owner_tid,
   module_capacity:json.module_capacity??json.Module_capacity,
   module_count:(json.module_hold??json.Module_hold??[]).length,
   slot_count:(json.module_slots??json.Module_slots??[]).length});
 }catch(e){emit('native_rune_recommendation_observer_error',{error:String(e)});}});
 Interceptor.attach(b.add(0x40d2c66),function(){const span=recommendation();if(span)span.missing_endpoint=true;});
 Interceptor.attach(b.add(0x3c311d0),{onEnter(){const span=recommendation();
  if(span&&this.returnAddress.equals(b.add(0x40d2bf4)))span.http_dispatched=true;}});
 Interceptor.attach(b.add(0x40fe220),{onEnter(a){this.response=a[1];},onLeave(r){try{
  emit('native_rune_recommendation_decoded',{ok:!!(r.toInt32()&255),result_count:this.response.add(24).readS32()});
 }catch(e){emit('native_rune_recommendation_observer_error',{error:String(e)});}}});
 send({event:'native_mission_observer_ready',read_only:true});
})();

// Deliver the original local matching UI callbacks before ClientService 1120
// starts travel. This supplies no remote players or dedicated-server replication.
// Only launcher-issued local-instance tickets can reach this path.
(() => {
 'use strict';
 const image=Process.mainModule.base;
 const componentOf=new NativeFunction(image.add(0x44b9720),'pointer',['pointer']);
 const accountOf=new NativeFunction(image.add(0x441f8a0),'pointer',['pointer']);
 const started=new NativeFunction(image.add(0x4472c00),'void',['pointer','pointer']);
 const succeeded=new NativeFunction(image.add(0x4472d30),'void',['pointer','pointer']);
 const seen=new Set(),outbound=new Map(),restarts=new Map();let pendingPreset=null;
 const applyPreset=new NativeFunction(image.add(0x41ce9c0),'void',['pointer','uint8','int','int']);
 const receive=new NativeFunction(image.add(0x4471c70),'void',['pointer','pointer','pointer']);
 const netMode=new NativeFunction(image.add(0x6ddb820),'int',['pointer']);
 const joinControllerOf=new NativeFunction(image.add(0x3ba90c0),'pointer',['pointer']);
 const requestJoin=new NativeFunction(image.add(0x4454710),'void',['pointer','pointer']);
 function owner(self){
    if(!self.readPointer().equals(image.add(0x9a781f0)))return;
    const component=componentOf(self);if(component.isNull())return;
    const pc=component.add(0x98).readPointer();if(pc.isNull()||netMode(pc)!==0)return;
    const account=accountOf(component);
    if(account.isNull()||account.add(0x28).readS64().toString()!==LAUNCH.account_uid)return;
    return component;
 }
 function infoValue(p){return {map:p.add(4).readS32(),type:p.add(8).readU8(),
    id:p.add(12).readS32(),difficulty:p.add(16).readS32(),
    privateMode:p.add(20).readU8(),random:p.add(21).readU8()};}
 function sameRequest(a,b){return ['map','type','id','difficulty','privateMode','random'].every(k=>a[k]===b[k]);}
 function serverValue(p){return {map:p.add(4).readS32(),type:p.add(12).readU8(),id:p.add(8).readS32(),
   difficulty:p.add(24).readS32(),privateMode:p.add(80).readU8(),random:p.add(81).readU8()};}
 Interceptor.attach(image.add(0x4471c70),{onEnter(a){
   const pending=outbound.get(a[0].toString());if(pending)pending.delivered=true;
 }});
 // The mission-context rematch path calls ServerRequestMatching directly. Unlike
 // the entry UI, it does not put the local matching manager in Requesting (3).
 // Keep a scoped marker; only its exact outgoing request may deliver a reply
 // while the manager still holds the old Idle/Success (0/6) state.
 Interceptor.attach(image.add(0x446f260),{
  onEnter(a){this.key=null;try{
    if(!owner(a[0])||a[2].add(8).readS32()!==1||a[2].readPointer().isNull()||
       a[2].readPointer().readS64().toString()!==LAUNCH.account_uid)return;
    const state=a[0].add(0x230).readU8();if(![0,3,6].includes(state))return;
    this.key=a[0].toString();this.marker={...serverValue(a[1]),state};restarts.set(this.key,this.marker);
  }catch(e){send({event:'native_instance_bridge_error',phase:'restart_capture',error:String(e)});}},
  onLeave(){if(this.key&&restarts.get(this.key)===this.marker)restarts.delete(this.key);}
 });
 // 1444703a0 receives the resolved server request, whose closure captures these
 // exact fields. Void-battle UI pending subtype/difficulty can still be zero.
 Interceptor.attach(image.add(0x44703a0),{
  onEnter(a){
   try{
    const self=a[0],p=a[1],accounts=a[2];if(!owner(self))return;
    if(accounts.add(8).readS32()!==1||accounts.readPointer().isNull()||
       accounts.readPointer().readS64().toString()!==LAUNCH.account_uid)return;
    const request=serverValue(p),restart=restarts.get(self.toString());
    if(restart&&sameRequest(restart,request))request.restartState=restart.state;
    const count=p.add(56).readS32(),mods=p.add(48).readPointer();
    if(count<0||count>32||(count>0&&mods.isNull()))throw Error('Invalid matching modifiers');
    request.preset=0;
    for(let i=0;i<count;i++){const m=mods.add(i*8);if(m.readU8()===1){
      if(request.preset)throw Error('Multiple dungeon presets');request.preset=m.add(4).readS32();
    }}
    if(request.preset<0)throw Error('Invalid dungeon preset');
    outbound.set(self.toString(),request);
    if(outbound.size>16)outbound.delete(outbound.keys().next().value);
    send({event:'native_instance_request_resolved',...request});
   }catch(e){send({event:'native_instance_bridge_error',phase:'request_capture',error:String(e)});}
  }
 });
 function localTicket(self,res){
    const privateMode=res.add(4).readU8();
    if(res.readS32()!==1||privateMode>1||res.add(5).readU8()!==0)return;
    if(!self.readPointer().equals(image.add(0x9a781f0)))return;
    const n=res.add(0x18).readS32(),p=res.add(0x10).readPointer();
    if(n<1||n>200||p.isNull())return;
    const ticket=p.readUtf16String(n-1);
    const match=/^local-instance:[a-f0-9]{24}:(\d+):(\d+):(\d+):(\d+):([01])$/.exec(ticket);
    if(!match||seen.has(ticket))return;
    const [map,type,id,difficulty,ticketPrivate]=match.slice(1).map(Number);
    if(ticketPrivate!==privateMode)return;
    if(![map,id].every(v=>Number.isInteger(v)&&v>0&&v<=2147483647)||type<1||type>14||difficulty<0||difficulty>5)return;
    const component=componentOf(self);if(component.isNull())return;
    const pc=component.add(0x98).readPointer();if(pc.isNull()||netMode(pc)!==0)return;
    const account=accountOf(component);
    if(account.isNull()||account.add(0x28).readS64().toString()!==LAUNCH.account_uid)return;
    return {self,component,ticket,map,type,id,difficulty,privateMode,preset:outbound.get(self.toString())?.preset||0};
 }
 function complete(v){
  if(!v)return;
    if(v.self.add(0x230).readU8()!==4)return;
    const controller=joinControllerOf(v.component);
    if(controller.isNull()||!controller.readPointer().equals(image.add(0x9a6f3b8)))throw Error('Native join controller is unavailable');
    if(controller.add(0x150).readU8()||controller.add(0x170).readU8())throw Error('Another native world transition is pending');
    const text=Memory.allocUtf16String(v.ticket),start=Memory.alloc(56),success=Memory.alloc(16);
    start.writeByteArray(new Uint8Array(56));success.writeByteArray(new Uint8Array(16));
    start.writeS64(int64(LAUNCH.account_uid));start.add(8).writeS32(v.map);
    start.add(12).writeS32(v.id);start.add(16).writeU8(v.type);start.add(20).writeS32(v.difficulty);
    start.add(32).writeU8(v.privateMode);start.add(40).writePointer(text);
    start.add(48).writeS32(v.ticket.length+1);start.add(52).writeS32(v.ticket.length+1);
    success.writeS64(int64(LAUNCH.account_uid));success.add(8).writeU8(1);success.add(12).writeS32(v.map);
    started(v.self,start);succeeded(v.self,success);
    if(v.self.add(0x230).readU8()!==6)throw Error('Native matching did not reach success state');
    seen.add(v.ticket);if(seen.size>64)seen.delete(seen.values().next().value);
    send({event:'native_local_instance_matched',map_template_id:v.map,instance_id:v.id,instance_type:v.type,private:v.privateMode===1,standalone:true});
    // Native RequestJoinGame initializes the world controller, binds its 1120
    // delegate and sends 1110. Only then does the service release this allocation.
    pendingPreset=v.preset?{id:v.id,preset:v.preset,ticket:v.ticket}:null;
    const join=Memory.alloc(0x100);join.writeByteArray(new Uint8Array(0x100));
    join.add(4).writeS32(v.map);join.add(8).writeS32(v.id);join.add(12).writeU8(v.type);
    join.add(16).writeS32(v.difficulty);join.add(0x51).writeU8(v.privateMode);
    // The original request constructors use this immutable identity transform.
    join.add(0x90).writeByteArray(image.add(0xbcbb2b0).readByteArray(48));
    requestJoin(controller,join);
    if(controller.add(0x150).readU8()!==1)throw Error('Native world request was not accepted');
    send({event:'native_local_instance_join_requested',map_template_id:v.map,instance_id:v.id,private:v.privateMode===1});
 }
 Interceptor.attach(image.add(0x4471b50),{
  onEnter(a){
   this.local=null;
   try{this.local=localTicket(a[0],a[1]);}
   catch(e){send({event:'native_instance_bridge_error',phase:'capture',error:String(e)});}
  },
  onLeave(){
   try{complete(this.local);}
   catch(e){send({event:'native_instance_bridge_error',phase:'notify',error:String(e)});}
  }
 });
 // The server response closure resolves its originating matching manager and
 // account list before entering this function. Its stock delivery then requires
 // a dedicated-server proxy class, absent in the local client backend. Forward
 // only that still-undelivered response to the same owner's original callback.
 Interceptor.attach(image.add(0x4471460),{
  onEnter(a){
   this.reply=null;
   try{
    const self=a[0],res=a[1],accounts=a[2],info=a[3];
    if(!self.readPointer().equals(image.add(0x9a781f0)))return;
    const requested=outbound.get(self.toString()),state=self.add(0x230).readU8();
    if(state!==3&&!(requested&&requested.restartState===state&&[0,6].includes(state)))return;
    if(accounts.add(8).readS32()!==1)return;
    const members=accounts.readPointer();
    if(members.isNull()||members.readS64().toString()!==LAUNCH.account_uid)return;
    const component=componentOf(self);if(component.isNull())return;
    const pc=component.add(0x98).readPointer();if(pc.isNull()||netMode(pc)!==0)return;
    const account=accountOf(component);
    if(account.isNull()||account.add(0x28).readS64().toString()!==LAUNCH.account_uid)return;
    const actual=infoValue(info);
    if(!requested||!sameRequest(requested,actual)){
      send({event:'native_instance_reply_ignored',reason:'request_mismatch',requested:requested||null,actual});return;
    }
    if(res.add(4).readU8()!==info.add(20).readU8()||res.add(5).readU8()!==info.add(21).readU8())return;
    const reason=res.readS32(),local=localTicket(self,res);
    if(reason<1||reason>36||(reason===1&&!local))return;
    // Group IDs resolve to a concrete child; ordinary requests must keep their
    // destination. Both kinds retain the originating request's mode and type.
    if(local&&(local.type!==actual.type||local.privateMode!==actual.privateMode||
       (![7,8].includes(actual.type)&&(local.map!==actual.map||local.id!==actual.id))))return;
    if(local)local.preset=requested.preset;
    this.reply={self,res,info,reason,local,state,requested,restart:requested.restartState!==undefined};
   }catch(e){send({event:'native_instance_bridge_error',phase:'delivery_capture',error:String(e)});}
  },
  onLeave(){
   const v=this.reply;this.reply=null;if(!v)return;
   try{
    // A normally delivered response already changed this state; never replay it.
    if(v.requested.delivered||v.self.add(0x230).readU8()!==v.state)return;
    outbound.delete(v.self.toString());
    receive(v.self,v.res,v.info);
    complete(v.local);
    send({event:'native_local_instance_reply_delivered',reason:v.reason,state:v.self.add(0x230).readU8(),restart:v.restart});
   }catch(e){send({event:'native_instance_bridge_error',phase:'delivery',error:String(e)});}
  }
 });
 // Original instance-object initialization, on the game thread. Preserve the
 // preset selected at the entry UI until its destination object exists.
 Interceptor.attach(image.add(0x41cdbe0),{
  onEnter(a){this.instance=null;try{
    if(!pendingPreset||a[1].toInt32()!==pendingPreset.id||(a[2].toInt32()&255)!==1)return;
    if(!a[0].readPointer().equals(image.add(0x9803f50)))return;
    this.instance={self:a[0],pending:pendingPreset};
  }catch(e){send({event:'native_instance_preset_error',phase:'capture',error:String(e)});}},
  onLeave(){const c=this.instance;if(!c||pendingPreset!==c.pending)return;try{
    const actor=c.self.add(0x108).readPointer();if(actor.isNull()||netMode(actor)!==0)return;
    const comp=componentOf(c.self);if(comp.isNull())return;
    const account=accountOf(comp);if(account.isNull()||account.add(0x28).readS64().toString()!==LAUNCH.account_uid)return;
    const instance=c.self.add(0xb0).readPointer();
    if(instance.isNull()||instance.add(0x40).readS32()!==c.pending.id)return;
    applyPreset(c.self,1,c.pending.id,c.pending.preset);
    if(c.self.add(0xe8).readS32()!==c.pending.id||c.self.add(0xec).readS32()!==c.pending.preset)
      throw Error('Native preset state did not update');
    pendingPreset=null;
    send({event:'native_instance_preset_applied',instance_id:c.pending.id,preset:c.pending.preset});
  }catch(e){pendingPreset=null;send({event:'native_instance_preset_error',phase:'apply',error:String(e)});}}
 });
 send({event:'native_instance_bridge_ready'});
})();

// Complete the local risk-info callback when ProcessEvent omits the client RPC.
// Native implementation retains ownership of the cache and menu delegates.
(() => {
 'use strict';
 const image=Process.mainModule.base,active=new Map();
 const componentOf=new NativeFunction(image.add(0x44b9720),'pointer',['pointer']);
 const accountOf=new NativeFunction(image.add(0x441f8a0),'pointer',['pointer']);
 const netMode=new NativeFunction(image.add(0x6ddb820),'int',['pointer']);
 const impl=image.add(0x4476e80),exec=image.add(0x36db250),vtable=image.add(0x9a776b8);
 const apply=new NativeFunction(impl,'void',['pointer','pointer']);
 function local(self){
  if(self.isNull()||!self.readPointer().equals(vtable))return false;
  const comp=componentOf(self);if(comp.isNull())return false;
  const pc=comp.add(0x98).readPointer();if(pc.isNull()||pc.add(0x108).readU8()!==3||netMode(pc)!==0)return false;
  const account=accountOf(comp);return !account.isNull()&&account.add(0x28).readS64().toString()===LAUNCH.account_uid;
 }
 function valid(p){
  if(p.isNull()||p.readS32()<=0)return false;
  const n=p.add(24).readS32(),a=p.add(16).readPointer();
  if(n<0||n>64||(n>0&&a.isNull()))return false;
  for(let i=0;i<n;i++){
   const row=a.add(i*40),slots=row.add(32).readS32();
   if(slots<0||slots>64||(slots>0&&row.add(24).readPointer().isNull()))return false;
  }
  return true;
 }
 Interceptor.attach(impl,{onEnter(a){
  for(const c of active.get(this.threadId)||[])if(c.self.equals(a[0])&&c.payload.equals(a[1]))c.delivered=true;
 }});
 Interceptor.attach(image.add(0x51d3f10),{
  onEnter(a){
   this.call=null;
   try{
    if(!local(a[0])||a[1].isNull()||!a[1].add(0xd8).readPointer().equals(exec)||!valid(a[2]))return;
    this.call={self:a[0],payload:a[2],delivered:false};
    const stack=active.get(this.threadId)||[];stack.push(this.call);active.set(this.threadId,stack);
   }catch(e){send({event:'native_instance_query_error',phase:'capture',error:String(e)});}
  },
  onLeave(){
   const c=this.call;if(!c)return;
   const stack=active.get(this.threadId)||[];stack.splice(stack.lastIndexOf(c),1);
   if(!stack.length)active.delete(this.threadId);
   try{
    if(!c.delivered&&local(c.self)){apply(c.self,c.payload);send({event:'native_instance_query_delivered',procedure:11500});}
   }catch(e){send({event:'native_instance_query_error',phase:'delivery',error:String(e)});}
  }
 });
})();

// Complete observed local client callbacks; persistent mutations belong to SQL.
// Entries, vtables and parameter layouts are pinned to build_info.CLIENT_SHA256.
(() => {
 'use strict';
 const base=Process.mainModule.base,active=new Map();
 const componentOf=new NativeFunction(base.add(0x44b9720),'pointer',['pointer']);
 const accountOf=new NativeFunction(base.add(0x441f8a0),'pointer',['pointer']);
 const netMode=new NativeFunction(base.add(0x6ddb820),'int',['pointer']);
 const waveComponentOf=new NativeFunction(base.add(0x4358140),'pointer',['pointer']);
 const waveControllerOf=new NativeFunction(base.add(0x4248900),'pointer',['pointer']);
 function local(self,vtable){
  if(self.isNull()||!self.readPointer().equals(vtable))return false;
  if(vtable.equals(base.add(0x9942950))){
   const wave=waveComponentOf(self);if(wave.isNull())return false;
   const pc=waveControllerOf(wave);if(pc.isNull()||pc.add(0x108).readU8()!==3||netMode(pc)!==0)return false;
   const comp=pc.add(0x830).readPointer();if(comp.isNull())return false;
   const account=accountOf(comp);return !account.isNull()&&own(account.add(0x28));
  }
  const comp=vtable.equals(base.add(0x9a548e8))?self:componentOf(self);if(comp.isNull())return false;
  const pc=comp.add(0x98).readPointer();
  if(pc.isNull()||pc.add(0x108).readU8()!==3||netMode(pc)!==0)return false;
  const account=accountOf(comp);
  return !account.isNull()&&account.add(0x28).readS64().toString()===LAUNCH.account_uid;
 }
 function array(p,max,min=0){
  const n=p.add(8).readS32(),capacity=p.add(12).readS32();
  return n>=min&&n<=max&&capacity>=n&&capacity<=1048576&&(n===0||!p.readPointer().isNull());
 }
 const own=p=>p.readS64().toString()===LAUNCH.account_uid;
 const reason=p=>p.readS32()>=0&&p.readS32()<256;
 const item=(p,type)=>p.add(8).readU8()===type&&p.add(16).readS64()>0n;
 const season=p=>p.readU8()<=1&&p.add(4).readS32()>0;
 const seasonSlot=p=>season(p)&&p.add(8).readU8()<16;
 const seasonNode=p=>seasonSlot(p)&&p.add(12).readS32()>=0&&p.add(12).readS32()<5&&p.add(16).readS32()>=0&&p.add(16).readS32()<4&&p.add(20).readU8()<=1;
 const warehouse=p=>p.readS32()>=0&&p.readS32()<256&&array(p.add(8),4096);
 const equipmentUid=p=>p.readU8()===2&&p.add(8).readS64()>0n;
 function optionEnchant(p){
  if(!equipmentUid(p)||!reason(p.add(16))||p.add(20).readS32()<0||!array(p.add(24),16))return false;
  const n=p.add(32).readS32(),data=p.add(24).readPointer(),slots=new Set();
  if(p.add(16).readS32()===1&&(n===0||p.add(20).readS32()===0))return false;
  for(let i=0;i<n;i++){
   const r=data.add(i*16),slot=r.add(2).readS16();
   if(r.readU8()>1||slot<0||slot>=16||slots.has(slot))return false;
   slots.add(slot);
  }
  return true;
 }
 function shop(p){
  // M1ItemServiceBuyItemResult has BuyInfoList and local consumed-item data.
  if(!array(p,1024,1)||!array(p.add(16),4096))return false;
  const data=p.readPointer(),n=p.add(8).readS32();
  for(let i=0;i<n;i++)if(!own(data.add(i*56))||!array(data.add(i*56+40),4096))return false;
  return true;
 }
 const archeSlot=p=>p.readU8()<=1&&p.add(4).readS32()>0&&p.add(8).readU8()<5;
 function archeInfo(p){
  if(p.readS32()<=0||p.add(4).readS32()<0||p.add(4).readS32()>40||p.add(8).readU8()>=5||!array(p.add(16),5))return false;
  const slots=p.add(16).readPointer(),count=p.add(24).readS32();
  for(let i=0;i<count;i++){
   const s=slots.add(i*40);
   if(s.readS32()<=0||s.add(4).readU8()>=5||!array(s.add(8),15)||!array(s.add(24),8))return false;
   const boards=s.add(24).readPointer(),n=s.add(32).readS32();
   for(let j=0;j<n;j++){
    const b=boards.add(j*40);
    if(b.readS32()<=0||!array(b.add(8),441)||!array(b.add(24),441))return false;
    for(const [off,stride] of [[8,2],[24,8]]){
     const rows=b.add(off).readPointer(),nn=b.add(off+8).readS32();
     for(let k=0;k<nn;k++)if(rows.add(k*stride).readU8()>=21||rows.add(k*stride+1).readU8()>=21)return false;
    }
   }
  }
  return true;
 }
 function archeAll(p){
  if(!array(p,64)||!array(p.add(16),64))return false;
  for(let i=0;i<p.add(8).readS32();i++)if(!archeInfo(p.readPointer().add(i*32)))return false;
  for(let i=0;i<p.add(24).readS32();i++){
   const g=p.add(16).readPointer().add(i*24);
   if(g.readS32()<=0||!array(g.add(8),5))return false;
   for(let j=0;j<g.add(16).readS32();j++){
    const s=g.add(8).readPointer().add(j*24);if(s.readU8()>=5||!array(s.add(8),15))return false;
   }
  }
  return true;
 }
 const definitions=[
  ['favorite_character',110,0x9a548e8,0x36b2e40,0x43ffc70,p=>p.readS64()>0n&&p.add(8).readU8()<=1&&reason(p.add(12)),'favorite'],
  ['currency_details',605,0x9a83d88,0x36f4b60,0x44a51c0,p=>own(p)&&array(p.add(8),16)],
  ['attendance_buy',1704,0x9a67848,0x36cd570,0x444d7b0,p=>p.readS32()>=0&&p.add(4).readS16()>=0&&p.add(6).readS16()>=-1&&p.add(8).readS16()>=-1],
  ['attendance_claim',1703,0x9a67848,0x36cd7f0,0x444d390,p=>p.readS32()>=0&&p.add(4).readS16()>=0&&p.add(6).readS16()>=-1&&p.add(8).readS16()>=-1&&p.add(12).readU8()<=1,'split12bool'],
  ['beginner_path',3800,0x9a6ea68,0x36d20e0,0x4459f40,p=>p.readS32()>0&&p.add(4).readU8()<=1&&reason(p.add(8))&&array(p.add(16),256),'jumping'],
  ['time_trial_info',11404,0x9a8f260,0x36f7410,0x44a8070,p=>p.readS32()>=0&&p.add(4).readS32()>=0&&p.add(8).readS64()>=0n],
  ['time_trial_success',11402,0x9a8f260,0x36f7500,0x44a79e0,p=>p.readS32()>0&&reason(p.add(8))&&p.add(12).readU8()<=1&&p.add(16).readS32()>=0&&p.add(20).readS32()>=0,'tidStruct'],
  ['wave_reward',10803,0x9942950,0x35d2ba0,0x435a070,p=>p.readS32()>0&&array(p.add(8),1,1)&&own(p.add(8).readPointer())&&array(p.add(8).readPointer().add(16),4096),'split8'],
  ['dice_roll',1706,0x9a67848,0x36ccae0,0x444f5e0,p=>p.readU8()<=1&&array(p.add(8),1000)&&p.add(24).readS32()>0,'split24int'],
  ['weapon_level',118,0x9a67fc8,0x36beb60,0x4446900,p=>equipmentUid(p)||p.readU8()===0&&p.add(8).readS64()===0n],
  ['consumable_decompose',125,0x9a64528,0x36bd220,0x4432ba0,p=>reason(p)&&array(p.add(8),1500)],
  ['title_save',2202,0x9a67fc8,0x36c86c0,0x4447a60,p=>reason(p)&&p.add(4).readS32()>=0&&p.add(8).readS32()>=0,'threeInts'],
  ['vehicle_level',3500,0x9a8cfd0,0x36fbe10,0x44ad1b0,p=>p.readU8()<=1&&p.add(4).readS32()>0],
  ['random_exchange',1602,0x9a83d88,0x36f3f00,0x44a7240,p=>reason(p)&&array(p.add(8),100)&&p.add(24).readS32()>=0&&p.add(32).readS32()>0&&p.add(36).readS32()>0&&p.add(36).readS32()<=100,'exchange'],
  ['t4_options',163,0x9a67fc8,0x36c9ee0,0x44499f0,p=>equipmentUid(p)&&reason(p.add(16))&&array(p.add(24),32)&&p.add(40).readS32()>=0,'split16struct'],
  ['t4_subperks',164,0x9a67fc8,0x36c9930,0x444aa40,p=>equipmentUid(p)&&p.add(16).readU8()<=1,'split16struct'],
  ['t4_confirm',165,0x9a67fc8,0x36c9bc0,0x444a190,p=>equipmentUid(p)&&p.add(16).readU8()<=1,'split16struct'],
  ['perk_enchant',1801,0x9a67fc8,0x36c8f20,0x4446f20,p=>reason(p)&&equipmentUid(p.add(8)),'reasonItem'],
  ['vehicle_options',3501,0x9a8cfd0,0x36fbc30,0x44ad5f0,p=>p.readU8()<=1&&p.add(4).readS32()>0],
  ['city_start',901,0x9a8afe0,0x36fdff0,0x44b5bb0,p=>p.readU8()<=1&&array(p.add(8),128),'split8'],
  ['exp_use',139,0x9a64528,0x36bc620,0x4433b80,p=>reason(p)&&p.add(4).readS32()>=0&&[2,5,12,17].includes(p.add(8).readU8())&&array(p.add(16),512),'expGrant'],
  ['eigen_exp',3302,0x9a548e8,0x36a47e0,0x4422120,p=>own(p)&&p.add(8).readS32()>0&&p.add(12).readS32()>=1&&p.add(12).readS32()<=40&&p.add(16).readS32()>=1&&p.add(16).readS32()<=40&&p.add(24).readS64()>=0n&&array(p.add(48),256)],
  ['arche_get',3200,0x9a4d138,0x369d450,0x43ec960,archeInfo],
  ['arche_all',3201,0x9a4d138,0x369d200,0x43ecd50,archeAll],
  ['arche_active',3202,0x9a4d138,0x369cf70,0x43ed2b0,p=>archeSlot(p)&&p.add(9).readU8()<21&&p.add(10).readU8()<21&&p.add(11).readU8()<=1],
  ['arche_clear',3203,0x9a4d138,0x369ca60,0x43ede60,archeSlot],
  ['arche_rename',3204,0x9a4d138,0x369c550,0x43ee400,p=>reason(p)&&p.add(4).readS32()>0&&p.add(8).readU8()<5&&array(p.add(16),15)],
  ['arche_select',3205,0x9a4d138,0x369c2d0,0x43ee980,archeSlot],
  ['arche_jewel',3208,0x9a4d138,0x369cce0,0x43ed880,p=>archeSlot(p)&&p.add(9).readU8()<21&&p.add(10).readU8()<21&&p.add(12).readS32()>=0],
  ['arche_points',3206,0x9a4d138,0x369c1e0,0x43eea90,p=>own(p)&&p.add(8).readS32()>0&&p.add(12).readS32()>=0&&p.add(12).readS32()<=40],
  ['arche_info',3207,0x9a4d138,0x369c010,0x43eed00,p=>own(p)&&archeInfo(p.add(8))],
  ['mastery_rank_up',1203,0x9a548e8,0x36a5030,0x441e910,p=>p.readS32()>=1&&p.readS32()<=40&&p.add(8).readS64()>=0n],
  ['item_tags',108,0x9a548e8,0x36a8ec0,0x4415900,p=>reason(p)&&p.add(4).readU8()<10&&p.add(5).readU8()<3,true],
  ['vessel_open',11326,0x9a69ce8,0x36c6d90,0x44447d0,p=>reason(p)&&array(p.add(8),4096)&&p.add(24).readS32()>0,'split24int'],
  ['vessel_offer',0,0x9a69ce8,0x36c70b0,0x4444230,p=>array(p,16,1)&&array(p.add(24),256),'split16struct'],
  ['package_open',1601,0x9a69ce8,0x36c7330,0x4443bc0,p=>reason(p)&&array(p.add(8),4096)&&array(p.add(40),16)&&p.add(36).readS32()>0&&p.add(56).readU8()<=1&&p.add(57).readU8()<=1,'package'],
  ['achievement',2301,0x9a7f160,0x36e6810,0x448a840,p=>p.readU8()<=1&&p.add(4).readS32()>0],
  ['drop_container',3303,0x9a69ce8,0x36c6970,0x44452f0,p=>array(p,4096)&&p.add(16).readS32()>0,'split16int'],
  ['consume',103,0x9a64528,0x36bd4e0,0x4432420,p=>reason(p)&&p.add(8).readS64()>0n&&p.add(16).readS32()>0],
  ['consume_selection',135,0x9a64528,0x36bcc00,0x4432420,p=>reason(p)&&p.add(8).readS64()>0n&&p.add(16).readS32()>0&&p.add(20).readS32()>0],
  ['weapon_reroll',122,0x9a67fc8,0x36ca8a0,0x444bb40,p=>p.readU8()<=1&&item(p,2)],
  ['option_enchant_count',136,0x9a67fc8,0x36ca580,0x44489f0,p=>equipmentUid(p)&&p.add(16).readS32()>=0,'split16struct'],
  ['option_enchant',137,0x9a67fc8,0x36ca1e0,0x4449060,optionEnchant,'split16struct'],
  ['warehouse_store',115,0x9a67fc8,0x36c9670,0x444afe0,warehouse],
  ['warehouse_take',116,0x9a67fc8,0x36c93b0,0x444b840,warehouse],
  ['capacity',155,0x9a64528,0x36bc1d0,0x4434820,p=>own(p)&&[1,2,3,6,8,9].includes(p.add(8).readU8())&&p.add(12).readS32()>=0&&p.add(12).readS32()<=1048576&&p.add(16).readU8()<=1],
  ['purchase',602,0x9a83d88,0x36f5a70,0x44a3770,shop],
  ['void_complete',11304,0x9a776b8,0x36dc050,0x4475e80,p=>p.readS32()>0&&p.add(4).readU8()<=1&&array(p.add(56),4096)],
  ['instance_complete',11322,0x9a776b8,0x36dbe70,0x44764b0,p=>p.add(24).readS32()>=0&&p.add(24).readS32()<=4&&array(p.add(8),256)&&array(p.add(32),256)],
  ['junk_decompose',120,0x9a548e8,0x36a9bd0,0x4417a50,p=>array(p,4096)&&array(p.add(16),4096),'split16struct'],
  ['reactor_enchant',2001,0x9a67fc8,0x36c8a60,0x4447540,p=>reason(p)&&equipmentUid(p.add(8))&&p.add(24).readS32()>=0&&p.add(28).readS32()>0&&p.add(28).readS32()<=5,'reactorEnchant'],
  ['ancestor_roll',4000,0x9a86308,0x36ed800,0x4495e50,p=>reason(p)&&[0,20,21,30,31,32,40,41,42].includes(p.add(4).readU8())&&array(p.add(8),7)&&item(p.add(16),4)&&array(p.add(40),16)&&array(p.add(56),16)],
  ['ancestor_confirm',4001,0x9a86308,0x36ed580,0x4496360,p=>p.readU8()<=1&&item(p,4)],
  ['ancestor_reset',4002,0x9a86308,0x36ed3a0,0x4496880,p=>p.readU8()<=1&&item(p,4)],
  ['risk_select',11502,0x9a776b8,0x36da630,0x4478180,p=>p.readS32()>0&&p.add(4).readU8()<5&&p.add(5).readU8()<=1,true],
  ['risk_disable',11504,0x9a776b8,0x36d9c50,0x4478c70,p=>p.readS32()>0&&p.add(4).readU8()<=1&&p.add(5).readU8()<=1,true],
  ['module_check',407,0x9a86308,0x36ee670,0x4493890,p=>reason(p)&&array(p.add(8),4096)],
  ['module_enchant',406,0x9a86308,0x36ef520,0x4491bc0,p=>reason(p)&&item(p,4)&&p.add(24).readS32()>=0&&p.add(24).readS32()<=30,'split24'],
  ['module_grant',405,0x9a86308,0x36ecbc0,0x4497430,p=>reason(p)&&[2,5].includes(p.add(4).readU8())&&p.add(8).readS32()>0&&p.add(12).readU8()<3&&p.add(16).readS32()>=0&&p.add(16).readS32()<16&&p.add(20).readU8()>=1&&p.add(20).readU8()<=6],
  ['skin_paint_save',1555,0x9a60570,0x36c2a30,0x443cae0,p=>p.readS32()>=0&&p.add(4).readS32()>0&&reason(p.add(8)),'threeInts'],
  ['character_paint_save',1578,0x9a60570,0x36c26b0,0x443d170,p=>p.readS32()>0&&p.add(4).readU8()<=1&&reason(p.add(8)),'characterPaint'],
  ['weapon_skin_save',1554,0x9a60570,0x36c3280,0x443bd40,p=>p.readS32()>0&&p.add(4).readS32()>0&&p.add(8).readU8()<=1&&reason(p.add(12)),'weaponSkin'],
  ['core_change',132,0x9a63a98,0x36be670,0x44358e0,p=>reason(p)&&item(p.add(16),2)&&p.add(40).readS16()>=0&&p.add(40).readS16()<16],
  ['core_confirm',133,0x9a63a98,0x36be480,0x4436020,p=>p.readU8()<=1&&item(p,2)&&p.add(24).readS16()>=0&&p.add(24).readS16()<16&&p.add(26).readU8()<=1],
  ['core_compose',134,0x9a63a98,0x36be180,0x44365a0,p=>p.readU8()<=1&&p.add(4).readS32()>0&&p.add(8).readS32()>0,'coreCraft'],
  ['core_open',130,0x9a63a98,0x36bea70,0x4434e10,p=>p.readU8()<=1&&item(p,2)],
  ['core_enchant',131,0x9a63a98,0x36be870,0x44354b0,p=>p.readU8()<=1&&item(p,2)&&p.add(24).readS16()>=0&&p.add(24).readS16()<16],
  ['season_unlock',2901,0x9a85e78,0x36f2b60,0x449f5c0,seasonNode],
  ['season_equip',2902,0x9a85e78,0x36f2710,0x449fcb0,seasonNode],
  ['season_clear',2903,0x9a85e78,0x36f2490,0x44a01e0,seasonSlot],
  ['season_select',2994,0x9a85e78,0x36f2210,0x44a0730,seasonSlot],
  ['season_rename',2995,0x9a85e78,0x36f1c90,0x44a0d50,p=>reason(p)&&p.add(4).readS32()>0&&p.add(8).readU8()<16&&array(p.add(16),256)&&array(p.add(32),256)],
  ['season_copy',2996,0x9a85e78,0x36f18f0,0x44a1280,p=>seasonSlot(p)&&p.add(12).readS32()>0&&p.add(16).readU8()<16],
  ['season_buy',2997,0x9a85e78,0x36f1800,0x44a1750,season]
 ];
 const specs=definitions.map(([name,procedure,vt,entry,impl,check,scalar])=>({name,procedure,vtable:base.add(vt),entry:base.add(entry),impl,check,scalar,
  apply:new NativeFunction(base.add(impl),'void',scalar==='favorite'?['pointer','int64','uint8','pointer']:scalar==='jumping'?['pointer','pointer','uint8','pointer']:scalar==='tidStruct'?['pointer','int','pointer']:scalar==='split12bool'?['pointer','pointer','uint8']:scalar==='exchange'?['pointer','pointer','int','int']:scalar==='reasonItem'?['pointer','int','pointer']:scalar==='reactorEnchant'?['pointer','int','pointer','int','pointer']:scalar==='expGrant'?['pointer','pointer','int','uint8','pointer']:scalar==='threeInts'?['pointer','int','int','int']:scalar==='characterPaint'?['pointer','int','uint8','int']:scalar==='weaponSkin'?['pointer','int','int','uint8','int']:scalar==='coreCraft'?['pointer','pointer','int','int']:scalar==='package'?['pointer','pointer','uint8','uint8','int']:['split8','split24','split16struct'].includes(scalar)?['pointer','pointer','pointer']:(scalar==='split16int'||scalar==='split24int')?['pointer','pointer','int']:scalar?['pointer','int','uint8','uint8']:['pointer','pointer'])}));
 for(const impl of new Set(specs.map(s=>s.impl)))Interceptor.attach(base.add(impl),{onEnter(a){
  // UHT copies struct parameters onto its own stack. Pointer identity differs
  // during normal dispatch, so match the innermost operation and service only.
  const stack=active.get(this.threadId)||[];
  for(let i=stack.length-1;i>=0;i--)if(stack[i].spec.impl===impl&&stack[i].self.equals(a[0])){
   stack[i].delivered=true;break;
  }
 }});
 Interceptor.attach(base.add(0x51d3f10),{
  onEnter(a){
   this.sessionCall=null;
   try{
    if(a[0].isNull()||a[1].isNull()||a[2].isNull())return;
    const entry=a[1].add(0xd8).readPointer(),spec=specs.find(s=>s.entry.equals(entry));
    if(!spec||!local(a[0],spec.vtable)||!spec.check(a[2]))return;
    const call={spec,self:a[0],payload:a[2],delivered:false};this.sessionCall=call;
    const stack=active.get(this.threadId)||[];stack.push(call);active.set(this.threadId,stack);
   }catch(e){send({event:'native_session_bridge_error',phase:'capture',error:String(e)});}
  },
  onLeave(){
   const call=this.sessionCall;if(!call)return;
   try{
    if(!call.delivered&&local(call.self,call.spec.vtable)&&call.spec.check(call.payload)){
     if(call.spec.scalar==='favorite')call.spec.apply(call.self,call.payload.readS64(),call.payload.add(8).readU8(),call.payload.add(12));
     else if(call.spec.scalar==='jumping')call.spec.apply(call.self,call.payload,call.payload.add(4).readU8(),call.payload.add(8));
     else if(call.spec.scalar==='tidStruct')call.spec.apply(call.self,call.payload.readS32(),call.payload.add(8));
     else if(call.spec.scalar==='split12bool')call.spec.apply(call.self,call.payload,call.payload.add(12).readU8());
     else if(call.spec.scalar==='exchange')call.spec.apply(call.self,call.payload,call.payload.add(32).readS32(),call.payload.add(36).readS32());
     else if(call.spec.scalar==='reasonItem')call.spec.apply(call.self,call.payload.readS32(),call.payload.add(8));
     else if(call.spec.scalar==='reactorEnchant')call.spec.apply(call.self,call.payload.readS32(),call.payload.add(8),call.payload.add(24).readS32(),call.payload.add(28));
     else if(call.spec.scalar==='expGrant')call.spec.apply(call.self,call.payload,call.payload.add(4).readS32(),call.payload.add(8).readU8(),call.payload.add(16));
     else if(call.spec.scalar==='threeInts')call.spec.apply(call.self,call.payload.readS32(),call.payload.add(4).readS32(),call.payload.add(8).readS32());
     else if(call.spec.scalar==='characterPaint')call.spec.apply(call.self,call.payload.readS32(),call.payload.add(4).readU8(),call.payload.add(8).readS32());
     else if(call.spec.scalar==='weaponSkin')call.spec.apply(call.self,call.payload.readS32(),call.payload.add(4).readS32(),call.payload.add(8).readU8(),call.payload.add(12).readS32());
     else if(call.spec.scalar==='coreCraft')call.spec.apply(call.self,call.payload,call.payload.add(4).readS32(),call.payload.add(8).readS32());
     else if(call.spec.scalar==='package')call.spec.apply(call.self,call.payload,call.payload.add(56).readU8(),call.payload.add(57).readU8(),call.payload.add(60).readS32());
     else if(call.spec.scalar==='split24int')call.spec.apply(call.self,call.payload,call.payload.add(24).readS32());
     else if(call.spec.scalar==='split16struct')call.spec.apply(call.self,call.payload,call.payload.add(16));
     else if(call.spec.scalar==='split8')call.spec.apply(call.self,call.payload,call.payload.add(8));
     else if(call.spec.scalar==='split24')call.spec.apply(call.self,call.payload,call.payload.add(24));
     else if(call.spec.scalar==='split16int')call.spec.apply(call.self,call.payload,call.payload.add(16).readS32());
     else if(call.spec.scalar)call.spec.apply(call.self,call.payload.readS32(),call.payload.add(4).readU8(),call.payload.add(5).readU8());
     else call.spec.apply(call.self,call.payload);
     send({event:'native_session_reply_delivered',procedure:call.spec.procedure});
    }
   }catch(e){send({event:'native_session_bridge_error',phase:'delivery',procedure:call.spec.procedure,error:String(e)});}
   finally{
    const stack=active.get(this.threadId)||[],index=stack.lastIndexOf(call);
    if(index>=0)stack.splice(index,1);
    if(!stack.length)active.delete(this.threadId);
   }
  }
 });
 send({event:'native_session_bridge_ready',procedures:specs.map(s=>s.procedure)});
})();

// Pinned client c0147688. Resume the original vessel-completion callback
// after its run/mission receipt is committed; never synthesize mission success.
(() => {
 'use strict';
 const b=Process.mainModule.base,zero=ptr(0),pending=new Map(),ready=[];
 const native=(r,type,args)=>new NativeFunction(b.add(r),type,args);
 const worldOf=native(0x6dbfcf0,'pointer',['pointer']),netMode=native(0x6ddb820,'int',['pointer']);
 const releaseArray=native(0x110b460,'void',['pointer']);
 const finish=native(0x42a32b0,'void',['pointer','pointer']);
 const report=(event,v={})=>send({event,...v});
 function actor(index,serial){
  if(index<0||index>=b.add(0xb75c314).readS32()||!serial)return null;
  const chunks=b.add(0xb75c300).readPointer();if(chunks.isNull())return null;
  const chunk=chunks.add((index>>>16)*8).readPointer();if(chunk.isNull())return null;
  const e=chunk.add((index&65535)*24);
  if(e.add(16).readU32()!==serial||(e.add(8).readU32()&0x30200000))return null;
  const p=e.readPointer();return p.isNull()?null:p;
 }
 function current(e){
  const owner=actor(e.index,e.serial);if(owner===null)return false;
  const mission=owner.add(0x98).readPointer();
  return !mission.isNull()&&netMode(mission)===0&&worldOf(mission).equals(e.world);
 }
 let original;
 const replacement=new NativeCallback((self,accounts,remain,delegate)=>{
  let handled=false;
  try{
   if(delegate.isNull()||!delegate.readPointer().equals(b.add(0x42a32b0))||
      !delegate.add(16).readPointer().isNull()||!delegate.add(32).readPointer().equals(b.add(0xa0c4948)))return original(self,accounts,remain,delegate);
   const index=delegate.add(40).readS32(),serial=delegate.add(44).readU32(),owner=actor(index,serial);
   if(owner===null)return original(self,accounts,remain,delegate);
   const mission=owner.add(0x98).readPointer();
   if(mission.isNull()||netMode(mission)!==0)return original(self,accounts,remain,delegate);
   const world=worldOf(mission),n=accounts.add(8).readS32(),data=accounts.readPointer();
   if(world.isNull()||n!==1||data.isNull()||data.readS64().toString()!==LAUNCH.account_uid||remain<0||remain>86400)
    return original(self,accounts,remain,delegate);
   const receipt=[LAUNCH.run_id,'vessel',index,serial,world.toString()].join(':');
   handled=true;
   // Match ownership cleanup at the tail of 1444c45f0 exactly once.
   releaseArray(accounts);
   const storage=delegate.add(32),destroy=new NativeFunction(storage.readPointer().add(16).readPointer(),'void',['pointer']);destroy(storage);
   if(!pending.has(receipt)){
    const e={index,serial,world,remain,receipt,last:Date.now(),attempts:1,retry:true};pending.set(receipt,e);
    report('native_vessel_completion_requested',{receipt,account_uid:LAUNCH.account_uid,remain_seconds:remain});
   }
  }catch(err){report('native_vessel_completion_error',{phase:'capture',error:String(err)});if(!handled)return original(self,accounts,remain,delegate);}
 },'void',['pointer','pointer','int','pointer']);
 original=new NativeFunction(Interceptor.replaceFast(b.add(0x44c45f0),replacement),'void',['pointer','pointer','int','pointer']);
 function receive(){recv('vessel-completion',m=>{
  try{
   const p=m.payload,e=pending.get(p.receipt);if(!e||p.account_uid!==LAUNCH.account_uid)return;
   if(p.ok&&!e.committed){e.committed=true;e.result=p.result;ready.push(e.receipt);}
   else if(!p.ok){e.retry=!!p.retry;e.last=Date.now();}
  }catch(err){report('native_vessel_completion_error',{phase:'response',error:String(err)});}receive();
 });}receive();
 function buffer(size){const p=Memory.alloc(size);p.writeByteArray(new Uint8Array(size));return p;}
 function array(header,data,n){header.writePointer(data);header.add(8).writeS32(n);header.add(12).writeS32(n);}
 Interceptor.attach(b.add(0x43fd5a0),{onLeave(){
  for(const [key,e] of pending){
   if(!current(e)){pending.delete(key);continue;}
   if(!e.committed&&e.retry&&Date.now()-e.last>=Math.min(1000*e.attempts,8000)){
    e.last=Date.now();e.attempts++;report('native_vessel_completion_requested',{receipt:key,account_uid:LAUNCH.account_uid,remain_seconds:e.remain});
   }
  }
  while(ready.length){
   const e=pending.get(ready.shift());if(!e||e.applied||!current(e))continue;
   try{
    const values=e.result.Tids,period=e.result.PeriodReward;
    if(!Array.isArray(values)||!values.length||values.length>16||values.some(v=>!Number.isInteger(v.Id)||v.Id<=0))throw Error('Invalid vessel offer');
    if(period.Acquires.length>256)throw Error('Invalid vessel period reward');
    const weak=buffer(12),result=buffer(16),row=buffer(48),tids=buffer(4*values.length);
    weak.writeS32(e.index);weak.add(4).writeU32(e.serial);weak.add(8).writeS32(e.remain);
    row.writeS64(int64(LAUNCH.account_uid));row.add(8).writeS32(period.PoolDataTid.Id);row.add(12).writeS32(period.RewardedCount);
    const acq=period.Acquires.length?buffer(period.Acquires.length*12):zero;
    period.Acquires.forEach((v,i)=>{const p=acq.add(i*12);p.writeU8(v.ItemInfo.Type);p.add(4).writeS32(v.ItemInfo.TemplateId);p.add(8).writeS32(v.Count);});
    array(row.add(16),acq,period.Acquires.length);
    values.forEach((v,i)=>tids.add(i*4).writeS32(v.Id));array(row.add(32),tids,values.length);array(result,row,1);
    e.applied=true;finish(weak,result);report('native_vessel_completion_applied',{receipt:e.receipt,reward_groups:values.map(v=>v.Id)});
   }catch(err){report('native_vessel_completion_error',{phase:'callback',error:String(err)});}
  }
 }});
})();

// Passive, exact-build verification of launcher sessions; no writes or calls.
(() => {
  const base=Process.mainModule.base;
  let questData=null, lastQuestState='', reports=0;
  const emit=(event,fields)=>{if(reports++<200)send({event,...fields});};
  Interceptor.attach(base.add(0x4404fd0),{
    onEnter(a){try{
      emit('native_initial_mastery_login',{
        level:a[1].add(0x80).readS64().toString(),
        exp:a[1].add(0x88).readS64().toString()
      });
    }catch(e){emit('initialization_observer_error',{phase:'login',error:String(e)});}}
  });
  Interceptor.attach(base.add(0x4dd0700),{onEnter(a){
    try{
      if((a[2].toInt32()&65535)!==1400 ||
         !a[0].readPointer().add(0x10).readPointer().equals(base.add(0x4dce540)))return;
      const account=a[3].add(0x38);
      emit('native_initial_mastery_world',{
        level:account.add(0x18).readS32(),exp:account.add(0x20).readS64().toString(),
        equipment_count:account.add(0x30).readS32(),
        character_count:account.add(0xb0).readS32(),
        wearing_count:account.add(0x1d0).readS32()
      });
    }catch(e){emit('initialization_observer_error',{phase:'world',error:String(e)});}
  }});
  function trackers(phase){
    if(questData===null)return;
    try{
      const value={main:questData.add(0x130).readS32(),sub:questData.add(0x134).readS32(),
        beginner:questData.add(0x12c).readS32(),pathGuide:questData.add(0x1f8).readS32()};
      const key=JSON.stringify(value);if(key===lastQuestState)return;lastQuestState=key;
      emit('native_initial_quest_trackers',{phase,...value});
    }catch(e){emit('initialization_observer_error',{phase,error:String(e)});}
  }
  Interceptor.attach(base.add(0x40b3490),{onEnter(a){this.qd=a[0];},onLeave(){questData=this.qd;trackers('loaded');}});
  Interceptor.attach(base.add(0x40b4060),{onEnter(a){questData=a[0];}});
  Interceptor.attach(base.add(0x4488550),{onLeave(){trackers('started');}});
  Interceptor.attach(base.add(0x4488c20),{onLeave(){trackers('progress');}});
  Interceptor.attach(base.add(0x4486030),{onLeave(){trackers('load_complete');}});
  Interceptor.attach(base.add(0x4488df0),{onEnter(a){try{
    const p=a[1];emit('native_initial_quest_progress',{
      quest_id:p.readS32(),param_index:p.add(4).readS32(),
      complete_state:p.add(8).readS32(),count:p.add(12).readS32(),complete:!!p.add(16).readU8()
    });
  }catch(e){emit('initialization_observer_error',{phase:'progress',error:String(e)});}}});
})();

// Observe decoded full-profile ownership; bounded and read-only.
(() => {
 const base=Process.mainModule.base;let count=0;
 function rows(p,stride,read){const n=p.add(8).readS32();if(n<0||n>4096)throw Error('Array bounds');
  const data=p.readPointer(),out=[];for(let i=0;i<n;i++)out.push(read(data.add(i*stride)));return out;}
 Interceptor.attach(base.add(0x4dd0700),{onEnter(a){try{
  if(count>=8)return;const proc=a[2].toInt32()&65535;
  if(proc===1400){
   const account=a[3].add(0x38),characters=rows(account.add(0xa8),40,p=>({tid:p.add(8).readS32(),level:p.add(24).readS32()}));
   const currencies=rows(account.add(0xb8),16,p=>({type:p.readU8(),count:p.add(8).readS64().toString()}));
   count++;send({event:'native_profile_world_received',characters:characters.length,
    levels:[...new Set(characters.map(c=>c.level))],currencies});
  }else if(proc===1558){
   const items=rows(a[3].add(8),16,p=>p.readS32());count++;
   send({event:'native_profile_cosmetics_received',items:items.length,unique:new Set(items).size,
    customize_characters:a[3].add(0x20).readS32()});
  }
 }catch(e){send({event:'native_profile_observer_error',error:String(e)});}}});
})();

// Passive, bounded observation of the normal launcher-driven teleport path.
// Does not call game functions, alter memory, issue requests or complete quests.
(() => {
 'use strict';
 const base=Process.mainModule.base,attempts=new Map();let serial=0,reports=0;
 function emit(event,data={}){if(reports++<250)send({event,...data});}
 function text(p){const n=p.add(8).readS32();if(n<0||n>1024)throw Error('FString bounds');return n?p.readPointer().readUtf16String(n-1):'';}
 function active(ctx){return attempts.get(ctx.threadId);}
 function phase(a,name,data){if(!a)return;a.stages.push({phase:name,...data});}
 Interceptor.attach(base.add(0x3900be0),{onEnter(){emit('native_teleport_hold_begin');}});
 Interceptor.attach(base.add(0x3900a10),{onEnter(){emit('native_teleport_hold_done');}});
 Interceptor.attach(base.add(0x4d203e0),{
  onEnter(args){
   const a={attempt:++serial,stages:[]};this.attempt=a;attempts.set(this.threadId,a);
   try{
    const point=args[1].add(0x28).readPointer();
    if(!point.isNull()){
     a.point_kind=point.add(0x28).readU8();
     if(a.point_kind===2){a.map_template_id=point.add(0x30).readS32();a.entry_point_id=text(point.add(200));}
    }
    emit('native_teleport_attempt',{attempt:a.attempt,map_template_id:a.map_template_id,
      entry_point_id:a.entry_point_id,point_kind:a.point_kind});
   }catch(e){phase(a,'observation_error',{error:String(e)});}
  },
  onLeave(){const a=this.attempt;if(a){emit('native_teleport_attempt_returned',a);attempts.delete(this.threadId);}}
 });
 Interceptor.attach(base.add(0x3c842a0),{
  onEnter(args){this.attempt=active(this);if(this.attempt)this.mapId=args[1].toInt32();},
  onLeave(ret){if(this.attempt)try{phase(this.attempt,'map_lookup',{
    map_template_id:this.mapId,found:!ret.isNull(),map_data_present:!ret.isNull()&&!ret.add(0x28).readPointer().isNull()});
   }catch(e){phase(this.attempt,'observation_error',{error:String(e)});}}
 });
 Interceptor.attach(base.add(0x3c7d270),{
  onEnter(args){this.attempt=active(this);if(this.attempt)try{this.pointId=text(args[1]);}catch(e){this.pointId='';}},
  onLeave(ret){phase(this.attempt,'entry_lookup',{entry_point_id:this.pointId,found:!ret.isNull()});}
 });
 Interceptor.attach(base.add(0x4454710),{
  onEnter(args){this.attempt=active(this);this.controller=args[0];try{
   const data={map_template_id:args[1].add(4).readS32(),join_kind:args[1].readU8(),
    field_difficulty:args[1].add(0x10).readS32(),battle_zone_id:args[1].add(0x14).readS32(),
    private_field:!!args[1].add(0x51).readU8(),
    request_in_progress:!!args[0].add(0x150).readU8(),other_transition:!!args[0].add(0x170).readU8()};
   phase(this.attempt,'join_controller',data);
   emit('native_world_join_controller',data);
  }catch(e){emit('native_world_observer_error',{phase:'join',error:String(e)});}},
  onLeave(){try{emit('native_world_join_returned',{
   request_in_progress:!!this.controller.add(0x150).readU8(),other_transition:!!this.controller.add(0x170).readU8()});
  }catch(e){emit('native_world_observer_error',{phase:'join_return',error:String(e)});}}
 });
 // Lab exit may bypass the map UI. Observe original return/leave entry points
 // without invoking them or altering pending state.
 for(const [offset,phaseName] of [[0x4420d50,'return_city'],[0x4420de0,'return_map']]){
  Interceptor.attach(base.add(offset),{onEnter(){emit('native_world_return_requested',{phase:phaseName});}});
 }
 Interceptor.attach(base.add(0x441bd00),{
  onEnter(args){emit('native_world_leave_requested',{join_after_leave:!!(args[1].toInt32()&255)});},
  onLeave(result){emit('native_world_leave_returned',{submitted:!!(result.toInt32()&255)});}
 });
 Interceptor.attach(base.add(0x4456440),{
  onEnter(args){this.controller=args[0];try{
   emit('native_world_join_notice',{reason:args[1].readS32(),
    map_template_id:args[1].add(0x54).readS32(),standalone:!!args[1].add(0x69).readU8(),
    request_in_progress:!!args[0].add(0x150).readU8()});
  }catch(e){emit('native_world_observer_error',{phase:'join_notice',error:String(e)});}},
  onLeave(){try{emit('native_world_join_notice_returned',{
   request_in_progress:!!this.controller.add(0x150).readU8(),other_transition:!!this.controller.add(0x170).readU8()});
  }catch(e){emit('native_world_observer_error',{phase:'join_notice_return',error:String(e)});}}
 });
 emit('native_teleport_observer_ready',{read_only:true});
})();
