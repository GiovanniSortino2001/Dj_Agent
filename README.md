# dj — laboratorio DJ offline eseguibile su Linux

Repository Python `src/dj`, CLI `dj`, NumPy come unica dipendenza base. Analizza WAV,
conserva un catalogo SQLite, confronta brani, propone transizioni, simula due deck e
produce anteprime audio. Include planner deterministico, selettore Qwen locale,
controller a regole, GRU addestrabile, export ONNX, inferenza e bridge MIDI Mixxx.

**È un prototipo di ricerca funzionante, non un DJ autonomo pronto per un live.**
La demo non richiede hardware, internet dopo l'installazione, modelli scaricati né
musica esterna. Tutti i WAV inclusi sono sintetizzati dal codice del progetto.

## Avvio rapido (Ubuntu/Debian, Python 3.10+)

Estrarre `dj.zip`, aprire un terminale nella cartella che contiene `dj/`:

```bash
cd dj
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
dj --version
dj --log results/my-demo.log demo --out examples/my-demo
python -m unittest discover -s tests -v
```

Equivalente senza dipendere dal PATH: `python -m dj ...`.
La demo usa esplicitamente NumPy, anche quando Essentia è installata. I comandi
`demo` rigenerano **solo** `catalog.sqlite` e gli output noti nella directory di
uscita: usare una directory dedicata, mai il proprio catalogo musicale.

Ascolto facoltativo tramite ALSA:

```bash
sudo apt-get install -y alsa-utils
aplay examples/my-demo/preview.wav
```

`preview.wav` contiene **la sola sovrapposizione** (non l'intero DJ set).
`track_1.wav`, `track_2.wav`, `track_3.wav` sono i brani originali, 24 secondi ciascuno.
Nello ZIP sono già presenti `examples/demo/` e i risultati verificati in `results/`.
Leggere [docs/VERIFICATION.md](docs/VERIFICATION.md) per esiti reali e limiti del collaudo.

## Analizzare la propria musica

Base: WAV PCM non compresso 8/16/24/32 bit, mono/stereo, 8–192 kHz, massimo
30 minuti e 256 MiB per file. MP3/AAC/FLAC e WAV float non sono decodificati dalla CLI;
convertire prima con FFmpeg, se installato. Esempio per un file:

```bash
sudo apt-get install -y ffmpeg
ffmpeg -i "canzone.mp3" -ar 22050 -ac 2 -c:a pcm_s16le "canzone.wav"
dj analyze canzone.wav --backend numpy --out results/canzone.json
dj scan canzone.wav examples/demo/track_1.wav --catalog data/library.sqlite --backend numpy
dj catalog --catalog data/library.sqlite
dj plan --catalog data/library.sqlite --out results/plan.json
dj preview --catalog data/library.sqlite --plan results/plan.json --out results/preview.wav
dj simulate --catalog data/library.sqlite --plan results/plan.json --out results/simulation.json
```

`scan` accetta anche directory (ricerca ricorsiva `*.wav`, estensione minuscola).
Per il confronto, sostituire `ID_A` e `ID_B` con gli ID stampati da `catalog`:

```bash
dj compare ID_A ID_B --catalog data/library.sqlite
```

Il catalogo usa SHA-256 abbreviato a 20 cifre esadecimali per identità di contenuto;
l'importazione ripetuta dello stesso file aggiorna la stessa riga. I percorsi sono
relativi alla directory del database: spostare insieme catalogo e brani mantenendo
la struttura. L'analisi non è ricalcolata automaticamente se si modifica un WAV:
rieseguire `scan` (un contenuto diverso produce un nuovo ID). Il renderer verifica
l'hash e rifiuta file modificati dopo l'analisi. SQLite gestisce commit
transazionali; un import parziale conserva i file validi e termina con exit code 2.

## Cosa viene realmente stimato

| Campo | Implementazione e significato |
|---|---|
| BPM/beat NumPy | Novità dell'inviluppo RMS, autocorrelazione 70–180 BPM, griglia a tempo costante e fase stimata. Possibili errori ×2/÷2, swing e variazioni non modellati. |
| Tonalità NumPy | FFT/chroma e correlazione con profili major/minor. La confidenza è il margine tra candidati, non una probabilità. |
| Energia | RMS lineare misurato, non LUFS e non intensità percepita. Confidenza 1 indica misura, non giudizio musicale. |
| Struttura | Finestre di 2 s, etichette low/mid/high energy relative alla mediana; confidenza fissa 0,25, dichiaratamente euristica. |
| Voce | `vocals: null`: nessun riconoscimento voce o separazione stem implementato. |
| Compatibilità | Tempo, tonalità, energia e affidabilità tempo; soglia di variazione velocità ±8%. Non misura la qualità artistica del mix. |
| Transizioni | 8/16/32 beat se la durata lo permette, uscita su beat stimato vicino alla fine, ingresso al primo beat. Non riconosce frasi o ritornelli. |

Silenzio: BPM e tonalità null, beat vuoti, nessuna transizione. Audio troppo breve:
misura l'energia ma può lasciare BPM/tonalità sconosciuti. Valori non finiti e WAV
vuoti/invalidi producono errori espliciti. I file lunghi vengono caricati in memoria;
non è un motore di analisi streaming. Nessuna confidenza è calibrata su un benchmark.

## Anteprima, controller e simulatore

`src/dj/control.py` definisce deck, scheduler stabile, controller a regole e safety.
Il simulatore avanza un clock virtuale a 50 Hz, applica limiti e produce una traccia
JSON. Non usa il clock audio di Mixxx. `src/dj/render.py` interpola la traccia per
applicare il crossfade equal-power, headroom 0,7 e riduzione globale del picco a 0,98.
Non è un limiter dinamico. B viene ricampionato alla velocità necessaria: **pitch e
tonalità cambiano**, non è un time-stretch con key lock. Ricampionamento lineare:
possibile aliasing. L'anteprima non predice esattamente l'audio di Mixxx.

La safety rifiuta NaN/Inf, limita crossfader [-1,1], velocità di variazione e feedback
scaduto. Il deck A si ferma nel simulatore solo se il fade ha raggiunto almeno 0,98;
un limite di slew molto basso può lasciare la transizione incompleta (vedere traccia).

Configurazione reale, chiavi sconosciute rifiutate:

```bash
dj --config configs/default.json simulate --catalog examples/demo/catalog.sqlite --plan examples/demo/plan.json --out results/custom-simulation.json
```

`analysis_backend` influenza `analyze/scan`; `controller_hz` e
`max_crossfader_slew` influenzano preview/simulazione; `feedback_timeout` e slew
influenzano anche MIDI. La demo standard mantiene parametri fissi riproducibili.

## Essentia opzionale

```bash
python -m pip install -e '.[essentia]'
dj analyze examples/demo/track_1.wav --backend essentia --out results/essentia.json
```

`auto` tenta Essentia e ripiega su NumPy se assente o fallisce; il log lo indica.
`essentia` esplicito produce errore se non disponibile/fallisce. Silenzio e audio
<6 s restano al fallback anche con questo selettore. Per Essentia, ricampionamento a
44.100 Hz, `RhythmExtractor2013(method='multifeature')` e `KeyExtractor`:
la confidenza tempo originale è conservata anche in `tempo_confidence_raw`;
il valore /5 clippato è solo un indice, non una calibrazione. Energia/struttura
rimangono NumPy. Disponibilità delle wheel dipende da versione Python/architettura;
se l'extra non si installa, la base resta pienamente utilizzabile.

## Qwen locale opzionale

Nessun modello è incluso. Serve un server **già avviato dall'utente** con endpoint
compatibile `/v1/chat/completions`, per esempio vLLM configurato per Qwen.
Modificare `qwen_model`, `qwen_endpoint`, `qwen_timeout` in `configs/default.json`
in base al modello e alla porta del server locale:

```bash
dj --config configs/default.json --log results/qwen.log plan --catalog examples/demo/catalog.sqlite --out results/qwen-plan.json --qwen
```

Il selettore invia solo le metriche dei primi 20 candidati e sceglie un indice JSON.
Non riceve file audio/percorsi, non inventa comandi, non controlla i deck. Endpoint
HTTP solo loopback, redirect vietati, timeout socket 10 s predefinito, risposta
massima 64 KiB. Errori HTTP/timeout/JSON/indici invalidi → planner deterministico;
`planner_status` rende visibile il fallback. Non è un deadline globale contro un
server che invii lentamente dati senza mai far scadere il timeout socket.
Testato con risposte controllate, **nessun Qwen reale eseguito nell'ambiente**.

## GRU, training reale, export ONNX e inferenza

Per evitare l'installazione non necessaria delle librerie CUDA su Linux CPU:

```bash
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e '.[ml]'
dj dataset --out examples/my-ml/dataset.npz --samples 256 --seed 42
dj train --data examples/my-ml/dataset.npz --out examples/my-ml/controller.pt --epochs 20
dj export --checkpoint examples/my-ml/controller.pt --out examples/my-ml/controller.onnx
dj infer --model examples/my-ml/controller.onnx --data examples/my-ml/dataset.npz --out examples/my-ml/inference.json
dj preview --catalog examples/demo/catalog.sqlite --plan examples/demo/plan.json --onnx examples/my-ml/controller.onnx --out examples/my-ml/preview_gru.wav
```

`src/dj/ml.py`: GRU PyTorch reale, 5 feature → hidden 16 → crossfader tanh.
256 traiettorie sintetiche, 32 step, split 80/20 **per sequenza**, Adam e MSE.
Feature: progress, energia A/B, errore fase, errore tempo. Target: rampa della
regola deterministica. Le ultime due feature non hanno causalità nel target;
il modello NON è addestrato a correggere beat o a giudicare la musica.
`dataset.npz.json` descrive schema/provenienza, `controller.pt.metrics.json`
contiene loss train/validation per epoca. È possibile sostituire il dataset con
le stesse quattro chiavi e forme documentate in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Export ONNX opset 17, forme fisse `[1,32,5]`, h0 `[1,1,16]`, exporter esplicito
`dynamo=False` per la GRU. Checker ONNX + confronto numerico PyTorch/ORT (tolleranza
1e-5). In rollout usa finestra scorrevole, h0 azzerato, prediction vincolata a ±0,1
dalla regola ed endpoint deterministici; segue il limite di slew. Questo rollout
ha una distribuzione temporale diversa dalle sequenze di training: è dimostrativo.
`infer` riporta MSE del primo esempio validation, non dell'intero split.

Il modello incluso è **solo un'imitazione di rampe sintetiche**, non un DJ competente.
Training, export e inferenza sono stati eseguiti davvero; metriche nel rapporto.
Per addestramento musicale servono dati reali, obiettivi e valutazioni separati.

## Mixxx su Linux

Vedere [docs/MIXXX.md](docs/MIXXX.md): mapping `mixxx/DJBridge.midi.xml`, script
`mixxx/DJBridge.js`, bridge `src/dj/midi.py`. Esempio dopo aver configurato ALSA:

```bash
python -m pip install -e '.[midi]'
dj --log results/midi.log midi-serve --seconds 120
# In una nuova esecuzione, dopo il setup manuale descritto in docs/MIXXX.md:
dj --log results/live-fade.log midi-fade --seconds 8 --setup-timeout 120
```

La prima modalità apre le porte e legge feedback, senza automatizzare il mix.
La seconda, solo dopo preflight, avvia B e fa un fade A→B. Richiede caricamento,
cue, tempo, routing audio e assegnazione crossfader **manuali**. Non carica percorsi
via MIDI, non esegue automaticamente i piani offline, non trasmette identità brano,
non dispone di sincronizzazione sample-accurate. Non usa la GRU nel live.
MIDI 7 bit e feedback ogni 100 ms: non adatti a correggere la fase del beat.
Mixxx/ALSA reale non verificato qui; mapping verificato solo con host mock e API primarie.

## Verifiche ripetibili

```bash
python -m unittest discover -s tests -v
# Node è facoltativo, soltanto per il test del mapping:
node tests/test_mapping.js
python scripts/verify.py
# Include training/export/Essentia se le dipendenze sono presenti:
python scripts/verify.py --extras
```

`verify.py` scrive una nuova sessione in `results/rerun/`, senza sovrascrivere le
verifiche consegnate. Nessun test apre una porta MIDI o muove controlli reali.
Exit code CLI: 0 successo, 2 input/dipendenza/operazione non valida, 130 interruzione.
Log su stderr, risultati JSON su stdout; `--log` aggiunge un file.

## Indice dei file

| File / directory | Ruolo |
|---|---|
| `pyproject.toml` | Pacchetto, CLI, extras e intervalli versioni |
| `src/dj/__init__.py`, `__main__.py` | Versione e avvio `python -m dj` |
| `src/dj/cli.py` | Tutti i comandi e demo completa |
| `src/dj/audio.py` | Lettura/scrittura PCM WAV, sintesi, ricampionamento |
| `src/dj/analysis.py` | BPM/beat/chroma/energia/struttura e adapter Essentia |
| `src/dj/catalog.py` | Catalogo SQLite persistente |
| `src/dj/transitions.py` | Compatibilità, candidati e validazione piani |
| `src/dj/planner.py` | Planner deterministico e selettore Qwen |
| `src/dj/control.py` | Stato deck, scheduler, controller e safety |
| `src/dj/render.py` | Preview audio offline e traccia simulata |
| `src/dj/ml.py` | Dataset, GRU, training, export e ORT |
| `src/dj/midi.py` | Bridge ALSA virtuale, feedback, fade con preflight |
| `src/dj/config.py`, `util.py` | Configurazione, validazione numerica, JSON atomico |
| `configs/default.json` | Parametri operativi documentati |
| `configs/constraints-verified.txt` | Versioni esatte dell’ambiente extras verificato |
| `mixxx/DJBridge.js`, `DJBridge.midi.xml` | Script/mapping Mixxx |
| `tests/test_core.py`, `test_ml.py`, `test_qwen_http.py`, `test_mapping.js` | Test Python e contratto JS mock |
| `scripts/verify.py` | Runner delle verifiche riproducibili |
| `scripts/connect_midi.py` | Connessioni ALSA per nome, con dry run |
| `docs/ARCHITECTURE.md` | Flusso, schema dataset e vincoli |
| `docs/MIXXX.md` | Setup Linux, protocollo MIDI, limiti e test locale |
| `docs/SOURCES.md` | Documentazione primaria consultata e scelte API |
| `docs/VERIFICATION.md` | Rapporto esecuzioni e componenti non verificati |
| `examples/demo/` | WAV sintetici, verità nota, catalogo, candidati, piano, traccia, preview |
| `examples/ml/` | Dataset, pesi addestrati, ONNX, metriche, inferenza, preview GRU |
| `results/` | Log grezzi, versioni e riepilogo verifiche |
| `.gitignore`, `LICENSE` | Esclusioni Git e licenza del codice originale |

Il codice può essere importato come libreria; le dipendenze opzionali sono lazy.
Per partire dal progetto come proprio repository: `git init`, poi aggiungere i file
desiderati. I dati generati possono essere grandi: scegliere cosa versionare.
