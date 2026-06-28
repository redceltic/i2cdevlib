# KI-Wirtschaftlichkeits-Check — N8N-Workflow (MVP v1)

Self-hosted N8N-Workflow, der aus einer **Gesprächsaufnahme** + einem **Kundendokument (PDF)**
automatisch eine strukturierte, lückentransparente **Wirtschaftlichkeitsanalyse als PDF** erzeugt.
DSGVO-konform — alle Modelle laufen lokal, keine Daten verlassen das System.

Umsetzung des Konzepts *„KI-Wirtschaftlichkeits-Check-Tool — MVP-Konzept v1.1"*.

Datei zum Import: [`Wirtschaftlichkeits-Check_MVP_v1.json`](./Wirtschaftlichkeits-Check_MVP_v1.json)

---

## Live-Dashboard (Mission Control, integriert)

Der Workflow **startet und endet per Webhook** und bringt ein eigenes, schwarzes Live-Dashboard mit
(Design „Mission Control"). Der frühere Form-Trigger ist **durch ein ins Dashboard integriertes Formular
ersetzt**. Ablauf:

1. Dashboard öffnen: **`GET https://<n8n-host>/webhook/wcheck`** → Button **„Start"** → das Formular
   (Unternehmen, Audio, Kundendokumente) klappt direkt im Dashboard auf.
2. Absenden → **`POST /webhook/wcheck-start`** (multipart) startet die Analyse, antwortet **sofort** mit
   `{run_id}` (Respond-Node, `responseMode: responseNode`) und lässt die Pipeline weiterlaufen.
3. Das Dashboard **pollt** `GET /webhook/wcheck-status?run=<id>` (alle 1,5 s) und aktualisiert nach **jedem
   Schritt** live: Fortschrittsring, Node-Status (mit Kurz-Ergebnis je Node), Kennzahlen und Live-Log.
4. Ist alles fertig, erscheint **„PDF herunterladen"** → **`GET /webhook/wcheck-pdf?run=<id>`** liefert das
   fertige PDF zum Download. (Die Dropbox-Ablage bleibt zusätzlich erhalten.)

### Variante B – Status als Dateien (gewählt)
Nach jeder Node schreibt ein **Checkpoint** den kumulierten Stand als Datei nach `/tmp`
(`wc_status_<run>.json`), die finale Node legt zusätzlich `wc_pdf_<run>.pdf` ab. Die Status-/PDF-Webhooks
lesen diese Dateien. Kein externer Dienst (Redis o. ä.) nötig.

**Aufräumen (DSGVO):** Die Dateien werden **nicht dauerhaft** vorgehalten:
- Das **Kunden-PDF wird direkt nach dem Download vom Server gelöscht** (`wc-pdf` → `unlink`). Der Download
  ist daher **einmalig**; ein zweiter Klick liefert „not_ready". Bei Bedarf erneut analysieren.
- Bei **jedem neuen Lauf** entfernt „Run anlegen" alle `wc_*`-Dateien, die **älter als 1 Stunde** sind
  (TTL-Sweep, selbstwartend, kein Scheduler). TTL in `dash_layer.py` (`Run anlegen`, Konstante `TTL`) änderbar.

> **VORAUSSETZUNG (einmalig setzen):** Die Code-Nodes lesen/schreiben per `fs`. In n8n muss dafür
> **`NODE_FUNCTION_ALLOW_BUILTIN=fs`** gesetzt sein (Env-Variable des n8n-Servers). Fehlt sie, läuft die
> **Analyse trotzdem** (alle `fs`-Aufrufe sind in `try/catch`), aber das Dashboard bleibt leer.
> Ablageort `/tmp` ist in der `WCBASE`-Konstante (in `Run anlegen`, den Checkpoints, den Webhook-Nodes)
> bzw. zentral in `dash_layer.py` änderbar.

> **Aktivierung:** Für echte (Production-)Webhook-URLs muss der Workflow in n8n **aktiv** geschaltet sein.
> Im Test-Modus lauten die Pfade `/webhook-test/...` und feuern nur nach „Execute workflow".

### Quelle / Generator
Der Workflow wird aus **`gen.py`** + **`dash_layer.py`** erzeugt (`python3 gen.py`). Die Dashboard-/Webhook-
Schicht (4 Webhooks, Checkpoints, Status-Builder, HTML) liegt vollständig in `dash_layer.py`.

---

## Architektur (Node-Übersicht)

```
Formular-Upload (Audio + PDF + Unternehmen)
   └─ Config ─ Inputs normalisieren ─ N00pre (Input-Qualität, regelbasiert) ─ IF Freigabe?
         ├─ nein → Eingabe abgelehnt (Fehlerreport mit Korrekturhinweisen)
         └─ ja  → ┌ N00  Whisper-Transkription ─────────────────────────┐
                  └ N00b PDF-Strecke (pro PDF):                          │
                       Text extrahieren → genug Text? ─ ja → Text        ┤ Sync → Analyse-Kontext
                                                      └ nein → rastern    │
                                                        + Vision-OCR ─────┘
                       → alle Dokumenttexte zusammenführen
                     → N01 Kontext & Prozess
                     → N02 Automatisierungsreife
                     → N03 Nutzen-TREIBER (Stunden/Volumen, keine €-Rechnung)
                     → N04 Kosten-TREIBER (Stunden/Infra, keine €-Rechnung)
                     → N05a Kennzahlen (DETERMINISTISCH: €, ROI, Break-Even, Sensitivität)
                     → N05b Kennzahl-Prosa (LLM, nur Text zu den Zahlen)
                     → N06 Umsetzbarkeit
                     → N07 Risiko & Compliance
                     → N08a Score-Aggregation (regelbasiert, KEIN LLM)
                     → N08b Begründungstext (LLM, ändert Score nicht)
                     → N09 Lückenaggregation (regelbasiert)
                     → N10 Report-HTML → Gotenberg PDF → Dropbox-Upload
```

Jede LLM-Node bekommt **nur den für sie relevanten Input** (atomares Prinzip aus dem Konzept).
N00pre, **N05a**, N08a und N09 sind **regelbasiert ohne LLM** und damit vollständig auditierbar.

### Arithmetik gehört nicht ins LLM
Alle Euro-/ROI-/Break-Even-Berechnungen passieren **deterministisch in `N05a` (JavaScript)** — das LLM
liefert in N03/N04 nur die **Treiber** (Stunden, Volumen, Infra-Kosten) mit Belegt/Geschätzt/Annahme,
und N05b formuliert ausschließlich Prosa zu den fertig berechneten Zahlen. So sind ROI Jahr 1 und Jahr 3
**garantiert konsistent** (gleiche Einmalkosten), und N05a enthält einen Reproduzierbarkeits-/Plausibilitäts-Check
(flaggt extreme Werte, mehrheitlich angenommene Treiber, fehlende Validierung).

### Wirtschafts-Parameter (eine Quelle der Wahrheit)
Die `Config`-Node enthält `params`: **ein** Stundensatz (für Nutzen *und* Kosten), Mandatsvolumen/Monat,
Entwicklungsstunden, Pflegestunden, Infra-€/Monat und das `validiert`-Flag. Aus den Quellen **extrahierte**
Werte haben Vorrang; fehlt ein Treiber, nutzt N05a den Config-Default und kennzeichnet ihn als `Annahme (Default)`.
Das verhindert zwei Stundensätze für dieselbe Person und unmarkierte Volumenannahmen.

### Wertmodell & abrechenbarer Zeitanteil (af)
Gesparte Zeit ist **nicht automatisch Geld**. N05a bestimmt das Wertmodell regelbasiert aus
LLM-**Fakten** (nicht aus einer vom LLM erfundenen Quote):
- **Umsatz** — belegter Verkaufspreis vorhanden → Wert steckt in der Verkaufsmarge (`af = 0`, keine Doppelzählung mit der Effizienz).
- **Effizienz** — Tätigkeit wird heute erbracht *und* Kapazität ausgelastet → freie Zeit fließt in bezahlte Arbeit.
- **Effizienz unsicher** — sonst; die Zeit wird nur dann zu Geld, wenn sie nachweislich für bezahlte Arbeit genutzt wird.

Der **abrechenbare Zeitanteil `af`** (Anteil der freigesetzten Zeit, der real verwertet wird) ist eine
**Auslastungs-Annahme als Band** (`af_szenarien` in der Config: konservativ/real/optimistisch), nicht ein
Schwarz-Weiß-Schalter. Daraus ergibt sich der realisierte Nutzen als **Spanne** (worst–real–best) statt einer
Scheingenauigkeit. Brutto-Zeitwert (bei `af=1`) und Verkaufs-Gesamtpotenzial werden separat als **nicht
realisierte Obergrenze** ausgewiesen — transparent statt mitgezählt. Ist die Auslastung im Input *belegt*,
nutzt N05a diese statt des Bandes.

### Validierungs-Kopplung (JC-06)
Solange `params.validiert = false`, gelten die Kennzahlen als **„vorläufig"** (Badge im PDF) und die
Ampel ist auf **max. „Pilotieren"** gedeckelt — ein unvalidiertes System erreicht kein „Weiterführen"
mit harten ROI-Zahlen. Nach bestandenem Vergleichstest `validiert: true` setzen → Zahlen werden final.

---

## Verwendete Infrastruktur (aus deinen bestehenden Workflows übernommen)

| Funktion | Endpunkt / Tool |
|---|---|
| Transkription | Whisper `http://100.120.133.22:8000/transcribe` (`large-v3`, `de`, `verbose_json`) |
| LLM | **LM Studio** (OpenAI-kompatibel) `http://100.120.133.22:1234/v1/chat/completions` |
| Bild-PDF-Rasterung | `http://100.120.133.22:5001/pdf2png` |
| Vision-OCR | LM Studio, Modell `qwen3-vl-30b` |
| PDF-Erzeugung | **Gotenberg** `http://gotenberg:3000/forms/chromium/convert/html` (HTML→PDF) |
| Ablage | Dropbox `/2 Leclere-Solutions/Wirtschaftlichkeits-Checks/` |

> **Anpassung gegenüber Konzept:** N10 nutzt **Gotenberg + HTML/CSS** statt ReportLab —
> konsistent mit deinen anderen Workflows und mit voller CSS-Kontrolle über das Layout.

---

## Modelle (LM Studio / MLX, Mac Studio 512 GB)

- **Analyse (N01–N08b):** `qwen/qwen3-235b-a22b-2507` — stärkstes verfügbares Modell, ideal für
  ROI/Zahlenlogik; bei 512 GB kein Problem.
- **Bild-PDF-OCR:** `qwen/qwen3-vl-30b`.
- **Schnellere Alternativen** (in `Config` → `llm_model` umstellbar):
  `nemotron-cascade-2-30b-a3b` oder `openai/gpt-oss-20b`.

Beide Modelle müssen in LM Studio geladen sein (Server auf Port 1234). Identifier mit
`GET http://100.120.133.22:1234/v1/models` prüfen; Modelle zentral in der `Config`-Node änderbar.

---

## N08a — Aggregations-Regelwerk (schließt offenen Punkt #2 des Konzepts)

Gewichteter Mittelwert der Teilscores (jeweils 0–10), skaliert auf 0–100:

| Dimension | Node | Gewicht |
|---|---|---|
| Automatisierungsreife | N02 | 20 % |
| Direkter Nutzen | N03 | 15 % |
| Wirtschaftlichkeit (ROI) | N05 | 30 % |
| Umsetzbarkeit | N06 | 20 % |
| Risiko & Compliance | N07 | 15 % |

`Score = Σ(score × Gewicht) / Σ(Gewicht der vorhandenen Scores) × 10`

**Ampel-Kategorie** (Basiswert nach Score): ≥80 *Gezielt skalieren* · 65–79 *Weiterführen* ·
50–64 *Pilotieren* · 35–49 *Vereinfachen* · <35 *Stoppen*.

**Fehlende/unsichere Teilscores werden ausgeschlossen** (nicht als 0 gewertet): ein Teilscore zählt
als „fehlend", wenn er keine Zahl liefert **oder** `score 0` bei `konfidenz 0` hat. Nur die vorhandenen
Teilscores gehen in den gewichteten Mittelwert ein.

**Datenvollständigkeit korrigiert die Kategorie:**
- *mittlere* Vollständigkeit → Downgrade um 1 Stufe
- **„Beobachten"** nur, wenn **< 40 % der Gewichtung** abgedeckt sind **oder ≥ 2 Nodes technisch
  fehlgeschlagen** sind (leeres Ergebnis) — nicht schon, wenn ohnehin erst später bestimmbare Werte fehlen
- Risiko-Score (N07) ≤ 3 → erzwingt mindestens **„Nachschärfen"**

**Technische Analysefehler** (leere Node-Antwort) werden separat geführt (`analyse_fehler`) und als
roter Hinweis im PDF ausgegeben — kein stilles Versagen (JC-04).

---

## Import & Inbetriebnahme

1. **Importieren:** N8N → *Workflows* → *Import from File* → `Wirtschaftlichkeits-Check_MVP_v1.json`.
2. **Credentials zuordnen:** Dropbox-Node (`Dropbox account 3`) ggf. neu verknüpfen.
3. **Config prüfen:** Node `Config` — `llm_model`, Endpunkt-URLs, Schwellen, Gewichte.
4. **Modell laden:** in LM Studio `gpt-oss-120b` (MLX) laden und Server auf Port `1234` starten.
5. **Testlauf:** Formular-URL öffnen, anonymisierte/synthetische Audio + PDF hochladen
   (für den Cloud-Vergleich aus dem Konzept **keine echten Kundendaten** in Cloud-Modelle).

### Test-Input
`test/TEST_Kundendokument_Mustermann_GmbH.pdf` — synthetisches, anonymisiertes Kunden-PDF
(KMU „Mustermann GmbH" mit Prozess-, Zeit- und Kostenangaben) zum Testen der PDF-Strecke.
Audio aus einer beliebigen vorhandenen deutschen Aufnahme (> 2 Min) nehmen.

### Eingangsschwellen (N00pre)
**Mindestens eine Eingabe genügt** — Audio `mp3/wav/m4a/ogg` **und/oder** ein/mehrere PDF(s).
Ein reines Konzept-PDF ohne Aufnahme läuft also genauso wie ein reines Interview ohne Dokument.
Fehlt das Audio, wird die Transkription übersprungen (Node `Audio vorhanden?` → `Ohne Audio`); fehlt
Text, wird das als Lücke markiert. Bild-PDFs laufen automatisch über den Vision-OCR-Fallback.
Der PDF-Kopf weist die Basis aus (`Gespräch + Dokument` / `nur Dokument` / `nur Gespräch`).

---

## PDF-Verarbeitung in v1 (mehrere Dokumente + Bild-PDF-Fallback)

- **Mehrere PDFs**: Das Formularfeld akzeptiert mehrere Dateien. `PDFs auftrennen` erzeugt ein
  Item pro PDF; am Ende führt `Dokumente zusammenfuehren` alle Texte (mit Dokument-Überschrift) zusammen.
- **Bild-PDF-Fallback**: Liefert die native Textextraktion zu wenig Text (< `pdf_min_chars`),
  wird das PDF über `:5001/pdf2png` gerastert und per **Vision-OCR** (`qwen3-vl-30b`) ausgelesen.
  Maschinenlesbare PDFs nehmen weiter den schnellen Textpfad.
- **Voraussetzung**: Für den Fallback muss in LM Studio zusätzlich das Vision-Modell
  (`vlm_model`, Standard `qwen3-vl-30b`) geladen sein.
- **Annahme**: `pdf2png` liefert pro Anfrage ein Bild. Mehrseitige *Bild*-PDFs werden über die
  zurückgegebene(n) Seite(n) verarbeitet — bei sehr großen Scan-Dokumenten ggf. seitenweise prüfen.

## Bewusst NICHT in v1 (Erweiterungen für v1.1)

- **Diarisierung (pyannote `:8001`)** — Sprecher-Trennung. Im Konzept „soweit möglich"; für die
  Wirtschaftlichkeitsanalyse nicht erforderlich. Lässt sich aus deinem Meeting-Workflow einhängen.
- **Transkript-Cleanup (Chunking + LLM-Glättung)** — wie im Meeting-Workflow, optional vor N01.
  Hier nicht nötig, da das Transkript nur Zwischeninput für N01 ist (kein Deliverable).
