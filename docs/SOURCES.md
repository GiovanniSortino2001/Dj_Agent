# Documentazione primaria consultata

Consultazione tramite web il 9 ottobre 2026. Nessuna libreria viene installata
implicitamente all'avvio della demo. Versioni effettivamente provate in VERIFICATION.md.

| Fonte ufficiale | Uso nel codice |
|---|---|
| https://github.com/mixxxdj/mixxx/wiki/midi-scripting | Firma handler (channel, control, value, status, group), `engine.getValue/setValue`, `engine.beginTimer/stopTimer`, `midi.sendShortMsg`, `Script-Binding`, scriptfiles/functionprefix. |
| https://manual.mixxx.org/2.5/en/chapters/appendix/mixxx_controls.html | `crossfader` [-1,1]; controlli `play`, `playposition`, `bpm`, `volume`, `track_loaded`. |
| https://github.com/mixxxdj/mixxx/wiki/Script-Timers | Timer senza busy wait nell'host audio. |
| https://essentia.upf.edu/reference/std_RhythmExtractor2013.html | Cinque output dell'algoritmo, input a 44.100 Hz, multifeature e confidenza. |
| https://essentia.upf.edu/reference/std_KeyExtractor.html | Key/scale/strength e sampleRate di KeyExtractor. |
| https://docs.pytorch.org/docs/2.14/onnx.html | `torch.onnx.export`, selezione `dynamo=False`, nomi input/output, opset. Forme fisse, h0 esplicito. |
| https://onnxruntime.ai/docs/api/python/api_summary.html | `InferenceSession`, provider CPU, `run` con tensori NumPy per nome. |

Scelte progettuali nostre: protocollo CC, watchdog, limiti di slew, criteri di
compatibilità e rimappature confidenza. Non sono funzionalità garantite dalle
API ufficiali. Il mapping è conforme ai contratti documentati e passa il mock;
questo NON dimostra che discovery porte, routing e audio reale funzionino sulla
macchina dell'utente. Il test locale descritto in MIXXX.md resta necessario.
