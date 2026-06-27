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
         └─ ja  → ┌ N00  Whisper-Transkription ┐
                  └ N00b PDF-Extraktion         ┴ Sync → Analyse-Kontext
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
Audio `mp3/wav/m4a/ogg`, PDF maschinenlesbar (≥ 200 Zeichen Text), PDF ≤ 50 MB.
Audiodauer (≥ 2 Min) und PDF-Lesbarkeit werden nach N00/N00b geprüft und sonst als Lücke markiert.

---

## Bewusst NICHT in v1 (Erweiterungen für v1.1)

- **Diarisierung (pyannote `:8001`)** — Sprecher-Trennung. Im Konzept „soweit möglich"; für die
  Wirtschaftlichkeitsanalyse nicht erforderlich. Lässt sich aus deinem Meeting-Workflow einhängen.
- **Bild-PDF-Fallback** — Rasterisierung `:5001/pdf2png` + Vision (`qwen3-vl`) für nicht
  maschinenlesbare PDFs. v1 erwartet maschinenlesbare PDFs (per N00pre).
- **Mehrere PDFs gleichzeitig** — v1 verarbeitet ein Dokument. Mehrere: vorher mergen oder
  Extraktions-Branch duplizieren.
- **Transkript-Cleanup (Chunking + LLM-Glättung)** — wie im Meeting-Workflow, optional vor N01.
