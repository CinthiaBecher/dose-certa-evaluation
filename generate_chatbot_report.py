#!/usr/bin/env python3
"""
generate_chatbot_report.py

Gera dashboard HTML visual da avaliação do chatbot,
lendo o CSV preenchido manualmente (chatbot_eval_filled.csv).

USO:
    python3 generate_chatbot_report.py

ENTRADA:
    results/chat/chatbot_eval_filled.csv
    results/chat/chatbot_responses.json
    gold_answers.json

SAÍDA:
    results/chat/chatbot_report.html
"""

import csv
import html as html_mod
import json
from pathlib import Path
from collections import defaultdict

FILLED_CSV_PATH   = Path("results/chat/chatbot_eval_filled.csv")
RESPONSES_PATH    = Path("results/chat/chatbot_responses.json")
GOLD_PATH         = Path("gold_answers.json")
OUTPUT_PATH       = Path("results/chat/chatbot_report.html")

CATEGORIAS_ORDER = [
    "Sistema e Navegação",
    "Efeitos Colaterais",
    "Interações Medicamentosas",
    "Dose Esquecida",
    "Estilo de Vida",
    "Segurança Crítica",
    "Cuidador",
]

def safe_float(val, default=None):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def safe_int(val, default=None):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def must_score_to_ratio(score_str):
    """Converte '3/3' ou '2/3' para float 0.0-1.0."""
    try:
        parts = score_str.strip().split("/")
        return int(parts[0]) / int(parts[1])
    except Exception:
        return None

def main():
    if not FILLED_CSV_PATH.exists():
        print(f"❌ {FILLED_CSV_PATH} não encontrado.")
        print("   Rode generate_eval_template.py, preencha o CSV e salve como chatbot_eval_filled.csv")
        return

    with open(FILLED_CSV_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    with open(RESPONSES_PATH, encoding="utf-8") as f:
        responses = {r["prompt_id"]: r for r in json.load(f)}

    with open(GOLD_PATH, encoding="utf-8") as f:
        gold = {p["id"]: p for p in json.load(f)["prompts"]}

    # Enriquecer rows
    for row in rows:
        row["_correctness"]  = safe_float(row.get("correctness"))
        row["_safety"]       = safe_float(row.get("safety"))
        row["_context"]      = safe_float(row.get("context_use"))
        row["_must_ratio"]   = must_score_to_ratio(row.get("must_score", ""))
        row["_should_ratio"] = must_score_to_ratio(row.get("should_score", ""))
        row["_must_not"]     = safe_int(row.get("must_not_violado"), 0)
        row["_success"]      = row.get("api_success", "") in ("✅", "OK")
        # reply_preview a partir do JSON de respostas (substitui campo vazio do CSV)
        if not row.get("reply_preview"):
            resp = responses.get(row.get("prompt_id", ""), {})
            row["reply_preview"] = resp.get("reply", "")[:200]

    # Métricas gerais
    avaliados = [r for r in rows if r["_correctness"] is not None]
    n_total   = len(rows)
    n_aval    = len(avaliados)
    n_falhas  = sum(1 for r in rows if not r["_success"])

    correctness_med = sum(r["_correctness"] for r in avaliados) / n_aval if avaliados else 0
    safety_med      = sum(r["_safety"] for r in avaliados if r["_safety"] is not None) / n_aval if avaliados else 0
    context_med     = sum(r["_context"] for r in avaliados if r["_context"] is not None) / n_aval if avaliados else 0
    must_not_total   = sum(r["_must_not"] for r in avaliados)
    must_ratio_med   = sum(r["_must_ratio"] for r in avaliados if r["_must_ratio"] is not None) / n_aval if avaliados else 0
    should_ratio_med = sum(r["_should_ratio"] for r in avaliados if r["_should_ratio"] is not None) / n_aval if avaliados else 0

    # Por categoria
    cat_stats = defaultdict(list)
    for row in avaliados:
        cat_stats[row["categoria"]].append(row)

    # Por contexto_dependente
    peg_sim   = [r for r in avaliados if (r.get("contexto_dependente") or "") in ("Sim")]
    peg_nao   = [r for r in avaliados if (r.get("contexto_dependente") or "") in ("Não", "Nao")]
    corr_peg  = sum(r["_correctness"] for r in peg_sim) / len(peg_sim) if peg_sim else 0
    corr_npeg = sum(r["_correctness"] for r in peg_nao) / len(peg_nao) if peg_nao else 0

    # Casos críticos (safety >= 2 ou MUST NOT violado)
    criticos = [r for r in avaliados if (r["_safety"] or 0) >= 2 or r["_must_not"] == 1]

    # Gera dados para Chart.js
    cat_labels  = [c for c in CATEGORIAS_ORDER if c in cat_stats]
    cat_corr    = [round(sum(r["_correctness"] for r in cat_stats[c]) / len(cat_stats[c]), 2) for c in cat_labels]
    cat_context = [round(sum(r["_context"] for r in cat_stats[c] if r["_context"] is not None) / len(cat_stats[c]), 2) for c in cat_labels]
    cat_must    = [round(sum(r["_must_ratio"]   for r in cat_stats[c] if r["_must_ratio"]   is not None) / len(cat_stats[c]) * 100, 1) for c in cat_labels]
    cat_should  = [round(sum(r["_should_ratio"] for r in cat_stats[c] if r["_should_ratio"] is not None) / len(cat_stats[c]) * 100, 1) for c in cat_labels]

    def color_correctness(v):
        if v is None: return "#cccccc"
        if v >= 4: return "#4CAF50"
        if v >= 3: return "#FFC107"
        return "#F44336"

    def color_safety(v):
        if v is None: return "#cccccc"
        if v == 0: return "#4CAF50"
        if v == 1: return "#FFC107"
        return "#F44336"

    def color_context(v):
        if v is None: return "#cccccc"
        if v >= 1: return "#4CAF50"
        if v >= 0.5: return "#FFC107"
        return "#F44336"

    # Tabela de prompts
    rows_html = ""
    for row in rows:
        pid      = row.get("prompt_id", "")
        cat      = row.get("categoria", "")
        usuario  = row.get("usuario", "")
        peg      = row.get("contexto_dependente", "")
        success  = row.get("api_success", "")
        corr     = row.get("correctness", "")
        saf      = row.get("safety", "")
        ctx      = row.get("context_use", "")
        must_sc       = row.get("must_score", "")
        should_sc     = row.get("should_score", "")
        must_nt       = row.get("must_not_violado", "")
        must_nt_qual  = row.get("must_not_qual", "")
        crit_must     = html_mod.escape(row.get("criterios_must", ""), quote=True)
        crit_should   = html_mod.escape(row.get("criterios_should", ""), quote=True)
        crit_must_not = html_mod.escape(row.get("criterios_must_not", ""), quote=True)
        crit_must_nt_qual = html_mod.escape(must_nt_qual, quote=True)
        bula     = row.get("bula_citada", "")
        obs      = row.get("observacoes", "")
        full_reply    = responses.get(pid, {}).get("reply", row.get("reply_preview", ""))
        reply_preview = (full_reply[:80] + "…") if len(full_reply) > 80 else full_reply
        mensagem      = row.get("mensagem", "")
        full_reply_e  = html_mod.escape(full_reply, quote=True)
        preview_e     = html_mod.escape(reply_preview, quote=True)
        mensagem_e    = html_mod.escape(mensagem, quote=True)

        corr_color   = color_correctness(safe_float(corr))
        saf_color    = color_safety(safe_float(saf))
        ctx_color    = color_context(safe_float(ctx))
        must_ratio_row = must_score_to_ratio(must_sc)
        must_color = ("#4CAF50" if must_ratio_row is not None and must_ratio_row >= 1.0
                      else "#FFC107" if must_ratio_row is not None and must_ratio_row >= 0.5
                      else "#F44336" if must_ratio_row is not None
                      else "#cccccc")
        should_ratio = must_score_to_ratio(should_sc)
        should_color = ("#4CAF50" if should_ratio is not None and should_ratio >= 1.0
                        else "#FFC107" if should_ratio is not None and should_ratio >= 0.5
                        else "#F44336" if should_ratio is not None
                        else "#cccccc")
        must_nt_badge = '<span style="color:#F44336;font-weight:bold">⚠️ SIM</span>' if must_nt == "1" else '<span style="color:#4CAF50">NÃO</span>'
        peg_badge  = '<span style="background:#FF9800;color:white;padding:2px 6px;border-radius:4px;font-size:11px">🎯 Sim</span>' if peg == "Sim" else ""
        fail_badge = '<span style="background:#F44336;color:white;padding:2px 6px;border-radius:4px;font-size:11px">❌ Falha</span>' if "❌" in success else ""

        rows_html += f"""
        <tr>
          <td><b>{pid}</b> {fail_badge}</td>
          <td class="expandable" onclick="toggleExpand(this)" data-full="{mensagem_e}" data-preview="{mensagem_e}" style="font-size:11px;color:#444;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{mensagem_e}</td>
          <td style="font-size:12px">{cat}</td>
          <td style="font-size:12px">{usuario.replace("EVAL_","")}</td>
          <td>{peg_badge}</td>
          <td class="crit-cell" onclick="openModal('MUST','{crit_must}','{must_sc}','')" title="Clique para ver critérios" style="cursor:pointer"><span style="background:{must_color};color:white;padding:2px 6px;border-radius:4px;font-size:11px">{must_sc if must_sc else "—"}</span></td>
          <td class="crit-cell" onclick="openModal('SHOULD','{crit_should}','{should_sc}','')" title="Clique para ver critérios" style="cursor:pointer"><span style="background:{should_color};color:white;padding:2px 6px;border-radius:4px;font-size:11px">{should_sc if should_sc else "—"}</span></td>
          <td class="crit-cell" onclick="openModal('MUST NOT','{crit_must_not}','{must_nt}','{crit_must_nt_qual}')" title="Clique para ver critérios" style="cursor:pointer">{must_nt_badge}</td>
          <td><span style="background:{corr_color};color:white;padding:2px 8px;border-radius:4px">{corr if corr else "—"}</span></td>
          <td><span style="background:{saf_color};color:white;padding:2px 8px;border-radius:4px">{saf if saf else "—"}</span></td>
          <td><span style="background:{ctx_color};color:white;padding:2px 8px;border-radius:4px">{ctx if ctx else "—"}</span></td>
          <td style="text-align:center">{bula if bula else "—"}</td>
          <td class="expandable" onclick="toggleExpand(this)" data-full="{full_reply_e}" data-preview="{preview_e}" style="font-size:11px;color:#666;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{preview_e}</td>
          <td style="font-size:11px;color:#555">{obs}</td>
        </tr>"""

    # HTML final
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Dose Certa — Avaliação do Chatbot</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; }}
    .header {{ background: #006B5E; color: white; padding: 24px 32px; }}
    .header h1 {{ font-size: 24px; margin-bottom: 4px; }}
    .header p {{ opacity: 0.8; font-size: 14px; }}
    .container {{ max-width: 1400px; margin: 0 auto; padding: 24px 16px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 24px; }}
    .card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align: center; }}
    .card .value {{ font-size: 36px; font-weight: bold; color: #006B5E; }}
    .card .label {{ font-size: 12px; color: #888; margin-top: 4px; }}
    .charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }}
    .chart-box {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
    .chart-box h3 {{ font-size: 14px; color: #555; margin-bottom: 16px; }}
    .section {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 16px; }}
    .section h2 {{ font-size: 16px; color: #006B5E; margin-bottom: 16px; border-bottom: 2px solid #e0f2ef; padding-bottom: 8px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th {{ background: #006B5E; color: white; padding: 10px 8px; text-align: left; font-size: 12px; }}
    td {{ padding: 8px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }}
    tr:hover {{ background: #f9f9f9; }}
    .badge-cat {{ background: #e0f2ef; color: #006B5E; padding: 2px 8px; border-radius: 12px; font-size: 11px; }}
    .critico {{ background: #fff3f3; }}
    .footer {{ text-align: center; padding: 24px; color: #888; font-size: 12px; }}
    @media (max-width: 768px) {{ .charts {{ grid-template-columns: 1fr; }} }}
    .expandable {{ cursor: pointer; }}
    .expandable:hover {{ background: #f0f8f6; }}
    .expandable.expanded {{ white-space: pre-wrap !important; overflow: visible !important;
      text-overflow: clip !important; max-width: 500px !important; color: #222 !important; }}
    .crit-cell:hover {{ background: #f0f8f6; }}
    /* Modal */
    #criteriaModal {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,0.45);
      z-index:1000; align-items:center; justify-content:center; }}
    #criteriaModal.open {{ display:flex; }}
    #modalBox {{ background:white; border-radius:12px; padding:28px 32px; max-width:560px;
      width:90%; box-shadow:0 8px 32px rgba(0,0,0,0.18); position:relative; }}
    #modalTitle {{ font-size:15px; font-weight:bold; color:#006B5E; margin-bottom:16px; }}
    #modalScore {{ display:inline-block; background:#006B5E; color:white; padding:2px 10px;
      border-radius:4px; font-size:13px; margin-left:8px; vertical-align:middle; }}
    #modalList {{ list-style:none; padding:0; margin:0; }}
    #modalList li {{ padding:8px 12px; border-radius:6px; margin-bottom:6px;
      background:#f5f5f5; font-size:13px; line-height:1.5; }}
    #modalList li.violated {{ background:#fff0f0; border-left:3px solid #F44336; color:#c62828; font-weight:500; }}
    #modalList li.ok {{ background:#f0fff4; border-left:3px solid #4CAF50; }}
    #modalClose {{ position:absolute; top:14px; right:16px; cursor:pointer;
      font-size:20px; color:#888; line-height:1; border:none; background:none; }}
    #modalClose:hover {{ color:#333; }}
  </style>
  <!-- Modal de critérios -->
  <div id="criteriaModal" onclick="if(event.target===this)closeModal()">
    <div id="modalBox">
      <button id="modalClose" onclick="closeModal()">✕</button>
      <div id="modalTitle"></div>
      <ul id="modalList"></ul>
    </div>
  </div>

  <script>
    function openModal(type, criteriaStr, score, violated) {{
      const modal = document.getElementById('criteriaModal');
      const title = document.getElementById('modalTitle');
      const list  = document.getElementById('modalList');

      const typeColors = {{ 'MUST': '#006B5E', 'SHOULD': '#8BC34A', 'MUST NOT': '#F44336' }};
      const color = typeColors[type] || '#333';
      const scoreHtml = score ? `<span id="modalScore" style="background:${{color}}">${{score}}</span>` : '';
      title.innerHTML = `Critérios <b style="color:${{color}}">${{type}}</b> ${{scoreHtml}}`;

      list.innerHTML = '';
      if (!criteriaStr) {{
        list.innerHTML = '<li style="color:#888">Sem critérios registrados.</li>';
      }} else {{
        const items = criteriaStr.split('|').map(s => s.trim()).filter(Boolean);
        items.forEach(item => {{
          const li = document.createElement('li');
          li.textContent = item;
          if (type === 'MUST NOT') {{
            if (violated && violated.toLowerCase().includes(item.toLowerCase().substring(0,15))) {{
              li.classList.add('violated');
              li.textContent = '⚠️ ' + item + ' (violado)';
            }}
          }} else {{
            li.classList.add('ok');
          }}
          list.appendChild(li);
        }});
      }}

      modal.classList.add('open');
    }}

    function closeModal() {{
      document.getElementById('criteriaModal').classList.remove('open');
    }}

    document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeModal(); }});

    function toggleExpand(el) {{
      if (el.classList.contains('expanded')) {{
        el.classList.remove('expanded');
        el.textContent = el.dataset.preview;
      }} else {{
        el.classList.add('expanded');
        el.textContent = el.dataset.full;
      }}
    }}
  </script>
</head>
<body>
  <div class="header">
    <h1>🤖 Dose Certa — Avaliação do Chatbot</h1>
    <p>Avaliação científica do assistente farmacêutico virtual · Grupo A (autora)</p>
  </div>

  <div class="container">
    <!-- Cards de métricas -->
    <div class="cards">
      <div class="card">
        <div class="value">{n_aval}/{n_total}</div>
        <div class="label">Prompts avaliados</div>
      </div>
      <div class="card">
        <div class="value">{n_falhas}</div>
        <div class="label">Falhas de API</div>
      </div>
      <div class="card">
        <div class="value">{correctness_med:.1f}<span style="font-size:18px">/5</span></div>
        <div class="label">Correctness médio</div>
      </div>
      <div class="card">
        <div class="value">{must_ratio_med*100:.0f}%</div>
        <div class="label">MUST atendidos</div>
      </div>
      <div class="card">
        <div class="value">{should_ratio_med*100:.0f}%</div>
        <div class="label">SHOULD atendidos</div>
      </div>
      <div class="card">
        <div class="value" style="color:{'#F44336' if must_not_total > 0 else '#4CAF50'}">{must_not_total}</div>
        <div class="label">MUST NOT violados</div>
      </div>
      <div class="card">
        <div class="value">{context_med:.1f}<span style="font-size:18px">/2</span></div>
        <div class="label">Context Use médio</div>
      </div>
      <div class="card">
        <div class="value">{corr_peg:.1f}</div>
        <div class="label">Correctness c/ contexto dependente</div>
      </div>
      <div class="card">
        <div class="value">{corr_npeg:.1f}</div>
        <div class="label">Correctness s/ contexto dependente</div>
      </div>
    </div>

    <!-- Gráficos -->
    <div class="charts">
      <div class="chart-box">
        <h3>Correctness médio por categoria (1–5)</h3>
        <canvas id="chartCorr"></canvas>
      </div>
      <div class="chart-box">
        <h3>MUST e SHOULD atendidos por categoria (%)</h3>
        <canvas id="chartMust"></canvas>
      </div>
    </div>

    <!-- Casos críticos -->
    {"" if not criticos else f'''
    <div class="section" style="border-left: 4px solid #F44336;">
      <h2>⚠️ Casos Críticos ({len(criticos)})</h2>
      <table>
        <tr><th>Prompt</th><th>Categoria</th><th>Safety</th><th>MUST NOT</th><th>Observações</th></tr>
        {"".join(f'<tr class="critico"><td><b>{r["prompt_id"]}</b></td><td>{r["categoria"]}</td><td style="color:#F44336"><b>{r.get("safety","")}</b></td><td>{r.get("must_not_qual","")}</td><td>{r.get("observacoes","")}</td></tr>' for r in criticos)}
      </table>
    </div>
    '''}

    <!-- Tabela completa -->
    <div class="section">
      <h2>📋 Avaliação completa por prompt</h2>
      <div style="overflow-x:auto">
        <table>
          <tr>
            <th>Prompt</th>
            <th>Pergunta</th>
            <th>Categoria</th>
            <th>Usuário</th>
            <th>Contexto dep.</th>
            <th>MUST</th>
            <th>SHOULD</th>
            <th>MUST NOT</th>
            <th>Correct.</th>
            <th>Safety</th>
            <th>Context</th>
            <th>Bula</th>
            <th>Resposta (preview)</th>
            <th>Observações</th>
          </tr>
          {rows_html}
        </table>
      </div>
    </div>
  </div>

  <div class="footer">
    Dose Certa · TCC 2 · UNISINOS · 2026 · Avaliação do Chatbot Farmacêutico
  </div>

  <script>
    const labels = {json.dumps(cat_labels)};
    const corr   = {json.dumps(cat_corr)};
    const must   = {json.dumps(cat_must)};
    const should = {json.dumps(cat_should)};

    new Chart(document.getElementById('chartCorr'), {{
      type: 'bar',
      data: {{
        labels,
        datasets: [{{
          label: 'Correctness médio',
          data: corr,
          backgroundColor: '#006B5E',
          borderRadius: 6,
        }}]
      }},
      options: {{
        responsive: true,
        scales: {{
          y: {{ min: 0, max: 5, ticks: {{ stepSize: 1 }} }}
        }},
        plugins: {{ legend: {{ display: false }} }}
      }}
    }});

    new Chart(document.getElementById('chartMust'), {{
      type: 'bar',
      data: {{
        labels,
        datasets: [
          {{
            label: 'MUST (%)',
            data: must,
            backgroundColor: '#006B5E',
            borderRadius: 4,
          }},
          {{
            label: 'SHOULD (%)',
            data: should,
            backgroundColor: '#B5CC18',
            borderRadius: 4,
          }}
        ]
      }},
      options: {{
        responsive: true,
        scales: {{
          y: {{ min: 0, max: 100, ticks: {{ callback: v => v + '%' }} }}
        }},
        plugins: {{ legend: {{ display: true, position: 'top' }} }}
      }}
    }});
  </script>
</body>
</html>"""

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Dashboard gerado: {OUTPUT_PATH}")
    print(f"   Abra no navegador: open {OUTPUT_PATH}")


if __name__ == "__main__":
    main()