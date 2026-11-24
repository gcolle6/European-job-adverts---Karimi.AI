# Piano di sviluppo: dal must_have grezzo al requisito normalizzato, come servizio

Scritto il 2026-11-04. Trasforma il metodo di split e normalizzazione, oggi una
serie di script locali, in una libreria e un servizio che gli sviluppatori di
Karimi possono usare. Comprende un agente che controlla i risultati e uno che
li valuta.

---

## 1. Vincoli

**Solo Europa.** Ogni dato, log, traccia, modello e chiamata LLM resta in una
regione europea di Google Cloud, sotto la normativa europea (GDPR, AI Act).
Deciso il 2026-11-04, per ragioni etiche.

**Permessi.** Deciso il 2026-11-04: non serve un consenso di Karimi per
spostare i dati in cloud. I dati sono una piccola frazione dei loro e sono
annunci pubblici. Il vincolo europeo resta.

**Karimi usa la libreria, non l'API.** Deciso il 2026-11-04, per il costo: con
l'API il calcolo gira sul progetto GCP del proprietario, con la libreria sulle
macchine di Karimi. Tutto ciò che l'API dava c'è anche nella libreria, report
di run compreso (`process`). Il codice dell'API resta nel progetto, ma non viene
offerto: si riattiva senza rifare niente se Karimi lo chiede o non lavora in
Python. Conseguenza: il vincolo europeo non è più garantito da noi per le loro
run, perché girano dove le installano. Resta una raccomandazione scritta nella
guida, e vale per tutto ciò che gira da noi (test, lotti nostri, agente tester).

**Cosa resta deterministico.** Lo split e la normalizzazione restano regole e
modelli locali (spaCy, opus-mt, embedding). Un LLM entra solo dove è stato
misurato meglio delle regole. Sul campione etichettato un LLM applicato a tutto
ha fatto peggio delle regole: 0,63/0,52 contro 0,69/0,56.

---

## 2. Dove siamo

| Pezzo | Stato | Misura |
|---|---|---|
| Split dei requisiti | regole + spaCy, traduzione opus-mt prima | conteggio cieco: 78% delle righe con il numero giusto di requisiti |
| Normalizzazione (anni, livello, testa, nucleo) | regole | 138 test |
| `req_group`, stesso requisito | embedding, soglia 0,90 | unioni giuste 14 su 15 (93%) |
| `req_topic`, stesso tema | gruppi uniti a 0,80, annidati | 29 coppie su 29 tra 0,80 e 0,90 giudicate uguali |
| Ruoli (`title_group`) | regole, Developer = Engineer solo per 62 casi | unioni sbagliate 0 su 9, unioni mancate 3 su 21 (dopo le correzioni, non alla cieca) |
| File | `must_have_atoms.parquet`, `titles.parquet` | uniti per `posting_id` |

Con 15 coppie per casella ogni percentuale ha un margine di circa ±12 punti.

Ciò che manca prima di un servizio:
- **un dizionario congelato**: oggi i gruppi si calcolano su tutto il corpus
  insieme, quindi un requisito nuovo da solo non ha un gruppo;
- **i numeri per versione**: un risultato non dice con quali regole è stato
  fatto.

---

## 3. Architettura

| # | Pezzo | Cosa fa | Strumento | Regione UE |
|---|---|---|---|---|
| 1 | Libreria | split e normalizzazione nel codice Python di Karimi, con `process()` | pacchetto pip | gira dove gira il codice di Karimi |
| 2 | Versioni | ogni riga dice con quali regole e quale dizionario è fatta | `rules_version`, `dict_version` | — |
| 3 | Test automatici | ogni modifica delle regole passa dai test e dalle misure | pytest, Cloud Build | build in regione UE |
| 4 | API (non offerta) | la stessa cosa via HTTP, solo se Karimi la chiede | FastAPI, Cloud Run | `europe-west*` |
| 5 | Job a lotti | elabora molti annunci insieme | Cloud Run Job, Workflows | `europe-west*` |
| 6 | Dati | annunci in ingresso, requisiti in uscita | Cloud Storage, BigQuery | bucket e dataset in UE |
| 7 | Agente monitor | calcola le misure di ogni lotto e avvisa se peggiorano | Cloud Scheduler, Cloud Monitoring | metriche e log in UE |
| 8 | Osservabilità | traccia ogni lotto: tempi, errori, regole scattate | OpenTelemetry, Cloud Trace, Cloud Logging | bucket di log in UE |
| 9 | Agente tester | giudica coppie e conteggi al posto dell'etichettatore | Vertex AI (Gemini o Claude), DeepEval | endpoint regionale UE |

Fuori dal piano: **RAGAS**, che misura sistemi RAG (fedeltà al contesto
recuperato), mentre qui non si recupera niente. E un LLM che faccia tutto lo
split.

**Stato reale al 2026-11-06**, riga per riga (dove diverge dalla tabella sopra,
vale questo):

| # | Pezzo | In piedi? | Come |
|---|---|---|---|
| 1 | Libreria | ✅ in locale | `karimi_normalise.process()`; non ancora distribuita: il magazzino Python `karimi-py` esiste, `release.sh` non è stato lanciato |
| 2 | Versioni | ✅ | `rules_version` e `dict_version` su ogni riga; impronta delle regole controllata da un test; sha256 di ogni file del dizionario |
| 3 | Test | ✅ in locale, non in cloud | 24 test veloci e 3 gate; Cloud Build non li lancia, perché i gate leggono etichette che restano sul PC. Hook pre-commit scritto, non attivato |
| 4 | API | ⏳ deploy in corso | FastAPI su Cloud Run, chiave API per la prova; container provato in locale. **Ora offerta**, per la prova con Chiara |
| 5 | Job a lotti | ⏳ deploy in corso | Cloud Run Job `karimi-batch`, a blocchi da 500; senza Workflows, che non serve |
| 6 | Dati | ✅ | bucket UE: lavori (cancellati dopo 30 giorni), dizionari, appoggio delle build. **Niente BigQuery**: file JSONL e CSV, e lo storico in `history/runs.jsonl` |
| 7 | Agente monitor | ⏳ codice provato, deploy dopo l'API | è il controllore `check.py` (livelli 1, 2, 4) e `karimi-sweep` ogni mattina; avviso email dai log |
| 8 | Osservabilità | ⏳ in parte | righe JSON per richiesta e per blocco, metriche dai log, dashboard Cloud Monitoring. **Non c'è OpenTelemetry**: niente span per passo, solo l'id di traccia di Cloud Run sulle richieste |
| 9 | Agente tester | ✅ tarato, ⏳ in cloud | **Qwen3-4B in locale con llama.cpp, dentro il job `karimi-check`**, non Vertex AI; niente DeepEval. Livello 3 del controllore |

### Struttura del codice (creata il 2026-11-04)

Niente gira ancora in cloud. Tutto è provato in locale.

| File | Pezzo | Stato |
|---|---|---|
| `karimi/` | le regole, **le stesse** dell'analisi | esistente |
| `karimi_normalise/process.py` | `process(postings)`: la sola chiamata per Karimi, con il report | funziona |
| `karimi_normalise/requirements.py` | `split_posting(items)`: traduzione, split, normalizzazione, colonne | funziona |
| `karimi_normalise/translate.py` | traduzione con `TranslationCache` | funziona |
| `karimi_normalise/titles.py` | `normalise_title(title)` | funziona |
| `karimi_normalise/dictionary.py` | ricerca nel dizionario: `known` / `group` / `topic` / `nuovo` | funziona |
| `karimi_normalise/freeze.py` | congela un dizionario con versione; `--diff` dice cosa si è spostato | funziona |
| `karimi_normalise/versions.py` | `RULES_VERSION` e l'impronta del codice delle regole | funziona |
| `karimi_normalise/parity.py` | confronto libreria e batch | funziona |
| `karimi_normalise/metrics.py` | report di ogni run: segnali con semaforo e lista da controllare | funziona |
| `karimi_normalise/reference.py` | le bande di una run normale, salvate col dizionario | funziona |
| `karimi_normalise/quality.py` | la scheda di qualità per versione, generata dagli script di misura | funziona |
| `karimi_normalise/site_data.py` | le tabelle per il sito: scheda, versioni, coseno, run | funziona |
| `karimi_normalise/api.py` | `/health`, `/quality`, `/split`, `/title`, `/batch` (con il report) | provata in locale |
| `karimi_normalise/CHANGELOG.md` | una riga per ogni cambio di regole o dizionario | iniziato |
| `tests/test_library.py` | 138 casi, impronta, impostazioni di traduzione, dizionario modificato | 5/5 |
| `pyproject.toml` | il pacchetto pip `karimi-normalise` | scritto |
| `deploy/eu_setup.sh` | fase 0: policy UE, log in UE, budget | **non eseguito** |
| `deploy/cloudbuild.yaml`, `deploy/Dockerfile` | fasi 2-3: test, poi immagine in UE | **non eseguito** |

Prima misura di parità, 100 annunci dev: **97,8% degli elementi identici** al
batch. Le 15 differenze lette (su 17) sono tutte regole P10–P15 arrivate dopo il batch,
e in quasi tutte la libreria fa meglio (`Ability to work nights` invece di
`Ability to nights`). Quindi il batch va rigenerato prima di congelare il
dizionario vero: la decisione aperta 2 ora ha la sua prova.

### Scheda di qualità e report di run (2026-11-04)

Due cose diverse, che usano gli stessi numeri:

- **Scheda di qualità**, una per versione: quanto è giusto il metodo, misurato
  su etichette umane. `python -m karimi_normalise.quality --dict <versione>`.
- **Report di run**, in ogni risposta di `/batch`: quanto la run somiglia ai
  dati misurati, con un semaforo per segnale e la lista da controllare. Non
  dice quanto è giusta: su una run non ci sono etichette.

Il riferimento si calcola quando si congela il dizionario. Il 90% degli
annunci fa il dizionario, il 10% viene cercato come una run nuova. Risultato
sul dizionario `0.0.dev2`:

| Su annunci mai visti | |
|---|---|
| requisiti già noti | 59,6% |
| gruppo trovato per somiglianza (≥ 0,90) | 10,8% |
| solo tema (0,80–0,90) | 11,5% |
| nuovi (< 0,80) | 18,1% |
| titoli nuovi | 38% |

E l'accordo con il batch, che è il criterio 2 della fase 1:
- gruppo per somiglianza uguale al batch: **76,8%**;
- solo tema, tema uguale al batch: **46,3%**. È la fascia più debole.

Due cose da migliorare prima del rilascio: la ricerca per i titoli (il 38%
nuovi è alto, perché oggi un titolo si unisce solo a chiave identica) e la
fascia "solo tema".

### Verso il rilascio a Karimi (2026-11-04)

| # | Passo | Stato |
|---|---|---|
| 1 | Batch rigenerato con P10–P15, dizionario `0.1.0` | ✅ parità 100%, soglie superate. Il 98,4% delle occorrenze resta nello stesso gruppo |
| 2 | Titoli cercati anche come varianti | ✅ ma i titoli nuovi scendono solo da 38,0% a 36,9%: non sono varianti di grafia, sono ruoli davvero diversi. La leva è `title_family` |
| 3 | Test automatici | ✅ 11 veloci a ogni commit (`.githooks/pre-commit`, da attivare con `git config core.hooksPath .githooks`); 3 soglie che bloccano il rilascio (`pytest -m gates`), fissate prima della misura |
| 4 | Pacchetto e guida | ✅ installazione base + `[translate]` + `[embed]`; traduzione a scelta di Karimi, embedding fisso; guida in `karimi_normalise/README.md`. Manca il canale di consegna (repository privato) |
| 5 | Storico del monitor | ✅ `log_run()` scrive una riga per run, senza testo degli annunci |
| 6 | Agente tester | ✅ Qwen3-4B in locale, prompt v5, tarato (vedi Fase 6). Gira dentro il job `karimi-check` |

Ancora deboli, e scritti nella guida: la fascia "solo tema" (46% uguale al
batch), i titoli nuovi (37%), le lingue senza modello di traduzione.

### Stato al 2026-11-05: API, controllore, sito

Deciso oggi, per la prova con Karimi (contatto: Chiara), entro il 6 novembre:

| # | Cosa | Stato |
|---|---|---|
| 1 | API su Cloud Run (`/v1/process` fino a 200 annunci; `/v1/jobs` per i lotti) | ✅ codice e 12 test; provata nel container (`karimi:local`, 9,2 GB) |
| 2 | Accesso con **chiave API** (`X-API-Key`, segreto in Secret Manager) | ✅ scelta per la prova; IAM resta la strada se diventa stabile |
| 3 | **Ogni chiamata** salvata come lavoro e controllata (`source: process`) | ✅ risultati, report, CSV, `check.json`; riga nello storico |
| 4 | Due CSV per Karimi: `postings.csv` (i campi inviati + colonne aggiunte) e `requirements.csv` | ✅ `exports.py` |
| 5 | Controllore a 4 livelli con il giudice dentro un secondo job (`karimi-check`) | ✅ `check.py`, 7 test; riferimento del giudice: 4,7% bocciate su gruppo, 11% su tema; container provato (`karimi-check:local`, 6,2 GB, llama.cpp b7923) |
| 6 | `GET /v1/metrics`, pubblico, solo aggregati: ciò che il sito legge | ✅ `dashboard.py` |
| 7 | Osservabilità: una riga JSON per richiesta e per blocco di lavoro, metriche dai log, dashboard Cloud Monitoring, avviso email | ✅ `deploy/dashboard.json`, passi 16-17 |
| 8 | Repo del sito per Lovable (`../karimi-normalise-site`: contratto dati, brief, snapshot) | ✅ in locale; push appena c'è l'URL |
| 9 | Progetto GCP `karimi-normalise-2026`, regione europe-west1 | ✅ creato (passo 1). **Fermo al passo 2: l'account di fatturazione risulta chiuso** |
| 10 | Velocità misurata: 8,1 min ogni 1.000 elementi (94% traduzione, 31% non inglese) | ✅ costo rivisto: ~3-8 $/mese per 100k requisiti |

Decisioni da ricordare: niente immagine senza sha256 del modello del
giudice; il giudice è ritarato se cambiano modello o build di llama.cpp; i
log non contengono mai testo degli annunci; i file dei lavori si cancellano
dopo 30 giorni, lo storico no.

### Annunci nuovi: lotto 1 (2026-11-15)

**Che cosa sono.** Il file `software_data_missing_from_ids_used.json`
contiene 18.254 annunci software e data. Nessun id è in comune con
`software_data_europe.json`, e solo 310 testi coincidono, quindi è il primo
test fuori campione. 1.320 annunci non hanno `must_have` e sono saltati. A
differenza del corpus del dizionario non sono solo europei, e manca il campo
lingua. Il file resta fuori da git.

**Come.** Lo abbiamo chiamato come farebbe un esterno, seguendo solo
`API.md`: un client che usa solo `requests` e nessun codice della libreria.
Gli annunci vengono mescolati una volta, con il seme 20261115; il lotto k è
`[k*1000, (k+1)*1000)`. Il lotto 1 è il job `4e0ddade887f5fd1`, con 1.000
annunci e 8.111 righe. I file sono in `output/new_postings/batch_01/`.

**Ogni passo, verificato:**

| passo | esito |
|---|---|
| `/health`, creazione del job, upload firmato, avvio | ✅ 200 / 202 |
| elaborazione | ✅ 17,4 minuti. Le 5 letture di stato fallite per errore SSL non compaiono nei log del server: sono un problema di rete del client, che le ha ritentate. Il server non ha nessuna risposta ≥ 400; l'unico ERROR è quello voluto del controllo rosso, che fa partire l'avviso via email |
| risultati, report, i due CSV | ✅ 16.098 requisiti, 1,98 per riga |
| controllo (`check.json`) | ✅ pronto 8,6 minuti dopo la fine |
| giudice | ✅ coppie di controllo 21 su 21, quindi affidabile. Gruppo: 3 bocciate su 40 (7,5%, riferimento 5,3%, p = 0,36). Argomento: 6 su 30 (20%, riferimento 12%, p = 0,14) |
| agente Inspector | ✅ 26 titoli di studio sospetti su 16.098 requisiti; letti tutti, sono errori veri |
| agente Curator | ✅ 10 proposte, 10 approvate dal giudice; l'API ora risponde con il dizionario `0.3.1+a10` |
| sito (`/v1/metrics`) | ✅ il run c'è, con i totali dei due agenti |

**Risultato: rosso, e il motivo sono i dati, non un guasto.** I segnali della
divisione sono tutti verdi (1,98 requisiti per riga, tipico 1,99). Sono rossi
solo quelli di copertura del dizionario:

| | lotto 1 | tipico |
|---|---|---|
| noti | 58,7% | 65,6% |
| nel gruppo per somiglianza | 10,6% | 8,8% |
| solo argomento | 12,8% | 11,1% |
| nuovi | 16,9% | 13,1% |
| titoli nuovi | 49,5% | 36,8% |

Il calo **non viene solo dagli annunci fuori Europa**. Su quelli europei i
requisiti noti sono 60,0% e i nuovi 15,7%. Fuori Europa i noti sono 57,2% e
i nuovi 19,7%. Il riferimento era misurato su annunci dello stesso export del
dizionario, quindi era ottimista: questa è la prima misura di copertura su
annunci davvero nuovi.

**Errori trovati dagli agenti, da correggere nelle regole (0.4.2):**

* titolo di studio seguito da `preferred`, `strongly preferred`, `is a plus`
  (`Ph.D. preferred`, `Master's preferred`): non viene letto come titolo e
  non risulta facoltativo;
* titolo `or equivalent / related experience`, che finisce dentro la materia
  (`Bachelor in or relevant experience`);
* anni dentro il titolo (`Master's degree 2–3 years of relevant experience`,
  `Bachelor’s degree (5–7 years experience) or Master's degree (3–5 years)`,
  `Bachelor’s with 10+ years`);
* `associate’s degree`, `Undergraduate Degree`, `Bachelor's degree student
  +4/5`;
* anni in forma di intervallo senza trattino: `(5 years 10 years)` esce come
  5–5, e il nome del requisito si rompe.

**Unioni del Curator, lette una per una.** Sette sono giuste: GCP BigQuery,
AWS Redshift, AWS GuardDuty, Apache Maven, IBM QRadar, IIoT platforms, Java
services. Due sono discutibili, perché tolgono il fornitore a una cosa più
specifica: SAP EAM → EAM e AWS MLOps engineering → MLOps engineering. **Una è
sbagliata: IT platforms → IT**. La regola `generic_suffix` accetta come
oggetto anche una sigla troppo generica, ed è lo stesso difetto di
`Information Technology → Information`. Il giudice le ha approvate tutte e
dieci: come già misurato, la precisione dipende dai rilevatori, non dal
giudice.

### Explore si aggiorna da solo (2026-11-15)

Con l'accordo di Karimi, ogni run che passa il controllo aggiunge i suoi
annunci alla pagina Explore. Prima Explore si costruiva una volta sola
dall'export di agosto e si caricava a mano su GitHub. Il codice è in
`karimi_normalise/explore.py`, e lo esegue il job di controllo
(l'"editore"):

* **un run entra** se il giudice è affidabile e nei limiti, e se i segnali
  della divisione sono normali. I requisiti nuovi non lo bloccano: sono
  proprio quello che porta;
* **dentro il run si escludono** i requisiti facoltativi, le righe rotte,
  quelli senza argomento, i titoli di studio segnalati dall'Inspector e le
  parole generiche. La stessa regola vale per gli annunci dell'export;
* **un annuncio mandato due volte conta una volta** (hash dell'id). Si
  conservano solo hash e conteggi, nessun testo;
* **il sito legge `/v1/explore`** dall'API; i file in
  `public/data/explore` servono solo se l'API non risponde;
* **lo sweep delle 6:00** decide i run controllati prima che il passo
  esistesse e ricostruisce Explore.

Ogni decisione, entrato o no e perché, è nella pagina Metrics alla voce "The
publisher".

### Regole 0.4.2 (2026-11-15)

Dal primo lotto di annunci nuovi (1.000, mandati all'API come un esterno). I
casi si prendono solo dal lotto 1; il lotto 2, mai letto, serve a misurare.

* **Titoli di studio.** Causa: nomi che le regole non conoscevano (`BS`, `MS`,
  `BA/BS`, `B.E.`, `B.Tech`, `MCA`, `HBO`, `WO`, `associate's`), parole davanti
  a più titoli (`Relevant bachelor's or master's`), `or relevant experience`
  incollato al campo. Soluzione: nomi nuovi (`BS`, `MS`, `WO` solo maiuscoli,
  così `MS Office` resta un prodotto), l'esperienza come seconda via, il campo
  tra parentesi incrociato con il titolo. Lotto 1: segnalazioni
  dell'Inspector 69 → 8.
* **"is a plus", "preferred" dentro il requisito.** Causa: la coda che dice
  quanto è voluto restava nel nucleo (`Python is a plus`). Soluzione: si toglie
  prima di normalizzare (`normalise_req.strip_optional`) e rende il requisito
  facoltativo. Lotto 1: 100 → 6.
* **Due regole morte da due giorni.** Causa: le patch 0.4.1 erano passate da un
  heredoc della shell, che ha trasformato `\b` in un carattere di backspace.
  Soluzione: si scrive codice solo con l'editor; un test fallisce se un file di
  regole contiene caratteri di controllo.
* **Lingue fuori dalle 7.** Causa: cinese, giapponese, polacco, lituano,
  ungherese... restavano non tradotti e quasi tutti `nuovo`. Soluzione: il
  cinese va a `opus-mt-zh-en`; il giapponese e le altre lingue, riconosciute
  dalle lettere, vanno a `opus-mt-mul-en` (il modello giapponese inventava
  frasi). Il multilingue sbaglia circa una voce su quattro; ogni requisito
  tradotto lo dice in `translated_by`.
* **Il batch decideva la lingua per conto suo.** Causa: lo script del batch
  aveva una copia sua della logica delle lingue. Così il dizionario lasciava
  non tradotte 866 voci (0,9%) che l'API traduce, e ne traduceva 105 polacche
  con il modello delle lingue romanze. Soluzione: una copia sola, quella della
  libreria; un test confronta la scelta, non solo le tabelle.
* **Curator.** Causa: tre unioni sbagliate (`IT platforms` → `IT`, `SAP EAM`
  → `EAM`, `AWS MLOps engineering` → `MLOps engineering`), perché toglieva un
  fornitore o una parola generica anche davanti a una categoria. Soluzione:
  una lista di categorie (EAM, MLOps, CRM...) che non si accorciano mai, e il
  fornitore deve essere un nome intero. Le tre unioni si annullano con
  `curator --reject`.

### Archivista ed Esploratore (2026-11-16)

Sul lotto 1 gli agenti avevano visto solo i titoli di studio e il calo di
copertura; "is a plus" e le righe non tradotte li avevo trovati io leggendo.
Due agenti nuovi, perché la prossima volta li trovino loro:

* **Archivista** (`archivist.py`, `error_catalogue.json`): il catalogo di ogni
  tipo di errore trovato, con causa, versione che l'ha risolto, test che lo
  protegge e residuo misurato. Su ogni run dice di ogni tipo: risolto in una
  versione più nuova, residuo atteso, tornato (sopra 3 volte il residuo:
  giallo) o aperto. Per un tipo aperto scrive la bozza del test e i file da
  cambiare; **una persona approva**, nessuna regola cambia da sola.
* **Esploratore** (`explorer.py`): Gemini 3.5 Flash su Vertex AI, endpoint
  multiregione UE, legge 30 righe di ogni run che l'Inspector non segnala e
  raggruppa ciò che non va in tipi. I tipi noti li collega al catalogo, quelli
  nuovi sono candidati che una persona conferma. Misurato prima: trova tutti
  gli errori noti, ma sui conteggi umani ha ragione solo nel 33% dei casi;
  quindi **segnala e non conta**, e non colora mai un run. Il modello locale
  Qwen3-14B è stato provato e scartato: stessi numeri, nomi dei tipi sbagliati,
  tre volte più lento.
* **Decidere dalla pagina Metrics**: i tipi nuovi si confermano o si scartano
  lì, solo dal responsabile del progetto, con il login Google. Il controllo lo
  fa l'API (`/v1/admin`), non il sito; solo dopo il login si vedono gli esempi
  con il testo degli annunci. Un tipo confermato entra nel catalogo come
  aperto, e il rilevatore lo scrivo e lo misuro io; uno scartato non viene più
  riproposto come nuovo.

### Il colore segue gli errori, non la novità (2026-11-16)

Il lotto 2 era rosso solo perché i suoi annunci erano nuovi per il dizionario,
mentre il giudice era verde. Decisione: **il colore dice quanti errori fa un
run**.

* **Errori, decidono il colore**: quota stimata di requisiti sbagliati =
  errori dell'Inspector + (decisioni per somiglianza bocciate dal giudice ×
  quota di requisiti messi per somiglianza). Verde sotto il 3%, giallo 3–6%,
  rosso sopra il 6%, soglie fissate prima di leggere un run.
* **Forma dello split**: requisiti per riga, requisiti di una parola, righe
  tenute intere. Al massimo giallo: una forma strana merita un'occhiata, non è
  un errore misurato.
* **Novità, senza colore**: copertura del dizionario, requisiti e titoli
  nuovi, quota tradotta. In blu sul sito, con "più del solito" quando escono
  dall'intervallo.
* I run controllati prima vengono riletti con la stessa regola. Explore accetta
  un run se gli errori non sono rossi.

### Il ciclo per ogni lotto (2026-11-17)

La regola di lavoro, decisa dal responsabile, per ogni lotto di annunci nuovi:

1. **si manda il lotto all'API** come un esterno;
2. **si trovano tutti gli errori**: quelli degli agenti (Inspector, Archivista,
   Esploratore, giudice) e quelli trovati da noi (la nostra lettura e la
   revisione umana in Metrics);
3. **ogni tipo trovato da noi entra nel catalogo degli agenti**, con il suo
   rilevatore, così la volta dopo lo trovano da soli;
4. **si correggono tutti gli errori del lotto** (nuova versione delle regole e
   del dizionario), si misura il residuo e si fa il deploy;
5. **si passa al lotto dopo**, che misura: il lotto appena corretto diventa
   sviluppo.

L'obiettivo: un lotto con solo risultati corretti, oppure dove ogni errore
viene trovato dagli agenti e la persona deve solo confermarlo. A ogni giro il
processo diventa più automatico e l'intervento umano si riduce.

**Ritest ogni 5 lotti (deciso il 2026-11-19 ogni 4, portato a 5 il
2026-11-23, dopo la revisione umana).** Ogni 5 lotti si rielaborano
gli stessi annunci dei 5 lotti precedenti con le regole e il dizionario di
oggi, per vedere quanto è migliorato il modello nel complesso. **Il ritest è
nostro e non si pubblica** (deciso il 2026-11-20): gira in locale con
`New project/retest_batches.py`, sugli stessi passi del job e del check di
produzione e con il giudice locale, e scrive solo in
`New project/output/retests/<versione regole>/`. Niente bucket, niente storia
dei run, niente sito. (Il campo `retest_of` dell'API e il calcolo nel check
restano: è il check che lo script usa; la colonna sul sito è stata tolta.)

Primo ritest, 2026-11-19, regole 0.4.6 e dizionario 0.3.7: lotto 1 da 15,0% a
7,2%, lotto 2 da 15,6% a 6,4%, lotto 3 da 14,5% a 5,1%, lotto 4 da 8,1% a 6,0%
di requisiti stimati sbagliati. Quasi tutto il guadagno è nella parte
dell'Inspector (circa 11–12% → 3,3–3,9%).

Il cambiamento non si legge contro il colore originale: l'Inspector impara tipi
nuovi tra un lotto e l'altro, quindi il lotto 4 riletto con i rilevatori del
lotto 5 ha più errori del suo 3,8% di allora. Il check del ritest rilegge
l'uscita originale con l'Inspector di oggi (`check.retest_baseline`; la parte
del giudice resta quella del giorno, perché il giudice non è cambiato) e
confronta le due letture con lo stesso strumento. Il ritest non aggiunge annunci
a Explore e non entra nella revisione umana.

**Giro del lotto 2 → regole 0.4.3.** Errori degli agenti: 125 dell'Inspector
(titoli di studio 56, code facoltative 24, "required" 15, "or similar" 13,
lingue 16) e 3 tipi nuovi dell'Esploratore. Tutti corretti; i tipi
dell'Esploratore sono entrati nel catalogo. Restano aperti, senza rilevatore
affidabile: pezzi rotti e liste lunghe.

**Giro del lotto 3 e della prima revisione umana → regole 0.4.4, dizionario
0.3.4.** La revisione del lotto 2 (100 righe) ha trovato 25 errori; l'Inspector
ne aveva trovati 0. Le convenzioni decise dopo: il nome preciso vince (il
contesto va in `extra`); esempi con nomi → sono i requisiti, esempi con nomi
comuni → resta la categoria; `including` è sottinteso; macro-gruppi dopo, come
progetto a parte. Le forme di quegli errori sono diventate rilevatori
dell'Inspector (`lead_punctuation`, `comma_in_key` solo su nomi,
`edge_preposition`, `duplicate_key`) e voci del catalogo con `found_by:
review`. Lotto 3: titoli di studio, lingue (spagnolo, olandese, croato),
"or more", "or above". Misura su split e normalizzazione: segnali sul lotto 3
da ~630 a ~130, sul lotto 2 da ~700 a ~140.

**Revisione umana del lotto 3 → regole 0.4.5, dizionario 0.3.5.** 41 errori su
100, ma il run era fatto con le regole 0.4.3: la 0.4.4 ne cambiava già 18.
Corretti gli altri (cornici intorno al nome, aggettivi di lode, "Interest in",
una parola per una soft skill, titoli di studio tedeschi e cinesi). Nuovo
rilevatore `frame_left`: sul lotto 3 così com'era ne avrebbe segnalati 274.
Giudice sul dizionario: gruppi sbagliati 3,3% (era 7,3%), topic 9% (era 17%).
Regola per le prossime revisioni: rivedere un run fatto con le regole in
produzione, sennò si misurano errori già corretti. Lotto 4 misura la 0.4.5.

**Revisione umana del lotto 4 → regole 0.4.6, dizionario 0.3.7.** Prima
revisione di un run fatto con le regole in produzione (0.4.5): 37 errori su
100, e l'Inspector ne aveva trovati 2. Regola nuova del giro, decisa dal
responsabile il 2026-11-18: **ogni tipo di errore diventa prima un rilevatore,
poi una regola**. Così:

* **8 rilevatori nuovi** (`errors.review_flag`, `errors.item_flags`): lingua
  letta come livello o skill, contesto rimasto, nome con parola inutile, verbo
  da solo, nomi rimasti in `extra`, verbi davanti all'oggetto, parola staccata
  dal suo nome, testa incollata ai pezzi. Più `roles_in_key` (ruoli
  alternativi rimasti insieme), dalla decisione del 2026-11-18;
* **misurati contro le etichette della persona** con
  `score_review_detectors.py`: sul lotto 4 trovano 29 errori su 37 (erano 2),
  ma sono tarati lì. Fuori campione, sulle revisioni dei lotti 2 e 3: 9 su 25 e
  17 su 41. Il numero vero lo dà la revisione del lotto 5;
* **regole 0.4.6**: delle 37 righe sbagliate ne cambiano 23, delle 63 giuste 2
  (lette). Ruoli alternativi: lo stesso ruolo scritto in più modi è un
  requisito (`Azure Cloud Architect, Lead Architect or Design Architect` →
  Cloud Architect), ruoli diversi sono requisiti separati. Gli anni della riga
  vanno a tutti i pezzi; il CSV ha `years_raw`, `level_words`, `qualifier`,
  `modes`;
* **restano aperti, ma segnalati**: coppie con una coda in comune
  (`shared_tail_lost`), verbi spezzati (`bare_verb`), località (`reside in
  California`), traduzione cinese incomprensibile;
* **dizionario**: la 0.3.6 è stata congelata prima della regola sui ruoli e
  non va mai online. La 0.3.7 è la stessa rifatta con la regola. Parità
  99,35% come prima, conteggio cieco invariato. ⚠️ Giudice: gruppi bocciati
  11 su 150 (7,3%, era 3,3%), topic 11 su 100 (era 9). Non significativo
  (p = 0,20), ma nella direzione sbagliata: lette una per una, 2 unioni
  sbagliate e il resto cornici rimaste nel nucleo (`role in Machine
  Learning`, `accompany architecture decisions`). Vanno nel giro del lotto 5.

Il lotto 5 (1.000 annunci, offset 4000) misura la 0.4.6. Si resta a 1.000
finché un lotto non è verde e la revisione sotto il 10%. Poi un lotto da 5.000
come prova grande.

**Giro del lotto 5 → regole 0.4.7, dizionario 0.3.8 (2026-11-23).** Il lotto
5 (regole 0.4.6) era rosso, 6,7%. In parallelo:

* **errori degli agenti**, letti riga per riga: 140 titoli di studio e 520
  altre segnalazioni (472 vere, 48 falsi allarmi: precisione stimata 0,91).
  Due tipi nuovi trovati da noi diventano rilevatori: `object_in_extra`
  (requisito vuoto, l'oggetto messo da parte) e `names_dropped` (nomi persi
  prima di "like / such as"). Regole: frasi con più parti tagliate prima
  della lista, diploma di scuola superiore come livello `school`, studenti
  ("Currently enrolled in"), parole di livello mancanti, "Titolo: a, b, c",
  anni in altre forme, lingue con CEFR;
* **revisione della persona** (100 righe): **23 sbagliate** (lotto 4: 37). I
  rilevatori della 0.4.6 ne trovavano 2. Quattro rilevatori nuovi dai suoi
  tipi (`level_as_core`, `years_left`, `availability_lost`, `role_cut`, più
  "with a focus on" in `context_left`): 8 su 23, misurati sulla stessa
  revisione. Con la 0.4.7, 18 delle 23 escono come dicono le note, e nessuna
  delle 77 giuste cambia. **Deciso dal responsabile**: un atteggiamento resta
  intero ("Desire to", "Passion for development").

Misure: segnali dell'Inspector sul lotto 5 rielaborato da 668 a 460 (dal 4,3%
al 3,0%). Su 3.000 righe a caso dei lotti 1–5 cambia il 3,6%; lette tutte, 12
peggioramenti trovati e corretti prima del rilascio. Domanda aperta per il
responsabile: una parentesi di nomi comuni ("editorial skills (procedures,
reporting, documentation)") va letta come tre requisiti, contro la
convenzione del 2026-11-17? Restano aperte frasi complesse rimaste intere
(`comma_in_key` 100). Il lotto 6 (offset 5000) misura la 0.4.7.

**Giro del lotto 6 → regole 0.4.8, dizionario 0.3.9 (2026-11-23).** Il lotto
6 (regole 0.4.7) è il primo **giallo**: 5,8% stimato (lotto 5: 6,7%). Gli
agenti: 478 segnalazioni, 415 vere. Revisione della persona: **20 sbagliate su
100** (lotto 5: 23, lotto 4: 37); i rilevatori ne trovavano 3. **Decisioni del
responsabile, stesso giorno**: (1) verbi coordinati su un oggetto generico =
un requisito per verbo, verbo tenuto (ribalta la regola del 29/10); con un
nome vince il nome; (2) le aree dopo l'oggetto sono requisiti; (3)
l'atteggiamento va via se ciò che segue sta in piedi da solo, resta se è una
parola sola troppo generica; (4) il ritest passa a ogni 5 lotti, dopo la
revisione; (5) una parentesi di nomi comuni resta la categoria. Su sua
domanda: "Learning" era spesso staccato da Deep/Machine Learning (letti come
livello o parola generica): ora restano interi. Misure: rilevatori 7 su 20
(in campione); 15 delle 20 escono come le note; 2 delle 80 giuste cambiano,
per la convenzione nuova; Inspector sul lotto 6 rielaborato dal 2,8% al 2,2%.
Il lotto 7 (offset 6000) misura la 0.4.8.

**Giro del lotto 7 → regole 0.4.9, dizionario 0.4.0 (2026-11-23).** Il lotto
7 (regole 0.4.8) torna **rosso**: 6,6% stimato, quasi tutto dal giudice dei
topic (8 coppie su 30 respinte: il campione per run è piccolo). Gli agenti:
482 segnalazioni, 443 vere; su 80 righe non segnalate, circa 17% sbagliate.
Revisione della persona: **22 sbagliate su 100**; l'Inspector ne segnalava 1.
**Come leggere le note** (il responsabile, stesso giorno): `/` separa i
requisiti da tenere distinti; livello, anni, expertise restano nelle colonne
complementari. Misure: 16 delle 22 escono come le note, 3 vicine, 3 aperte
(due traduzioni mancate, svedese e spagnolo, e una frase verbo+artefatti);
0 delle 78 giuste cambiano; Inspector sul lotto 7 rielaborato dal 3,2% al
2,2%; 77 dei 3.000 elementi di controllo cambiano, tutti letti. Il lotto 8
(offset 7000) misura la 0.4.9. Il giudice topic passa da 30 a 100 coppie per
run (decisione del responsabile, 23/11).

**Giro del lotto 8 → regole 0.4.10, dizionario 0.4.1 (2026-11-24).** Il lotto
8 (regole 0.4.9) è **giallo**: 3,9% stimato. Gli agenti: 364 segnalazioni, 326
vere; sulle righe non segnalate circa 10% sbagliate (lotto 7: circa 20%).
Revisione della persona: **14 sbagliate su 100** (lotto 7: 22). Decisioni del
responsabile: "passion for X and Y" sono due requisiti; un solo gruppo per soft
skill (autonomy, teamwork, analytical skills; poi adaptability e problem
solving dalla revisione); il ritest dei lotti 1-5 è fatto, il prossimo è sui
lotti 6-10. Misure: le 14 note escono come scritte; delle 86 giuste cambiano
solo i nomi dei gruppi; Inspector sul lotto 8 rielaborato dal 4,7% al 2,0% (con
i rilevatori nuovi); 162 dei 3.000 elementi di controllo cambiano, tutti letti.
Il lotto 9 (offset 8000) misura la 0.4.10, primo con il giudice a 100 coppie.

### Revisione umana e Curator (2026-11-17)

* **Revisione di una persona**: l'unico numero che conta tutti gli errori,
  split compreso. Il responsabile, con il login, legge 100 righe estratte a
  caso da un run, senza vedere cosa hanno detto gli agenti, e segna corretta o
  incorretta con una nota; si invia da 50 in su. Sul sito: quota sbagliata con
  il margine al 95%, e l'Inspector misurato contro questa etichetta (precisione
  e richiamo). Righe e note restano private.
* **Il Curator non toglie mai il fornitore**: `Google Studio` non è `Studio`,
  e `AWS GuardDuty` chiede AWS. Le unioni di questo tipo si annullano tutte;
  quelle con parola generica o versione dopo restano (`EDA tools` → `EDA`).
  Una sigla che finisce in S non è un plurale (`SAP IDM` era finito su
  `IDMS`): corretto nel Curator, e da correggere nelle regole con la 0.4.3.

### Agenti e passi, tutti insieme (2026-11-19)

Le sezioni sopra aggiungono un pezzo alla volta. Qui c'è il quadro intero di
oggi. Dove le tabelle di §2 e §3 (scritte il 4-6 novembre) dicono altro, vale
questo.

**Gli agenti.**

| Agente | Cosa fa | Quando | Decide il colore? |
|---|---|---|---|
| **Inspector** (`errors.py`) | rileva tipi di errore noti su ogni requisito: titoli di studio, code facoltative, forme dello split, i 9 rilevatori della revisione del lotto 4 | ogni run, nel job di controllo | sì, la sua quota |
| **Giudice** (`tester.py`, Qwen3-4B locale, prompt v5) | giudica un campione delle decisioni prese per somiglianza (gruppo, topic), con coppie di controllo | ogni run | sì, la quota bocciata × quota messa per somiglianza |
| **Curator** (`curator.py`) | propone unioni nel dizionario (alias); mai togliere il fornitore | ogni run | no |
| **Archivista** (`archivist.py`, `error_catalogue.json`) | per ogni tipo noto: risolto, residuo atteso, tornato, aperto; per un tipo aperto scrive la bozza del test | ogni run | giallo se un tipo torna |
| **Esploratore** (`explorer.py`, Gemini su Vertex AI UE) | legge 30 righe non segnalate e propone tipi nuovi | ogni run | no, segnala e basta |
| **Editore** (`explore.py`) | mette nella pagina Explore i run che passano | ogni run, e lo sweep delle 6:00 | no |
| **Controllore** (`check.py`) | mette insieme tutto: livelli 1-4, colore, `check.json` | ogni run | è lui che colora |
| **Revisione umana** (`review.py`, pagina Metrics) | 100 righe a caso, giusta o sbagliata, con nota | un run per lotto | no: è la misura di tutti gli altri |

**I passi di un giro**, con chi li fa oggi:

| # | Passo | Oggi | Automatico? |
|---|---|---|---|
| 1 | mandare il lotto all'API come un esterno | io, con `external_job.py` | a mano |
| 2 | controllo del run (tutti gli agenti sopra) | job `karimi-check` | ✅ |
| 3 | revisione di 100 righe | il responsabile, su Metrics | a mano, per scelta |
| 4 | confrontare revisione e agenti, rilevatore per rilevatore | io, con `score_review_detectors.py` | a mano |
| 5 | scrivere i rilevatori nuovi e misurarli dentro e fuori campione | io | a mano |
| 6 | scrivere le regole, i test, il CHANGELOG, la voce del catalogo | io | a mano |
| 7 | rifare il dizionario (traduzione → split → gruppi → freeze → parità → qualità → giudice → Explore) | io, script locale di ~1 ora, giudice locale | semi |
| 8 | commit e deploy | il responsabile, in PowerShell | a mano |
| 9 | controllare `/health` e lanciare il lotto dopo | io | a mano |

**Cosa manca: agenti e passi.** In ordine di quanto lavoro umano tolgono.

1. **Misura dei rilevatori sul sito.** Oggi la revisione misura l'Inspector
   solo nel suo insieme, e con i rilevatori che c'erano quando è stato
   estratto il campione. Il punto 4 (precisione e richiamo per rilevatore,
   rilette con l'Inspector di oggi) va nel job: quando arriva una revisione,
   il controllore la rilegge da solo. Serve anche una regola fissa: **un
   rilevatore entra nel colore solo con precisione ≥ 0,80 su una revisione
   che non l'ha tarato**. Oggi lo decido io caso per caso.
2. **Le note della revisione diventano candidati del catalogo.** Oggi le
   leggo io. L'Esploratore può raggruppare le note delle righe segnate
   sbagliate in tipi, come già fa con le righe non segnalate. La persona
   conferma. È il passo che più si avvicina al "trova gli errori da solo".
3. **Rilettura dei lotti vecchi con le regole nuove ("replay").** Per sapere
   quante righe giuste cambia una regola, oggi ho script nella mia cartella di
   lavoro. Deve diventare un passo fisso della catena: ogni revisione già fatta
   viene rifatta con le regole nuove, e si contano righe sbagliate che cambiano
   e righe giuste che cambiano. Una regola che cambia righe giuste si legge
   prima del rilascio.
4. **Catena del dizionario più robusta.** Questo giro ha perso una notte: la
   catena è ripartita quando la 0.3.6 esisteva già, e il freeze, giustamente,
   non sovrascrive. Si fermava dopo un'ora di lavoro. Poi il giudice locale si
   è spento. Due controlli **all'inizio**: la versione è libera, il giudice
   risponde. E più avanti: la catena gira in un Cloud Run Job in UE, così non
   dipende dal PC acceso.
5. **Ispettore della traduzione.** Nessun agente guarda la traduzione: `Master
   ' s degree` (13 titoli persi nel lotto 4), `3.7.1995 years`, il cinese
   incomprensibile li ho trovati io. Rilevatori semplici: date o numeri
   impossibili, apostrofi staccati, parole non tradotte. Le righe segnalate si
   rifanno con `opus-mt-mul-en` o si tengono nella lingua originale.
6. **Regole per i rilevatori aperti**: `shared_tail_lost`, `bare_verb`,
   località. Oggi sono segnalati, non corretti.
7. **Lancio del lotto e controllo del deploy senza di me.** Uno script che
   dopo il deploy legge `/health`, verifica le versioni, lancia il lotto dopo
   e avvisa quando è pronto per la revisione.

**Deciso il 2026-11-19: da 7 agenti a 4.** Inspector e Archivista diventano
un agente solo, con un catalogo solo: ogni tipo di errore porta rilevatore,
causa, versione che lo corregge, test e misura sulla revisione. Oggi lo stesso
tipo è scritto in tre posti (`INSPECTOR_DETECTORS`, `CAUSES`,
`error_catalogue.json`). Restano separati il Giudice (sì/no tarato,
riproducibile), l'Esploratore (domanda aperta; raggrupperà anche le note della
revisione, punto 2) e il Curator (l'unico che scrive nel dizionario). Il
controllo e l'Editore sono passi, non agenti. La misura per rilevatore (punto
1) diventa una funzione dell'Inspector unito. **Quando**: dopo la revisione del
lotto 5, così i rilevatori nuovi sono misurati prima di cambiare struttura.

Da non automatizzare: la revisione umana (è la misura, e deve restare cieca) e
le decisioni di convenzione (`Cloud Architect` sì, Data Engineer + Data
Scientist separati). Quelle restano del responsabile.

### Come si migliora dopo il rilascio

Sì, split e normalizzazione restano migliorabili. Il percorso è fisso, così un
miglioramento non rompe chi usa i risultati:

1. **Si trova un difetto**: dal monitor, dall'agente tester, da Karimi o
   leggendo.
2. **Diventa un caso di test**: una riga in `test_patterns.py` con il risultato
   giusto. Ora fallisce.
3. **Si corregge la regola** in `karimi/`. Libreria e analisi la ricevono
   insieme, perché il codice è uno solo.
4. **I test girano tutti**: i 138 casi vecchi devono restare verdi, così una
   correzione non ne rompe un'altra. Poi le misure (conteggio cieco, coppie).
5. **Nuova versione**: `RULES_VERSION` sale e si scrive una riga nel
   `CHANGELOG.md`. Se la si dimentica, il test dell'impronta fallisce.
6. **Nuovo dizionario**, se cambiano i gruppi: `freeze --version` con un nome
   nuovo, mai sopra il vecchio. `freeze --diff vecchio nuovo` dice quali
   gruppi sono rimasti, rinominati, divisi o uniti.
7. **Si rielabora**: ogni risultato porta le sue versioni, quindi si sa quali
   righe sono vecchie. Si possono rifare oppure tenere, ma non si confondono.

Il limite onesto: un requisito già consegnato con le regole vecchie resta
sbagliato finché non lo si rielabora. Le versioni non correggono nulla da sole:
dicono solo cosa va rifatto.

---

## 4. Fasi

L'ordine segue le dipendenze: ogni fase usa quella prima. Il criterio "fatto"
va fissato prima di vedere i risultati, come per le soglie in `config.py`.

### Fase 0: fondamenta europee (mezza giornata)

Con la sola libreria serve solo per ciò che gira da noi: test, lotti nostri,
agente tester. Non blocca la consegna a Karimi.

- Progetto GCP con la policy di organizzazione `constraints/gcp.resourceLocations`
  impostata a `in:eu-locations`: risorse fuori UE non si possono creare.
- Una regione principale. `europe-west1` (Belgio) ha la maggior parte dei servizi;
  `europe-west8` (Milano) è l'alternativa vicina. Controllare che Vertex AI
  abbia lì i modelli che servono.
- Posizione predefinita dei log in UE. Il bucket `_Default` di Cloud Logging
  nasce `global` se non si cambia l'impostazione.
- Avviso sul budget.

**Fatto quando** creare un bucket in `us-central1` viene rifiutato.

### Fase 1: libreria `karimi-normalise` (la più importante)

- Separare dal codice di analisi i moduli che servono al servizio:
  `atomise`, `pos`, `normalise_req`, `normalise_title`, la traduzione, e la
  ricerca nel dizionario.
- **Dizionario congelato**, un artefatto con versione:
  - per i requisiti: i nuclei di ogni gruppo con il loro embedding, la mappa
    gruppo → tema, la classe chiusa dei nomi (`names`);
  - per i titoli: acronimi imparati, varianti, lista Developer = Engineer.
- **Un requisito nuovo** cerca il nucleo più vicino nella stessa testa, con gli
  stessi nomi:
  - coseno ≥ 0,90 → `req_group` e `req_topic`;
  - tra 0,80 e 0,90 → solo `req_topic`;
  - sotto 0,80 → segnato `nuovo`.
- **Un titolo nuovo** passa dalle stesse regole; il gruppo viene dal dizionario,
  altrimenti `nuovo`.
- Interfaccia:
  - `split(text) -> list[Requirement]`, dove ogni requisito porta anni, livello,
    testa, nucleo, gruppo, tema, il percorso seguito e le regole scattate;
  - `normalise_title(title) -> Title`.
- **Ogni output porta `rules_version` e `dict_version`**, come la cache legata
  alla versione del prompt.

**Fatto quando:**
1. sui 16.990 annunci lo split è identico a quello attuale;
2. il gruppo assegnato dal dizionario coincide con quello del calcolo a lotti
   per almeno una quota fissata prima. I due metodi non sono uguali: quello a
   lotti unisce un solo passo sul corpus intero, quindi la differenza va
   misurata, non data per zero;
3. i 138 test passano.

**Decisione prima di congelare:** rigenerare i requisiti con le regole P10–P15
(oggi `must_have_atoms.parquet` è fatto con le regole precedenti). Congelare è
il momento naturale per farlo.

### Fase 2: test automatici (piccola, subito dopo)

- In CI: i 138 test di `test_patterns.py`, `score_counts.py` sul conteggio
  cieco, `score_pairs.py` sulle coppie.
- Soglie di blocco fissate ora, per esempio: il conteggio cieco non scende sotto
  il 78%, le unioni sbagliate tra ruoli non salgono.

**Fatto quando** una modifica che rompe una regola fa fallire la build.

### Fase 3: distribuire la libreria a Karimi

Cambiata il 2026-11-04: Karimi usa la libreria, non l'API.

- **Pacchetto e dizionario con versione**, deciso il 2026-11-04: prima
  **privato**, Artifact Registry (repository Python) più un bucket, entrambi
  in una regione UE, letti solo dagli account a cui si dà accesso
  (`deploy/release.sh`: `setup`, `grant`, poi una riga per versione). Poi
  **PyPI, pubblico**, con il solo codice: il dizionario è fatto dagli annunci
  di Karimi e diventa pubblico solo se loro sono d'accordo. Senza
  un'organizzazione Google Cloud la regola che rifiuta le regioni fuori UE non
  esiste: la regione è scritta nello script su ogni risorsa.
- **CI/CD.** CI: 11 test veloci prima di ogni commit (`.githooks/pre-commit`)
  e 3 soglie che bloccano il rilascio. CD: `release.sh` lancia tutti i test,
  costruisce il pacchetto, lo carica con la sua scheda di qualità. Gli stessi
  passi in Cloud Build possono venire dopo.
- **Guida di installazione**: modelli spaCy e opus-mt, dove metterli, come
  lavorare senza internet, la raccomandazione di elaborare in UE.
- **`process(postings)`**: una chiamata, che restituisce requisiti, titoli e il
  report di run. Fatta.
- **Cache delle traduzioni** (`TranslationCache`): fatta. Usa lo stesso
  formato del batch, quindi `translate_cache.jsonl` la può riempire subito.

Misura su 100 annunci (16 thread di CPU, in locale):

| | tempo reale | CPU | di cui traduzione |
|---|---|---|---|
| cache vuota | 65 s | 196 s | 180 s (92%) |
| cache piena | 0,7 s | 6,5 s | 0 s |

La traduzione è quasi tutto il costo. Nel corpus gli elementi tradotti si
ripetono poco (35.296 volte per 29.333 elementi diversi), quindi alla prima
elaborazione la cache risparmia circa il 17%. Il guadagno grande è su ogni
rielaborazione: la traduzione non dipende dalle regole, quindi dopo una
correzione rifare tutto costa una frazione.

L'API e il job su Cloud Run restano scritti (`api.py`, `deploy/`) e non
vengono offerti.

**Fatto quando** Karimi installa il pacchetto da zero seguendo la guida ed
elabora un proprio lotto, con lo stesso risultato del nostro.

### Fase 4: agente monitor

Con la sola libreria il monitor vede solo i lotti nostri. Le run di Karimi
producono lo stesso report (`run_report`) sulla loro macchina: se vogliono,
possono mandarci la sola riga di misure, senza testo degli annunci.

- Ogni lotto scrive una riga di misure in BigQuery:
  - frammenti, verbi orfani, duplicati, contenuto perso (da `split_quality.py`);
  - quota di requisiti `nuovo`, quota di titoli `nuovo`;
  - quota per percorso (`rules` / `single` / `llm`);
  - lingue.
- Cloud Monitoring avvisa quando una misura esce dalla sua banda storica.
- Nessun LLM, se non per scrivere un riassunto settimanale.

**Fatto quando** un lotto peggiorato apposta fa scattare l'avviso.

### Fase 5: osservabilità

- OpenTelemetry nella libreria: uno span per passo (traduzione, split,
  normalizzazione, dizionario), con la regola scattata come attributo.
- Esportazione verso Cloud Trace e Cloud Logging in UE. Verificare dove Cloud
  Trace conserva i dati. Se non basta, un collector OpenTelemetry verso un
  backend in UE.
- Per le sole parti LLM (fase 6) si può aggiungere **Langfuse**, ospitato su
  Cloud Run in UE oppure nella sua regione cloud europea. **LangSmith** solo se
  si usa la sua regione UE: da verificare.

**Fatto quando** un lotto si legge passo per passo, con tempi ed errori.

### Fase 6: agente tester (ultima)

- LLM come giudice su Vertex AI, endpoint regionale UE (mai l'endpoint globale).
- Ha le stesse istruzioni dell'etichettatore: `PAIRS_GUIDE.md` per le coppie,
  `COUNT_GUIDE.md` per i conteggi.
- **Taratura prima dell'uso**, sulle etichette che esistono:
  - 74 coppie con risposta: 59 del primo giro e 15 del secondo;
  - 120 conteggi.
- Si misura accordo e kappa di Cohen con la soglia fissata prima, e si
  riportano separati:
  - le risposte alla cieca;
  - le 8 corrette dopo aver visto le regole.
- **Due domande, non una.** Le etichette umane rispondono soprattutto a "stesso
  tema?", perché le 29 coppie vicine sono tutte "sì". Per "stesso requisito?"
  ci sono poche etichette severe. Il giudice va tarato separatamente per
  `req_group` e per `req_topic`.
- In uso:
  - ogni lotto, un campione delle unioni nuove giudicato dall'agente;
  - ogni mese, un piccolo controllo umano, per vedere se il giudice si sposta.
- DeepEval per strutturare le metriche del giudice. Gira in locale; i risultati
  non vanno inviati alla piattaforma cloud di DeepEval.

**Fatto quando** il giudice raggiunge la soglia di accordo sulle etichette
umane. Un giudice che dà due volte la stessa risposta è riproducibile, non per
questo corretto.

**Prima taratura, 2026-11-04** (`karimi_normalise/tester.py`, LLM in locale con
`llama-server`, nessun testo esce dalla macchina; soglie fissate prima: accordo
≥ 0,85, kappa ≥ 0,60). Le 74 coppie etichettate alla cieca:

| giudice | requisiti, "stesso tema" | requisiti, "stesso requisito" | ruoli | secondi a domanda |
|---|---|---|---|---|
| Qwen2.5-7B | 0,80 | 0,68 | 0,73 (kappa 0,45) | 5,9 |
| Qwen3-4B | 0,91 | 0,80 | 0,63 (kappa 0,20) | 3,5 |

**Nessuno dei due è tarato.** E le etichette che esistono non bastano a tararlo:

- sui requisiti la persona ha detto "diversi" 1 volta su 44. Un giudice che
  risponde sempre "uguali" avrebbe 0,98 di accordo: lo 0,91 di Qwen3-4B è sotto
  quella base, quindi non dice niente. Servono coppie in cui la risposta
  giusta è "diversi";
- molti "disaccordi" sono il giudice che segue la guida dove la persona no
  (`codecs` ~ `coding`, `risk` ~ `risk mitigation`, `attitude` ~ `curious
  attitude`): lo stesso contrasto già visto tra guida ed etichette;
- sui ruoli il giudice unisce le coppie Developer / Engineer che tu hai deciso
  diverse (`Solution Developer` ~ `Solutions Engineer`, `Product`, `IT`, `System`).
  Sono decisioni del progetto che la guida non contiene, quindi il giudice non
  le può sapere.

**Seconda taratura, 2026-11-05: il giudice v5 è tarato.** Tre fonti, mai
sommate: le 74 coppie umane, le 83 decisioni Developer / Engineer
(`developer_engineer_REVIEW.csv`) e 40 coppie di controllo con due nomi
diversi (diverse per la regola dei nomi, non per una persona). Ogni fonte è
divisa una volta in sviluppo e verifica (seme fisso). I prompt si sono cambiati
solo sullo sviluppo; la verifica si è letta una volta per prompt.

| prompt (Qwen3-4B) | cosa cambia | esito sullo sviluppo |
|---|---|---|
| v1 | la guida dell'etichettatore | ruoli 0,67 |
| v2 | + le decisioni del progetto | ruoli 0,87, ma controlli 0,70 |
| v3 | + ragiona prima di rispondere | **scartato**: ruoli Developer / Engineer 0,50 |
| v4 | regole 2 e 7 riscritte | **scartato**: dice "uguali" a ogni Developer / Engineer |
| **v5** | v2, e ciò che il progetto DEFINISCE lo decide il codice | passa tutto |

Il 7B, provato con v2 e v4, non fa meglio: sui requisiti è troppo severo.

Sulla verifica, mai usata per scegliere:

| | v1 | **v5** |
|---|---|---|
| ruoli, etichette ricontrollate (15) | 0,60 (kappa 0,25) | **0,87 (kappa 0,71)** |
| Developer / Engineer (41) | 0,73 (kappa −0,05) | 0,98 (dalla lista) |
| requisiti, stesso tema (21) | 1,00 | 0,95 |
| requisiti, stesso requisito, unite (8) | 1,00 | 1,00 |
| controlli, nomi diversi (20) | 0,95 | 1,00 (dal codice) |

**Cosa vuol dire, senza gonfiarlo:**

- il guadagno è tutto sui **ruoli**. Sui requisiti v1 andava già bene sulla
  verifica, e v5 sbaglia una coppia in più su 21 (`database management` ~
  `Database design`): rumore;
- Developer / Engineer e i nomi diversi li decide il **codice**, perché sono
  definizioni del progetto. Il 98% lì misura la lista, non il modello. La lista
  è stata decisa X per X, e nessun prompt la fa ricostruire a un modello
  (provato con v2, v4 e due modelli);
- dove decide il modello, cioè ruoli con lo stesso nome del lavoro e requisiti
  vicini, i campioni sono piccoli: 8 coppie di ruoli (0,75) e 19 di requisiti
  (0,95). Ogni cifra vale ± 10-15 punti;
- i due errori sui ruoli sono gli stessi in sviluppo e verifica: `Digital` ~
  `CRM Specialist` e `AI Platform` ~ `AI Solutions Engineer`, che tu hai detto
  uguali e la regola "specialità diversa = ruolo diverso" dice diversi.

**Difetto trovato nelle regole dei titoli:** `Quality Assurance Developer` e
`QA Engineer` sono uguali per la lista, ma la regola non li unisce, perché non
sa che `QA` = `Quality Assurance` (la sigla non è definita da nessun titolo).
Non corretto: cambia le regole, quindi `RULES_VERSION` e il dizionario.

Codice: `karimi_normalise/tester.py`, prompt `v5`, `by_code` per la parte
decisa dal codice. Risultati in `New project/output/tester/eval_*.json`.

### Fase 7, facoltativa: agente pipeline

- Workflows che orchestra i passi come regista.
- Un LLM solo sul 19% di elementi che le regole non sanno separare, e solo se
  sul set di test fa meglio delle regole.

---

## 5. Normativa europea: punti da tenere d'occhio

- **GDPR.** Pubblico non vuol dire escluso dal GDPR. Il `must_have` non
  contiene quasi mai dati personali, ma il testo completo dell'annuncio può
  avere nomi, email e telefoni di chi recluta. Si elabora solo il `must_have`
  e il titolo, e si registra cosa si conserva e per quanto.
- **AI Act.** I sistemi usati per selezionare persone o per indirizzare annunci
  di lavoro sono ad alto rischio (allegato III). Normalizzare annunci non
  valuta persone. Se però Karimi usa questi risultati per abbinare o filtrare
  candidati, quell'uso può rientrarci. Va chiarito con Karimi prima di
  collegarlo a qualunque abbinamento.
- **Modelli.** opus-mt, spaCy e l'embedding sono modelli aperti che girano
  dentro il container in UE: nessun testo esce. Il solo flusso verso un LLM è
  quello dell'agente tester, su endpoint UE.

---

## 6. Decisioni aperte

Aggiornate il 2026-11-19. Chiuse: la regione (europe-west1, Belgio), la
rigenerazione con P10–P15 (fatta), l'API (riaperta il 2026-11-04 accanto alla
libreria), le soglie del giudice (fissate il 2026-11-05).

1. **`title_family`:** una famiglia di ruolo sopra `title_group`, come
   `req_topic` sopra `req_group`. Serve una lista di famiglie decisa a mano.
2. **Macro-gruppi dei requisiti** (comunicazione, leadership, cloud...):
   progetto a parte, con una lista che il responsabile approva.
3. **Località come requisito** (`reside in California`, `based in Berlin`): è
   un requisito, una colonna o si scarta?
4. **Soglia di precisione per far entrare un rilevatore nel colore**
   (proposta: 0,80 fuori campione, vedi sopra).
5. **Quando passare al lotto da 5.000**: proposta, un lotto verde con la
   revisione sotto il 10%.
