// Mocked host contract test. This is NOT a real Mixxx/ALSA integration test.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const state={'[Master]:crossfader':-1,'[Channel1]:track_loaded':1,'[Channel2]:track_loaded':1};
const sent=[]; let callback,stopped=false;
const context={Date:Date,isFinite:isFinite,Math:Math,midi:{sendShortMsg:(...x)=>sent.push(x)},engine:{
 getValue:(g,k)=>state[g+':'+k]||0,
 setValue:(g,k,v)=>{state[g+':'+k]=v;},
 beginTimer:(ms,cb)=>{assert.equal(ms,100);callback=cb;return 1;},
 stopTimer:id=>{assert.equal(id,1);stopped=true;}
}};
vm.createContext(context); vm.runInContext(fs.readFileSync('mixxx/DJBridge.js','utf8'),context);
const b=context.DJBridge; b.init();
b.command(1,10,127); assert.equal(state['[Channel2]:play'],undefined); // disarmed
b.command(0,118,127); b.command(1,10,127); assert.equal(state['[Channel2]:play'],1);
b.command(0,1,127); assert.equal(state['[Master]:crossfader'],-1); // jump rejected
b.command(0,1,5); assert(state['[Master]:crossfader']>-1);
b.command(0,7,64); assert(state['[Channel1]:volume']<=1);
b.lastHeartbeat=Date.now()-501; b.command(1,10,0); assert.equal(state['[Channel2]:play'],1);
callback(); assert.equal(sent.length,13); assert.equal(sent[0][1],117); assert.equal(sent.at(-1)[1],119);
for (const [status,cc,value] of sent) assert(Number.isInteger(value)&&value>=0&&value<=127);
b.shutdown(); assert(stopped); console.log('PASS: mock Mixxx contract, watchdog, jump guard, feedback frame (13 messages)');
