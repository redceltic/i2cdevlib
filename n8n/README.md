# KI-Wirtschaftlichkeits-Check — N8N-Workflow (MVP v1)

Self-hosted N8N-Workflow, der aus einer **Gesprächsaufnahme** + einem **Kundendokument (PDF)**
automatisch eine strukturierte, lückentransparente **Wirtschaftlichkeitsanalyse als PDF** erzeugt.
DSGVO-konform — alle Modelle laufen lokal, keine Daten verlassen das System.

Umsetzung des Konzepts *„KI-Wirtschaftlichkeits-Check-Tool — MVP-Konzept v1.1"*.

Datei zum Import: [`Wirtschaftlichkeits-Check_MVP_v1.json`](./Wirtschaftlichkeits-Check_MVP_v1.json)

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
                     → N03 Direkter Nutzen (€)
                     → N04 Vollkosten (€)
                     → N05 Nutzen-Kosten / ROI / Break-Even
                     → N06 Umsetzbarkeit
                     → N07 Risiko & Compliance
                     → N08a Score-Aggregation (regelbasiert, KEIN LLM)
                     → N08b Begründungstext (LLM, ändert Score nicht)
                     → N09 Lückenaggregation (regelbasiert)
                     → N10 Report-HTML → Gotenberg PDF → Dropbox-Upload
```

Jede LLM-Node bekommt **nur den für sie relevanten Input** (atomares Prinzip aus dem Konzept).
N00pre, N08a und N09 sind **regelbasiert ohne LLM** und damit vollständig auditierbar.

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

## Modell (LM Studio / MLX, Mac Studio 512 GB)

- **Standard:** `gpt-oss-120b` (MLX) — bewährt für deutsche strukturierte Ausgabe, schnelles MoE,
  starkes Reasoning für ROI/Kosten, Apache-2.0.
- **Max-Quality-Alternative** (RAM ist vorhanden): `qwen3-235b-a22b` (MLX) — nahe Frontier-Niveau,
  v. a. für N05 (ROI/Sensitivität).
- **Leichter/schneller:** `qwen3-30b-a3b` (MLX).

Modell **zentral** in der `Config`-Node änderbar (`llm_model`). Exakten Identifier mit
`GET http://100.120.133.22:1234/v1/models` prüfen und ggf. anpassen.

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

**Datenvollständigkeit korrigiert die Kategorie** (deshalb 72 ≠ automatisch „Weiterführen"):
- *mittlere* Vollständigkeit → Downgrade um 1 Stufe
- *geringe* Vollständigkeit → Kategorie wird **„Beobachten"**
- Risiko-Score (N07) ≤ 3 → erzwingt mindestens **„Nachschärfen"**

Vollständigkeit ergibt sich aus der Zahl der `[Fehlend]`-Kennzeichnungen + Lücken + fehlender Teilscores.
Das Regelwerk wird als Klartext im PDF mit ausgegeben.

---

## Import & Inbetriebnahme

1. **Importieren:** N8N → *Workflows* → *Import from File* → `Wirtschaftlichkeits-Check_MVP_v1.json`.
2. **Credentials zuordnen:** Dropbox-Node (`Dropbox account 3`) ggf. neu verknüpfen.
3. **Config prüfen:** Node `Config` — `llm_model`, Endpunkt-URLs, Schwellen, Gewichte.
4. **Modell laden:** in LM Studio `gpt-oss-120b` (MLX) laden und Server auf Port `1234` starten.
5. **Testlauf:** Formular-URL öffnen, anonymisierte/synthetische Audio + PDF hochladen
   (für den Cloud-Vergleich aus dem Konzept **keine echten Kundendaten** in Cloud-Modelle).

### Eingangsschwellen (N00pre)
Audio `mp3/wav/m4a/ogg` (Pflicht), mindestens ein PDF (Pflicht). PDFs werden NICHT mehr auf
Maschinenlesbarkeit abgewiesen — Bild-PDFs laufen automatisch über den Vision-OCR-Fallback.
Audiodauer (≥ 2 Min) wird nach N00 geprüft und sonst als Lücke markiert.

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
