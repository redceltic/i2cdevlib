#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generator fuer den KI-Wirtschaftlichkeits-Check N8N-Workflow (MVP v1)."""
import json

INSTANCE = "a0614df2cfd5aeb98559c07e95e5a3ac8e7ab7c6b9bd4979f66c809fd549f8d8"
nodes = []
connections = {}

def add(name, ntype, params, tv=1, pos=(0, 0), extra=None):
    node = {
        "parameters": params,
        "id": "node-" + name.lower().replace(" ", "-").replace("·", "x").replace(":", "")[:40],
        "name": name,
        "type": ntype,
        "typeVersion": tv,
        "position": list(pos),
    }
    if extra:
        node.update(extra)
    nodes.append(node)
    return name

def connect(a, b, out=0, inp=0):
    connections.setdefault(a, {}).setdefault("main", [])
    main = connections[a]["main"]
    while len(main) <= out:
        main.append([])
    main[out].append({"node": b, "type": "main", "index": inp})

CODE = "n8n-nodes-base.code"
HTTP = "n8n-nodes-base.httpRequest"

# Shared JS helpers embedded into code nodes
PARSE_FN = (
    "function parseLLM(nodeName){\n"
    "  try {\n"
    "    const r = $(nodeName).first().json;\n"
    "    let c = (r && r.choices && r.choices[0] && r.choices[0].message && r.choices[0].message.content) || '';\n"
    "    if (typeof c !== 'string') c = JSON.stringify(c);\n"
    "    const tEnd = c.lastIndexOf('</think>');\n"
    "    if (tEnd !== -1) c = c.slice(tEnd + 8);            // alles bis inkl. letztem </think> verwerfen\n"
    "    c = c.replace(/<think>[\\s\\S]*?<\\/think>/g,'').replace(/```json|```/g,'');\n"
    "    const s = c.indexOf('{'), e = c.lastIndexOf('}');\n"
    "    return JSON.parse(s>=0 && e>s ? c.slice(s, e+1) : c);\n"
    "  } catch(_) { return {}; }\n"
    "}\n"
)

SYS_BASE = (
    "Du bist ein praeziser Wirtschaftlichkeits-Analyst fuer KMU. Du arbeitest streng faktenbasiert "
    "und erfindest NIEMALS Zahlen. Jede Zahl und jede Aussage erhaelt eine Kennzeichnung: "
    "'Belegt' (direkt aus dem Input, mit Quelle), 'Geschaetzt' (abgeleitet, mit Herleitung), "
    "'Annahme' (Standardannahme, nicht im Input vorhanden), 'Fehlend' (nicht verfuegbar, vor Entscheidung zu klaeren). "
    "MINDEST-PRINZIP: Wenn ein exakter Wert (noch) nicht ermittelbar ist, liefere die bestmoegliche "
    "begruendete Schaetzung - bevorzugt als Spanne (best/real/worst) - mit Kennzeichnung 'Geschaetzt' oder "
    "'Annahme'. 'Fehlend' NUR, wenn es gar keine Grundlage fuer eine Schaetzung gibt. Liegen Bausteine vor "
    "(z.B. Zeitaufwand, Haeufigkeit, Stundensatz), MUSST du daraus rechnen statt 'Fehlend' zu setzen. "
    "AUSNAHME (wichtig): Bei NACHFRAGE- oder PREISABHAENGIGEN Groessen (kuenftiger Umsatz, Verkaufspreis, "
    "ob gesparte Zeit real verkauft/abgerechnet werden kann) ohne Beleg ist 'Fehlend' + Bedingung das KORREKTE "
    "Ergebnis - hier NICHT selbstsicher schaetzen. Eine erfundene Umsatz-/Preiszahl ist ein teurer Falsch-sicher-Fehler. "
    "Antworte AUSSCHLIESSLICH mit EINEM gueltigen JSON-Objekt nach dem vorgegebenen Schema. "
    "Kein Markdown, kein Codeblock, kein Fliesstext davor oder danach. Alle Inhalte auf Deutsch."
)

# ---------------------------------------------------------------- 0) Eingang via Dashboard-Webhook
# Der fruehere Form-Trigger ist durch die Webhook-/Dashboard-Schicht (siehe dash_layer.py) ersetzt:
# Webhook "Analyse-Start" -> "Run anlegen" -> Config. Das Formular ist ins Dashboard integriert.

# ---------------------------------------------------------------- Config
add("Config", CODE, {"jsCode":
"// Zentrale Konfiguration - hier Modell/Endpunkte/Gewichte aendern.\n"
"const inp = $input.first();\n"
"// Stundensatz: Formular-Eingabe (pro Kunde) hat Vorrang vor dem branchenunabhaengigen Default.\n"
"const _ovRaw = inp.json && (inp.json.stundensatz_override != null ? inp.json.stundensatz_override : (inp.json.body && inp.json.body.stundensatz));\n"
"const _ov = Number(_ovRaw);\n"
"const _satsBelegt = Number.isFinite(_ov) && _ov > 0;\n"
"const _sats = _satsBelegt ? _ov : 60;   // 60 EUR/h = neutraler KMU-Default (UNBELEGT, bitte je Kunde setzen)\n"
"// Vorgaenge/Monat (Volumen) - Formular-Eingabe hat Vorrang vor dem Default.\n"
"const _volN = Number(inp.json && (inp.json.vorgaenge_override != null ? inp.json.vorgaenge_override : (inp.json.body && inp.json.body.vorgaenge)));\n"
"const _volBelegt = Number.isFinite(_volN) && _volN > 0; const _vol = _volBelegt ? _volN : 3;\n"
"// Aufbau-/Entwicklungsstunden (einmalig) - Formular-Eingabe hat Vorrang vor dem Default.\n"
"const _entN = Number(inp.json && (inp.json.aufbaustunden_override != null ? inp.json.aufbaustunden_override : (inp.json.body && inp.json.body.aufbaustunden)));\n"
"const _entBelegt = Number.isFinite(_entN) && _entN > 0; const _ent = _entBelegt ? _entN : 24;\n"
"// Verwendung: 'intern' (Default, reine Prozessoptimierung) oder 'verkauf' (externes Produkt) + optional Verkaufspreis.\n"
"const _na = String((inp.json && (inp.json.nutzungsart || (inp.json.body && inp.json.body.nutzungsart))) || 'intern').toLowerCase();\n"
"const _nutzungsart = (_na === 'verkauf') ? 'verkauf' : 'intern';\n"
"const _vpN = Number(inp.json && (inp.json.verkaufspreis_override != null ? inp.json.verkaufspreis_override : (inp.json.body && inp.json.body.verkaufspreis)));\n"
"const _verkaufspreis = (Number.isFinite(_vpN) && _vpN > 0) ? _vpN : null;\n"
"return [{\n"
"  json: { ...inp.json, config: {\n"
"    // LLM (LM Studio, OpenAI-kompatibel). Standard: qwen3-235b-a22b-2507 (MLX, 512GB).\n"
"    // Schnellere Alternativen: 'nemotron-cascade-2-30b-a3b' oder 'openai/gpt-oss-20b'\n"
"    llm_url:   'http://100.120.133.22:1234/v1/chat/completions',\n"
"    llm_model: 'qwen/qwen3-235b-a22b-2507',\n"
"    whisper_url:   'http://100.120.133.22:8000/transcribe',\n"
"    gotenberg_url: 'http://gotenberg:3000/forms/chromium/convert/html',\n"
"    // Bild-PDF-Fallback (nicht maschinenlesbare PDFs): Rasterung + Vision-OCR\n"
"    rasterize_url: 'http://100.120.133.22:5001/pdf2png',\n"
"    vlm_model: 'qwen/qwen3-vl-30b',\n"
"    temperature: 0,\n"
"    thresholds: { audio_min_sek: 120, pdf_max_mb: 50, audio_exts: ['mp3','wav','m4a','ogg'], pdf_min_chars: 200 },\n"
"    // Aggregationsgewichte N08a (Summe = 1.0)\n"
"    gewichte: { N02: 0.20, N03: 0.15, N05: 0.30, N06: 0.20, N07: 0.15 },\n"
"    // === Wirtschafts-Parameter (EINE Quelle der Wahrheit; aus Quellen extrahierte Werte haben Vorrang) ===\n"
"    params: {\n"
"      stundensatz_eur: _sats, stundensatz_belegt: _satsBelegt,  // Formular-Eingabe > Default 60; belegter Quellwert hat in N05a weiter Vorrang\n"
"      // af = Anteil der freigesetzten Zeit, der REAL in abrechenbare Arbeit fliesst. BAND statt Punktwert,\n"
"      // weil es eine Auslastungs-ANNAHME ist (NIE 1.0 als Default). Deterministisch aus Fakten + Band gerechnet.\n"
"      af_szenarien:     { konservativ: 0.2, real: 0.4, optimistisch: 0.7 },  // nicht ausgelastet\n"
"      af_szenarien_eng: { konservativ: 0.4, real: 0.6, optimistisch: 0.85 }, // ausgelastet (dreht Auftraege ab)\n"
"      kapazitaet_ausgelastet: false, // true -> hoeheres af-Band gerechtfertigt (verdraengt reale Arbeit)\n"
"      mandate_pro_monat: _vol, mandate_belegt: _volBelegt,       // Formular-Eingabe > Default 3; treibt den Nutzen linear\n"
"      entwicklungsstunden: _ent, entwicklungsstunden_belegt: _entBelegt,    // Formular-Eingabe > Default 24; belegte Quellangabe hat in N04/N05a weiter Vorrang\n"
"      pflege_stunden_pro_monat: 1,// laufende Eigenleistung (Wartung/Fehlerbehandlung)\n"
"      infra_eur_pro_monat: 30,    // anteilige Infrastruktur (Strom/Backup/Abschreibung)\n"
"      nutzungsart: _nutzungsart, verkaufspreis: _verkaufspreis,  // intern (Default) vs. verkauf; Preis nur bei Verkauf\n"
"      lizenz_eur_pro_monat: 0,    // externe Lizenzen/Cloud (self-hosted i.d.R. 0)\n"
"      sens_volumen: [1, 3, 5],    // Sensitivitaet: worst/real/best Mandate pro Monat\n"
"      validiert: false            // JC-06 Vergleichstest bestanden? -> erst dann harte Zahlen / >Pilotieren\n"
"    }\n"
"  } },\n"
"  binary: inp.binary\n"
"}];\n"
}, tv=2, pos=(-1000, 0))
# Trigger: Webhook -> Run anlegen -> "Antwort: run_id" (Respond, sofort 200) -> Config -> Pipeline.
connect("Antwort: run_id", "Config")

# ---------------------------------------------------------------- Normalize binaries
add("Inputs normalisieren", CODE, {"jsCode":
"// Bringt die Form-Uploads auf feste Binary-Keys: 'audio' und 'pdf_0','pdf_1',...\n"
"const inp = $input.first();\n"
"// Binary direkt vom Webhook lesen (robust, falls die Respond-Node die Binaerdaten nicht durchreicht).\n"
"let bin = inp.binary || {};\n"
"try { const wb = $('Webhook: Analyse-Start').first().binary; if (wb && Object.keys(wb).length) bin = wb; } catch(e){}\n"
"const out = {};\n"
"let audioKey = null;\n"
"const pdfKeys = [];\n"
"for (const [k, v] of Object.entries(bin)) {\n"
"  const mt = (v.mimeType || '').toLowerCase();\n"
"  const fn = (v.fileName || '').toLowerCase();\n"
"  if (!audioKey && (mt.startsWith('audio') || /\\.(mp3|wav|m4a|ogg)$/.test(fn))) audioKey = k;\n"
"  else if (mt.includes('pdf') || fn.endsWith('.pdf')) pdfKeys.push(k);\n"
"}\n"
"if (audioKey) out.audio = bin[audioKey];\n"
"pdfKeys.forEach((k, i) => { out['pdf_' + i] = bin[k]; });\n"
"return [{ json: { ...inp.json, _pdf_count: pdfKeys.length }, binary: out }];\n"
}, tv=2, pos=(-800, 0))
connect("Config", "Inputs normalisieren")

# ---------------------------------------------------------------- N00pre Input-Qualitaetspruefung
add("N00pre · Input-Qualitaetspruefung", CODE, {"jsCode":
"// Regelbasierte Eingangspruefung (kein LLM). Setzt json.freigabe + json.fehlerreport.\n"
"const inp = $input.first();\n"
"const cfg = $('Config').first().json.config;\n"
"const t = cfg.thresholds;\n"
"const bin = inp.binary || {};\n"
"const errors = [];\n"
"const audio = bin.audio;\n"
"const pdfCount = Number(inp.json._pdf_count || 0);\n"
"const has_audio = !!audio;\n"
"const has_pdf = pdfCount > 0;\n"
"if (has_audio) {\n"
"  const fn = (audio.fileName || '').toLowerCase();\n"
"  const okExt = t.audio_exts.some(e => fn.endsWith('.' + e)) || (audio.mimeType || '').startsWith('audio');\n"
"  if (!okExt) errors.push('Audioformat nicht unterstuetzt (erlaubt: ' + t.audio_exts.join(', ') + ').');\n"
"}\n"
"// Mindestens eine Eingabe genuegt (Audio ODER PDF) - z.B. nur ein Konzept-PDF.\n"
"if (!has_audio && !has_pdf) errors.push('Bitte mindestens eine Audiodatei ODER ein PDF hochladen.');\n"
"const freigabe = errors.length === 0;\n"
"return [{ json: { ...inp.json, freigabe, has_audio, has_pdf, fehlerreport: errors,\n"
"  hinweis_dauer: 'Audiodauer >= ' + (t.audio_min_sek/60) + ' Min und PDF-Maschinenlesbarkeit werden nach N00/N00b geprueft.' },\n"
"  binary: bin }];\n"
}, tv=2, pos=(-600, 0))
connect("Inputs normalisieren", "N00pre · Input-Qualitaetspruefung")

# ---------------------------------------------------------------- IF Freigabe
add("Freigabe erteilt?", "n8n-nodes-base.if", {
    "conditions": {"options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
        "conditions": [{"id": "cond-freigabe",
            "leftValue": "={{ $json.freigabe }}", "rightValue": True,
            "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
        "combinator": "and"},
    "options": {},
}, tv=2.2, pos=(-400, 0))
connect("N00pre · Input-Qualitaetspruefung", "Freigabe erteilt?")

# False branch -> Fehlerreport (terminal)
add("Eingabe abgelehnt", CODE, {"jsCode":
"// Negativfall JC-00: Workflow startet die Analyse NICHT, liefert konkrete Korrekturhinweise.\n"
"const j = $input.first().json;\n"
"// Dashboard-Status auf 'abgelehnt' setzen, damit das Polling nicht endlos laeuft.\n"
"const fs = (function(){ try { return require('fs'); } catch(e){ return null; } })();\n"
"let run = null; try { run = $('Run anlegen').first().json.run_id; } catch(e){}\n"
"try { if (fs && run) { fs.writeFileSync('/tmp/wc_status_' + run + '.json', JSON.stringify({\n"
"  run_id: run, state: 'rejected', pct: 0, done_count: 0, total: 11, nodes: [],\n"
"  meldung: 'Eingangspruefung nicht bestanden', korrekturhinweise: (j.fehlerreport || []),\n"
"  log: [{ ts: new Date().toLocaleTimeString('de-DE'), msg: 'Eingabe abgelehnt' }] })); } } catch(e){}\n"
"return [{ json: { status: 'abgelehnt', unternehmen: j.Unternehmen || '',\n"
"  meldung: 'Eingangspruefung nicht bestanden. Bitte korrigieren und erneut hochladen.',\n"
"  korrekturhinweise: j.fehlerreport || [] } }];\n"
}, tv=2, pos=(-200, 200))
connect("Freigabe erteilt?", "Eingabe abgelehnt", out=1)

# ---------------------------------------------------------------- N00 Whisper
add("N00 · Whisper Transkription", HTTP, {
    "method": "POST",
    "url": "={{ $('Config').first().json.config.whisper_url }}",
    "sendBody": True, "contentType": "multipart-form-data",
    "bodyParameters": {"parameters": [
        {"parameterType": "formBinaryData", "name": "file", "inputDataFieldName": "audio"},
        {"name": "model_size", "value": "large-v3"},
        {"name": "response_format", "value": "verbose_json"},
        {"name": "language", "value": "de"},
    ]},
    "options": {"timeout": 1800000},
}, tv=4.2, pos=(-20, -160),
    extra={"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 3000,
           "onError": "continueRegularOutput"})

# Audio ist optional: nur transkribieren, wenn eine Aufnahme vorhanden ist.
add("Audio vorhanden?", "n8n-nodes-base.if", {
    "conditions": {"options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
        "conditions": [{"id": "cond-audio",
            "leftValue": "={{ $json.has_audio }}", "rightValue": True,
            "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
        "combinator": "and"},
    "options": {},
}, tv=2.2, pos=(-200, -120))
connect("Freigabe erteilt?", "Audio vorhanden?", out=0)
connect("Audio vorhanden?", "N00 · Whisper Transkription", out=0)

add("Audio -> Transkript", CODE, {"jsCode":
"// Normalisiert die Whisper-Antwort auf {transcript, dauer}.\n"
"const w = $('N00 · Whisper Transkription').first().json;\n"
"const transcript = w.transcription || w.text ||\n"
"  (Array.isArray(w.segments) ? w.segments.map(s => s.text).join(' ') : '');\n"
"const dauer = Number(w.duration || w.audio_duration || 0);\n"
"return [{ json: { transcript, dauer, quelle: 'audio' } }];\n"
}, tv=2, pos=(160, -160))
connect("N00 · Whisper Transkription", "Audio -> Transkript")

add("Ohne Audio", CODE, {"jsCode":
"// Kein Audio hochgeladen -> leeres Transkript, Analyse laeuft auf Dokumentbasis.\n"
"return [{ json: { transcript: '', dauer: 0, quelle: 'kein_audio' } }];\n"
}, tv=2, pos=(160, -60))
connect("Audio vorhanden?", "Ohne Audio", out=1)

# Konsolidierung NICHT per Merge (gibt bei uebersprungenem Eingang 0 / PDF-only nichts aus -> 500),
# sondern per Code-Node: liest den Zweig, der gelaufen ist, und liefert IMMER genau ein Transkript.
add("Transkript", CODE, {"jsCode":
"// Genau einer der beiden Zweige laeuft (Audio vorhanden? IF). Lies den gelaufenen, liefere immer 1 Item.\n"
"let tr = { transcript: '', dauer: 0, quelle: 'kein_audio' };\n"
"try { const a = $('Audio -> Transkript').first().json; if (a && (a.quelle === 'audio' || (a.transcript && a.transcript.length))) tr = a; } catch(e){}\n"
"if (tr.quelle !== 'audio') { try { const o = $('Ohne Audio').first().json; if (o) tr = o; } catch(e){} }\n"
"return [{ json: tr }];\n"
}, tv=2, pos=(360, -120))
connect("Audio -> Transkript", "Transkript")
connect("Ohne Audio", "Transkript")

# ---------------------------------------------------------------- N00b PDF-Sub-Pipeline (Multi-PDF + Bild-PDF-Fallback)
add("PDFs auftrennen", CODE, {"jsCode":
"// Ein Item pro hochgeladenem PDF (binary 'pdf').\n"
"const inp = $input.first();\n"
"const bin = inp.binary || {};\n"
"const items = [];\n"
"let idx = 0;\n"
"for (const [k, v] of Object.entries(bin)) {\n"
"  if (k.indexOf('pdf_') === 0) {\n"
"    items.push({ json: { pdf_index: idx, pdf_name: v.fileName || ('Dokument_' + (idx + 1)) }, binary: { pdf: v } });\n"
"    idx++;\n"
"  }\n"
"}\n"
"if (!items.length) items.push({ json: { pdf_index: 0, pdf_name: '(kein PDF)' }, binary: {} });\n"
"return items;\n"
}, tv=2, pos=(-200, 120))
connect("Freigabe erteilt?", "PDFs auftrennen", out=0)

add("N00b · PDF-Text", "n8n-nodes-base.extractFromFile", {
    "operation": "pdf", "binaryPropertyName": "pdf", "options": {},
}, tv=1, pos=(-20, 120), extra={"onError": "continueRegularOutput"})
connect("PDFs auftrennen", "N00b · PDF-Text")

add("PDF-Text bewerten", CODE, {"mode": "runOnceForEachItem", "jsCode":
"// Pro PDF: Textmenge bewerten, Original-PDF-Binary wiederherstellen, OCR-Bedarf markieren.\n"
"const src = $('PDFs auftrennen').item;\n"
"const cfg = $('Config').first().json.config;\n"
"const text = String($json.text || $json.data || '');\n"
"const hasPdf = !!(src.binary && src.binary.pdf);  // Platzhalter ohne PDF -> kein OCR\n"
"return { json: {\n"
"  pdf_index: src.json.pdf_index, pdf_name: src.json.pdf_name,\n"
"  text, text_len: text.trim().length,\n"
"  needs_ocr: hasPdf && text.trim().length < cfg.thresholds.pdf_min_chars\n"
"}, binary: src.binary };\n"
}, tv=2, pos=(160, 120))
connect("N00b · PDF-Text", "PDF-Text bewerten")

add("PDF braucht OCR?", "n8n-nodes-base.if", {
    "conditions": {"options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
        "conditions": [{"id": "cond-ocr",
            "leftValue": "={{ $json.needs_ocr }}", "rightValue": True,
            "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
        "combinator": "and"},
    "options": {},
}, tv=2.2, pos=(360, 120))
connect("PDF-Text bewerten", "PDF braucht OCR?")

# --- Bild-PDF-Zweig: rastern -> Vision-OCR
add("PDF rasterisieren", HTTP, {
    "method": "POST",
    "url": "={{ $('Config').first().json.config.rasterize_url }}",
    "sendBody": True, "contentType": "binaryData", "inputDataFieldName": "pdf",
    "options": {"response": {"response": {"responseFormat": "file"}}, "timeout": 120000},
}, tv=4.2, pos=(560, 40), extra={"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 2000,
    "onError": "continueRegularOutput"})
connect("PDF braucht OCR?", "PDF rasterisieren", out=0)

add("Vision-OCR Prompt", CODE, {"jsCode":
"// Baut pro Bildseite einen Vision-Request (qwen3-vl) zur woertlichen Textextraktion.\n"
"const cfg = $('Config').first().json.config;\n"
"const sources = $('PDF-Text bewerten').all().filter(it => it.json.needs_ocr);\n"
"const all = $input.all();\n"
"const out = [];\n"
"for (let i = 0; i < all.length; i++) {\n"
"  const buf = await this.helpers.getBinaryDataBuffer(i, 'data');\n"
"  const b = all[i].binary && all[i].binary.data;\n"
"  const mime = (b && b.mimeType) || 'image/png';\n"
"  const dataUrl = 'data:' + mime + ';base64,' + buf.toString('base64');\n"
"  const src = sources[i] || { json: {} };\n"
"  out.push({ json: {\n"
"    pdf_index: src.json.pdf_index != null ? src.json.pdf_index : i,\n"
"    pdf_name: src.json.pdf_name || ('Dokument_' + (i + 1)),\n"
"    requestBody: {\n"
"      model: cfg.vlm_model, temperature: 0, max_tokens: 2000, stream: false,\n"
"      messages: [\n"
"        { role: 'system', content: 'Du bist ein praeziser OCR-Assistent. Gib den gesamten lesbaren Text des Dokumentbildes woertlich und vollstaendig zurueck, ohne Kommentar, ohne Markdown.' },\n"
"        { role: 'user', content: [\n"
"          { type: 'text', text: 'Extrahiere den gesamten Text aus diesem Dokumentbild woertlich.' },\n"
"          { type: 'image_url', image_url: { url: dataUrl } }\n"
"        ] }\n"
"      ]\n"
"    }\n"
"  } });\n"
"}\n"
"return out;\n"
}, tv=2, pos=(760, 40))
connect("PDF rasterisieren", "Vision-OCR Prompt")

add("Vision-OCR", HTTP, {
    "method": "POST",
    "url": "={{ $('Config').first().json.config.llm_url }}",
    "sendBody": True, "specifyBody": "json",
    "jsonBody": "={{ JSON.stringify($json.requestBody) }}",
    "options": {"timeout": 600000},
}, tv=4.2, pos=(960, 40),
    extra={"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 2000, "onError": "continueRegularOutput"})
connect("Vision-OCR Prompt", "Vision-OCR")

add("OCR-Text sammeln", CODE, {"jsCode":
"// Vision-Antworten -> {pdf_index, pdf_name, text}.\n"
"const prompts = $('Vision-OCR Prompt').all();\n"
"const res = $input.all();\n"
"return res.map((it, i) => {\n"
"  const j = it.json; let c = '';\n"
"  if (j && j.choices && j.choices[0] && j.choices[0].message) c = j.choices[0].message.content || '';\n"
"  c = String(c).replace(/<think>[\\s\\S]*?<\\/think>/g, '').trim();\n"
"  const p = prompts[i] ? prompts[i].json : {};\n"
"  return { json: { pdf_index: p.pdf_index != null ? p.pdf_index : i, pdf_name: p.pdf_name || ('Dokument_' + (i + 1)), text: c } };\n"
"});\n"
}, tv=2, pos=(1160, 40))
connect("Vision-OCR", "OCR-Text sammeln")

# --- Beide Zweige sammeln + zusammenfuehren
add("PDF-Texte sammeln", "n8n-nodes-base.merge", {"mode": "append", "options": {}}, tv=3, pos=(960, 160))
connect("PDF braucht OCR?", "PDF-Texte sammeln", out=1, inp=0)   # Text-Pfad
connect("OCR-Text sammeln", "PDF-Texte sammeln", inp=1)         # OCR-Pfad

add("Dokumente zusammenfuehren", CODE, {"jsCode":
"// Alle Dokumenttexte (Text-Pfad + OCR-Pfad) nach Reihenfolge zu einem Block.\n"
"const items = $input.all();\n"
"const docs = items.map(it => it.json).filter(d => d && d.text != null)\n"
"  .sort((a, b) => (a.pdf_index || 0) - (b.pdf_index || 0));\n"
"const combined = docs.map(d => '### ' + (d.pdf_name || 'Dokument') + '\\n' + (d.text || '')).join('\\n\\n');\n"
"return [{ json: { dokumente: combined, doc_count: docs.length, doc_names: docs.map(d => d.pdf_name) } }];\n"
}, tv=2, pos=(1160, 160))
connect("PDF-Texte sammeln", "Dokumente zusammenfuehren")

# ---------------------------------------------------------------- Merge sync (Audio + Dokumente)
add("Sync: Transkript + Dokument", "n8n-nodes-base.merge", {
    "mode": "combine", "combineBy": "combineByPosition", "options": {},
}, tv=3, pos=(1360, 80))
connect("Transkript", "Sync: Transkript + Dokument", inp=0)
connect("Dokumente zusammenfuehren", "Sync: Transkript + Dokument", inp=1)

# ---------------------------------------------------------------- Analyse-Kontext
add("Analyse-Kontext bauen", CODE, {"jsCode":
"// Buendelt Transkript + Dokumenttext + Meta. Erste Lueckenpruefung (Dauer, PDF-Textmenge).\n"
"const cfg = $('Config').first().json.config;\n"
"let tr = { transcript: '', dauer: 0, quelle: 'kein_audio' };\n"
"try { tr = $('Transkript').first().json || tr; } catch(e){}\n"
"let ex = { dokumente: '', doc_count: 0 };\n"
"try { ex = $('Dokumente zusammenfuehren').first().json || ex; } catch(e){}\n"
"const meta = $('N00pre · Input-Qualitaetspruefung').first().json;\n"
"const transcript = tr.transcript || '';\n"
"const dauer = Number(tr.dauer || 0);\n"
"const doku = ex.dokumente || '';\n"
"const has_audio = tr.quelle === 'audio' && transcript.trim().length > 0;\n"
"const has_doku = doku.trim().length >= cfg.thresholds.pdf_min_chars;\n"
"const luecken = [];\n"
"if (!has_audio)\n"
"  luecken.push({ was: 'Keine Gespraechsaufnahme vorhanden', wo: 'N00',\n"
"    konsequenz: 'Analyse nur auf Dokumentbasis - GF-Aussagen, Ziele und Mengengeruest evtl. unvollstaendig.' });\n"
"else if (dauer && dauer < cfg.thresholds.audio_min_sek)\n"
"  luecken.push({ was: 'Audiodauer unter ' + (cfg.thresholds.audio_min_sek/60) + ' Min', wo: 'N00',\n"
"    konsequenz: 'Gespraechsinhalt evtl. unvollstaendig - Analyse weniger belastbar.' });\n"
"if (!has_doku)\n"
"  luecken.push({ was: 'Kein (lesbarer) Dokumenttext vorhanden', wo: 'N00b',\n"
"    konsequenz: (doku.trim().length > 0 ? 'Sehr wenig Text (' + doku.trim().length + ' Zeichen) - moeglicherweise Bild-PDF.' : 'Keine Dokumente - Analyse nur auf Gespraechsbasis.') });\n"
"// B2: Vom Anwender im Formular gesetzte Treiber - gelten als BELEGT (eine Quelle der Wahrheit fuer alle Nodes).\n"
"const cp = cfg.params; const anw = [];\n"
"if (cp.stundensatz_belegt) anw.push('Stundensatz ' + cp.stundensatz_eur + ' EUR/h');\n"
"if (cp.mandate_belegt) anw.push('Vorgaenge/Monat ' + cp.mandate_pro_monat);\n"
"if (cp.entwicklungsstunden_belegt) anw.push('Aufbau-/Entwicklungsstunden ' + cp.entwicklungsstunden);\n"
"anw.push('Verwendung: ' + (cp.nutzungsart === 'verkauf' ? ('Verkauf/Vermietung' + (cp.verkaufspreis ? ' zu ' + cp.verkaufspreis + ' EUR/Vorgang' : ' (Preis offen)')) : 'interne Prozessoptimierung (kein Verkauf)'));\n"
"return [{ json: {\n"
"  unternehmen: meta.Unternehmen || meta.unternehmen || '',\n"
"  datum: new Date().toISOString().slice(0, 10),\n"
"  anwender_eingaben: anw,\n"
"  transcript, dokumente: doku, dauer_sek: dauer, has_audio, has_doku, luecken_global: luecken\n"
"} }];\n"
}, tv=2, pos=(240, 0))
connect("Sync: Transkript + Dokument", "Analyse-Kontext bauen")

# ---------------------------------------------------------------- Helper to build LLM prompt + http nodes
def llm_pair(node_id, label, x, sys, user_js, prev_for_parse=None, max_tokens=1600, reasoning=False):
    """Erstellt ein Prompt-Code-Node + ein LM-Studio-HTTP-Node.
    reasoning=False -> /no_think (schnell, deterministisch). reasoning=True -> Modell darf denken."""
    pname = node_id + " · Prompt"
    lname = node_id + " · LLM"
    sys_full = sys if reasoning else ("/no_think\n" + sys)
    js = PARSE_FN
    js += "const cfg = $('Config').first().json.config;\n"
    js += "const ctx = $('Analyse-Kontext bauen').first().json;\n"
    if prev_for_parse:
        for var, nm in prev_for_parse:
            js += "const %s = parseLLM('%s');\n" % (var, nm)
    js += "const sys = %s;\n" % json.dumps(sys_full, ensure_ascii=False)
    js += user_js
    js += ("return [{ json: { requestBody: {\n"
           "  model: cfg.llm_model, temperature: cfg.temperature,\n"
           "  max_tokens: -1, stream: false,\n"
           "  messages: [ { role: 'system', content: sys }, { role: 'user', content: usr } ]\n"
           "} } }];\n")
    add(pname, CODE, {"jsCode": js}, tv=2, pos=(x, 0))
    add(lname, HTTP, {
        "method": "POST",
        "url": "={{ $('Config').first().json.config.llm_url }}",
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify($json.requestBody) }}",
        "options": {"timeout": 600000},
    }, tv=4.2, pos=(x + 160, 0),
        extra={"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 2000,
               "onError": "continueRegularOutput"})
    connect(pname, lname)
    return pname, lname

# ----- N01 Kontext & Prozess
n01_user = (
"const usr = 'Extrahiere aus Transkript und Kundendokument den geschaeftlichen Kontext und die "
"betroffenen Prozesse fuer eine Wirtschaftlichkeitsanalyse einer geplanten KI-/Automatisierungsloesung.\\n' +\n"
"'Das analysierte Unternehmen lautet (aus dem Formular): \"' + (ctx.unternehmen || 'unbekannt') + '\". "
"Verwende diesen Namen im Feld unternehmen, sofern die Quellen keinen anderen nennen.\\n' +\n"
"'PFLICHT: Fuelle unternehmen, branche und groesse_hinweis IMMER aus. Leite Branche und Groesse aus den Quellen ab "
"(Mindest-Prinzip - lieber begruendete Annahme/Schaetzung mit Kennzeichnung als leer). Diese drei Felder NIE leer lassen.\\n\\n' +\n"
"'Antworte als JSON mit Schema: {\"unternehmen\":\"\",\"branche\":\"\",\"groesse_hinweis\":\"\",' +\n"
"'\"betroffene_prozesse\":[{\"name\":\"\",\"beschreibung\":\"\",\"haeufigkeit\":\"\",\"heutiger_aufwand\":\"\"}],' +\n"
"'\"ist_zustand\":\"\",\"ziele\":[\"\"],\"geplante_loesung\":\"\",\"rahmenbedingungen\":\"\",' +\n"
"'\"kennzeichnungen\":[{\"wert\":\"\",\"art\":\"Belegt|Geschaetzt|Annahme|Fehlend\",\"quelle_oder_herleitung\":\"\"}],' +\n"
"'\"luecken\":[{\"was\":\"\",\"wo\":\"N01\",\"konsequenz\":\"\"}]}\\n\\n' +\n"
"'=== TRANSKRIPT ===\\n' + (ctx.transcript || '(keine Aufnahme)') + '\\n\\n=== KUNDENDOKUMENT ===\\n' + (ctx.dokumente || '(kein Dokument)');\n"
)
llm_pair("N01", "Kontext", 460,
    SYS_BASE + " Aufgabe: Kontext- und Prozessextraktion (Node N01).", n01_user, max_tokens=2200)
connect("Analyse-Kontext bauen", "N01 · Prompt")

PREV_N01 = [("n01", "N01 · LLM")]

def ctx_block(varname="n01"):
    return ("const basis = JSON.stringify(%s);\n" % varname)

# ----- N02 Automatisierungsreife
n02_user = ctx_block() + (
"const usr = 'Bewerte die Automatisierungsreife des Vorhabens anhand von 8 Kriterien "
"(Standardisierung, Regelbasiertheit, Datenverfuegbarkeit, Volumen/Haeufigkeit, Fehleranfaelligkeit heute, "
"Schnittstellen, Stabilitaet des Prozesses, Akzeptanz). Vergib pro Kriterium 0-10 und einen Gesamtscore 0-10. "
"Gib IMMER einen Gesamtscore ab, auch bei duenner Datenlage (dann konservativ schaetzen, art=Annahme). Antworte niemals leer.\\n\\n' +\n"
"'Uebernimm KEINE Kennzeichnungen oder Felder aus N01 - liefere nur deine eigene Reife-Bewertung.\\n\\n' +\n"
"'JSON-Schema: {\"score\":0,\"kriterien\":[{\"name\":\"\",\"wert\":0,\"begruendung\":\"\"}],\"konfidenz\":0.0,' +\n"
"'\"luecken\":[{\"was\":\"\",\"wo\":\"N02\",\"konsequenz\":\"\"}]}\\n\\n=== KONTEXT (N01) ===\\n' + basis;\n"
)
llm_pair("N02", "Automatisierungsreife", 760,
    SYS_BASE + " Aufgabe: Bewertung Automatisierungsreife (Node N02).", n02_user, PREV_N01)
connect("N01 · LLM", "N02 · Prompt")

# ----- N03 Direkter Nutzen (nur TREIBER extrahieren - KEINE Euro-/ROI-Rechnung!)
n03_user = ctx_block() + (
"const p = $('Config').first().json.config.params;\n"
"const usr = 'Extrahiere die TREIBER des direkten Nutzens als Zahlen. Du RECHNEST KEINE Euro-Betraege und KEINEN ROI - "
"das uebernimmt eine nachgelagerte Rechen-Node. Liefere nur die Mengengeruest-Werte mit Kennzeichnung.\\n' +\n"
"'KRITISCH: Du bestimmst die Abrechenbarkeit (af) NICHT als Zahl. Du lieferst nur FAKTEN: ob die Taetigkeit heute "
"schon erbracht/verkauft wird, ob konkrete Nachfrage gedeckt ist, und eine Auslastungszahl NUR falls explizit belegt. "
"Die Auslastungsquote berechnet die nachgelagerte Rechen-Node aus diesen Fakten und einem Config-Band. Erfinde keine Quote.\\n' +\n"
"'Felder (jeder wert = EINE Zahl): eingesparte_stunden_pro_vorgang (Std. reine Bearbeitungszeit, die je Vorgang wegfaellt), "
"fehlerreduktion_stunden_pro_vorgang (Wert VERMIEDENER Fehler/Nacharbeit, die HEUTE real anfaellt - NICHT die neue "
"Pruef-/QA-Zeit des KI-Outputs, die ist eine KOSTE und gehoert zu N04), "
"mandate_pro_monat (Anzahl Vorgaenge/Monat), "
"stundensatz_eur (Wert der Arbeitszeit - belegt, wenn im Text, z.B. 200 Euro pro Stunde -> art=Belegt), "
"verkaufspreis_pro_vorgang (Preis je Analyse - NUR wenn belegt; sonst art=Fehlend, NICHT erfinden), "
"liefer_eigenaufwand_std_pro_vorgang (Std. Eigenaufwand je verkauftem Vorgang).\\n' +\n"
"'FAKTEN-Felder: taetigkeit_wird_heute_erbracht (ja|nein - wird die Leistung heute schon erbracht/abgerechnet?), "
"nachfrage_gedeckt (ja|nein|unklar - gibt es bereits zahlende Kunden/gesicherte Nachfrage?), "
"auslastung_belegt (0..1 NUR wenn eine konkrete Auslastung oder abgelehnte Auftraege im Input genannt sind; sonst art=Fehlend).\\n' +\n"
"'Nimm Werte aus den Quellen (art=Belegt/Geschaetzt mit Herleitung); sonst wert=null + art=\"Fehlend\". Erfinde keine Zahl.\\n' +\n"
"((ctx.anwender_eingaben && ctx.anwender_eingaben.length) ? ('WICHTIG (B2): Folgende Werte hat der ANWENDER im Formular angegeben - behandle sie als VORHANDEN/BELEGT (art=Belegt), NICHT als fehlend, und ziehe den Score dafuer NICHT herunter: ' + ctx.anwender_eingaben.join('; ') + '.\\n') : '') +\n"
"'\\n' +\n"
"'JSON-Schema: {\"score\":0,\"nachfrage_gedeckt\":\"ja|nein|unklar\",' +\n"
"'\"taetigkeit_wird_heute_erbracht\":{\"wert\":\"ja|nein\",\"art\":\"Belegt|Geschaetzt\",\"herleitung\":\"\"},' +\n"
"'\"auslastung_belegt\":{\"wert\":null,\"art\":\"Belegt|Fehlend\",\"herleitung\":\"\"},' +\n"
"'\"eingesparte_stunden_pro_vorgang\":{\"wert\":null,\"art\":\"Belegt|Geschaetzt|Annahme|Fehlend\",\"herleitung\":\"\"},' +\n"
"'\"fehlerreduktion_stunden_pro_vorgang\":{\"wert\":null,\"art\":\"\",\"herleitung\":\"\"},' +\n"
"'\"mandate_pro_monat\":{\"wert\":null,\"art\":\"\",\"herleitung\":\"\"},' +\n"
"'\"stundensatz_eur\":{\"wert\":null,\"art\":\"\",\"herleitung\":\"\"},' +\n"
"'\"verkaufspreis_pro_vorgang\":{\"wert\":null,\"art\":\"\",\"herleitung\":\"\"},' +\n"
"'\"liefer_eigenaufwand_std_pro_vorgang\":{\"wert\":null,\"art\":\"\",\"herleitung\":\"\"},' +\n"
"'\"konfidenz\":0.0,\"luecken\":[{\"was\":\"\",\"wo\":\"N03\",\"konsequenz\":\"\"}]}\\n\\n=== KONTEXT (N01) ===\\n' + basis +\n"
"'\\n\\n=== TRANSKRIPT (fuer konkrete Zahlen/Zeiten) ===\\n' + (ctx.transcript || '(keine Aufnahme)');\n"
)
llm_pair("N03", "Direkter Nutzen", 1060,
    SYS_BASE + " Aufgabe: Nutzen-TREIBER extrahieren (Node N03). Du lieferst Mengengeruest (Stunden, Volumen), KEINE Euro-Rechnung. "
    "Der Score 0-10 spiegelt, wie substanziell und belegt der Nutzen ist.",
    n03_user, PREV_N01)
connect("N02 · LLM", "N03 · Prompt")

# ----- N04 Vollkosten (nur KOSTENTREIBER extrahieren - KEINE Euro-Summen/ROI!)
n04_user = ctx_block() + (
"const usr = 'Extrahiere die KOSTENTREIBER als Zahlen. Du RECHNEST KEINE Gesamtkosten und KEINEN ROI - "
"das uebernimmt die Rechen-Node. PFLICHT-Prinzip: Self-hosted ist NICHT kostenlos. Aufbauaufwand und laufende Pflege "
"fallen IMMER an (Opportunitaetskosten der Eigenleistung), Infrastruktur (Strom/Backup/Abschreibung) ebenso.\\n' +\n"
"'Felder (jeder wert = EINE Zahl): entwicklungsstunden (einmaliger Aufbauaufwand in STUNDEN, > 0; "
"WICHTIG: steht im Text eine Dauer in Tagen/Wochen (z.B. \"zwei Tage\"), rechne in Stunden um (1 Tag = 8 Std, "
"1 Woche = 40 Std) und setze art=Belegt - nicht auf den Default zurueckfallen), "
"pflege_stunden_pro_monat (NUR technische Wartung/Updates - typ. 0,5-2 h/Monat bei niedriger Frequenz; "
"NICHT die Pruefzeit pro Vorgang hier hineinrechnen, das ist ein eigenes Feld), "
"pruefzeit_std_pro_vorgang (menschliche Kontrolle/Freigabe des KI-Outputs JE Vorgang - skaliert mit Volumen, "
"reale Betriebskoste), "
"infra_eur_pro_monat (anteilige Infrastruktur, > 0 wenn Server/Strom genutzt werden), "
"lizenz_eur_pro_monat (externe Lizenzen/Cloud; self-hosted i.d.R. 0). "
"Nimm Werte aus den Quellen wenn vorhanden; sonst wert=null + art=\"Fehlend\" (Rechen-Node setzt Standardwert). Erfinde keine Zahl.\\n' +\n"
"((ctx.anwender_eingaben && ctx.anwender_eingaben.length) ? ('WICHTIG (B2): Vom ANWENDER im Formular angegeben - als VORHANDEN/BELEGT behandeln (z.B. Aufbau-/Entwicklungsstunden), NICHT als fehlend bewerten: ' + ctx.anwender_eingaben.join('; ') + '.\\n') : '') +\n"
"'\\n' +\n"
"'JSON-Schema: {\"score\":0,' +\n"
"'\"entwicklungsstunden\":{\"wert\":null,\"art\":\"Belegt|Geschaetzt|Annahme|Fehlend\",\"herleitung\":\"\"},' +\n"
"'\"pflege_stunden_pro_monat\":{\"wert\":null,\"art\":\"\",\"herleitung\":\"\"},' +\n"
"'\"pruefzeit_std_pro_vorgang\":{\"wert\":null,\"art\":\"\",\"herleitung\":\"\"},' +\n"
"'\"infra_eur_pro_monat\":{\"wert\":null,\"art\":\"\",\"herleitung\":\"\"},' +\n"
"'\"lizenz_eur_pro_monat\":{\"wert\":null,\"art\":\"\",\"herleitung\":\"\"},' +\n"
"'\"konfidenz\":0.0,\"luecken\":[{\"was\":\"\",\"wo\":\"N04\",\"konsequenz\":\"\"}]}\\n\\n=== KONTEXT (N01) ===\\n' + basis;\n"
)
llm_pair("N04", "Vollkosten", 1360,
    SYS_BASE + " Aufgabe: Kostentreiber extrahieren (Node N04). Du lieferst Mengengeruest (Stunden, Infra-EUR), KEINE Gesamtrechnung. "
    "Score 0-10: 10 = sehr geringe/gut belegte Kostenbasis.",
    n04_user, PREV_N01)
connect("N03 · LLM", "N04 · Prompt")

# ----- N05a Kennzahlen (DETERMINISTISCH - kein LLM; einzige Quelle der Arithmetik)
add("N05a · Kennzahlen", CODE, {"jsCode":
PARSE_FN +
"// Rechnet Nutzen/Kosten/ROI/Break-Even/Sensitivitaet REGELBASIERT.\n"
"// Treiber-Vorrang: Belegt > Geschaetzt > Config-Fallback. Config nur, wenn keine Evidenz da ist.\n"
"const p = $('Config').first().json.config.params;\n"
"const n03 = parseLLM('N03 · LLM'), n04 = parseLLM('N04 · LLM');\n"
"const herkunft = [];\n"
"function pick(obj, key, def, label, floor, cfgBelegt) {\n"
"  const cell = obj && obj[key];\n"
"  let w = cell ? Number(cell.wert) : NaN;\n"
"  const art = cell ? String(cell.art || '').toLowerCase() : '';\n"
"  let quelle, herleitung;\n"
"  if (Number.isFinite(w) && (art === 'belegt' || art === 'geschaetzt')) { quelle = (cell.art || 'Geschaetzt'); herleitung = cell.herleitung || ''; }\n"
"  else if (cfgBelegt && Number.isFinite(Number(def))) { w = Number(def); quelle = 'Anwender-Eingabe (Formular)'; herleitung = 'Pro Kunde im Dashboard angegeben.'; }\n"
"  else { w = def; quelle = 'Config-Standard (Fallback)'; herleitung = 'Keine belegte/geschaetzte Quelle - Config-Wert (' + def + ').'; }\n"
"  if (floor != null && w < floor) { w = floor; quelle = quelle + ' / Mindestwert'; herleitung = 'Mindestansatz erzwungen (Self-hosted ist nicht kostenlos): ' + label + '.'; }\n"
"  herkunft.push({ groesse: label, wert: w, quelle: quelle, herleitung: herleitung });\n"
"  return w;\n"
"}\n"
"// === Wertmodell & af-Resolver (deterministisch; LLM liefert nur Fakten) ===\n"
"const nachfrage = (n03 && n03.nachfrage_gedeckt) ? String(n03.nachfrage_gedeckt).toLowerCase() : 'unklar';\n"
"const wird_erbracht = String((n03 && n03.taetigkeit_wird_heute_erbracht && n03.taetigkeit_wird_heute_erbracht.wert) || '').toLowerCase().indexOf('ja') === 0;\n"
"const ausgelastet = !!p.kapazitaet_ausgelastet;\n"
"// Stundensatz gesondert: belegt/geschaetzt aus Quelle > Anwender-Eingabe (Formular) > unbelegter Default.\n"
"let sats, satsBelegt;\n"
"{ const cell = n03 && n03.stundensatz_eur; const w = cell ? Number(cell.wert) : NaN; const art = cell ? String(cell.art||'').toLowerCase() : '';\n"
"  if (Number.isFinite(w) && w > 0 && (art === 'belegt' || art === 'geschaetzt')) { sats = w; satsBelegt = true; herkunft.push({ groesse:'Stundensatz EUR/h', wert:sats, quelle:(cell.art||'Geschaetzt')+' (Quelle)', herleitung: cell.herleitung||'' }); }\n"
"  else if (p.stundensatz_belegt) { sats = p.stundensatz_eur; satsBelegt = true; herkunft.push({ groesse:'Stundensatz EUR/h', wert:sats, quelle:'Anwender-Eingabe (Formular)', herleitung:'Pro Kunde im Dashboard angegeben.' }); }\n"
"  else { sats = p.stundensatz_eur; satsBelegt = false; herkunft.push({ groesse:'Stundensatz EUR/h', wert:sats, quelle:'Default-Annahme (UNBELEGT)', herleitung:'KEIN belegter Stundensatz - branchenunabhaengiger Default. ALLE Euro-Kennzahlen skalieren DIREKT mit diesem Wert; realen Satz des Kunden im Formular eintragen.' }); } }\n"
"const h_save = pick(n03,'eingesparte_stunden_pro_vorgang', 2, 'Eingesparte Std/Vorgang');\n"
"const h_err  = pick(n03,'fehlerreduktion_stunden_pro_vorgang', 0, 'Vermiedene Fehler Std/Vorgang');\n"
"const vol    = pick(n03,'mandate_pro_monat', p.mandate_pro_monat, 'Vorgaenge/Monat', 1, p.mandate_belegt);\n"
"const liefer_h = pick(n03,'liefer_eigenaufwand_std_pro_vorgang', 0, 'Liefer-Eigenaufwand Std/Vorgang');\n"
"// Verkaufspreis NUR wenn belegt/geschaetzt (nie erfinden).\n"
"// Verwendung (aus Formular): 'intern' = reine Prozessoptimierung (Default), 'verkauf' = externes Produkt.\n"
"const nutzungsart = (String(p.nutzungsart || 'intern').toLowerCase() === 'verkauf') ? 'verkauf' : 'intern';\n"
"const preisCell = n03 && n03.verkaufspreis_pro_vorgang;\n"
"const preisNum = preisCell ? Number(preisCell.wert) : NaN;\n"
"const preisArt = preisCell ? String(preisCell.art||'').toLowerCase() : '';\n"
"const preisForm = Number(p.verkaufspreis);\n"
"// Verkaufspreis nur relevant, wenn verkauft wird. Formular-Eingabe hat Vorrang vor LLM-Beleg. Intern -> immer null.\n"
"let preis_belegt = null;\n"
"if (nutzungsart === 'verkauf') {\n"
"  if (Number.isFinite(preisForm) && preisForm > 0) preis_belegt = preisForm;\n"
"  else if (Number.isFinite(preisNum) && (preisArt==='belegt' || preisArt==='geschaetzt')) preis_belegt = preisNum;\n"
"}\n"
"// Auslastung NUR wenn explizit belegt.\n"
"const auslCell = n03 && n03.auslastung_belegt;\n"
"const auslNum = auslCell ? Number(auslCell.wert) : NaN;\n"
"const ausl_belegt = (Number.isFinite(auslNum) && /belegt/i.test((auslCell && auslCell.art)||'')) ? Math.max(0, Math.min(1, auslNum)) : null;\n"
"// Wertmodell REGELBASIERT (nicht vom LLM): Preis belegt -> Umsatz; sonst erbracht & ausgelastet -> Effizienz; sonst unsicher.\n"
"let wertmodell;\n"
"if (nutzungsart === 'intern') wertmodell = 'effizienz';        // interne Prozessoptimierung -> Wert = freigesetzte Zeit (af-Band), KEIN Verkauf\n"
"else if (preis_belegt != null) wertmodell = 'umsatz_neu';      // verkauft + Preis bekannt\n"
"else wertmodell = 'verkauf_unklar';                            // Verkauf geplant, aber kein Preis angegeben\n"
"// af und Verkaufspfad sind ZWEI Sichten auf DENSELBEN Zeitwert -> nie beide voll (keine Doppelzaehlung).\n"
"const band = (ausgelastet ? p.af_szenarien_eng : p.af_szenarien) || { konservativ:0.2, real:0.4, optimistisch:0.7 };\n"
"let af_low, af_real, af_high, af_quelle;\n"
"if (wertmodell === 'umsatz_neu') { af_low=0; af_real=0; af_high=0; af_quelle='Umsatzmodell: af=0 (Wert in Verkaufsmarge, keine Doppelzaehlung)'; }\n"
"else if (ausl_belegt != null) { af_real=ausl_belegt; af_low=Math.max(0, ausl_belegt-0.2); af_high=Math.min(1, ausl_belegt+0.2); af_quelle='Belegt (Auslastung aus Quelle)'; }\n"
"else { af_low=band.konservativ; af_real=band.real; af_high=band.optimistisch; af_quelle='Config-Band (Auslastung unbelegt; ' + (ausgelastet?'ausgelastet':'nicht ausgelastet') + ')'; }\n"
"// B6/B7: Bei UNKLARER/keiner Nachfrage konvertiert freigesetzte Zeit im Worst Case GAR NICHT in Geld -> wahre Untergrenze af=0.\n"
"if (wertmodell !== 'umsatz_neu' && nachfrage !== 'ja' && ausl_belegt == null) { af_low = 0; af_quelle += ' / Worst-Case af=0 (Nachfrage ' + nachfrage + ': freigesetzte Zeit evtl. ohne Geldwert)'; }\n"
"// B7: Terminologie ans Wertmodell koppeln (Effizienz rechnet keine Stunden ab).\n"
"const af_label = (wertmodell === 'umsatz_neu') ? 'Abrechenbarer Zeitanteil af' : 'Wertschoepfend genutzter Zeitanteil af';\n"
"herkunft.push({ groesse: af_label, wert: af_real, quelle: af_quelle, herleitung: 'VERWERTUNGS-ANNAHME, keine Tatsache. Band ' + af_low + '/' + af_real + '/' + af_high + '. Fakten: wird_erbracht=' + wird_erbracht + ', nachfrage=' + nachfrage + ', preis_belegt=' + (preis_belegt!=null) + '.' });\n"
"// Kostentreiber\n"
"const ent_h  = pick(n04,'entwicklungsstunden', p.entwicklungsstunden, 'Entwicklungsstunden', 8, p.entwicklungsstunden_belegt);\n"
"const pfl_h  = pick(n04,'pflege_stunden_pro_monat', p.pflege_stunden_pro_monat, 'Pflege Std/Monat', 0.5);\n"
"const pruef_h= pick(n04,'pruefzeit_std_pro_vorgang', 0, 'Pruefzeit Std/Vorgang');\n"
"const infra  = pick(n04,'infra_eur_pro_monat', p.infra_eur_pro_monat, 'Infra EUR/Monat', 1);\n"
"const lizenz = pick(n04,'lizenz_eur_pro_monat', p.lizenz_eur_pro_monat, 'Lizenz EUR/Monat', 0);\n"
"const einmalkosten = ent_h * sats;\n"
"// Pro-Vorgang-Pruefzeit ist eine KOSTE und skaliert mit Volumen (F2).\n"
"function kostenMonatF(ph, v){ return ph*sats + pruef_h*v*sats + infra + lizenz; }\n"
"const kosten_monat = kostenMonatF(pfl_h, vol), kosten_jahr = kosten_monat * 12;\n"
"// Nutzen: Effizienz (af-Band) + Umsatz (REALISIERT nur bei gedeckter Nachfrage, sonst Potenzial).\n"
"const freed = h_save + h_err;\n"
"const effM = (af) => freed * vol * sats * af;\n"
"const eff_low = effM(af_low), eff_real = effM(af_real), eff_high = effM(af_high);\n"
"let umsatz_real_m = 0, umsatz_potenzial_m = 0;\n"
"if (preis_belegt != null) { const db = Math.max(0, preis_belegt - liefer_h*sats) * vol; if (nachfrage === 'ja') umsatz_real_m = db; else umsatz_potenzial_m = db; }\n"
"const real_m  = eff_real + umsatz_real_m;\n"
"const worst_m = eff_low  + umsatz_real_m;\n"
"const best_m  = eff_high + umsatz_real_m + umsatz_potenzial_m;\n"
"const nutzen_monat = real_m, nutzen_jahr = Math.round(real_m * 12);\n"
"const brutto_zeitwert_jahr = Math.round(freed * vol * sats * 12);   // af=1 Obergrenze\n"
"const potenzial_jahr = Math.round(best_m * 12);\n"
"const netto_monat = real_m - kosten_monat, netto_jahr = netto_monat * 12;\n"
"// === B1: Plausibilitaets-Gate (physikalischer Last-Check) VOR der Headline ===\n"
"const FTE_H_MONAT = 160;\n"
"const freed_h_month = freed * vol;\n"
"const fte_last = Math.round((freed_h_month / FTE_H_MONAT) * 100) / 100;\n"
"const qOf = (g) => { const e = herkunft.find(x => x.groesse === g); return e ? String(e.quelle) : ''; };\n"
"const h_save_fb = /Config-Standard|Default|Mindestwert/i.test(qOf('Eingesparte Std/Vorgang'));\n"
"const vol_fb    = /Config-Standard|Default|Mindestwert/i.test(qOf('Vorgaenge/Monat'));\n"
"// Implausibel: freigesetzte Zeit > 1 VZAe aus unbelegtem Treiber, ODER extreme Zeitersparnis je Routinevorgang aus Fallback.\n"
"const implausibel = ( (fte_last > 1.0 && (h_save_fb || vol_fb)) || (h_save > 1.0 && h_save_fb) );\n"
"const plausibilitaet = { ok: !implausibel, fte_last: fte_last, freed_h_month: Math.round(freed_h_month),\n"
"  hinweis: implausibel ? ('Angesetzte Zeitersparnis ' + freed + ' Std/Vorgang x ' + vol + ' Vorgaenge = ' + Math.round(freed_h_month) + ' Std/Monat = ' + fte_last + ' Vollzeit-Aequivalente allein fuer diesen Prozess - aus unbelegten Standardannahmen abgeleitet und damit physikalisch unrealistisch. Die Euro-Headline ist NICHT belastbar, bis Zeitersparnis je Vorgang UND Volumen belegt sind.') : '' };\n"
"const nutzen_bedingt = (umsatz_potenzial_m > 0) || (wertmodell === 'verkauf_unklar');   // nur bei Verkaufsabsicht\n"
"// ROI - EINE Definition fuer Jahr 1 und Jahr 3 (gleiche Einmalkosten).\n"
"function roiN(jahre, nm, km){ const ej = einmalkosten; const denom = km*12*jahre + ej; const net = (nm - km)*12; return denom > 0 ? Math.round(((net*jahre - ej)/denom)*1000)/10 : null; }\n"
"const beF = (nm, km) => (nm - km) > 0 ? Math.round((einmalkosten/(nm - km))*10)/10 : null;\n"
"const roi1 = roiN(1, real_m, kosten_monat), roi3 = roiN(3, real_m, kosten_monat);\n"
"const break_even = beF(real_m, kosten_monat);\n"
"// Sensitivitaet 1: af-Band (fuer diesen Fall der relevanteste Treiber)\n"
"const sensitivitaet_af = [['worst', worst_m, af_low], ['real', real_m, af_real], ['best', best_m, af_high]].map(function(t){ return { szenario: t[0] + ' (af ' + t[2] + ')', af: t[2], nutzen_jahr: Math.round(t[1]*12), break_even_monate: beF(t[1], kosten_monat), roi_jahr1: roiN(1, t[1], kosten_monat) }; });\n"
"const worstRoi = sensitivitaet_af[0].roi_jahr1;\n"
"// Sensitivitaet 2: Volumen. Worst = 0 (Nachfrage bleibt aus), ausser Nachfrage gesichert (F3).\n"
"const umsRealM = (v) => (preis_belegt != null && nachfrage === 'ja') ? Math.max(0, preis_belegt - liefer_h*sats) * v : 0;\n"
"const worstVol = (nachfrage === 'ja') ? Math.max(1, Math.round(vol*0.5)) : 0;\n"
"const svol = [worstVol, vol, Math.round(vol*1.5)];\n"
"const sensitivitaet = ['worst','real','best'].map(function(k,i){ const v = svol[i]; const nm = freed*v*sats*af_real + umsRealM(v); const km = kostenMonatF(pfl_h, v); return { szenario: k, vorgaenge_monat: v, nutzen_jahr: Math.round(nm*12), break_even_monate: beF(nm, km), roi_jahr1: roiN(1, nm, km) }; });\n"
"// Sensitivitaet 3: Pflegeaufwand\n"
"const sp = [Math.max(0.5, Math.round(pfl_h*0.4*10)/10), pfl_h, Math.round(pfl_h*2*10)/10];\n"
"const sensitivitaet_pflege = ['niedrig','real','hoch'].map(function(k,i){ const ph = sp[i]; const km = kostenMonatF(ph, vol); return { szenario: k, pflege_std_monat: ph, kosten_monat: Math.round(km), break_even_monate: beF(real_m, km), roi_jahr1: roiN(1, real_m, km) }; });\n"
"// Score deterministisch auf den REAL-Fall; negativer Worst-Case deckelt (F5).\n"
"let score;\n"
"if (netto_monat <= 0) score = 2; else if (break_even == null) score = 5; else if (break_even <= 3) score = 8; else if (break_even <= 6) score = 7; else if (break_even <= 12) score = 5; else if (break_even <= 24) score = 4; else score = 3;\n"
"if (worst_m - kosten_monat < 0) score = Math.min(score, 5);\n"
"// Daten-Konfidenz (getrennt von Rechensicherheit)\n"
"// B2/Belegt-Konsistenz: Fallback = Annahme/Default/Band (inkl. af-Annahme). Belegt = alles uebrige (Quelle ODER Anwender-Eingabe).\n"
"// WICHTIG: /belegt/ wuerde faelschlich 'unbelegt' matchen -> daher ueber den Fallback-Zaehler ableiten (eine Quelle der Wahrheit).\n"
"const fallbacks = herkunft.filter(x => /Config-Standard|Config-Band|Mindestwert|Unbekannt|Default-Annahme|UNBELEGT/i.test(x.quelle)).length;\n"
"const belegtN = herkunft.length - fallbacks;\n"
"const validiert = !!p.validiert;\n"
"const belegtAnteil = belegtN / herkunft.length;\n"
"let konfidenz = Math.max(0.2, Math.round((0.35 + 0.55 * belegtAnteil) * 100) / 100);\n"
"if (!validiert) konfidenz = Math.min(konfidenz, 0.6);\n"
"if (implausibel) konfidenz = Math.min(konfidenz, 0.3);\n"
"const status_zahlen = validiert ? 'final' : 'vorlaeufig';\n"
"// B4: Score-Daempfung - hoher Teilscore darf nicht auf duenner/implausibler Datenbasis stehen.\n"
"if (belegtAnteil < 0.5 || konfidenz < 0.5) score = Math.min(score, 6);\n"
"if (implausibel) score = Math.min(score, 3);\n"
"// B5: Label an Betriebszustand/Validierung koppeln - nichts ist 'realisiert', solange nicht validiert/produktiv.\n"
"const nutzen_label = validiert ? 'Realisierter Nutzen' : 'Erwarteter realisierbarer Nutzen (bedingt)';\n"
"const warnungen = [];\n"
"if (implausibel) warnungen.push('PLAUSIBILITAET: ' + plausibilitaet.hinweis);\n"
"if (!satsBelegt) warnungen.push('STUNDENSATZ NICHT BELEGT: Es wurde der branchenunabhaengige Default ' + sats + ' EUR/h verwendet (im Dokument/Transkript kein Satz gefunden). SAEMTLICHE Euro-Werte (Nutzen, ROI, Break-Even) skalieren direkt damit - bei einem anderen realen Satz aendern sich alle Zahlen proportional. Bitte den tatsaechlichen Stundensatz des Kunden im Formular angeben.');\n"
"if (wertmodell === 'verkauf_unklar') warnungen.push('VERKAUF GEPLANT, ABER KEIN PREIS: Externer Verkauf/Vermietung ist vorgesehen, aber es wurde kein Verkaufspreis angegeben - das Umsatzpotenzial ist NICHT beziffert. Bitte den geplanten Preis im Formular eintragen. Der ausgewiesene Nutzen enthaelt nur den internen Effizienzwert (Anteil af).');\n"
"else if (umsatz_potenzial_m > 0) warnungen.push('VERKAUFSPOTENZIAL UNGESICHERT: Verkaufspreis bekannt, aber Nachfrage nicht gesichert - das Umsatzpotenzial (' + Math.round(umsatz_potenzial_m*12) + ' EUR/Jahr) ist als NICHT realisiert ausgewiesen.');\n"
"if (ausl_belegt == null && wertmodell !== 'umsatz_neu') warnungen.push(af_label + ' NICHT belegt - Verwertungs-Annahme als Band ' + af_low + '/' + af_real + '/' + af_high + ' angesetzt; bestimmt den realisierten Effizienznutzen stark. Bei freier Kapazitaet ist af real eher klein. In Config.params (af_szenarien) pruefen.');\n"
"if (wertmodell === 'effizienz') warnungen.push('INTERNE NUTZUNG: Reine Prozessoptimierung (kein Verkauf). Der Nutzen ist der Wert der freigesetzten Arbeitszeit - dieser wird nur dann zu Geld, wenn die Zeit nachweislich fuer wertschoepfende Arbeit genutzt wird (Anteil af). Realisierter Nutzen daher als Spanne (worst ' + Math.round(worst_m*12) + ' bis best ' + Math.round(best_m*12) + ' EUR/Jahr).');\n"
"if (nachfrage !== 'ja') warnungen.push('Nachfrage nicht gesichert (nachfrage_gedeckt=' + nachfrage + '): Worst-Case = 0 Vorgaenge -> reiner Verlust moeglich.');\n"
"if (fallbacks >= 3) warnungen.push(fallbacks + ' von ' + herkunft.length + ' Treibern sind Standardannahmen/unbekannt (nicht belegt) - in Config.params anpassen.');\n"
"if (netto_monat <= 0) warnungen.push('Laufende Kosten erreichen/uebersteigen den realisierten Nutzen - Wirtschaftlichkeit marginal.');\n"
"if (!validiert) warnungen.push('Kennzahlen sind VORLAEUFIG: Der Vergleichstest (lokal vs. Cloud, JC-06) ist noch nicht bestanden.');\n"
"return [{ json: {\n"
"  score, konfidenz, rechensicherheit: 'deterministisch (Arithmetik regelbasiert)', status_zahlen, validiert,\n"
"  implausibel, plausibilitaet, nutzen_label, belegt_anteil: Math.round(belegtAnteil*100)/100, af_bezeichnung: af_label,\n"
"  wertmodell, nutzungsart, nachfrage_gedeckt: nachfrage, nutzen_bedingt,\n"
"  verkaufspotenzial_eur_jahr: Math.round(umsatz_potenzial_m * 12),\n"
"  af_band: { konservativ: af_low, real: af_real, optimistisch: af_high }, abrechenbarkeit_belegt: (ausl_belegt != null),\n"
"  stundensatz_eur: sats, stundensatz_belegt: satsBelegt, vorgaenge_pro_monat: vol,\n"
"  nutzen_eur_jahr: Math.round(nutzen_jahr), nutzen_eur_monat: Math.round(nutzen_monat),\n"
"  realisiert_spanne_eur_jahr: { worst: Math.round(worst_m*12), real: Math.round(nutzen_jahr), best: Math.round(best_m*12) },\n"
"  brutto_zeitwert_eur_jahr: brutto_zeitwert_jahr, potenzial_eur_jahr: potenzial_jahr,\n"
"  einmalkosten_eur: Math.round(einmalkosten), kosten_eur_monat: Math.round(kosten_monat), kosten_eur_jahr: Math.round(kosten_jahr),\n"
"  roi_jahr1_prozent: roi1, roi_jahr3_prozent: roi3, break_even_monate: break_even,\n"
"  sensitivitaet_af, sensitivitaet, sensitivitaet_pflege, parameter_herkunft: herkunft, warnungen,\n"
"  rechenweg: 'Wertmodell: ' + wertmodell + '. Realisierter Nutzen/Monat = Effizienz (' + (h_save+h_err) + ' Std x ' + vol + ' x ' + sats + ' EUR x af=' + af_real + ' = ' + Math.round(eff_real) + ' EUR)' + (umsatz_real_m>0 ? ' + Umsatz ' + Math.round(umsatz_real_m) + ' EUR' : '') + ' = ' + Math.round(nutzen_monat) + ' EUR. '\n"
"    + 'Theoretisches Maximum (af=1) = ' + brutto_zeitwert_jahr + ' EUR/Jahr (NICHT realisiert).' + (umsatz_potenzial_m>0 ? ' Zusaetzliches Verkaufspotenzial bei gesicherter Nachfrage = ' + Math.round(umsatz_potenzial_m*12) + ' EUR/Jahr (NICHT realisiert).' : '') + ' '\n"
"    + 'Kosten/Monat = Pflege ' + pfl_h + ' Std + Pruefzeit ' + pruef_h + ' Std x ' + vol + ' Vorgaenge (x ' + sats + ' EUR) + Infra ' + infra + ' + Lizenz ' + lizenz + ' = ' + Math.round(kosten_monat) + ' EUR. '\n"
"    + 'Einmalkosten = ' + ent_h + ' Std x ' + sats + ' = ' + Math.round(einmalkosten) + ' EUR.',\n"
"  luecken: [].concat(Array.isArray(n03.luecken)?n03.luecken:[], Array.isArray(n04.luecken)?n04.luecken:[])\n"
"} }];\n"
}, tv=2, pos=(1660, 0))
connect("N04 · LLM", "N05a · Kennzahlen")

# ----- N05b (LLM) - schreibt NUR die Prosa zu den fertig berechneten Zahlen
n05b_user = (
"const k = $('N05a · Kennzahlen').first().json;\n"
"const gate = k.implausibel ? ('\\n\\nACHTUNG FALSCH-SICHER-SPERRE: Die Kennzahlen sind als IMPLAUSIBEL/NICHT BELASTBAR markiert (' + (k.plausibilitaet && k.plausibilitaet.hinweis || '') + '). "
"Du DARFST in diesem Fall die konkreten Euro-, ROI- und Break-Even-Zahlen NICHT als Aussage/Headline nennen (kein \"der Nutzen liegt bei X EUR\", kein \"ROI von Y %\", kein \"Amortisation nach Z Monaten\"). "
"Fuehre stattdessen mit dem Vorbehalt: erklaere, dass die Wirtschaftlichkeit auf unbelegten Standardannahmen sitzt und erst nach Erhebung von Zeitersparnis je Vorgang und Volumen belastbar bezifferbar ist.') : '';\n"
"const usr = 'Formuliere 2-3 Saetze Prosa zur Wirtschaftlichkeit AUF BASIS der bereits berechneten Zahlen. "
"Du AENDERST oder ERFINDEST KEINE Zahlen - verwende exakt die uebergebenen Werte. Erklaere knapp, "
"was Nutzen, Kosten, ROI und Break-Even fuer den Geschaeftsfuehrer bedeuten, und nenne den groessten Hebel/Unsicherheit. "
"Verwende fuer den Parameter af die Bezeichnung \"' + (k.af_bezeichnung || 'wertschoepfend genutzter Zeitanteil') + '\" (NICHT \"abrechenbar\", ausser bei Verkaufsmodell).' + gate + '\\n\\n' +\n"
"'JSON-Schema: {\"begruendung\":\"\"}\\n\\n=== BERECHNETE KENNZAHLEN ===\\n' + JSON.stringify(k);\n"
)
llm_pair("N05b", "Kennzahl-Prosa", 1960,
    SYS_BASE + " Aufgabe: Prosa-Einordnung der berechneten Kennzahlen (Node N05b). KEINE eigenen Zahlen.",
    n05b_user, max_tokens=700)
connect("N05a · Kennzahlen", "N05b · Prompt")

# ----- N06 Umsetzbarkeit
n06_user = ctx_block() + (
"const usr = 'Bewerte technische und organisatorische Umsetzbarkeit (Score 1-10) mit Begruendung. "
"Beruecksichtige vorhandene Self-hosted-Infrastruktur (n8n, lokale Modelle), Datenlage, Change/Akzeptanz, Abhaengigkeiten.\\n\\n' +\n"
"'JSON-Schema: {\"score\":0,\"technisch\":{\"score\":0,\"begruendung\":\"\"},\"organisatorisch\":{\"score\":0,\"begruendung\":\"\"},' +\n"
"'\"konfidenz\":0.0,\"luecken\":[{\"was\":\"\",\"wo\":\"N06\",\"konsequenz\":\"\"}]}\\n\\n=== KONTEXT (N01) ===\\n' + basis;\n"
)
llm_pair("N06", "Umsetzbarkeit", 1960,
    SYS_BASE + " Aufgabe: Umsetzbarkeit technisch + organisatorisch (Node N06).", n06_user, PREV_N01)
connect("N05b · LLM", "N06 · Prompt")

# ----- N07 Risiko & Compliance
n07_user = ctx_block() + (
"const usr = 'Bewerte Risiko und Compliance: DSGVO, Governance, Modell-/Halluzinationsrisiko, Abhaengigkeiten. "
"WICHTIG: Ist ein kritisches Risiko - insbesondere die Falsch-sicher-/Halluzinationsrate - NICHT durch einen "
"bestandenen Validierungstest abgesichert, halte den Score niedrig (max. 6). Fuer Entscheidungs-Deliverables ist "
"die Falsch-sicher-Rate das dominante Einzelrisiko, nicht DSGVO/Technik. "
"WICHTIG zu GoBD und branchenspezifischen Vorgaben: Pruefe ZUERST, ob sie ueberhaupt einschlaegig sind. "
"GoBD gilt nur, wenn steuerlich/buchhalterisch relevante Aufzeichnungen erzeugt oder aufbewahrt werden. "
"Ein reines Beratungs-/Analyse-Deliverable ist in der Regel NICHT GoBD-pflichtig. "
"Wenn nicht einschlaegig: setze das Feld auf \"nicht einschlaegig\" und erzeuge dazu KEINE Luecke und KEIN Risiko. "
"VOICE/AUDIO-SONDERFALL (B8): Werden Telefon-/Sprachdaten verarbeitet (Anrufe, Aufnahmen, Sprachbestellungen), "
"darf DSGVO NICHT allein aus einer Lastenheft-Deklaration als \"abgesichert\" gelten. Pruefe die Pflicht-Checkliste: "
"(1) Einwilligung VOR der Aufzeichnung, (2) Hinweispflicht/Ansage, (3) Rechtsgrundlage fuer Stimmdaten (biometrie-nah), "
"(4) Loeschkonzept fuer Audio. Fehlt eine dokumentierte Einwilligung-vor-Aufnahme, ist dsgvo_status MAXIMAL \"teils offen\" "
"(nie \"abgesichert\"), und es ist eine entsprechende Luecke zu erzeugen. "
"GoBD-PFLICHTREGEL: Treten im Prozess Belege, Belegerfassung, Bestellungen, Auftraege, Lieferscheine, Quittungen, "
"Rechnungen oder buchungs-/steuerrelevante Aufzeichnungen auf (auch wenn sie nur Vorstufe sind, z.B. Bestelldaten, "
"die spaeter in Rechnung/Lieferung einfliessen), dann ist gobd_status MINDESTENS \"pruefen\" und gobd_anwendbar=true - "
"NIEMALS \"nicht einschlaegig\". Nur reine Analyse-/Beratungs-Deliverables ohne solche Belege sind GoBD-frei. "
"Bewerte nur tatsaechlich anwendbare Regime. Score 0-10 (10 = sehr geringes Risiko, sauber abgesichert).\\n\\n' +\n"
"'JSON-Schema: {\"score\":0,\"dsgvo_status\":\"\",\"gobd_anwendbar\":false,\"gobd_status\":\"\",\"governance_status\":\"\",' +\n"
"'\"kritische_risiken\":[\"\"],\"konfidenz\":0.0,\"luecken\":[{\"was\":\"\",\"wo\":\"N07\",\"konsequenz\":\"\"}]}\\n\\n' +\n"
"'=== KONTEXT (N01) ===\\n' + basis;\n"
)
llm_pair("N07", "Risiko-Compliance", 2260,
    SYS_BASE + " Aufgabe: Risiko & Compliance (Node N07).", n07_user, PREV_N01)
connect("N06 · LLM", "N07 · Prompt")

# ---------------------------------------------------------------- N08a Score-Aggregation (regelbasiert)
add("N08a · Score-Aggregation", CODE, {"jsCode":
PARSE_FN +
"// Regelbasierte Aggregation - KEIN LLM, vollstaendig auditierbar.\n"
"const cfg = $('Config').first().json.config;\n"
"const g = cfg.gewichte;\n"
"const n02 = parseLLM('N02 · LLM'), n03 = parseLLM('N03 · LLM'), n04 = parseLLM('N04 · LLM');\n"
"const n05 = $('N05a · Kennzahlen').first().json;  // deterministisch berechnet\n"
"const n06 = parseLLM('N06 · LLM'), n07 = parseLLM('N07 · LLM');\n"
"// F4: Ohne bestandene Validierung ist das dominante Risiko (Halluzination/Falsch-sicher) NICHT abgesichert\n"
"// -> Risiko-Score auf max. 6 deckeln (sonst stuetzt ein 9er den Gesamtscore unverdient).\n"
"const _n07cap = !!(n05 && n05.validiert) ? 10 : 6;\n"
"if (n07 && Number.isFinite(Number(n07.score)) && Number(n07.score) > _n07cap) { n07._score_roh = n07.score; n07.score = _n07cap; }\n"
"const isEmpty = (o) => !o || typeof o !== 'object' || Object.keys(o).length === 0;\n"
"// Fehlende Datenbasis (score 0 bei konfidenz 0) NICHT als 'schlecht' werten, sondern ausschliessen.\n"
"const sc = (o) => {\n"
"  const v = Number(o && o.score);\n"
"  if (!isFinite(v)) return null;\n"
"  const k = Number(o && o.konfidenz);\n"
"  if (v === 0 && (!isFinite(k) || k === 0)) return null;\n"
"  return Math.max(0, Math.min(10, v));\n"
"};\n"
"// Leere Nodes = Analysefehler (technisch), nicht legitime Luecke.\n"
"const analyse_fehler = [['N02',n02],['N03',n03],['N05',n05],['N06',n06],['N07',n07]].filter(p => isEmpty(p[1])).map(p => p[0]);\n"
"const parts = [['N02', sc(n02), g.N02], ['N03', sc(n03), g.N03], ['N05', sc(n05), g.N05], ['N06', sc(n06), g.N06], ['N07', sc(n07), g.N07]];\n"
"let wsum = 0, gsum = 0; const fehlende = [];\n"
"for (const [k, v, w] of parts) { if (v == null) fehlende.push(k); else { wsum += v * w; gsum += w; } }\n"
"const score100 = gsum > 0 ? Math.round((wsum / gsum) * 10) : 0;\n"
"function countFehlend(o) { let c = 0;\n"
"  if (o && Array.isArray(o.kennzeichnungen)) for (const k of o.kennzeichnungen) if (String(k.art||'').toLowerCase() === 'fehlend') c++;\n"
"  if (o && Array.isArray(o.luecken)) c += o.luecken.length; return c; }\n"
"// Nur echte Analysefehler + fehlende Teilscores treiben die Unvollstaendigkeit; einzelne [Fehlend]-Marker zaehlen schwaecher.\n"
"const fehlendTotal = analyse_fehler.length * 4 + fehlende.length * 2 + Math.min(4, [n02,n03,n04,n05,n06,n07].reduce((a,o)=>a+countFehlend(o),0));\n"
"const completeness = fehlendTotal <= 3 ? 'hoch' : (fehlendTotal <= 8 ? 'mittel' : 'gering');\n"
"const order = ['Stoppen','Vereinfachen','Nachschaerfen','Pilotieren','Weiterfuehren','Gezielt skalieren'];\n"
"function baseCat(s){ if(s>=80) return 'Gezielt skalieren'; if(s>=65) return 'Weiterfuehren'; if(s>=50) return 'Pilotieren'; if(s>=35) return 'Vereinfachen'; return 'Stoppen'; }\n"
"let cat = baseCat(score100);\n"
"if (completeness === 'mittel') cat = order[Math.max(0, order.indexOf(cat) - 1)];\n"
"// Vollwertige Abwertung auf 'Beobachten' nur, wenn zu wenige Teilscores fuer eine belastbare Aussage da sind.\n"
"if (gsum < 0.40 || analyse_fehler.length >= 2) cat = 'Beobachten';\n"
"if (sc(n07) != null && sc(n07) <= 3 && order.indexOf(cat) > order.indexOf('Nachschaerfen')) cat = 'Nachschaerfen';\n"
"// Validierungs-Kopplung (JC-06): vor bestandenem Vergleichstest KEINE Hochstufung ueber 'Pilotieren'.\n"
"const validiert = !!(n05 && n05.validiert);\n"
"let validierungs_deckel = false;\n"
"if (!validiert && order.indexOf(cat) > order.indexOf('Pilotieren')) { cat = 'Pilotieren'; validierungs_deckel = true; }\n"
"return [{ json: {\n"
"  score: score100, kategorie: cat, completeness, analyse_fehler,\n"
"  validiert, status: validiert ? 'final' : 'vorlaeufig', validierungs_deckel,\n"
"  teilscores: parts.map(p => ({ node: p[0], score: p[1], gewicht: p[2] })),\n"
"  fehlende_teilscores: fehlende, abgedeckte_gewichtung: Math.round(gsum * 100),\n"
"  regelwerk: 'Gewichteter Mittelwert der VORHANDENEN Teilscores (N02 20%, N03 15%, N05 30%, N06 20%, N07 15%) x10. '\n"
"    + 'N04 (Kosten) ist KEINE eigene Score-Dimension, sondern fliesst als Kosten-Input in N05 - daher nicht im Mittel (kein \"wegen Unsicherheit ausgeschlossen\"). '\n"
"    + 'Fehlende/unsichere Teilscores werden ausgeschlossen (nicht als 0 gewertet). '\n"
"    + 'Downgrade um 1 Stufe bei mittlerer Datenvollstaendigkeit; \"Beobachten\" nur wenn < 40% Gewichtung abgedeckt '\n"
"    + 'oder >= 2 Nodes technisch fehlgeschlagen. \"Nachschaerfen\" erzwungen wenn Risiko-Score (N07) <= 3. '\n"
"    + (validiert ? 'Validiert: harte Kennzahlen freigeschaltet.' : 'NICHT validiert (JC-06 ausstehend): Kategorie auf max. \"Pilotieren\" gedeckelt, Kennzahlen vorlaeufig.')\n"
"} }];\n"
}, tv=2, pos=(2560, 0))
connect("N07 · LLM", "N08a · Score-Aggregation")

# ---------------------------------------------------------------- N08b Begruendungstext (LLM)
n08b_user = (
"const a = $('N08a · Score-Aggregation').first().json;\n"
"const usr = 'Formuliere die Management-Begruendung zur Ampel-Empfehlung. Der Score und die Kategorie sind "
"bereits regelbasiert bestimmt - DU AENDERST SIE NICHT, du begruendest sie nur. 2-3 Saetze, ohne Fachjargon, "
"GF-lesbar. Nenne die 3 wichtigsten offenen Punkte.\\n\\n' +\n"
"'JSON-Schema: {\"begruendung\":\"\",\"offene_punkte\":[\"\",\"\",\"\"]}\\n\\n' +\n"
"'Score: ' + a.score + '/100\\nKategorie: ' + a.kategorie + '\\nDatenvollstaendigkeit: ' + a.completeness +\n"
"'\\nTeilscores: ' + JSON.stringify(a.teilscores) + '\\nKontext: ' + JSON.stringify($('N01 · LLM').first().json).slice(0, 1500);\n"
)
llm_pair("N08b", "Begruendung", 2760,
    SYS_BASE + " Aufgabe: Sprachliche Begruendung der bereits berechneten Ampel (Node N08b). Score/Kategorie NICHT veraendern.",
    n08b_user, max_tokens=900)
connect("N08a · Score-Aggregation", "N08b · Prompt")

# ---------------------------------------------------------------- N09 Lueckenaggregation
add("N09 · Lueckenaggregation", CODE, {"jsCode":
PARSE_FN +
"// Sammelt alle Luecken regelbasiert und ENTDOPPELT sie: gleiche Luecke = ein Eintrag,\n"
"// betroffene Nodes werden zusammengefasst (verhindert die mehrfach gelistete gleiche Luecke).\n"
"const ctx = $('Analyse-Kontext bauen').first().json;\n"
"const map = { N01:'N01 · LLM', N02:'N02 · LLM', N03:'N03 · LLM', N04:'N04 · LLM', N06:'N06 · LLM', N07:'N07 · LLM' };\n"
"const norm = (s) => String(s||'').toLowerCase().replace(/[^a-z0-9aeoeueaeoeuess ]/gi,'').replace(/\\s+/g,' ').trim();\n"
"const byKey = new Map();\n"
"function addL(was, wo, kons) {\n"
"  const key = norm(was); if (!key) return;\n"
"  if (byKey.has(key)) { const e = byKey.get(key);\n"
"    if (wo && e.nodes.indexOf(wo) < 0) e.nodes.push(wo);\n"
"    if ((!e.konsequenz || e.konsequenz.length < 5) && kons) e.konsequenz = kons;\n"
"  } else { byKey.set(key, { was: was, nodes: wo ? [wo] : [], konsequenz: kons || '' }); }\n"
"}\n"
"(ctx.luecken_global || []).forEach(l => addL(l.was, l.wo, l.konsequenz));\n"
"for (const [id, nm] of Object.entries(map)) {\n"
"  const o = parseLLM(nm);\n"
"  if (o && Array.isArray(o.luecken)) for (const l of o.luecken) addL(l.was, l.wo || id, l.konsequenz);\n"
"  if (o && Array.isArray(o.kennzeichnungen)) for (const k of o.kennzeichnungen)\n"
"    if (String(k.art||'').toLowerCase() === 'fehlend') addL(k.wert || 'Fehlender Wert', id, k.quelle_oder_herleitung || '');\n"
"}\n"
"// N05a (deterministische Kennzahlen-Node) liefert json direkt - nicht via parseLLM.\n"
"const k = $('N05a · Kennzahlen').first().json;\n"
"if (k && Array.isArray(k.luecken)) for (const l of k.luecken) addL(l.was, l.wo || 'N05', l.konsequenz);\n"
"if (k && Array.isArray(k.warnungen)) for (const w of k.warnungen) addL(w, 'N05', 'Hinweis der Kennzahlen-Berechnung.');\n"
"const luecken = [...byKey.values()].map(e => ({ was: e.was, wo: e.nodes.join(', '), konsequenz: e.konsequenz }));\n"
"return [{ json: { luecken, anzahl: luecken.length } }];\n"
}, tv=2, pos=(3060, 0))
connect("N08b · LLM", "N09 · Lueckenaggregation")

# ---------------------------------------------------------------- N10 Report HTML
add("N10 · Report HTML", CODE, {"jsCode":
PARSE_FN +
"const ctx = $('Analyse-Kontext bauen').first().json;\n"
"const a = $('N08a · Score-Aggregation').first().json;\n"
"const b = parseLLM('N08b · LLM');\n"
"const n01 = parseLLM('N01 · LLM'), n03 = parseLLM('N03 · LLM'), n04 = parseLLM('N04 · LLM');\n"
"const n05 = $('N05a · Kennzahlen').first().json;       // deterministische Kennzahlen\n"
"const n05b = parseLLM('N05b · LLM');                   // Prosa zu den Kennzahlen\n"
"if (n01 && !String(n01.unternehmen || '').trim()) n01.unternehmen = ctx.unternehmen || '(unbekannt)';\n"
"const n02 = parseLLM('N02 · LLM'), n06 = parseLLM('N06 · LLM'), n07 = parseLLM('N07 · LLM');\n"
"const vorlaeufig = !(a && a.validiert);\n"
"const vBadge = vorlaeufig ? ' <span style=\"background:#fff3cd;color:#7a5c00;font-size:10px;font-weight:600;padding:1px 7px;border-radius:9px\">vorlaeufig</span>' : '';\n"
"const luecken = ($('N09 · Lueckenaggregation').first().json.luecken) || [];\n"
"const esc = (s) => String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');\n"
"const AMPEL = { 'Gezielt skalieren':'#2e7d32','Weiterfuehren':'#558b2f','Pilotieren':'#F39200','Vereinfachen':'#ef6c00','Nachschaerfen':'#e65100','Beobachten':'#6b7280','Stoppen':'#c62828' };\n"
"const ampelColor = AMPEL[a.kategorie] || '#6b7280';\n"
"const eur = (o) => { const w = o ? Number(o.wert) : NaN; return Number.isFinite(w) ? (w.toLocaleString('de-DE') + ' \\u20ac') : '<span style=\"color:#999\">[Fehlend]</span>'; };\n"
"// Direkter Jahresnutzen: Summe, sonst Spanne (real/max) als Fallback.\n"
"const num = (v, suf) => Number.isFinite(Number(v)) ? (Number(v).toLocaleString('de-DE') + (suf||'')) : '<span style=\"color:#999\">[Fehlend]</span>';\n"
"const art = (o) => (o && o.art) ? ('<span style=\"color:#888;font-size:11px\">[' + esc(o.art) + ']</span>') : '';\n"
"const op = (b.offene_punkte || a.fehlende_teilscores || []).slice(0,3);\n"
"const opHtml = op.length ? op.map(x => '<li>' + esc(x) + '</li>').join('') : '<li>Keine kritischen offenen Punkte.</li>';\n"
"const scoreRows = (a.teilscores||[]).map(t => '<tr><td style=\"padding:6px 12px;border-bottom:1px solid #eee\">' + esc(t.node) + '</td>' +\n"
"  '<td style=\"padding:6px 12px;border-bottom:1px solid #eee;text-align:center\">' + (t.score==null?'<span style=\"color:#c62828\">[Fehlend]</span>':esc(t.score)+' / 10') + '</td>' +\n"
"  '<td style=\"padding:6px 12px;border-bottom:1px solid #eee;text-align:right;color:#888\">' + Math.round(t.gewicht*100) + '%</td></tr>').join('');\n"
"const lueckenRows = luecken.length ? luecken.map((l,i) => '<tr><td style=\"padding:6px 10px;border-bottom:1px solid #eee\">' + (i+1) + '</td>' +\n"
"  '<td style=\"padding:6px 10px;border-bottom:1px solid #eee\">' + esc(l.was) + '</td>' +\n"
"  '<td style=\"padding:6px 10px;border-bottom:1px solid #eee;font-family:monospace;color:#666\">' + esc(l.wo) + '</td>' +\n"
"  '<td style=\"padding:6px 10px;border-bottom:1px solid #eee\">' + esc(l.konsequenz) + '</td></tr>').join('')\n"
"  : '<tr><td colspan=\"4\" style=\"padding:8px;color:#999\">Keine Luecken erfasst.</td></tr>';\n"
"// --- Lesbare Aufbereitung der Node-JSONs (statt Roh-Dump) ---\n"
"const LBL = { unternehmen:'Unternehmen', branche:'Branche', groesse_hinweis:'Groesse', betroffene_prozesse:'Betroffene Prozesse', ist_zustand:'Ist-Zustand', ziele:'Ziele', geplante_loesung:'Geplante Loesung', rahmenbedingungen:'Rahmenbedingungen', kennzeichnungen:'Kennzeichnungen', luecken:'Luecken', score:'Score', konfidenz:'Konfidenz', kriterien:'Kriterien', begruendung:'Begruendung', name:'Name', wert:'Wert', art:'Art', quelle_oder_herleitung:'Quelle/Herleitung', herleitung:'Herleitung', was:'Was fehlt', wo:'Node', konsequenz:'Konsequenz', zeitersparnis_eur_monat:'Zeitersparnis \\u20ac/Monat', fehlerreduktion_eur_monat:'Fehlerreduktion \\u20ac/Monat', summe_nutzen_eur_jahr:'Summe Nutzen \\u20ac/Jahr', spanne_eur_jahr:'Spanne \\u20ac/Jahr', einmalkosten_eur:'Einmalkosten \\u20ac', laufende_kosten_eur_monat:'Laufende Kosten \\u20ac/Monat', kostenpositionen:'Kostenpositionen', kategorie:'Kategorie', eur:'\\u20ac', intervall:'Intervall', roi_jahr1_prozent:'ROI Jahr 1 (%)', roi_jahr3_prozent:'ROI Jahr 3 (%)', break_even_monate:'Break-Even (Monate)', sensitivitaet:'Sensitivitaet', rechenweg:'Rechenweg', best:'Best', real:'Real', worst:'Worst', technisch:'Technisch', organisatorisch:'Organisatorisch', dsgvo_status:'DSGVO', gobd_anwendbar:'GoBD anwendbar', gobd_status:'GoBD', governance_status:'Governance', kritische_risiken:'Kritische Risiken', min:'Min', max:'Max', haeufigkeit:'Haeufigkeit', heutiger_aufwand:'Heutiger Aufwand', beschreibung:'Beschreibung', "
"eingesparte_stunden_pro_vorgang:'Eingesparte Std/Vorgang', fehlerreduktion_stunden_pro_vorgang:'Fehlerreduktion Std/Vorgang', mandate_pro_monat:'Vorgaenge/Monat', "
"entwicklungsstunden:'Entwicklungsstunden', pflege_stunden_pro_monat:'Pflege Std/Monat', infra_eur_pro_monat:'Infra \\u20ac/Monat', lizenz_eur_pro_monat:'Lizenz \\u20ac/Monat', "
"nutzen_eur_jahr:'Nutzen \\u20ac/Jahr', nutzen_eur_monat:'Nutzen \\u20ac/Monat', einmalkosten_eur:'Einmalkosten \\u20ac', kosten_eur_monat:'Kosten \\u20ac/Monat', kosten_eur_jahr:'Kosten \\u20ac/Jahr', "
"stundensatz_eur:'Stundensatz \\u20ac', status_zahlen:'Status', validiert:'Validiert', parameter_herkunft:'Parameter-Herkunft', warnungen:'Warnungen', groesse:'Groesse', quelle:'Quelle', "
"szenario:'Szenario', mandate_monat:'Vorgaenge/Monat', nutzen_jahr:'Nutzen \\u20ac/Jahr', roi_jahr1:'ROI Jahr 1 (%)', "
"rechensicherheit:'Rechensicherheit', abrechnungsfaktor:'Auslastungsfaktor', sensitivitaet:'Sensitivitaet (Volumen)', sensitivitaet_pflege:'Sensitivitaet (Pflegeaufwand)', pflege_std_monat:'Pflege Std/Monat', stundensatz_eur:'Stundensatz \\u20ac/h', "
"wertmodell:'Wertmodell', nutzungsart:'Verwendung', implausibel:'Implausibel', plausibilitaet:'Plausibilitaet', nutzen_label:'Nutzen-Label', belegt_anteil:'Belegt-Anteil', fte_last:'Vollzeit-Aequivalente', freed_h_month:'Freigesetzte Std/Monat', hinweis:'Hinweis', ok:'OK', verkaufspotenzial_eur_jahr:'Verkaufspotenzial \\u20ac/Jahr (nicht realisiert)', nachfrage_gedeckt:'Nachfrage gesichert', nutzen_bedingt:'Nutzen bedingt', af_band:'Genutzter Zeitanteil af (Band)', af_bezeichnung:'af-Bezeichnung', konservativ:'Konservativ', optimistisch:'Optimistisch', abrechenbarkeit_belegt:'Auslastung belegt', vorgaenge_pro_monat:'Vorgaenge/Monat', vorgaenge_monat:'Vorgaenge/Monat', brutto_zeitwert_eur_jahr:'Theoretisches Maximum \\u20ac/Jahr (af=1)', potenzial_eur_jahr:'Optimistisches Potenzial \\u20ac/Jahr (nicht realisiert)', realisiert_spanne_eur_jahr:'Erwarteter realisierbarer Nutzen \\u20ac/Jahr (Spanne)', sensitivitaet_af:'Sensitivitaet (genutzter Zeitanteil af)', af:'af', break_even_monate:'Break-Even (Monate)' };\n"
"const lbl = (k) => LBL[k] || (String(k).charAt(0).toUpperCase() + String(k).slice(1).replace(/_/g,' '));\n"
"const ART = { belegt:'#2e7d32', geschaetzt:'#F39200', annahme:'#6b7280', fehlend:'#c62828' };\n"
"const artBadge = (v) => '<span style=\"background:' + (ART[String(v).toLowerCase()]||'#6b7280') + ';color:#fff;font-size:10px;padding:1px 7px;border-radius:9px\">' + esc(v) + '</span>';\n"
"const isObj = (x) => x && typeof x === 'object' && !Array.isArray(x);\n"
"const eurKey = (k) => /eur/i.test(String(k));\n"
"const fmtN = (v) => { if (typeof v === 'number') { if (!Number.isFinite(v)) return '<span style=\"color:#bbb\">&ndash;</span>'; return Number.isInteger(v) ? v.toLocaleString('de-DE') : String(v).replace('.',','); } return esc(v); };\n"
"const fmt = (v, eur) => (typeof v === 'number' && eur) ? (fmtN(v) + ' \\u20ac') : fmtN(v);\n"
"function renderVal(v, eur){\n"
"  if (v == null || v === '') return '<span style=\"color:#bbb\">&ndash;</span>';\n"
"  if (Array.isArray(v)) {\n"
"    if (!v.length) return '<span style=\"color:#bbb\">&ndash;</span>';\n"
"    if (v.every(x => !isObj(x) && !Array.isArray(x))) return '<ul style=\"margin:2px 0 2px 16px;padding:0\">' + v.map(x => '<li>' + fmt(x, eur) + '</li>').join('') + '</ul>';\n"
"    const keys = [...new Set(v.flatMap(o => isObj(o) ? Object.keys(o) : []))];\n"
"    return '<table style=\"width:100%;border-collapse:collapse;margin:4px 0;font-size:11px\"><thead><tr>' + keys.map(k => '<th style=\"text-align:left;background:#f4f6f8;padding:3px 7px;border:1px solid #e3e8ee;color:#555\">' + esc(lbl(k)) + '</th>').join('') + '</tr></thead><tbody>' + v.map(o => '<tr>' + keys.map(k => { const ke = eur || eurKey(k); let c = isObj(o) ? o[k] : undefined; if (k === 'art' && c) c = artBadge(c); else c = (isObj(c) || Array.isArray(c)) ? renderVal(c, ke) : fmt(c, ke); return '<td style=\"padding:3px 7px;border:1px solid #e3e8ee;vertical-align:top\">' + (c == null || c === '' ? '<span style=\"color:#bbb\">&ndash;</span>' : c) + '</td>'; }).join('') + '</tr>').join('') + '</tbody></table>';\n"
"  }\n"
"  if (isObj(v)) {\n"
"    if ('wert' in v || 'art' in v) { const parts = [];\n"
"      if ('wert' in v) { let w = v.wert; if (isObj(w)) w = (w.real != null ? w.real : (w.wert != null ? w.wert : (w.max != null ? w.max : w.min))); parts.push('<strong>' + ((w == null || w === '') ? '<span style=\"color:#bbb\">&ndash;</span>' : fmt(w, eur)) + '</strong>'); }\n"
"      if (v.art) parts.push(artBadge(v.art));\n"
"      if (v.herleitung) parts.push('<span style=\"color:#666\">' + esc(v.herleitung) + '</span>');\n"
"      if (v.quelle_oder_herleitung) parts.push('<span style=\"color:#666\">' + esc(v.quelle_oder_herleitung) + '</span>');\n"
"      return parts.join(' '); }\n"
"    return renderObj(v, eur);\n"
"  }\n"
"  return fmt(v, eur);\n"
"}\n"
"function renderObj(o, eurParent){\n"
"  return '<table style=\"width:100%;border-collapse:collapse;margin:2px 0;font-size:12px\"><tbody>' + Object.keys(o).map(k => '<tr><td style=\"width:165px;padding:4px 8px;border-bottom:1px solid #eee;color:#555;vertical-align:top;font-weight:600\">' + esc(lbl(k)) + '</td><td style=\"padding:4px 8px;border-bottom:1px solid #eee;vertical-align:top\">' + renderVal(o[k], eurParent || eurKey(k)) + '</td></tr>').join('') + '</tbody></table>';\n"
"}\n"
"const detail = (titel, obj) => '<h3 style=\"font-size:13px;color:#823b2f;margin:18px 0 6px\">' + esc(titel) + '</h3>' + ((obj && Object.keys(obj).length) ? renderObj(obj) : '<div style=\"color:#c62828;font-size:12px\">Kein Ergebnis von dieser Node.</div>');\n"
"// Kuratiertes Glossar (statisch - keine LLM-Generierung, daher keine Halluzination).\n"
"const GLOSSAR = [\n"
"  ['ROI (Return on Investment)', 'Verhaeltnis von Nutzen zu Kosten ueber einen Zeitraum, in Prozent. 100% = Investition einmal verdient.'],\n"
"  ['Break-Even', 'Zeitpunkt, ab dem der kumulierte Nutzen die Kosten deckt (hier in Monaten).'],\n"
"  ['Direkter Nutzen', 'In Euro bezifferbarer Vorteil, v.a. eingesparte Arbeitszeit und vermiedene Fehler.'],\n"
"  ['Opportunitaetskosten / -wert', 'Wert der Zeit, die durch Automatisierung fuer anderes (z.B. abrechenbare Beratung) frei wird.'],\n"
"  ['Sensitivitaet', 'Bandbreite des Ergebnisses unter guenstigen (best), realistischen (real) und unguenstigen (worst) Annahmen.'],\n"
"  ['Automatisierungsreife', 'Wie gut sich ein Prozess automatisieren laesst (Standardisierung, Datenlage, Haeufigkeit, Stabilitaet).'],\n"
"  ['DSGVO', 'Datenschutz-Grundverordnung. Hier durch lokale Verarbeitung (Self-hosting) erfuellt - keine Datenweitergabe an Dritte.'],\n"
"  ['GoBD', 'Regeln fuer ordnungsgemaesse, revisionssichere elektronische Buchfuehrung/Archivierung. Nur einschlaegig bei steuer-/buchhaltungsrelevanten Aufzeichnungen.'],\n"
"  ['Self-hosted / Self-hosting', 'Betrieb der Software auf eigener Infrastruktur statt in der Cloud - volle Datenkontrolle.'],\n"
"  ['N8N', 'Workflow-Automatisierungs-Plattform, in der dieser Ablauf als Node-Kette umgesetzt ist.'],\n"
"  ['Whisper', 'Lokales KI-Modell zur Spracherkennung (Audio -> Text).'],\n"
"  ['Ollama / LLM', 'Lokal betriebenes Sprachmodell (Large Language Model) fuer die Textanalyse.'],\n"
"  ['OCR / Vision-Modell', 'Texterkennung aus Bildern bzw. gescannten (Bild-)PDFs.'],\n"
"  ['Kennzeichnung', 'Belegt = direkt aus der Quelle; Geschaetzt = nachvollziehbar abgeleitet; Annahme = Standardwert; Fehlend = nicht verfuegbar.'],\n"
"  ['Ampel / Empfehlung', 'Gesamturteil von Stoppen bis Gezielt skalieren, abgeleitet aus Score und Datenvollstaendigkeit.'],\n"
"];\n"
"const glossarHtml = '<dl style=\"margin:0\">' + GLOSSAR.map(g => '<dt style=\"font-weight:600;color:#2c3e50;margin-top:8px;font-size:12px\">' + esc(g[0]) + '</dt><dd style=\"margin:0 0 2px 0;color:#555;font-size:12px\">' + esc(g[1]) + '</dd>').join('') + '</dl>';\n"
"const html = '<!DOCTYPE html><html lang=\"de\"><head><meta charset=\"UTF-8\"><style>' +\n"
"  '@page{size:A4;margin:16mm}*{box-sizing:border-box;margin:0;padding:0}' +\n"
"  'body{font-family:Segoe UI,Tahoma,sans-serif;color:#2c3e50;line-height:1.55;font-size:13px}' +\n"
"  'h1{font-size:23px;margin-bottom:4px}h2{font-size:16px;color:#823b2f;margin:22px 0 10px;border-bottom:2px solid #823b2f;padding-bottom:4px}' +\n"
"  'table{width:100%;border-collapse:collapse;margin-top:6px}th{text-align:left;background:#f9fafb;padding:6px 10px;font-size:11px;color:#666;text-transform:uppercase}' +\n"
"  '.page-break{page-break-before:always}</style></head><body>' +\n"
"  '<div style=\"border-bottom:3px solid #823b2f;padding-bottom:14px;margin-bottom:18px\">' +\n"
"    '<h1>KI-Wirtschaftlichkeits-Check</h1>' +\n"
"    '<div style=\"color:#666;font-size:13px\"><strong>' + esc(ctx.unternehmen) + '</strong> &middot; Erstellt am ' + esc(ctx.datum) + ' &middot; Basis: ' + ((ctx.has_audio && ctx.has_doku) ? 'Gespraech + Dokument' : (ctx.has_audio ? 'nur Gespraech' : 'nur Dokument')) + ' &middot; DSGVO-konform (self-hosted)</div>' +\n"
"  '</div>' +\n"
"  '<div style=\"display:flex;gap:18px;align-items:center;background:linear-gradient(135deg,' + ampelColor + '22,#fff);border-left:6px solid ' + ampelColor + ';border-radius:10px;padding:18px\">' +\n"
"    '<div style=\"font-size:40px;font-weight:700;color:' + ampelColor + ';white-space:nowrap\">' + esc(a.score) + '<span style=\"font-size:18px;color:#999\"> / 100</span></div>' +\n"
"    '<div><div style=\"font-size:13px;color:#666\">Empfehlung</div><div style=\"font-size:22px;font-weight:700;color:' + ampelColor + '\">' + esc(a.kategorie) + '</div>' +\n"
"    '<div style=\"font-size:12px;color:#888\">Datenvollstaendigkeit: ' + esc(a.completeness) + '</div></div>' +\n"
"  '</div>' +\n"
"  ((a.analyse_fehler && a.analyse_fehler.length) ? '<div style=\"background:#fdecea;border-left:5px solid #c62828;border-radius:8px;padding:12px 14px;margin-top:14px;font-size:13px;color:#7f1d1d\"><strong>Analysehinweis:</strong> Folgende Nodes lieferten kein Ergebnis und wurden NICHT bewertet: ' + esc(a.analyse_fehler.join(', ')) + '. Der Score basiert nur auf ' + esc(a.abgedeckte_gewichtung) + ' % der Dimensionsgewichtung - bitte erneut ausfuehren.</div>' : '') +\n"
"  '<div style=\"background:#f8fafb;border:1px solid #e8eef3;border-radius:8px;padding:14px;margin-top:14px;font-size:14px\">' + ((n05.implausibel) ? '<strong style=\"color:#b00020\">Hinweis vorab:</strong> Die Kernannahmen (Zeitersparnis/Volumen) sind unbelegt und fuehren zu einer physikalisch unrealistischen Lastannahme - die Wirtschaftlichkeit ist daher NICHT belastbar beziffert. ' : '') + esc(b.begruendung || 'Begruendung nicht verfuegbar.') + '</div>' +\n"
"  '<h2>Die 3 wichtigsten offenen Punkte</h2><ol style=\"padding-left:20px\">' + opHtml + '</ol>' +\n"
"  (n05.stundensatz_belegt === false ? '<div style=\"background:#fdecea;border-left:5px solid #c62828;border-radius:8px;padding:11px 14px;margin-top:12px;font-size:13px;color:#7f1d1d\"><strong>Stundensatz unbelegt:</strong> Es wurde der branchenunabhaengige Standardwert ' + num(n05.stundensatz_eur,' \\u20ac') + '/h angesetzt (im Dokument/Gespraech kein Satz genannt). <strong>Alle</strong> Euro-Kennzahlen (Nutzen, ROI, Break-Even) skalieren direkt damit - bitte den realen Stundensatz des Kunden im Formular eintragen, dann werden die Zahlen belastbar.</div>' : '') +\n"
"  (n05.nutzen_bedingt ? '<div style=\"background:#fdecea;border-left:5px solid #c62828;border-radius:8px;padding:11px 14px;margin-top:12px;font-size:13px;color:#7f1d1d\"><strong>Verkaufsnutzen bedingt:</strong> Das Verkaufs-/Umsatzpotenzial ist mangels belegtem Preis bzw. gesicherter Nachfrage NICHT beziffert (vor Entscheidung zu klaeren). Der ausgewiesene realisierte Nutzen enthaelt nur den Opportunitaetswert der gesparten Zeit; das Brutto-Potenzial ist die nicht realisierte Obergrenze.</div>' : '') +\n"
"  ((n05.implausibel) ? '<div style=\"background:#fde2e2;border-left:6px solid #b00020;border-radius:8px;padding:12px 14px;margin-top:12px;font-size:13px;color:#7f0014\"><strong>&#9888; Plausibilitaet &ndash; Headline NICHT belastbar:</strong> ' + esc(n05.plausibilitaet && n05.plausibilitaet.hinweis) + '</div>' : '') +\n"
"  '<h2>Kennzahlen' + vBadge + '</h2>' +\n"
"  '<div style=\"font-size:12px;color:#666;margin:-4px 0 8px\"><strong>Verwendung:</strong> ' + (n05.nutzungsart === 'verkauf' ? 'externes Produkt (Verkauf/Vermietung) &ndash; Nutzen = interne Effizienz + Umsatz' : 'interne Prozessoptimierung &ndash; Nutzen = Wert der freigesetzten Arbeitszeit, kein Verkauf') + '</div>' +\n"
"  '<table><tr><td style=\"padding:6px 12px;border-bottom:1px solid #eee\">' + esc(n05.nutzen_label || 'Erwarteter realisierbarer Nutzen (bedingt)') + ' (Jahr)</td><td style=\"padding:6px 12px;border-bottom:1px solid #eee;text-align:right\">' + (n05.implausibel ? '<span style=\"color:#b00020;font-weight:700\">nicht belastbar</span>' : '<strong>' + num(n05.nutzen_eur_jahr,' \\u20ac') + '</strong>') + ((n05.realisiert_spanne_eur_jahr) ? '<br><span style=\"font-size:11px;color:#888\">Spanne ' + num(n05.realisiert_spanne_eur_jahr.worst,' \\u20ac') + ' &ndash; ' + num(n05.realisiert_spanne_eur_jahr.best,' \\u20ac') + (n05.implausibel ? ' (auf unbelegtem Treiber)' : '') + '</span>' : '') + '</td></tr>' +\n"
"    '<tr><td style=\"padding:6px 12px;border-bottom:1px solid #eee;color:#888\">Theoretisches Maximum (af=1, nicht realisiert)</td><td style=\"padding:6px 12px;border-bottom:1px solid #eee;text-align:right;color:#888\">' + num(n05.brutto_zeitwert_eur_jahr,' \\u20ac') + '</td></tr>' +\n"
"    ((n05.verkaufspotenzial_eur_jahr > 0) ? '<tr><td style=\"padding:6px 12px;border-bottom:1px solid #eee;color:#888\">Zusaetzliches Verkaufspotenzial (nicht realisiert)</td><td style=\"padding:6px 12px;border-bottom:1px solid #eee;text-align:right;color:#888\">' + num(n05.verkaufspotenzial_eur_jahr,' \\u20ac') + '</td></tr>' : '') +\n"
"    '<tr><td style=\"padding:6px 12px;border-bottom:1px solid #eee\">Laufende Kosten (Monat)</td><td style=\"padding:6px 12px;border-bottom:1px solid #eee;text-align:right\">' + num(n05.kosten_eur_monat,' \\u20ac') + '</td></tr>' +\n"
"    '<tr><td style=\"padding:6px 12px;border-bottom:1px solid #eee\">Einmalkosten (Aufbau)</td><td style=\"padding:6px 12px;border-bottom:1px solid #eee;text-align:right\">' + num(n05.einmalkosten_eur,' \\u20ac') + '</td></tr>' +\n"
"    '<tr><td style=\"padding:6px 12px;border-bottom:1px solid #eee\">Break-Even</td><td style=\"padding:6px 12px;border-bottom:1px solid #eee;text-align:right' + (n05.implausibel?';color:#b00020':'') + '\">' + (n05.break_even_monate!=null?num(n05.break_even_monate,' Monate'):'<span style=\"color:#999\">sofort positiv</span>') + (n05.implausibel?' <span style=\"font-size:10px\">(nicht belastbar)</span>':'') + '</td></tr>' +\n"
"    '<tr><td style=\"padding:6px 12px;border-bottom:1px solid #eee\">ROI Jahr 1 / Jahr 3' + vBadge + '</td><td style=\"padding:6px 12px;border-bottom:1px solid #eee;text-align:right' + (n05.implausibel?';color:#b00020':'') + '\">' + num(n05.roi_jahr1_prozent,'%') + ' / ' + num(n05.roi_jahr3_prozent,'%') + (n05.implausibel?' <span style=\"font-size:10px\">(nicht belastbar)</span>':'') + '</td></tr></table>' +\n"
"  (n05.rechenweg ? '<div style=\"font-size:11px;color:#888;margin-top:5px\">Rechenweg: ' + esc(n05.rechenweg) + ' (Stundensatz ' + num(n05.stundensatz_eur,' \\u20ac') + ', ' + num(n05.vorgaenge_pro_monat) + ' Vorgaenge/Monat)</div>' : '') +\n"
"  ((n05.implausibel) ? '<div style=\"background:#fff4f4;border:1px solid #f3c0c0;border-radius:8px;padding:10px 12px;margin-top:8px;font-size:13px;color:#7f0014\">Eine belastbare Euro-/ROI-/Break-Even-Aussage ist hier NICHT moeglich: die Rechnung sitzt auf unbelegten Standardannahmen (siehe Plausibilitaets-Hinweis). Erst nach Erhebung von Zeitersparnis je Vorgang UND Volumen lassen sich die Zahlen serioes beziffern.</div>' : (n05b && n05b.begruendung ? '<div style=\"background:#f8fafb;border:1px solid #e8eef3;border-radius:8px;padding:10px 12px;margin-top:8px;font-size:13px\">' + esc(n05b.begruendung) + '</div>' : '')) +\n"
"  (vorlaeufig ? '<div style=\"background:#fff3cd;border-left:5px solid #e0a800;border-radius:8px;padding:10px 14px;margin-top:8px;font-size:12px;color:#7a5c00\"><strong>Vorlaeufig:</strong> Diese Kennzahlen gelten bis zum bestandenen Vergleichstest (lokal vs. Cloud, JC-06) als Schaetzung. Erst danach werden sie als final ausgewiesen, und die Empfehlung kann ueber \"Pilotieren\" hinausgehen.</div>' : '') +\n"
"  '<h2>Score-Zusammensetzung (regelbasiert, N08a)</h2><table><thead><tr><th>Dimension</th><th style=\"text-align:center\">Score</th><th style=\"text-align:right\">Gewicht</th></tr></thead><tbody>' + scoreRows + '</tbody></table>' +\n"
"  '<div style=\"font-size:11px;color:#888;margin-top:6px\">' + esc(a.regelwerk) + '</div>' +\n"
"  '<div class=\"page-break\"></div><h2>Detailanalyse je Node</h2>' +\n"
"  detail('N01 Kontext & Prozess', n01) + detail('N02 Automatisierungsreife', n02) + detail('N03 Direkter Nutzen', n03) +\n"
"  detail('N04 Vollkosten', n04) + detail('N05 Nutzen-Kosten / ROI', n05) + detail('N06 Umsetzbarkeit', n06) + detail('N07 Risiko & Compliance', n07) +\n"
"  '<div class=\"page-break\"></div><h2>Lueckenliste (N09)</h2><table><thead><tr><th>#</th><th>Was fehlt</th><th>Node</th><th>Konsequenz</th></tr></thead><tbody>' + lueckenRows + '</tbody></table>' +\n"
"  '<h2 style=\"margin-top:22px\">Glossar</h2>' + glossarHtml +\n"
"  '<div style=\"margin-top:24px;padding-top:12px;border-top:1px solid #eee;font-size:11px;color:#999;text-align:center\">KI-Wirtschaftlichkeits-Check &middot; ' + esc(ctx.unternehmen) + ' &middot; ' + esc(ctx.datum) + ' &middot; Verarbeitung self-hosted & DSGVO-konform</div>' +\n"
"  '</body></html>';\n"
"const safe = (s) => String(s||'Unternehmen').replace(/[^a-zA-Z0-9_-]/g,'_').slice(0,40);\n"
"const fileName = 'Wirtschaftlichkeits-Check_' + safe(ctx.unternehmen) + '_' + ctx.datum + '.pdf';\n"
"return [{ json: { fileName, unternehmen: ctx.unternehmen },\n"
"  binary: { data: { data: Buffer.from(html, 'utf8').toString('base64'), mimeType: 'text/html', fileName: 'index.html', fileExtension: 'html' } } }];\n"
}, tv=2, pos=(3260, 0))
connect("N09 · Lueckenaggregation", "N10 · Report HTML")

# ---------------------------------------------------------------- Gotenberg HTML -> PDF
add("Gotenberg: HTML zu PDF", HTTP, {
    "method": "POST",
    "url": "={{ $('Config').first().json.config.gotenberg_url }}",
    "sendBody": True, "contentType": "multipart-form-data",
    "bodyParameters": {"parameters": [
        {"parameterType": "formBinaryData", "name": "files", "inputDataFieldName": "data"},
        {"name": "paperWidth", "value": "8.27"},
        {"name": "paperHeight", "value": "11.69"},
        {"name": "marginTop", "value": "0.5"},
        {"name": "marginBottom", "value": "0.5"},
        {"name": "printBackground", "value": "true"},
    ]},
    "options": {"response": {"response": {"responseFormat": "file"}}, "timeout": 120000},
}, tv=4.2, pos=(3460, 0),
    extra={"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 2000,
           "onError": "continueRegularOutput"})  # Gotenberg-Ausfall darf den Lauf nicht mit 500 abbrechen
connect("N10 · Report HTML", "Gotenberg: HTML zu PDF")

# ---------------------------------------------------------------- Dropbox upload
add("Dropbox: PDF ablegen", "n8n-nodes-base.dropbox", {
    "authentication": "oAuth2",
    "operation": "upload",
    "path": "=/2 Leclere-Solutions/Wirtschaftlichkeits-Checks/{{ $('N10 · Report HTML').first().json.fileName }}",
    "binaryData": True,
    "binaryPropertyName": "data",
}, tv=1, pos=(3660, 0), extra={
    "credentials": {"dropboxOAuth2Api": {"id": "pwReOckhgFTDJeG9", "name": "Dropbox account 3"}},
    "onError": "continueRegularOutput",  # Dropbox-Fehler (z.B. fehlende Credentials) darf den Lauf nicht abbrechen; PDF ist bereits gespeichert.
})
connect("Gotenberg: HTML zu PDF", "Dropbox: PDF ablegen")

# ---------------------------------------------------------------- Dashboard-/Webhook-Schicht (Live-Dashboard, Variante B)
import os as _os
_dl = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "dash_layer.py")
exec(open(_dl, encoding="utf-8").read())

# ---------------------------------------------------------------- assemble
workflow = {
    "name": "KI-Wirtschaftlichkeits-Check MVP v1",
    "nodes": nodes,
    "connections": connections,
    "active": False,
    "settings": {"executionOrder": "v1"},
    "pinData": {},
    "meta": {"templateCredsSetupCompleted": True, "instanceId": INSTANCE},
    "tags": [],
}

out_path = "/home/user/i2cdevlib/n8n/Wirtschaftlichkeits-Check_MVP_v1.json"
import os
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(workflow, f, ensure_ascii=False, indent=2)
print("OK ->", out_path)
print("Nodes:", len(nodes))
print("Connections:", len(connections))
