# Architettura e contratti

`WAV → analisi → SQLite → compatibilità/candidati → planner → piano validato →
controller + safety → simulatore → renderer WAV` è il percorso offline completo.

Il planner è sostituibile: `plans(tracks)` produce candidati e `choose(plans)` ne
sceglie uno. Qwen seleziona soltanto un candidato; una risposta generativa non
può modificare durata, cue, rate o controlli. Il controller espone
`target(progress, energy_a, energy_b, phase_error, tempo_error)` e restituisce una
posizione normalizzata. La safety è esterna e resta obbligatoria.

`Mixxx ↔ script JS ↔ ALSA MIDI ↔ MidiBridge → preflight/Rule fade → Mixxx` è il
percorso live sperimentale. Le due pipeline condividono validazione e safety;
il collegamento piano→cue e velocità live è manuale. Non esiste un RPC nascosto,
una API REST Mixxx inventata o un caricamento automatico di brani.

## Modelli di dati

Catalogo: tabella `tracks(id PRIMARY KEY, path, analysis)`, analisi JSON. Schema
v0.1 senza migrazioni: future versioni dovranno introdurre versionamento esplicito.
ID del contenuto, path relativo al database, durata, sample rate, backend,
BPM opzionale, tempo_confidence, lista beat in secondi, key/key_pc/mode opzionali,
key_confidence, energy RMS, structure a finestre, vocals null.

Piano: ID `a`/`b`, `start_a` e `start_b` in secondi dei file originali, durata in
secondi di playback, `rate_b` = BPM_A/BPM_B. Per B, il tempo sorgente avanza a
`rate_b`. Il renderer legge `start_b + t * rate_b`. Il parametro `beats` indica
la durata in beat al tempo di A; non un riconoscimento di frase musicale.

`DeckState`: ID, durata, posizione, play, volume [0,1], rate [.75,1.25], loaded.
Il clock del simulatore è virtuale. Lo scheduler ordina stabilmente eventi allo
stesso istante. Il MIDI usa clock monotonic per timeout/slew e wall clock nel
watchdog JS: nessuna garanzia hard realtime. In caso di timeout si congela il
controllo; la riproduzione prosegue. Non si attua un mute automatico.

## Dataset e modello

File NPZ, `allow_pickle=False`, quattro array float32:

| Chiave | Forma |
|---|---|
| x_train | [N_train, 32, 5] |
| y_train | [N_train, 32, 1] |
| x_val | [N_val, 32, 5] |
| y_val | [N_val, 32, 1] |

Feature in ordine: progress [0,1], RMS A [0,1], RMS B [0,1], phase_error [-1,1],
tempo_error [-1,1]. Target crossfader [-1,1]. Nessun NaN, split non vuoti.
Per dati reali tenere set/sessioni/brani disgiunti fra train/validation/test per
ridurre leakage. Il dataset sintetico genera progressi non lineari, energie e
piccoli errori; il target dipende SOLO dal progresso.

ONNX: input `features` [1,32,5], `h0` [1,1,16]; output `crossfader` [1,32,1],
`h1` [1,1,16]. Il wrapper rollout ricostruisce la finestra di 32 osservazioni e
azzera h0: non somma stato ricorrente e finestre sovrapposte. L'export a forme
fisse è intenzionale, non promette batch/sequence dinamici.

## Limiti deliberati

- Nessuna classificazione affidabile di struttura, voce, genere o emozione.
- Nessuna separazione stem, scelta effetti, EQ automatica o loudness matching LUFS.
- Nessuna valutazione umana della piacevolezza musicale.
- Key compatibility approssimata: le scale relative non sono trattate come Camelot completo.
- Catalogo locale e CLI, nessuna UI o servizio da mantenere.
- Pesi/checkpoint locali attendibili soltanto; `torch.load(weights_only=True)` è usato.
- Non è un sistema per set live senza supervisione. La sicurezza è sui parametri,
  non sulla qualità sonora o sul livello SPL di una scheda audio esterna.
