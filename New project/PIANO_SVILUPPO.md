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
| 6 | Agente tester | in attesa della scelta dell'LLM |

Ancora deboli, e scritti nella guida: la fascia "solo tema" (46% uguale al
batch), i titoli nuovi (37%), le lingue senza modello di traduzione.

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

1. **Regione principale:** Belgio o Milano.
2. **Rigenerare i requisiti con P10–P15** prima di congelare il dizionario.
   La parità (97,8%) mostra che le differenze vengono tutte da lì.
3. **`title_family`:** una famiglia di ruolo sopra `title_group`, come
   `req_topic` sopra `req_group`. Serve una lista di famiglie decisa a mano.
4. **Linguaggio degli sviluppatori di Karimi:** se non è Python, si riattiva
   l'API. Deciso per ora: solo libreria.
5. **Soglie di accordo per l'agente tester**, da fissare prima della taratura.
