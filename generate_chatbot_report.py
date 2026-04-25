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
        row["_correctness"] = safe_float(row.get("correctness"))
        row["_safety"]      = safe_float(row.get("safety"))
        row["_context"]     = safe_float(row.get("context_use"))
        row["_must_ratio"]  = must_score_to_ratio(row.get("must_score", ""))
        row["_must_not"]    = safe_int(row.get("must_not_violado"), 0)
        row["_success"]     = row.get("api_success", "") in ("✅", "OK")
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
    must_not_total  = sum(r["_must_not"] for r in avaliados)
    must_ratio_med  = sum(r["_must_ratio"] for r in avaliados if r["_must_ratio"] is not None) / n_aval if avaliados else 0

    # Por categoria
    cat_stats = defaultdict(list)
    for row in avaliados:
        cat_stats[row["categoria"]].append(row)

    # Por Contexto dep.
    peg_sim   = [r for r in avaliados if (r.get("Contexto dep.") or "") in ("Sim")]
    peg_nao   = [r for r in avaliados if (r.get("Contexto dep.") or "") in ("Não", "Nao")]
    corr_peg  = sum(r["_correctness"] for r in peg_sim) / len(peg_sim) if peg_sim else 0
    corr_npeg = sum(r["_correctness"] for r in peg_nao) / len(peg_nao) if peg_nao else 0

    # Casos críticos (safety >= 2 ou MUST NOT violado)
    criticos = [r for r in avaliados if (r["_safety"] or 0) >= 2 or r["_must_not"] == 1]

    # Gera dados para Chart.js
    cat_labels  = [c for c in CATEGORIAS_ORDER if c in cat_stats]
    cat_corr    = [round(sum(r["_correctness"] for r in cat_stats[c]) / len(cat_stats[c]), 2) for c in cat_labels]
    cat_context = [round(sum(r["_context"] for r in cat_stats[c] if r["_context"] is not None) / len(cat_stats[c]), 2) for c in cat_labels]
    cat_must    = [round(sum(r["_must_ratio"] for r in cat_stats[c] if r["_must_ratio"] is not None) / len(cat_stats[c]) * 100, 1) for c in cat_labels]

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

    # Tabela de prompts
    rows_html = ""
    for row in rows:
        pid      = row.get("prompt_id", "")
        cat      = row.get("categoria", "")
        usuario  = row.get("usuario", "")
        peg      = row.get("Contexto dep.", "")
        success  = row.get("api_success", "")
        corr     = row.get("correctness", "")
        saf      = row.get("safety", "")
        ctx      = row.get("context_use", "")
        must_sc  = row.get("must_score", "")
        must_nt  = row.get("must_not_violado", "")
        bula     = row.get("bula_citada", "")
        obs      = row.get("observacoes", "")
        reply    = row.get("reply_preview", "")[:200]

        corr_color = color_correctness(safe_float(corr))
        saf_color  = color_safety(safe_float(saf))
        must_nt_badge = '<span style="color:#F44336;font-weight:bold">⚠️ SIM</span>' if must_nt == "1" else '<span style="color:#4CAF50">NÃO</span>'
        peg_badge  = '<span style="background:#FF9800;color:white;padding:2px 6px;border-radius:4px;font-size:11px">🎯 Sim</span>' if peg in ("Sim") else ""
        fail_badge = '<span style="background:#F44336;color:white;padding:2px 6px;border-radius:4px;font-size:11px">❌ Falha</span>' if "❌" in success else ""

        rows_html += f"""
        <tr>
          <td><b>{pid}</b> {fail_badge}</td>
          <td style="font-size:12px">{cat}</td>
          <td style="font-size:12px">{usuario.replace("EVAL_","")}</td>
          <td>{peg_badge}</td>
          <td style="font-size:11px;color:#555">{must_sc}</td>
          <td>{must_nt_badge}</td>
          <td><span style="background:{corr_color};color:white;padding:2px 8px;border-radius:4px">{corr if corr else "—"}</span></td>
          <td><span style="background:{saf_color};color:white;padding:2px 8px;border-radius:4px">{saf if saf else "—"}</span></td>
          <td style="text-align:center">{ctx if ctx else "—"}</td>
          <td style="text-align:center">{bula if bula else "—"}</td>
          <td style="font-size:11px;color:#666;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{reply}">{reply[:80]}...</td>
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
  </style>
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
        <h3>MUST atendidos por categoria (%)</h3>
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
            <th>Categoria</th>
            <th>Usuário</th>
            <th>Contexto dep.</th>
            <th>MUST</th>
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
        datasets: [{{
          label: 'MUST atendidos (%)',
          data: must,
          backgroundColor: '#B5CC18',
          borderRadius: 6,
        }}]
      }},
      options: {{
        responsive: true,
        scales: {{
          y: {{ min: 0, max: 100, ticks: {{ callback: v => v + '%' }} }}
        }},
        plugins: {{ legend: {{ display: false }} }}
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