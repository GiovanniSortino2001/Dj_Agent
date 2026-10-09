/* Experimental Mixxx 2.4+/2.5 mapping. No arbitrary path loading. */
var DJBridge = {timer: null, lastHeartbeat: 0, sequence: 0};
DJBridge.init = function () {
    DJBridge.lastHeartbeat = 0;
    DJBridge.timer = engine.beginTimer(100, DJBridge.feedback);
};
DJBridge.shutdown = function () {
    if (DJBridge.timer !== null) { engine.stopTimer(DJBridge.timer); }
    DJBridge.timer = null;
    DJBridge.lastHeartbeat = 0;
};
DJBridge.command = function (channel, control, value) {
    if (channel > 1 || !isFinite(value) || value < 0 || value > 127) { return; }
    if (channel === 0 && control === 118) {
        DJBridge.lastHeartbeat = value > 0 ? Date.now() : 0;
        return;
    }
    // Watchdog freezes controls, never mutes ongoing playback.
    if (!DJBridge.lastHeartbeat || Date.now() - DJBridge.lastHeartbeat > 500) { return; }
    var group = '[Channel' + (channel + 1) + ']';
    if (channel === 0 && control === 1) {
        var requested = value / 127 * 2 - 1;
        var current = engine.getValue('[Master]', 'crossfader');
        // A second guard against sudden incoming full-scale jumps.
        if (Math.abs(requested - current) <= 0.12) {
            engine.setValue('[Master]', 'crossfader', requested);
        }
    } else if (control === 7) {
        engine.setValue(group, 'volume', value / 127);
    } else if (control === 10 && engine.getValue(group, 'track_loaded')) {
        engine.setValue(group, 'play', value >= 64 ? 1 : 0);
    }
};
DJBridge.byte = function (x) { return Math.max(0, Math.min(127, Math.round(x))); };
DJBridge.feedback = function () {
    // Begin/end frame markers: Python rejects incomplete snapshots.
    midi.sendShortMsg(0xB0, 117, DJBridge.sequence);
    for (var ch = 0; ch < 2; ch++) {
        var group = '[Channel' + (ch + 1) + ']';
        midi.sendShortMsg(0xB0 + ch, 20, engine.getValue(group, 'play') ? 127 : 0);
        midi.sendShortMsg(0xB0 + ch, 21, DJBridge.byte(engine.getValue(group, 'playposition') * 127));
        midi.sendShortMsg(0xB0 + ch, 22, DJBridge.byte(engine.getValue(group, 'bpm') / 2));
        midi.sendShortMsg(0xB0 + ch, 23, engine.getValue(group, 'track_loaded') ? 127 : 0);
        midi.sendShortMsg(0xB0 + ch, 24, DJBridge.byte(engine.getValue(group, 'volume') * 127));
    }
    midi.sendShortMsg(0xB0, 25, DJBridge.byte((engine.getValue('[Master]', 'crossfader') + 1) * 63.5));
    midi.sendShortMsg(0xB0, 119, DJBridge.sequence);
    DJBridge.sequence = (DJBridge.sequence + 1) % 128;
};
