# ShinobiCam — Kawarimi no Jutsu per Microsoft Teams

ShinobiCam è una webcam virtuale per Windows 10/11 e macOS (Apple Silicon). Riconosce il sigillo ninja che hai registrato e
riproduce la tecnica della sostituzione: una nuvola di fumo ti copre, sparisci e al tuo posto
compare un tronco di legno. Dopo circa 2 secondi torna il fumo e ricompari. L'effetto viene
applicato al video inviato a Teams, quindi lo vedono anche gli altri partecipanti.

Tutto gira in locale: niente cloud, niente API esterne, nessuna connessione durante l'uso.

```
webcam fisica ─▶ ShinobiCam (mani → sigillo → fumo/tronco) ─▶ OBS Virtual Camera ─▶ Teams
```

---

## 1. Requisiti

| Cosa | Note |
|---|---|
| Windows 10 o 11, 64 bit **oppure** macOS 13+ su Apple Silicon (M1 o successivi) | I Mac Intel non sono supportati: mediapipe non pubblica pacchetti per macOS Intel. |
| Una webcam fisica | |
| **OBS Studio 30 o successivo** | Serve solo per registrare il driver "OBS Virtual Camera". ShinobiCam **non** può installare driver da solo. |

Python non serve per usare l'app: basta l'eseguibile.

### Installare la webcam virtuale (una volta sola)

1. Scarica e installa OBS Studio da <https://obsproject.com>.
2. Apri OBS e premi **Avvia videocamera virtuale** (in basso a destra), poi **Ferma videocamera virtuale**.
3. **Chiudi OBS.** OBS e ShinobiCam non possono usare la webcam virtuale nello stesso momento
   (il dispositivo è uno solo). Mentre usi ShinobiCam, OBS deve restare chiuso o almeno con la videocamera virtuale ferma.

> In Teams il dispositivo compare come **"OBS Virtual Camera"** e non come "ShinobiCam": quel
> nome lo decide il driver di OBS, non l'app. In alternativa puoi usare il backend
> `unitycapture` ([Unity Capture](https://github.com/schellingb/UnityCapture), dispositivo
> "Unity Video Capture"), ma è DirectShow-only e non l'ho verificato con Teams.

### Su macOS

Al punto 2, quando premi **Avvia videocamera virtuale** in OBS, macOS chiede di consentire
l'**estensione fotocamera** di OBS. Approvala in Impostazioni di Sistema; in alcuni casi serve un
riavvio. Le altre regole valgono anche qui, OBS compreso: deve restare chiuso mentre usi ShinobiCam.

## 2. Installazione

**Windows**

1. Estrai `ShinobiCam-win64.zip` dove preferisci (es. `C:\Programmi\ShinobiCam`).
2. Avvia `ShinobiCam\ShinobiCam.exe`.

Se Windows SmartScreen avvisa che l'app non è riconosciuta: **Ulteriori informazioni → Esegui comunque**
(l'eseguibile non è firmato digitalmente).

**macOS**

1. Estrai `ShinobiCam-macos-arm64.zip` e sposta `ShinobiCam.app` in **Applicazioni**.
2. Al primo avvio fai **clic destro → Apri**. L'app ha solo una firma ad-hoc e non è notarizzata,
   quindi Gatekeeper la blocca col doppio clic. Se macOS la dichiara "danneggiata", esegui
   `xattr -dr com.apple.quarantine /Applications/ShinobiCam.app`.
3. Quando avvii la webcam, consenti l'accesso alla **Fotocamera**.

## 3. Primo utilizzo

1. **Webcam fisica**: scegli la tua webcam. Non selezionare "OBS Virtual Camera" come sorgente:
   l'app lo segnala e lo blocca.
2. **Avvia webcam virtuale**. In alternativa usa **Solo anteprima (simulazione)** per provare
   senza inviare nulla a Teams.
3. **Calibra sfondo**: hai 5 secondi per uscire dall'inquadratura, poi l'app acquisisce la stanza
   vuota. Così durante la sostituzione sparisci davvero. La webcam non deve muoversi: se la
   sposti o cambia molto la luce, ricalibra.
   - Senza calibrazione l'app funziona in **modalità semplificata**: il tronco compare davanti a te
     ma resti visibile. Il pannello "Stato" lo indica in arancione.
4. **Registra sigillo**: dopo 3 secondi di preparazione esegui il sigillo e tienilo per 4 secondi,
   muovendo leggermente le mani. Le mani devono essere ben illuminate e dentro l'inquadratura.
5. **Prova**: esegui il sigillo e tienilo per circa 0,3 s. Se il riconoscimento non scatta,
   premi **F9**.

Sequenza dell'effetto: fumo (0,5 s) → tronco (1,8–2,5 s, regolabile) → fumo (0,5 s) → cooldown
(3–5 s, regolabile), durante il quale il sigillo viene ignorato.

### F9 (attivazione manuale)

Su Windows F9 viene registrato come scorciatoia **globale**, quindi funziona anche quando la
finestra attiva è Teams. Se un'altra app usa già F9, il pannello Stato mostra "F9 (solo con
finestra attiva)".

Su macOS F9 funziona **solo con la finestra di ShinobiCam attiva** e va premuto con **fn+F9**.
Durante una riunione usa il sigillo, oppure clicca **Testa sostituzione**. Su Mac non ho
implementato una scorciatoia globale: richiederebbe il permesso Accessibilità e librerie che
con Tkinter tendono a causare crash.

## 4. Configurare Microsoft Teams

1. Avvia ShinobiCam e premi **Avvia webcam virtuale**. Il pallino diventa verde:
   "Webcam virtuale attiva: OBS Virtual Camera".
2. In Teams (anche su Mac): **… (Impostazioni e altro) → Impostazioni → Dispositivi → Fotocamera** → scegli
   **OBS Virtual Camera**. Durante una riunione puoi farlo anche dalla freccia accanto al
   pulsante **Fotocamera**.
3. Se il dispositivo non compare, chiudi completamente Teams (anche dall'icona nell'area di
   notifica) e riaprilo dopo aver avviato ShinobiCam.

Non servono plugin né modifiche a Teams. Finché ShinobiCam è in esecuzione la webcam virtuale
resta attiva. Se la webcam fisica si scollega, Teams vede una schermata "webcam non disponibile"
e il video riprende da solo quando la webcam torna.

**Ripristina webcam normale** interrompe subito l'effetto e disattiva il riconoscimento: Teams
riceve il video della webcam senza modifiche. Per spegnere tutto premi **Arresta**.

## 5. Impostazioni

| Controllo | Effetto | Quando si applica |
|---|---|---|
| Risoluzione | 1280×720 (predefinita), 640×360 o 640×480 per PC lenti | al prossimo Avvia |
| FPS | 30 / 24 / 15 | al prossimo Avvia |
| Backend | `obs` (predefinito) / `unitycapture` | al prossimo Avvia |
| Soglia confidenza | più alta = meno falsi positivi, più bassa = riconosce più facilmente | subito |
| Cooldown | pausa dopo ogni jutsu (3–5 s) | subito |
| Durata tronco | 1,8–2,5 s | al prossimo jutsu |
| Debug | mostra landmark delle mani e confidenza **solo nell'anteprima locale**; a Teams non arrivano | subito |
| Carica tronco PNG | usa un tuo PNG con trasparenza al posto del tronco incluso | al prossimo jutsu |

I dati utente (impostazioni, sigillo, sfondo, log) sono in `%APPDATA%\ShinobiCam` su Windows
e in `~/Library/Application Support/ShinobiCam` su macOS.

Il tronco incluso è un asset originale generato via codice (`tools/make_assets.py`). Non vengono
usati materiali grafici di terzi.

## 6. Risoluzione dei problemi

| Sintomo | Soluzione |
|---|---|
| "Webcam virtuale non trovata" | Installa OBS 30+ ed esegui la procedura del §1 (avvia/ferma la videocamera virtuale una volta). |
| "La webcam virtuale è già in uso" | Chiudi OBS o ferma la sua videocamera virtuale; chiudi altre istanze di ShinobiCam. |
| Teams non mostra "OBS Virtual Camera" | Riavvia Teams dopo aver avviato ShinobiCam; controlla che il pallino sia verde. |
| Teams mostra un'immagine nera o ferma | Premi **Arresta** e poi **Avvia**; verifica che nessun'altra app stia usando la webcam fisica (Teams compreso: in Teams scegli OBS Virtual Camera, non la webcam fisica). |
| "Webcam non disponibile, nuovo tentativo..." | La webcam fisica è occupata da un'altra app o è scollegata. Chiudi le altre app o ricollegala: la riconnessione è automatica. |
| Il sigillo non viene riconosciuto | Attiva Debug e controlla la confidenza: se resta sotto la soglia, abbassala oppure registra di nuovo il sigillo con luce migliore. Usa F9 come riserva. |
| Il sigillo scatta da solo | Alza la soglia; registra un sigillo più distintivo (non mani aperte o a riposo). |
| Mani sovrapposte non riconosciute | Durante la registrazione esegui il sigillo così come lo farai davvero: vengono salvate anche le pose in cui MediaPipe vede una sola mano. |
| Durante il tronco si vede "un fantasma" di me | Lo sfondo non è più valido (luce cambiata, webcam spostata, esposizione automatica): ricalibra lo sfondo. |
| FPS bassi / CPU alta | Usa 640×360 e/o 24 FPS. Il riconoscimento gira su un thread separato e non rallenta il video. |
| Riconoscimento "non disponibile" | Il modello `models\hand_landmarker.task` manca dal pacchetto: reinstalla lo zip. Nel frattempo F9 funziona. |
| macOS: "webcam non disponibile" anche se la webcam funziona | Impostazioni di Sistema → Privacy e sicurezza → Fotocamera: abilita ShinobiCam (o il Terminale, se lo avvii da sorgente). |
| macOS: l'app si chiude appena avvio la webcam | Usa l'app generata da `scripts/build.sh`: contiene il permesso fotocamera nell'Info.plist. |
| macOS: "Webcam virtuale non trovata" con OBS installato | Apri OBS, avvia la videocamera virtuale e approva l'estensione in Impostazioni di Sistema; poi riavvia il Mac. |
| Qualcos'altro | Allega `%APPDATA%\ShinobiCam\shinobicam.log`. Esegui `ShinobiCam.exe --selftest` e leggi `%APPDATA%\ShinobiCam\selftest.txt`. |

---

## 7. Sviluppo

Serve Python 3.11 x64.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1   # .venv, dipendenze, modello (verifica SHA-256), controllo OBS
.venv\Scripts\python.exe -m shinobicam                        # avvia la GUI
.venv\Scripts\python.exe -m pytest -q                         # test
.venv\Scripts\python.exe -m shinobicam.simulate demo.mp4      # video dimostrativo senza webcam né Teams
```

Con `simulate` puoi usare anche immagini tue: `--background stanza.png --person io.png`
(stessa risoluzione), oppure `--no-plate` per vedere la modalità semplificata.

Su macOS:

```bash
./scripts/setup.sh                                  # .venv, dipendenze, modello, controllo OBS
.venv/bin/python -m shinobicam                      # GUI (il Terminale chiederà il permesso Fotocamera)
.venv/bin/python -m pytest -q
```

### Build dell'eseguibile

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

Lo script esegue i test, lancia PyInstaller (`ShinobiCam.spec`, build `--onedir`), avvia
`ShinobiCam.exe --selftest` e crea:

- `dist\ShinobiCam\ShinobiCam.exe`, con le risorse in `dist\ShinobiCam\_internal\`
  (modello, asset, `libmediapipe.dll`);
- `dist\ShinobiCam-win64.zip`, da distribuire.

Su macOS `./scripts/build.sh` crea `dist/ShinobiCam.app` (con il permesso fotocamera
nell'Info.plist), ne esegue il selftest e produce `dist/ShinobiCam-macos-arm64.zip`.

Il workflow `.github/workflows/build.yml` fa la stessa cosa su runner Windows e macOS di
GitHub e pubblica gli zip come artifact.

### Dipendenze (versioni bloccate)

| Pacchetto | Versione | Perché |
|---|---|---|
| mediapipe | 0.10.35 | Ultima della serie 0.10 (Tasks API stabile). La 1.1.0 era uscita da pochi giorni ed è una nuova major. |
| opencv-contrib-python | 4.14.0.94 | È la build richiesta da mediapipe. Non installare anche `opencv-python`, va in conflitto. Ho evitato OpenCV 5.0 (nuova major). |
| numpy | 2.4.6 | Ultima serie compatibile con Python 3.11 (la 2.5 richiede 3.12). |
| pyvirtualcam | 0.15.0 | Backend OBS / Unity Capture su Windows. |
| pillow | 12.3.0 | Anteprima Tk e icona. |
| pygrabber | 0.2 | Nomi delle webcam via DirectShow (solo Windows). Su macOS i nomi arrivano da `system_profiler`, nessuna dipendenza in più. |
| pyinstaller / pytest | 6.22.3 / 9.1.1 | Build e test. |

Note sul packaging: mediapipe ≥ 0.10.30 carica `libmediapipe.dll` tramite `ctypes` da
`mediapipe/tasks/c`. PyInstaller non rileva questo caricamento, quindi lo spec include
esplicitamente `collect_dynamic_libs("mediapipe")` e il package `mediapipe.tasks.c`.

### Architettura

```
shinobicam/
  app.py               entry point, logging, --selftest, --simulate
  ui.py                GUI Tkinter
  pipeline.py          thread: render/output a FPS fissi + inferenza separata; comandi via coda
  camera_manager.py    cattura con riconnessione automatica, slot "ultimo frame" (scarta i frame vecchi)
  gesture_detector.py  MediaPipe Hand Landmarker, descrittore normalizzato, profilo, filtro temporale
  gesture_calibration.py  registrazione guidata del sigillo
  effect_engine.py     macchina a stati IDLE→SMOKE_IN→SUBSTITUTION→SMOKE_OUT→COOLDOWN, tronco, composizione
  smoke_renderer.py    fumo a particelle stile anime (opaco garantito al picco)
  background_manager.py  sfondo pulito + localizzazione della persona per differenza
  virtual_camera.py    pyvirtualcam + messaggi d'errore comprensibili
  hotkey.py            F9 globale (RegisterHotKey)
  simulate.py          simulazione offline
assets/  log.png, icon.ico (originali, rigenerabili con tools/make_assets.py)
models/  hand_landmarker.task (scaricato da setup.ps1)
tests/   pytest
```

Come funziona il riconoscimento: i 21 landmark di ogni mano vengono resi indipendenti da
posizione, scala e rotazione. Le due mani si ordinano per posizione sullo schermo e non per
etichetta Sinistra/Destra, perché MediaPipe la scambia quando le mani si incrociano. La
registrazione salva decine di campioni, raggruppati per numero di mani visibili, e una
tolleranza ricavata dalla loro dispersione. Durante l'uso la confidenza dipende dalla distanza
dal campione più vicino. Il jutsu parte solo se la confidenza resta sopra soglia per 300 ms; le
perdite brevi (< 200 ms) sono tollerate. Dopo lo scatto il sigillo va rilasciato prima di
poterlo riattivare.

Come funziona la scomparsa: al picco di opacità del fumo l'immagine passa dalla webcam allo
sfondo calibrato con il tronco sovrapposto. Il tronco viene posizionato sul busto, ricavato dalla
differenza con lo sfondo, oppure dalla posizione delle mani. Al secondo picco di fumo torna
l'immagine reale. I test verificano che il fumo copra il 100% dell'area nel momento del cambio.

## 8. Stato della verifica

Verificato su macOS (Apple Silicon):

- 51 test automatici superati: gesti, soglie/cooldown, macchina a stati, rendering, composizione
  con sfondo, modello mancante, webcam assente o persa, backend non installato o occupato,
  arresto durante l'animazione, asset nel bundle, overlay di debug assente dal flusso inviato,
  GUI Tk;
- cattura da webcam reale a 720p e MediaPipe su frame reali (~18 ms per inferenza);
- build PyInstaller con lo stesso `.spec` ed esecuzione del binario congelato (`--selftest` e `--simulate`);
- messaggio reale di pyvirtualcam quando OBS non è installato;
- **flusso completo su Mac**: webcam reale → effetto → OBS Virtual Camera a 30 FPS. Ho riletto
  il dispositivo virtuale da un altro processo, come fa un'app di videochiamata, e c'erano
  fumo, tronco e ritorno;
- `scripts/setup.sh` e `scripts/build.sh`, `ShinobiCam.app` con permesso fotocamera, selftest
  dell'app che apre la OBS Virtual Camera;
- nomi delle webcam su Mac nello stesso ordine degli indici OpenCV (verificato inviando un
  colore noto alla camera virtuale).

**Non verificato**: Teams su Mac (il dispositivo virtuale funziona, ma non ho aperto Teams),
l'avvio di `ShinobiCam.app` da Finder su un altro Mac (Gatekeeper), l'esecuzione su Windows, l'eseguibile `.exe`, gli script PowerShell, il
backend OBS su Windows e la comparsa della webcam virtuale in Microsoft Teams. Non avevo
accesso a una macchina Windows. Il workflow GitHub Actions compila e fa il selftest dell'exe su
Windows a ogni push, ma non può provare Teams. Prima di usarlo in una riunione vera, provalo
in una riunione di test.

## Licenza

MIT (vedi `LICENSE`). Il modello MediaPipe Hand Landmarker è di Google, licenza Apache 2.0.
