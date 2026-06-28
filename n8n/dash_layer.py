# -*- coding: utf-8 -*-
# Dashboard-/Webhook-Schicht fuer den Wirtschaftlichkeits-Check (Design 3 "Mission Control", schwarz).
# Variante B: Live-Status als Dateien in /tmp (wc_status_<run>.json, wc_pdf_<run>.pdf).
# Wird via exec() aus gen.py eingebunden und nutzt dort definierte add/connect/CODE/connections/nodes.
import json as _json

WCBASE = "/tmp"   # Ablage der Status-/PDF-Dateien (flach, kein mkdir noetig). Bei Bedarf anpassen.
RESP = "n8n-nodes-base.respondToWebhook"
WEBHOOK = "n8n-nodes-base.webhook"

# ============================================================ resplice: Checkpoint in bestehende Kante einfuegen
def resplice(a, mid, b, out=0):
    """Leitet die bestehende Verbindung a->b um auf a->mid->b (Checkpoint dazwischen)."""
    lst = connections[a]["main"][out]
    for c in lst:
        if c["node"] == b:
            c["node"] = mid
    connect(mid, b)

# ============================================================ Snapshot-Builder (geteiltes JS)
def snap_js(final):
    F = "true" if final else "false"
    return (
"const fs = (function(){ try { return require('fs'); } catch(e){ return null; } })();\n"
"const FINAL = " + F + ";\n"
"const WCBASE = " + _json.dumps(WCBASE) + ";\n"
"function got(n){ try { return $(n).first().json; } catch(e){ return null; } }\n"
"function parseLLM(n){ try {\n"
"  const r = got(n); if(!r) return null;\n"
"  let c = (r.choices && r.choices[0] && r.choices[0].message && r.choices[0].message.content) || '';\n"
"  if (typeof c !== 'string') c = JSON.stringify(c);\n"
"  const te = c.lastIndexOf('</think>'); if (te !== -1) c = c.slice(te + 8);\n"
"  c = c.replace(/<think>[\\s\\S]*?<\\/think>/g,'').replace(/```json|```/g,'');\n"
"  const s = c.indexOf('{'), e = c.lastIndexOf('}');\n"
"  const o = JSON.parse(s>=0 && e>s ? c.slice(s, e+1) : c);\n"
"  return (o && Object.keys(o).length) ? o : null;\n"
"} catch(e){ return null; } }\n"
"let base = null, run = null;\n"
"try { base = $('Run anlegen').first().json; run = base.run_id; } catch(e){}\n"
"const cell = (o,k)=>{ try { const v=o[k]; return (v && typeof v==='object' && 'wert' in v) ? v.wert : v; } catch(e){ return null; } };\n"
"const eur = (x)=>{ try { return Number(x).toLocaleString('de-DE') + ' \\u20ac'; } catch(e){ return x + ' \\u20ac'; } };\n"
"const tr = got('Transkript'); const docs = got('Dokumente zusammenfuehren');\n"
"const n01=parseLLM('N01 \\u00b7 LLM'), n02=parseLLM('N02 \\u00b7 LLM'), n03=parseLLM('N03 \\u00b7 LLM');\n"
"const n04=parseLLM('N04 \\u00b7 LLM'), n06=parseLLM('N06 \\u00b7 LLM'), n07=parseLLM('N07 \\u00b7 LLM');\n"
"const n05 = got('N05a \\u00b7 Kennzahlen'); const n08 = got('N08a \\u00b7 Score-Aggregation');\n"
"function st(key,label,done,summary){ return { key:key, label:label, status: done?'done':'wait', summary: done?(summary||''):'' }; }\n"
"const j3 = (a)=>a.filter(Boolean).join(' \\u00b7 ');\n"
"const stations = [\n"
"  st('N00','Eingang & Qualitaet', !!tr, tr ? (tr.quelle==='audio' ? ('Transkript \\u00b7 ' + (tr.dauer?Math.round(tr.dauer)+' s':'Audio')) : 'kein Audio \\u00b7 Dokumentbasis') : ''),\n"
"  st('N00b','Dokumente (Text/OCR)', !!docs, docs ? ((docs.doc_count||0) + ' Dokument(e) \\u00b7 ' + ((docs.dokumente||'').length) + ' Zeichen') : ''),\n"
"  st('N01','Kontext & Prozess', !!n01, n01 ? j3([cell(n01,'unternehmen'), n01.branche]) : ''),\n"
"  st('N02','Automatisierungsreife', !!n02, n02 ? ('Score ' + (n02.score!=null?n02.score:'?') + '/10') : ''),\n"
"  st('N03','Direkter Nutzen', !!n03, n03 ? j3([ cell(n03,'eingesparte_stunden_pro_vorgang')!=null?cell(n03,'eingesparte_stunden_pro_vorgang')+' Std/Vorgang':null, cell(n03,'mandate_pro_monat')!=null?cell(n03,'mandate_pro_monat')+'/Monat':null, cell(n03,'stundensatz_eur')!=null?cell(n03,'stundensatz_eur')+' \\u20ac/h':null ]) : ''),\n"
"  st('N04','Vollkosten', !!n04, n04 ? j3([ cell(n04,'entwicklungsstunden')!=null?'Aufbau '+cell(n04,'entwicklungsstunden')+' Std':null, cell(n04,'pflege_stunden_pro_monat')!=null?'Pflege '+cell(n04,'pflege_stunden_pro_monat')+' Std/M':null ]) : ''),\n"
"  st('N05','Kennzahlen / ROI', !!n05, n05 ? ('Nutzen ' + eur(n05.nutzen_eur_jahr) + ' \\u00b7 BE ' + (n05.break_even_monate!=null?n05.break_even_monate+' Mon':'sofort') + ' \\u00b7 Score ' + n05.score) : ''),\n"
"  st('N06','Umsetzbarkeit', !!n06, n06 ? ('Score ' + (n06.score!=null?n06.score:'?') + '/10') : ''),\n"
"  st('N07','Risiko & Compliance', !!n07, n07 ? ('Score ' + (n07.score!=null?n07.score:'?') + '/10') : ''),\n"
"  st('N08','Score & Empfehlung', !!n08, n08 ? ('Score ' + (n08.score!=null?n08.score:'?') + '/100 \\u00b7 ' + (n08.kategorie||'')) : ''),\n"
"  st('N10','Report-PDF', FINAL, FINAL ? 'PDF erstellt' : '')\n"
"];\n"
"let current = null;\n"
"for (const s of stations){ if (s.status !== 'done'){ s.status='run'; current=s.key; break; } }\n"
"const done_count = stations.filter(s=>s.status==='done').length;\n"
"const total = stations.length; const pct = Math.round(done_count/total*100);\n"
"let kpi = null;\n"
"if (n05) { kpi = {\n"
"  nutzen: eur(n05.nutzen_eur_jahr),\n"
"  nutzen_sub: (n05.realisiert_spanne_eur_jahr ? ('Spanne ' + eur(n05.realisiert_spanne_eur_jahr.worst) + ' \\u2013 ' + eur(n05.realisiert_spanne_eur_jahr.best)) : ''),\n"
"  breakeven: (n05.break_even_monate!=null ? ('~' + n05.break_even_monate + ' Mon.') : 'sofort positiv'),\n"
"  roi: (n05.roi_jahr1_prozent!=null ? (n05.roi_jahr1_prozent + ' %') : '\\u2013'),\n"
"  roi_sub: (n05.roi_jahr3_prozent!=null ? ('Jahr 3: ' + n05.roi_jahr3_prozent + ' %') : ''),\n"
"  empfehlung: (n08 ? (n08.kategorie || '\\u2013') : '\\u2026'),\n"
"  empfehlung_sub: (n05.status_zahlen==='final' ? 'final' : 'vorlaeufig')\n"
"}; }\n"
"let log = [];\n"
"try { if (fs && run){ const prev = JSON.parse(fs.readFileSync(WCBASE + '/wc_status_' + run + '.json','utf8')); if (Array.isArray(prev.log)) log = prev.log; } } catch(e){}\n"
"const known = new Set(log.map(l=>l.key));\n"
"const now = new Date().toLocaleTimeString('de-DE');\n"
"for (const s of stations){ if (s.status==='done' && !known.has(s.key)){ log.unshift({ ts: now, key: s.key, node: s.key, msg: (s.label + (s.summary ? (' \\u2014 ' + s.summary) : '')) }); } }\n"
"const snap = { run_id: run, unternehmen: (base&&base.unternehmen)||'', datum: (base&&base.datum)||'', state: FINAL?'done':'running', pct: pct, done_count: done_count, total: total, current: current, nodes: stations, kpi: kpi, log: log.slice(0,40), pdf_ready: FINAL };\n"
"try { if (fs && run){ fs.writeFileSync(WCBASE + '/wc_status_' + run + '.json', JSON.stringify(snap)); } } catch(e){}\n"
    )

# ============================================================ Dashboard HTML (Design 3, schwarz)
DASH_HTML = r"""<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KI-Wirtschaftlichkeits-Check</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#08090c;--panel:#0d0f14;--panel2:#11141b;--line:#1d2230;--accent:#F39200;--brand:#b5503f;--green:#3ddc84;--txt:#e6edf5;--mut:#8a98ad;--mut2:#5a6675}
body{background:#08090c;color:var(--txt);font-family:'Segoe UI',Inter,Tahoma,sans-serif;min-height:100vh}
.wrap{max-width:1360px;margin:0 auto;padding:26px 30px}
.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px}
.kick{font-size:12px;color:var(--accent);letter-spacing:2px;font-weight:700}
.title{font-size:23px;font-weight:700}
.sub{font-size:13px;color:var(--mut)}
.btn{padding:11px 22px;border-radius:9px;font-weight:700;font-size:14px;border:1px solid transparent;cursor:pointer;text-decoration:none;display:inline-block}
.btn-start{background:linear-gradient(90deg,var(--brand),var(--accent));color:#fff}
.btn-ghost{background:#161b24;color:var(--mut2);border:1px solid #232a38}
.btn-dl{background:rgba(243,146,0,.16);color:var(--accent);border:1px solid rgba(243,146,0,.45)}
.btn-dl.off{background:#161b24;color:var(--mut2);border-color:#232a38;pointer-events:none}
.card{background:#0d0f15;border:1px solid var(--line);border-radius:16px;padding:20px}
.center{min-height:64vh;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
.hero-ic{width:88px;height:88px;border-radius:50%;background:rgba(243,146,0,.12);border:1px solid rgba(243,146,0,.4);display:flex;align-items:center;justify-content:center;font-size:40px;color:var(--accent);margin-bottom:18px}
.hero-h{font-size:30px;font-weight:800;margin-bottom:8px}
.hero-p{font-size:15px;color:var(--mut);max-width:520px;margin-bottom:26px;line-height:1.6}
.grid{display:grid;grid-template-columns:330px 1fr 1fr;gap:18px}
.ring{width:170px;height:170px;border-radius:50%;margin:6px auto;display:flex;align-items:center;justify-content:center;background:#15202c}
.ring>div{width:130px;height:130px;border-radius:50%;background:#0d0f15;display:flex;flex-direction:column;align-items:center;justify-content:center}
.lab{font-size:11px;color:var(--mut2);letter-spacing:1px;font-weight:700;margin-bottom:12px}
.kpis{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.kpi{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);border-radius:12px;padding:13px 15px}
.kpi .k{font-size:10px;color:var(--mut2);text-transform:uppercase;letter-spacing:.5px}
.kpi .v{font-size:20px;font-weight:700;margin-top:3px}
.kpi .s{font-size:10px;color:var(--mut)}
.node{display:flex;align-items:center;gap:12px;padding:9px 12px;border-radius:9px;background:rgba(255,255,255,.02);margin-bottom:6px}
.node.run{background:rgba(243,146,0,.12);border:1px solid rgba(243,146,0,.4)}
.dot{width:9px;height:9px;border-radius:50%;flex:none}
.dot.done{background:var(--green);box-shadow:0 0 10px var(--green)}
.dot.run{background:var(--accent);box-shadow:0 0 10px var(--accent)}
.dot.wait{background:#3a4452}
.nid{font-family:monospace;font-size:12px;color:var(--accent);width:40px;flex:none}
.nl{font-size:13px;font-weight:600}
.ns{font-size:11px;color:var(--mut);margin-left:4px}
.nok{margin-left:auto;font-size:11px;font-weight:700}
.logrow{font-family:monospace;font-size:11px;color:#8a98ad;padding:3px 0}
.logts{color:#586377}.lognd{color:var(--accent)}
.form-row{display:flex;flex-direction:column;gap:6px;margin-bottom:16px;text-align:left;width:100%;max-width:480px}
.form-row label{font-size:12px;color:var(--mut);font-weight:600}
.form-row input{background:#11141b;border:1px solid #232a38;border-radius:9px;padding:11px 13px;color:var(--txt);font-size:14px}
.form-row input[type=file]{padding:9px 11px}
.hidden{display:none}
.pulse{animation:p 1.4s infinite}@keyframes p{0%,100%{opacity:1}50%{opacity:.45}}
.barwrap{height:8px;background:#15202c;border-radius:5px;overflow:hidden;margin-top:10px}
.bar{height:100%;background:linear-gradient(90deg,var(--brand),var(--accent));width:0%}
</style></head><body><div class="wrap">

<div class="top">
  <div><div class="kick">● MISSION CONTROL</div><div class="title">KI-Wirtschaftlichkeits-Check</div>
  <div class="sub" id="sub">Self-hosted &middot; DSGVO-konform</div></div>
  <div id="topbtns">
    <button class="btn btn-start" id="startBtn">▶ Start</button>
  </div>
</div>

<!-- IDLE / FORM -->
<div id="view-idle" class="card center">
  <div class="hero-ic">▶</div>
  <div class="hero-h">Analyse starten</div>
  <div class="hero-p">Gespraechsaufnahme und/oder Kundendokument(e) hochladen &ndash; mindestens eines von beidem genuegt. Die Verarbeitung laeuft vollstaendig self-hosted.</div>
  <form id="frm" class="hidden" style="width:100%;display:flex;flex-direction:column;align-items:center">
    <div class="form-row"><label>Unternehmen *</label><input name="Unternehmen" required placeholder="z. B. Leclere Solutions"></div>
    <div class="form-row"><label>Audio (optional) &ndash; mp3, wav, m4a, ogg</label><input type="file" name="audio" accept=".mp3,.wav,.m4a,.ogg"></div>
    <div class="form-row"><label>Kundendokumente (optional) &ndash; PDF, mehrere moeglich</label><input type="file" name="dokumente" accept=".pdf" multiple></div>
    <button class="btn btn-start" type="submit" style="margin-top:6px">Analyse starten ▶</button>
    <div class="sub" id="frmerr" style="color:#ff6b6b;margin-top:10px"></div>
  </form>
</div>

<!-- RUNNING / DONE -->
<div id="view-run" class="hidden">
  <div class="barwrap"><div class="bar" id="bar"></div></div>
  <div class="sub" id="runline" style="margin:8px 0 16px">Analyse laeuft &hellip;</div>
  <div class="grid">
    <div style="display:flex;flex-direction:column;gap:16px">
      <div class="card" style="text-align:center">
        <div class="ring" id="ring"><div><div style="font-size:34px;font-weight:800" id="pct">0%</div><div style="font-size:11px;color:var(--mut)" id="ncount">0 / 11</div></div></div>
        <div class="sub" id="ringsub">Analyse laeuft &hellip;</div>
      </div>
      <div class="kpis" id="kpis"></div>
    </div>
    <div class="card"><div class="lab">NODE-STATUS</div><div id="nodes"></div></div>
    <div class="card"><div class="lab">LIVE-LOG</div><div id="log"></div></div>
  </div>
</div>

<script>
var runId=null, timer=null;
var startBtn=document.getElementById('startBtn'), frm=document.getElementById('frm');
// Endpunkte relativ zum Dashboard-Pfad aufloesen (robust gegen /webhook/ vs /webhook-test/ und Trailing-Slash).
function apiBase(){ var p=location.pathname.replace(/\/+$/,''); return p.replace(/\/[^\/]*$/,'/'); }
var BASE=apiBase();
function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function show(id){ ['view-idle','view-run'].forEach(function(v){ document.getElementById(v).classList.toggle('hidden', v!==id); }); }
function setLine(html){ document.getElementById('runline').innerHTML=html; }
function fail(msg){ clearInterval(timer); setLine('<span style="color:#ff6b6b">⚠ '+esc(msg)+'</span>'); document.getElementById('ringsub').textContent='Fehler'; }
startBtn.onclick=function(){ frm.classList.remove('hidden'); startBtn.classList.add('hidden'); };

frm.onsubmit=function(e){
  e.preventDefault();
  document.getElementById('frmerr').textContent='';
  // SOFORT in die Laufansicht wechseln, damit der Nutzer Feedback bekommt (Upload kann dauern).
  show('view-run');
  document.getElementById('topbtns').innerHTML='<a class="btn btn-dl off" id="dlBtn">⤓ PDF herunterladen</a>';
  document.getElementById('pct').textContent='0%';
  document.getElementById('ncount').textContent='0 / 11';
  document.getElementById('ringsub').textContent='Upload …';
  document.getElementById('nodes').innerHTML='<div class="ns" style="padding:8px">Analyse wird vorbereitet …</div>';
  document.getElementById('kpis').innerHTML='';
  document.getElementById('log').innerHTML='';
  setLine('Verbindung wird aufgebaut …');
  var fd=new FormData(frm);
  var xhr=new XMLHttpRequest();
  xhr.open('POST', BASE+'wc-start');
  xhr.upload.onprogress=function(ev){
    if(ev.lengthComputable){ var p=Math.round(ev.loaded/ev.total*100);
      document.getElementById('bar').style.width=p+'%';
      document.getElementById('pct').textContent=p+'%';
      setLine('Dateien werden hochgeladen … <strong style="color:var(--accent)">'+p+'%</strong>'+(p>=100?' &middot; starte Analyse …':''));
    }
  };
  xhr.onload=function(){
    if(xhr.status>=200 && xhr.status<300){
      var d=null; try{ d=JSON.parse(xhr.responseText); }catch(e){}
      if(d && d.run_id){
        runId=d.run_id;
        document.getElementById('bar').style.width='0%';
        document.getElementById('pct').textContent='0%';
        document.getElementById('ringsub').textContent='Analyse laeuft …';
        setLine('Analyse gestartet &hellip;');
        poll(); timer=setInterval(poll,1500);
        return;
      }
      fail('Upload ok, aber keine run_id erhalten (HTTP '+xhr.status+'). Antwortet "wc-start" mit JSON?');
    } else {
      fail('HTTP '+xhr.status+' bei '+BASE+'wc-start — ist der Workflow in n8n AKTIV (Production-Webhook)?');
    }
  };
  xhr.onerror=function(){ fail('Verbindung zu '+BASE+'wc-start fehlgeschlagen — Workflow aktiv & URL korrekt?'); };
  xhr.send(fd);
};

function poll(){
  if(!runId) return;
  fetch(BASE+'wc-status?run='+encodeURIComponent(runId)).then(function(r){return r.json();}).then(render).catch(function(){});
}

function render(d){
  if(!d || d.state==='unknown' || d.state==='pending') return;
  var pct=d.pct||0;
  document.getElementById('bar').style.width=pct+'%';
  document.getElementById('pct').textContent=pct+'%';
  document.getElementById('ncount').textContent=(d.done_count||0)+' / '+(d.total||11);
  document.getElementById('ring').style.background='conic-gradient(var(--accent) '+(pct*3.6)+'deg,#15202c '+(pct*3.6)+'deg)';
  if(d.state==='rejected'){
    document.getElementById('runline').innerHTML='<span style="color:#ff6b6b">Eingabe abgelehnt: '+esc(d.meldung||'')+'</span>';
    document.getElementById('ringsub').textContent='abgelehnt';
    clearInterval(timer); return;
  }
  document.getElementById('sub').textContent=(d.unternehmen?esc(d.unternehmen)+' · ':'')+(d.datum||'')+' · self-hosted · DSGVO-konform';
  // nodes
  var nh='';
  (d.nodes||[]).forEach(function(n){
    var ok=n.status==='done'?'<span class="nok" style="color:var(--green)">OK</span>':(n.status==='run'?'<span class="nok" style="color:var(--accent)">…</span>':'');
    nh+='<div class="node '+(n.status==='run'?'run':'')+'"><span class="dot '+n.status+'"></span>'+
        '<span class="nid">'+esc(n.key)+'</span><span class="nl">'+esc(n.label)+'</span>'+
        (n.summary?'<span class="ns">— '+esc(n.summary)+'</span>':'')+ok+'</div>';
  });
  document.getElementById('nodes').innerHTML=nh;
  // kpis
  var k=d.kpi, kh='';
  function kpi(lab,val,sub){ return '<div class="kpi"><div class="k">'+lab+'</div><div class="v">'+esc(val)+'</div><div class="s">'+esc(sub||'')+'</div></div>'; }
  if(k){ kh=kpi('Realis. Nutzen/Jahr',k.nutzen,k.nutzen_sub)+kpi('Break-Even',k.breakeven,'')+kpi('ROI Jahr 1',k.roi,k.roi_sub)+kpi('Empfehlung',k.empfehlung,k.empfehlung_sub); }
  else { kh='<div class="kpi" style="grid-column:span 2"><div class="k">Kennzahlen</div><div class="v" style="font-size:14px;color:var(--mut)">werden ab N05 berechnet …</div></div>'; }
  document.getElementById('kpis').innerHTML=kh;
  // log
  document.getElementById('log').innerHTML=(d.log||[]).map(function(l){
    return '<div class="logrow"><span class="logts">'+esc(l.ts||'')+'</span> '+(l.node?'<span class="lognd">'+esc(l.node)+'</span> ':'')+esc(l.msg||'')+'</div>';
  }).join('');
  // state
  if(d.state==='done'){
    document.getElementById('runline').innerHTML='<span style="color:var(--green)">✓ Analyse abgeschlossen</span>';
    document.getElementById('ringsub').textContent='fertig';
    var dl=document.getElementById('dlBtn');
    if(dl){ dl.classList.remove('off'); dl.classList.add('btn-dl'); dl.setAttribute('href',BASE+'wc-pdf?run='+encodeURIComponent(runId)); dl.setAttribute('target','_blank'); }
    clearInterval(timer);
  } else {
    var cur=(d.nodes||[]).filter(function(n){return n.status==='run';})[0];
    var hint=(cur&&cur.key==='N00')?' <span style="color:var(--mut2)">(Transkription per Whisper &ndash; kann je nach Audiolaenge einige Minuten dauern)</span>':'';
    document.getElementById('runline').innerHTML='Analyse laeuft &hellip; '+(cur?('aktuell: <strong style="color:var(--accent)">'+esc(cur.key)+' '+esc(cur.label)+'</strong>'):'')+hint;
    document.getElementById('ringsub').textContent='Analyse laeuft …';
  }
}
</script>
</div></body></html>"""

# ============================================================ Knoten anlegen
DX, DY = -1700, 760   # Layout-Bereich fuer die Webhook-Schicht (unterhalb der Pipeline)

# ---- 1) Analyse-Start-Webhook -> Run anlegen -> (Respond run_id | Config)
add("Webhook: Analyse-Start", WEBHOOK, {
    "httpMethod": "POST", "path": "wc-start", "responseMode": "responseNode", "options": {},
}, tv=2, pos=(DX, DY), extra={"webhookId": "wc-start-01"})

add("Run anlegen", CODE, {"jsCode":
"// Erzeugt run_id, normalisiert das Formular und schreibt den Initial-Status (alle Schritte 'wartet').\n"
"const item = $input.first();\n"
"const j = item.json || {};\n"
"const body = j.body || j;\n"
"const unternehmen = body.Unternehmen || body.unternehmen || j.Unternehmen || '';\n"
"const run_id = (Date.now().toString(36) + Math.random().toString(36).slice(2,7));\n"
"const datum = new Date().toISOString().slice(0,10);\n"
"const fs = (function(){ try { return require('fs'); } catch(e){ return null; } })();\n"
"const WCBASE = " + _json.dumps(WCBASE) + ";\n"
"const labels = [['N00','Eingang & Qualitaet'],['N00b','Dokumente (Text/OCR)'],['N01','Kontext & Prozess'],['N02','Automatisierungsreife'],['N03','Direkter Nutzen'],['N04','Vollkosten'],['N05','Kennzahlen / ROI'],['N06','Umsetzbarkeit'],['N07','Risiko & Compliance'],['N08','Score & Empfehlung'],['N10','Report-PDF']];\n"
"const stations = labels.map((s,i)=>({ key:s[0], label:s[1], status: i===0?'run':'wait', summary:'' }));\n"
"// TTL-Aufraeumung: alte Status-/PDF-Dateien (> 1 Std.) loeschen, damit nichts (v.a. Kunden-PDFs) liegen bleibt.\n"
"try { if (fs) { const nowMs = Date.now(); const TTL = 3600 * 1000; for (const f of fs.readdirSync(WCBASE)) {\n"
"  if (/^wc_(status|pdf)_/.test(f)) { try { const st = fs.statSync(WCBASE + '/' + f); if (nowMs - st.mtimeMs > TTL) fs.unlinkSync(WCBASE + '/' + f); } catch(e){} }\n"
"} } } catch(e){}\n"
"const snap = { run_id, unternehmen, datum, state:'running', pct:0, done_count:0, total:stations.length, current:'N00', nodes:stations, kpi:null, pdf_ready:false, log:[{ ts:new Date().toLocaleTimeString('de-DE'), key:'start', node:'', msg:'Analyse gestartet' }] };\n"
"try { if (fs) { fs.writeFileSync(WCBASE + '/wc_status_' + run_id + '.json', JSON.stringify(snap)); } } catch(e){}\n"
"return [{ json: { ...j, Unternehmen: unternehmen, run_id, datum }, binary: item.binary }];\n"
}, tv=2, pos=(DX + 220, DY))
connect("Webhook: Analyse-Start", "Run anlegen")

add("Antwort: run_id", RESP, {
    "respondWith": "text",
    "responseBody": "={{ JSON.stringify({ run_id: $json.run_id, ok: true }) }}",
    "options": {"responseHeaders": {"entries": [{"name": "Content-Type", "value": "application/json"}]}},
}, tv=1.1, pos=(DX + 440, DY - 90))
connect("Run anlegen", "Antwort: run_id")
# Run anlegen -> Config wird in gen.py per connect("Run anlegen","Config") verbunden.

# ---- 2) Dashboard-Webhook -> HTML -> Respond
add("Webhook: Dashboard", WEBHOOK, {
    "httpMethod": "GET", "path": "wc", "responseMode": "responseNode", "options": {},
}, tv=2, pos=(DX, DY + 220), extra={"webhookId": "wc-dashboard-01"})
add("Dashboard HTML", CODE, {"jsCode":
"// Liefert das schwarze Mission-Control-Dashboard (Formular integriert, Live-Polling).\n"
"return [{ json: { html: " + _json.dumps(DASH_HTML) + " } }];\n"
}, tv=2, pos=(DX + 220, DY + 220))
connect("Webhook: Dashboard", "Dashboard HTML")
add("Antwort: Dashboard", RESP, {
    "respondWith": "text", "responseBody": "={{ $json.html }}",
    "options": {"responseHeaders": {"entries": [{"name": "Content-Type", "value": "text/html; charset=utf-8"}]}},
}, tv=1.1, pos=(DX + 440, DY + 220))
connect("Dashboard HTML", "Antwort: Dashboard")

# ---- 3) Status-Webhook -> Datei lesen -> Respond JSON
add("Webhook: Status", WEBHOOK, {
    "httpMethod": "GET", "path": "wc-status", "responseMode": "responseNode", "options": {},
}, tv=2, pos=(DX, DY + 440), extra={"webhookId": "wc-status-01"})
add("Status lesen", CODE, {"jsCode":
"// Liest die Status-Datei zum run und gibt sie als JSON-String zurueck.\n"
"const q = ($input.first().json.query) || {};\n"
"const run = q.run || '';\n"
"const fs = (function(){ try { return require('fs'); } catch(e){ return null; } })();\n"
"const WCBASE = " + _json.dumps(WCBASE) + ";\n"
"let payload = '{\"state\":\"unknown\"}';\n"
"try { if (fs && run) { payload = fs.readFileSync(WCBASE + '/wc_status_' + run + '.json', 'utf8'); } } catch(e){ payload = '{\"state\":\"pending\"}'; }\n"
"return [{ json: { payload } }];\n"
}, tv=2, pos=(DX + 220, DY + 440))
connect("Webhook: Status", "Status lesen")
add("Antwort: Status", RESP, {
    "respondWith": "text", "responseBody": "={{ $json.payload }}",
    "options": {"responseHeaders": {"entries": [{"name": "Content-Type", "value": "application/json"}]}},
}, tv=1.1, pos=(DX + 440, DY + 440))
connect("Status lesen", "Antwort: Status")

# ---- 4) PDF-Webhook -> Datei lesen -> Respond (Download)
add("Webhook: PDF", WEBHOOK, {
    "httpMethod": "GET", "path": "wc-pdf", "responseMode": "responseNode", "options": {},
}, tv=2, pos=(DX, DY + 660), extra={"webhookId": "wc-pdf-01"})
add("PDF lesen", CODE, {"jsCode":
"// Liest die fertige PDF-Datei zum run und gibt sie als Binary 'data' zurueck.\n"
"const q = ($input.first().json.query) || {};\n"
"const run = q.run || '';\n"
"const fs = (function(){ try { return require('fs'); } catch(e){ return null; } })();\n"
"const WCBASE = " + _json.dumps(WCBASE) + ";\n"
"let buf = null; try { if (fs && run) buf = fs.readFileSync(WCBASE + '/wc_pdf_' + run + '.pdf'); } catch(e){}\n"
"if (!buf) return [{ json: { error: 'not_ready' } }];\n"
"// DSGVO: Kunden-PDF direkt nach dem Ausliefern vom Server entfernen (Download nur einmal moeglich).\n"
"try { if (fs && run) fs.unlinkSync(WCBASE + '/wc_pdf_' + run + '.pdf'); } catch(e){}\n"
"return [{ json: {}, binary: { data: { data: buf.toString('base64'), mimeType: 'application/pdf', fileName: 'Wirtschaftlichkeits-Check.pdf', fileExtension: 'pdf' } } }];\n"
}, tv=2, pos=(DX + 220, DY + 660))
connect("Webhook: PDF", "PDF lesen")
add("Antwort: PDF", RESP, {
    "respondWith": "binary", "responseBinaryPropertyName": "data",
    "options": {"responseHeaders": {"entries": [
        {"name": "Content-Type", "value": "application/pdf"},
        {"name": "Content-Disposition", "value": "attachment; filename=\"Wirtschaftlichkeits-Check.pdf\""},
    ]}},
}, tv=1.1, pos=(DX + 440, DY + 660))
connect("PDF lesen", "Antwort: PDF")

# ============================================================ Checkpoints in die Pipeline einfuegen (Variante B)
CP_X0, CP_Y = 460, 420
_cp_i = [0]
def checkpoint(after_node, before_node, out=0):
    """Fuegt nach after_node einen Status-Checkpoint ein (vor before_node)."""
    name = "CP " + after_node.split(" ")[0].replace("·", "x")
    add(name, CODE, {"jsCode":
        "// Live-Checkpoint: schreibt den aktuellen Analyse-Status (Variante B, /tmp).\n"
        + snap_js(False) + "return $input.all();\n"
    }, tv=2, pos=(CP_X0 + _cp_i[0] * 150, CP_Y))
    _cp_i[0] += 1
    resplice(after_node, name, before_node, out=out)
    return name

# Reihenfolge entspricht der Pipeline; jeder CP markiert die fertigen Schritte + den naechsten als 'laeuft'.
checkpoint("Analyse-Kontext bauen", "N01 · Prompt")     # N00/N00b fertig, N01 laeuft
checkpoint("N01 · LLM", "N02 · Prompt")
checkpoint("N02 · LLM", "N03 · Prompt")
checkpoint("N03 · LLM", "N04 · Prompt")
checkpoint("N04 · LLM", "N05a · Kennzahlen")
checkpoint("N05a · Kennzahlen", "N05b · Prompt")
checkpoint("N06 · LLM", "N07 · Prompt")
checkpoint("N07 · LLM", "N08a · Score-Aggregation")
checkpoint("N08a · Score-Aggregation", "N08b · Prompt")

# ---- Final: nach Gotenberg PDF speichern + Status 'done', dann weiter zu Dropbox
add("N10 · PDF speichern & finalisieren", CODE, {"jsCode":
"// Speichert die fertige PDF nach /tmp und schreibt den Abschluss-Status (state=done).\n"
"const fs0 = (function(){ try { return require('fs'); } catch(e){ return null; } })();\n"
"let run0 = null; try { run0 = $('Run anlegen').first().json.run_id; } catch(e){}\n"
"let buf = null; try { buf = await this.helpers.getBinaryDataBuffer(0, 'data'); } catch(e){}\n"
"try { if (fs0 && run0 && buf) { fs0.writeFileSync(" + _json.dumps(WCBASE) + " + '/wc_pdf_' + run0 + '.pdf', buf); } } catch(e){}\n"
+ snap_js(True) +
"return $input.all();\n"
}, tv=2, pos=(3560, 0))
resplice("Gotenberg: HTML zu PDF", "N10 · PDF speichern & finalisieren", "Dropbox: PDF ablegen")
