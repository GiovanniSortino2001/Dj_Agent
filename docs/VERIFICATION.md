# Rapporto delle verifiche effettive

Data: 9 ottobre 2026. Esecuzione reale su Linux x86_64, Python 3.12.14,
kernel 6.18.44, glibc 2.39. Questo rapporto distingue test funzionali da qualità
musicale e da integrazione con dispositivi esterni.

## Risultato

- **39 test Python passati**, incluso HTTP loopback reale con server finto e timeout.
- Stessi test passati in un **venv isolato con solo NumPy** come dipendenza runtime.
- CLI installata con `pip install -e .`, entrypoint `dj`, `python -m dj`, help/version verificati.
- Demo NumPy completa: 3 WAV, catalogo SQLite, 12 candidati, piano, simulazione,
  preview WAV stereo 22.050 Hz, audio finito e picco entro 0,98.
- Essentia reale: analisi di `track_1.wav` completata con backend `essentia`.
- Dataset/training PyTorch reale, export ONNX/checker e inferenza ORT CPU riusciti.
- Preview con controller ONNX riuscita; tutti i controlli passano attraverso safety.
- Mapping XML parsabile (6 binding); JavaScript sintatticamente valido; test mock passato.
- **Mixxx/ALSA reale: non verificato**, porta sequencer assente; tentativo documentato.
- **Qwen reale: non verificato**, nessun modello/server caricato; selezione/errore/timeout
  verificati con mock e server HTTP locale controllato, CLI con fallback reale.

## Dipendenze effettivamente usate

| Componente | Versione |
|---|---|
| Python | 3.12.14 |
| NumPy, ambiente con extras | 2.3.5 |
| NumPy, venv base isolato | 2.5.3 |
| PyTorch | 2.14.1 |
| ONNX | 1.23.2 |
| ONNX Runtime | 1.31.0 |
| Essentia | 2.1b6.dev1389 |
| mido | 1.3.3 |
| python-rtmidi | 1.5.8 |
| dj-offline-lab | 0.1.0 |

Le wheel PyTorch installate nell'ambiente contengono anche dipendenze CUDA;
**training/inferenza eseguiti su CPU**, nessuna prova GPU. `pyproject.toml` fornisce
intervalli compatibili dichiarati; questi non implicano verifica di ogni versione.
`configs/constraints-verified.txt` fotografa le versioni dell'ambiente extras.
`results/versions.json` e `results/clean-base-summary.json` riportano l'ambiente.
Il primo riepilogo base precede gli ultimi test aggiunti; il log finale
`results/clean-base-tests.log` contiene tutti i 39 test.

## Comandi e log

Comandi dalla radice `dj/`, con ambiente corretto attivo. Gli stdout/stderr sono
conservati. Exit code 0 per le righe PASS; 2 atteso per l'apertura MIDI non disponibile.

| Comando | Esito | Evidenza |
|---|---|---|
| `python -m pip install -e .` in venv pulito | PASS | `results/clean-base-install.log` |
| `dj --help`, `dj --version` | PASS, 0.1.0 | `results/cli-help.log`, `cli-version.log` |
| `python -m unittest discover -s tests -v` | PASS, 39 | `results/tests.log`, `clean-base-tests.log` |
| `node tests/test_mapping.js` | PASS, host mock | `results/mapping.log` |
| `python -m compileall -q src scripts tests` | PASS | Exit code 0 osservato |
| `node --check mixxx/DJBridge.js` | PASS | Exit code 0 osservato |
| Parsing XML `xml.etree.ElementTree.parse(...)` | PASS | 6 binding, exit code 0 osservato |
| `python -m dj demo --out examples/demo` | PASS | `results/demo.log` |
| `python -m dj scan examples/demo/track_1.wav examples/demo/track_2.wav --catalog results/scan-catalog.sqlite --backend numpy` | PASS | `results/scan.log` |
| `python -m dj catalog --catalog results/scan-catalog.sqlite` | PASS | `results/catalog.log` |
| `dj compare ID_A ID_B --catalog examples/demo/catalog.sqlite` con ID del piano | PASS | `results/compare.log` |
| `python -m dj --config configs/default.json preview --catalog examples/demo/catalog.sqlite --plan examples/demo/plan.json --out results/configured-preview.wav` | PASS | `results/config-preview.log` |
| `python -m dj analyze examples/demo/track_1.wav --backend essentia --out examples/demo/essentia_analysis.json` | PASS | `results/essentia.log` |
| `python -m dj dataset --out examples/ml/dataset.npz --samples 256` | PASS | `results/dataset.log` |
| `python -m dj train --data examples/ml/dataset.npz --out examples/ml/controller.pt --epochs 20` | PASS | `results/train.log` |
| `python -m dj export --checkpoint examples/ml/controller.pt --out examples/ml/controller.onnx` | PASS | `results/export.log` |
| `python -m dj infer --model examples/ml/controller.onnx --data examples/ml/dataset.npz --out examples/ml/inference.json` | PASS | `results/infer.log` |
| `python -m dj preview --catalog examples/demo/catalog.sqlite --plan examples/demo/plan.json --onnx examples/ml/controller.onnx --out examples/ml/preview_gru.wav` | PASS | `results/preview-gru.log` |
| `python -m dj --config configs/default.json --log results/qwen-fallback.log plan --catalog examples/demo/catalog.sqlite --out examples/demo/qwen-fallback-plan.json --qwen` | PASS con fallback | `results/qwen-cli.log` |
| `python -m dj midi-serve --seconds 1` | BLOCCATO da ambiente, exit 2 atteso | `results/midi-attempt.log` |
| `python scripts/verify.py --extras` | PASS, 10 gruppi di comandi | `results/full-verify.log`, `results/verified/summary.json` |

Il runner `verify.py --extras` usa 128 sequenze e 5 epoche per lo smoke ripetibile;
i pesi inclusi in `examples/ml/` derivano invece da 256 sequenze e 20 epoche.
Le due esecuzioni non vanno confuse. I log in `results/verified/` riportano la
ripetizione; quelli direttamente in `results/` la produzione degli esempi inclusi.

## Misure della demo NumPy

| WAV | BPM sintetizzato | BPM stimato | Errore assoluto |
|---|---:|---:|---:|
| track_1.wav | 120 | 120,158 | 0,158 |
| track_2.wav | 124 | 123,671 | 0,329 |
| track_3.wav | 128 | 127,952 | 0,048 |

Beat regolari e accordi sintetici rendono questo caso favorevole. Questi numeri
NON dimostrano accuratezza su musica reale. Tonalità, ritmo variabile, downbeat,
frasi e compatibilità artistica non sono valutati quantitativamente qui.
Essentia sul primo WAV: BPM 120,0032, tonalità C major, confidenza tempo grezza
3,7826. Struttura e voce rimangono rispettivamente euristica e non implementata.

## Misure del modello incluso

- Dataset seed 42, 204 sequenze training e 52 validation, nessuna sequenza condivisa.
- 20 epoche, validation MSE finale **0,00234492** sul target sintetico crossfader.
- MSE del primo esempio validation via ORT: **0,00189178**.
- Export opset 17, `dynamo=False`, h0 esplicito e forme fisse.
- Errore massimo PyTorch/ONNX Runtime **1,79745e-7**, soglia 1e-5, checker ONNX passato.
- L'exporter ha prodotto il warning generico GRU relativo a batch variabili;
  qui batch=1 e lunghezza=32 sono fissi, h0 è un input esplicito. Warning conservato
  in `results/export.log`, non nascosto.
- Il controller imita una rampa; queste metriche **non valutano capacità DJ**.

## Copertura dei guasti

WAV vuoti, invalidi e troncati; silenzio; audio brevissimo; antiphase stereo;
PCM24 con segno; NaN/Inf; BPM non valido; resampling invalido; catalogo vuoto;
import idempotente; file modificato dopo scan; piano oltre durata/ID errati/rate
non finito; transizione completa e volutamente rallentata dalla safety;
render finito/non silenzioso; scan parziale; timeout/JSON/indice errato Qwen;
URL remoto vietato; slew, range, monotonicità scheduler; frame MIDI incompleti,
sequenza errata e timeout; dataset corrotto, target fuori range e split.

## Non verificato o non implementato

**Implementato ma non verificabile qui:** apertura e routing ALSA, riconoscimento
preset in Mixxx reale, audio device routing, timing live, effettivo preflight/fade
su Mixxx; Qwen reale e comportamento del suo template; installazione extras su
altre distribuzioni/architetture. `connect_midi.py` è una procedura host da provare,
non una connessione dimostrata in questo container.

**Non implementato per scelta esplicita:** caricamento automatico per percorso in
Mixxx, identificazione brani nel feedback, beat sync preciso via MIDI, time-stretch
professionale/key-lock nel renderer, gestione effetti/EQ, voce/stem/struttura
semantica, capacità musicale da training sintetico. Nessun test con hardware DJ,
nessun ascolto umano certificato della qualità e nessun benchmark su librerie reali.

## Portabilità dello ZIP

Archivio estratto in una directory diversa; import verificato dal percorso estratto
e preview rigenerata con il Python del venv NumPy-only usando `PYTHONPATH=src`.
Catalogo, ID/hash e percorsi relativi funzionano dopo l'estrazione. Exit code 0;
88.084 frame stereo, picco 0,473169. Integrità CRC dello ZIP verificata con
`zipfile.ZipFile.testzip()`. Nessun ambiente virtuale, cache o dipendenza binaria
Python è incluso: l'installazione è quella descritta nel README.
