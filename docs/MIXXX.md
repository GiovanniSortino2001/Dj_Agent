# Mixxx: integrazione live sperimentale su Linux

## Stato delle verifiche

API consultate nel manuale 2.5 e wiki ufficiale. Script testato in Node con engine
e midi simulati. Le librerie Python MIDI si importano, ma questo ambiente non
espone `/dev/snd/seq`: l'apertura di una porta virtuale fallisce. Non è stato
eseguito Mixxx e non si dichiara un test audio/MIDI end-to-end riuscito.

Il bridge non espone una API di caricamento file. Si prepara una singola
transizione manualmente, poi si automatizza il crossfade con feedback. I risultati
del planner offline servono come guida: ID, file, cue, durata, `rate_b`; non sono
trasmessi automaticamente a Mixxx. Il MIDI non contiene identità dei file.

## Installazione e mapping

Dalla radice del repository, ambiente virtuale attivo:

```bash
sudo apt-get install -y mixxx alsa-utils libasound2-dev
python -m pip install -e '.[midi]'
mkdir -p "$HOME/.mixxx/controllers"
cp mixxx/DJBridge.js mixxx/DJBridge.midi.xml "$HOME/.mixxx/controllers/"
aconnect -l
```

Il percorso sopra è quello utente tipico di Mixxx Linux. Con Flatpak/Snap il profilo
può essere in un'altra directory: usare la cartella controller del profilo reale.
Per log di debug avviare `mixxx --controller-debug` da terminale.

Usiamo una porta **ALSA MIDI Through duplex**, visibile sia a Mixxx sia a Python.
Se `aconnect -l` non mostra una porta `Midi Through Port-0`:

```bash
sudo modprobe snd-seq-dummy
aconnect -l
```

Se il kernel non supporta il modulo o manca `/dev/snd/seq`, fermarsi: serve ALSA
sequencer nell'host, non basta installare mido in un container.

## Prova di solo feedback

Terminale 1:

```bash
dj --log results/midi-monitor.log midi-serve --seconds 120
```

Terminale 2, finché le porte virtuali sono aperte:

```bash
python scripts/connect_midi.py --dry-run
python scripts/connect_midi.py
aconnect -l
```

Lo script individua per nome `DJ-to-Mixxx`, `DJ-from-Mixxx` e la porta Through,
rifiuta ambiguità e invoca `aconnect` per le due connessioni. Nomi/ID variano per
host; `--through 'nome univoco'` seleziona un'altra porta. Non presumere che gli
ID numerici di un esempio siano uguali sul proprio PC. Se le connessioni sono già
presenti, `aconnect` può terminare nonzero: controllare l'elenco, non duplicarle.

In Mixxx → Preferenze → Controller:

1. Selezionare il dispositivo **Midi Through**, ingresso e uscita corrispondenti.
2. Caricare il preset **DJ Offline Lab Bridge** e abilitarlo.
3. Assicurarsi che Mixxx invii l'output sulla stessa porta Through duplex.
4. Muovere manualmente il crossfader: il log Python deve riflettere il valore;
   caricare un brano e verificare `loaded`, poi `playing`.

Percorso comandi: Python out → Through → ingresso Mixxx.
Percorso feedback: uscita Mixxx → Through → Python in.
Il Through può anche rimandare l'evento al mittente: CC comandi e feedback sono
disgiunti, quindi gli echi non vengono trattati come feedback/comandi validi.
Non collegare output di mapping diversi o un loop MIDI aggiuntivo sulla stessa
porta. La modalità monitor non manda heartbeat di arming e non controlla i deck.

Il pairing/discovery dei dispositivi dipende dal backend della build Mixxx;
se non è possibile selezionare la coppia Through, configurare le porte nel backend
locale e verificare prima il solo monitor. Questo routing è una procedura da
verificare sull'host, non un risultato già dimostrato nel container.

## Fade reale controllato

Prima di lanciare il comando:

- In Sound Hardware configurare **Master output** sulla scheda desiderata e, se
  disponibile, cuffie/preascolto separati. MIDI non trasporta audio.
- Caricare A su deck 1, B su deck 2. Verificare personalmente i file del piano.
- Assegnare deck 1 a sinistra e deck 2 a destra del crossfader, reverse/hamster OFF.
  Queste assegnazioni non sono incluse nel feedback e non sono verificate dal codice.
- Impostare curva di mixing/constant power nelle preferenze. Il suono dipende dalla
  curva di Mixxx; non assumere uguaglianza numerica con la preview offline.
- Volume deck entrambi a 1; crossfader completamente a sinistra. Regolare gain/master
  per headroom in cuffia. ReplayGain/EQ/effetti di Mixxx restano impostazioni manuali.
- A già in play con abbastanza tempo restante; B caricato, in pausa al cue d'ingresso.
  Allineare BPM e cue manualmente, eventualmente usando sync/beatgrid di Mixxx.
  Il comando avvia B appena ricevuto il feedback: **non attende il prossimo beat**.

Chiudere il monitor. Terminale 1:

```bash
dj --log results/midi-fade.log midi-fade --seconds 8 --setup-timeout 120
```

Terminale 2, dopo l'apertura delle nuove porte:

```bash
python scripts/connect_midi.py
```

Le porte vengono ricreate a ogni esecuzione, quindi le connessioni vanno ristabilite.
Il comando aspetta al massimo setup-timeout per il **primo** frame valido, poi
controlla i prerequisiti e termina se non soddisfatti. Non aspetta indefinitamente
che l'utente prepari i deck. Prepararli prima di collegare il feedback.

Sequenza: preflight → heartbeat/arming → `play=1` su B → attesa feedback play
(max 2 s) → fade a 50 Hz con feedback max 0,5 s → disarm.
A e B restano in riproduzione alla fine: fermare A manualmente.
Il protocollo consente anche volume e play assoluto, ma la CLI non cambia volume.
Nessun seek, rate, caricamento, sync o effetto viene comandato.

## Protocollo implementato

Numeri di canale nella tabella: **zero-based** (0 = canale MIDI 1).

| Direzione | Canale / CC | Valore |
|---|---|---|
| Python→Mixxx | 0 / 118 | 127 rinnova heartbeat, 0 disarma |
| Python→Mixxx | 0 / 1 | Crossfader 0…127 → -1…1 |
| Python→Mixxx | 0 o 1 / 7 | Volume 0…127 → 0…1 |
| Python→Mixxx | 0 o 1 / 10 | Play assoluto: >=64 acceso, altrimenti spento |
| Mixxx→Python | 0 / 117 | Inizio frame, contatore 0…127 |
| Mixxx→Python | 0 o 1 / 20 | Stato play 0/127 |
| Mixxx→Python | 0 o 1 / 21 | Posizione normalizzata ×127 |
| Mixxx→Python | 0 o 1 / 22 | BPM /2 (saturato a 254 BPM) |
| Mixxx→Python | 0 o 1 / 23 | Track loaded 0/127 |
| Mixxx→Python | 0 o 1 / 24 | Volume ×127 (saturato a 1) |
| Mixxx→Python | 0 / 25 | Crossfader normalizzato ×127 |
| Mixxx→Python | 0 / 119 | Fine frame con medesimo contatore |

Frame completo di 13 messaggi ogni 100 ms. Python pubblica solo frame completi
con marcatori coerenti. MIDI ordina i messaggi; non si implementa un protocollo
ACK/retry per ogni controllo. La risoluzione di posizione per 5 minuti è circa
2,36 secondi: inutilizzabile come beat-phase feedback. BPM quantizzato a 2 BPM,
crossfader a 128 livelli. Precisione scheduling non sample-accurate.

## Safety e guasti

NaN/Inf e valori fuori range rifiutati, slew limit in Python, salti >0,12 rifiutati
nello script, watchdog JS a 500 ms senza heartbeat. Feedback assente/scaduto,
ritardo scheduler >200 ms, deck non in play o crossfader esterno divergente >0,2
interrompono il fade. La chiusura disarma lo script senza fermare i brani.

**Freeze non significa stop audio**: il fader resta all'ultimo valore. Se B è già
partito, continuerà a suonare. Il fallback richiede intervento umano; non esiste
un'uscita di emergenza audio garantita. `Ctrl+C` interrompe e disarma nel finally.

Prove locali prima di un uso reale: volume basso/cuffie, perdita cavo/connessione,
chiusura Python, rimozione brano, intervento manuale sul fader, fine brano durante
fade. Verificare che il fader si blocchi e che i log mostrino l'errore atteso.
La presenza di `track_loaded` non prova quale file sia caricato né che l'audio
stia raggiungendo un'uscita: questo resta fuori dal protocollo.
