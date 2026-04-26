#!/usr/bin/env python3
"""
generate_grupob_report.py

Gera dashboard HTML da avaliação do Grupo B (avaliadores leigos),
lendo o CSV exportado do Google Forms.

USO:
    python3 generate_grupob_report.py

ENTRADA:
    grupo_b_responses.csv   — CSV exportado do Google Forms

SAIDA:
    results/chat/grupob_report.html
"""

import csv
import json
from pathlib import Path
from collections import Counter

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================

CSV_PATH    = Path("grupo_b_responses.csv")
OUTPUT_PATH = Path("results/chat/grupob_report.html")

PROMPTS = [
    "P00A", "P00C", "P01", "P03", "P06", "P08",
    "P11", "P14", "P15", "P16", "P17", "P21", "P23", "P26"
]

PROMPTS_LABELS = {
    "P00A": "Quais remédios estou tomando?",
    "P00C": "Dor de cabeça — qual remédio causou?",
    "P01":  "Tontura após remédio da pressão",
    "P03":  "Palpitações e insônia",
    "P06":  "Posso tomar anti-inflamatório?",
    "P08":  "Remédio da tireoide com café?",
    "P11":  "Esqueci a Losartana — o que faço?",
    "P14":  "Frequência da Dipirona",
    "P15":  "Dieta sem gordura e colesterol",
    "P16":  "Posso fazer exercício?",
    "P17":  "Pressão 180/110 — emergência",
    "P21":  "Grávida e com dor",
    "P23":  "Remédios do pai (cuidador)",
    "P26":  "Pai recusou os remédios",
}

CATEGORIAS = {
    "P00A": "Sistema e Navegação", "P00C": "Sistema e Navegação",
    "P01":  "Efeitos Colaterais",  "P03":  "Efeitos Colaterais",
    "P06":  "Interações",          "P08":  "Interações",
    "P11":  "Dose Esquecida",      "P14":  "Dose Esquecida",
    "P15":  "Estilo de Vida",      "P16":  "Estilo de Vida",
    "P17":  "Segurança Crítica",   "P21":  "Segurança Crítica",
    "P23":  "Cuidador",            "P26":  "Cuidador",
}

# ==============================================================================
# PARSING DO CSV DO GOOGLE FORMS
# ==============================================================================

def parse_google_forms_csv(path: Path) -> list[dict]:
    """
    Lê o CSV do Google Forms e retorna lista de dicts por avaliador,
    com estrutura: {prompt_id: {helpfulness, clarity, deferral}}
    """
    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    avaliadores = []
    # Linha 0 = cabeçalho, linhas 1+ = respostas
    for row in rows[1:]:
        if not any(row):
            continue
        avaliador = {}
        # Cada prompt tem 3 colunas: help (1-3), clarity (1-5), deferral (texto)
        # Colunas 0 = timestamp, depois grupos de 3, última = comentário
        col = 1
        for pid in PROMPTS:
            if col + 2 >= len(row):
                break
            try:
                help_val     = int(row[col].strip()) if row[col].strip() else None
                clarity_val  = int(row[col+1].strip()) if row[col+1].strip() else None
                deferral_raw = row[col+2].strip()
                # Simplifica o texto do deferral
                if "Adequado" in deferral_raw and "Não se aplica" not in deferral_raw and "Desnecessário" not in deferral_raw:
                    deferral = "Adequado"
                elif "Desnecessário" in deferral_raw or "Desnecessario" in deferral_raw:
                    deferral = "Desnecessário"
                elif "Não se aplica" in deferral_raw or "Nao se aplica" in deferral_raw:
                    deferral = "N/A"
                else:
                    deferral = deferral_raw[:20]
            except (ValueError, IndexError):
                help_val, clarity_val, deferral = None, None, ""
            avaliador[pid] = {
                "helpfulness": help_val,
                "clarity":     clarity_val,
                "deferral":    deferral,
            }
            col += 3
        avaliadores.append(avaliador)
    return avaliadores


# ==============================================================================
# CÁLCULO DE MÉTRICAS
# ==============================================================================

def calc_metrics(avaliadores: list[dict]) -> dict:
    n_aval = len(avaliadores)
    results = {}

    for pid in PROMPTS:
        helps    = [a[pid]["helpfulness"] for a in avaliadores if a.get(pid) and a[pid]["helpfulness"]]
        claritys = [a[pid]["clarity"]     for a in avaliadores if a.get(pid) and a[pid]["clarity"]]
        deferrals= [a[pid]["deferral"]    for a in avaliadores if a.get(pid) and a[pid]["deferral"]]

        results[pid] = {
            "help_med":      round(sum(helps) / len(helps), 2) if helps else None,
            "clarity_med":   round(sum(claritys) / len(claritys), 2) if claritys else None,
            "deferral_count":dict(Counter(deferrals)),
            "n":             len(helps),
        }

    # Médias gerais
    all_helps    = [v for pid in PROMPTS for v in
                    [a[pid]["helpfulness"] for a in avaliadores if a.get(pid) and a[pid]["helpfulness"]]]
    all_claritys = [v for pid in PROMPTS for v in
                    [a[pid]["clarity"]     for a in avaliadores if a.get(pid) and a[pid]["clarity"]]]
    all_deferrals= [a[pid]["deferral"] for pid in PROMPTS for a in avaliadores
                    if a.get(pid) and a[pid]["deferral"]]

    def simple_kappa(r1, r2):
        n = len(r1)
        if n == 0: return None
        agree = sum(a == b for a, b in zip(r1, r2))
        p_o = agree / n
        cats = list(set(r1 + r2))
        p_e = sum((r1.count(c)/n) * (r2.count(c)/n) for c in cats)
        if p_e >= 1.0: return 1.0
        return round((p_o - p_e) / (1 - p_e), 3)

    def weighted_kappa(r1, r2, min_val, max_val):
        n = len(r1)
        if n == 0: return None
        cats = list(range(min_val, max_val + 1))
        k = len(cats)
        conf = [[0]*k for _ in range(k)]
        for a, b in zip(r1, r2):
            i = cats.index(a)
            j = cats.index(b)
            conf[i][j] += 1
        w = [[(i-j)**2 / (k-1)**2 for j in range(k)] for i in range(k)]
        row_s = [sum(conf[i]) / n for i in range(k)]
        col_s = [sum(conf[i][j] for i in range(k)) / n for j in range(k)]
        p_o = sum(w[i][j] * conf[i][j] / n for i in range(k) for j in range(k))
        p_e = sum(w[i][j] * row_s[i] * col_s[j] for i in range(k) for j in range(k))
        if p_e >= 1.0: return 1.0
        return round(1 - (p_o / p_e), 3) if p_e > 0 else 1.0

    # Kappa (só calculável com 2+ avaliadores)
    kappa_help, kappa_clarity, kappa_deferral = None, None, None
    pct_concordancia_help = pct_concordancia_clarity = pct_concordancia_deferral = None

    if n_aval >= 2:
        r1_help     = [avaliadores[0][pid]["helpfulness"] for pid in PROMPTS if avaliadores[0].get(pid)]
        r2_help     = [avaliadores[1][pid]["helpfulness"] for pid in PROMPTS if avaliadores[1].get(pid)]
        r1_clarity  = [avaliadores[0][pid]["clarity"]     for pid in PROMPTS if avaliadores[0].get(pid)]
        r2_clarity  = [avaliadores[1][pid]["clarity"]     for pid in PROMPTS if avaliadores[1].get(pid)]
        r1_deferral = [avaliadores[0][pid]["deferral"]    for pid in PROMPTS if avaliadores[0].get(pid)]
        r2_deferral = [avaliadores[1][pid]["deferral"]    for pid in PROMPTS if avaliadores[1].get(pid)]

        n = len(PROMPTS)
        pct_concordancia_help     = round(sum(a==b for a,b in zip(r1_help, r2_help)) / n * 100, 1)
        pct_concordancia_clarity  = round(sum(a==b for a,b in zip(r1_clarity, r2_clarity)) / n * 100, 1)
        pct_concordancia_deferral = round(sum(a==b for a,b in zip(r1_deferral, r2_deferral)) / n * 100, 1)

        kappa_help     = simple_kappa(r1_help, r2_help)
        kappa_clarity  = weighted_kappa(r1_clarity, r2_clarity, 1, 5)
        kappa_deferral = simple_kappa(r1_deferral, r2_deferral)

    def_counter = Counter(all_deferrals)
    total_def = sum(def_counter.values())

    return {
        "per_prompt":    results,
        "help_med_geral":    round(sum(all_helps) / len(all_helps), 2) if all_helps else 0,
        "clarity_med_geral": round(sum(all_claritys) / len(all_claritys), 2) if all_claritys else 0,
        "deferral_adequado_pct": round(def_counter.get("Adequado", 0) / total_def * 100, 1) if total_def else 0,
        "deferral_desnecessario_pct": round(def_counter.get("Desnecessário", 0) / total_def * 100, 1) if total_def else 0,
        "deferral_na_pct": round(def_counter.get("N/A", 0) / total_def * 100, 1) if total_def else 0,
        "kappa_help":     kappa_help,
        "kappa_clarity":  kappa_clarity,
        "kappa_deferral": kappa_deferral,
        "pct_help":     pct_concordancia_help,
        "pct_clarity":  pct_concordancia_clarity,
        "pct_deferral": pct_concordancia_deferral,
        "n_avaliadores": n_aval,
        "n_prompts": len(PROMPTS),
    }


# ==============================================================================
# GERAÇÃO DO HTML
# ==============================================================================

def gerar_html(m: dict) -> str:

    def kappa_badge(k, pct):
        if k is None:
            return f'<span style="color:#888">—</span>'
        if k >= 0.80:
            color, label = "#4CAF50", "Quase perfeito"
        elif k >= 0.60:
            color, label = "#8BC34A", "Substancial"
        elif k >= 0.40:
            color, label = "#FFC107", "Moderado"
        else:
            color, label = "#FF9800", f"Paradoxo κ — concordância direta: {pct}%"
        return f'<span style="color:{color};font-weight:bold">{k}</span> <span style="font-size:12px;color:#888">({label})</span>'

    def help_color(v):
        if v is None: return "#ccc"
        if v >= 2.8: return "#4CAF50"
        if v >= 2.0: return "#FFC107"
        return "#F44336"

    def clarity_color(v):
        if v is None: return "#ccc"
        if v >= 4.5: return "#4CAF50"
        if v >= 3.5: return "#FFC107"
        return "#F44336"

    # Dados para Chart.js por categoria
    cats = ["Sistema e Navegação","Efeitos Colaterais","Interações",
            "Dose Esquecida","Estilo de Vida","Segurança Crítica","Cuidador"]

    cat_helps = []
    cat_claritys = []
    for cat in cats:
        pids = [p for p in PROMPTS if CATEGORIAS.get(p) == cat]
        h_vals = [m["per_prompt"][p]["help_med"] for p in pids if m["per_prompt"][p]["help_med"]]
        c_vals = [m["per_prompt"][p]["clarity_med"] for p in pids if m["per_prompt"][p]["clarity_med"]]
        cat_helps.append(round(sum(h_vals)/len(h_vals), 2) if h_vals else 0)
        cat_claritys.append(round(sum(c_vals)/len(c_vals), 2) if c_vals else 0)

    # Tabela de prompts
    rows_html = ""
    for pid in PROMPTS:
        pp = m["per_prompt"][pid]
        h  = pp["help_med"]
        c  = pp["clarity_med"]
        d  = pp["deferral_count"]
        adequado = d.get("Adequado", 0)
        desnec   = d.get("Desnecessário", 0)
        na       = d.get("N/A", 0)

        rows_html += f"""
        <tr>
          <td><b>{pid}</b></td>
          <td style="font-size:12px;color:#555">{PROMPTS_LABELS.get(pid,'')}</td>
          <td style="font-size:12px">{CATEGORIAS.get(pid,'')}</td>
          <td><span style="background:{help_color(h)};color:white;padding:2px 8px;border-radius:4px">{h if h else '—'}</span></td>
          <td><span style="background:{clarity_color(c)};color:white;padding:2px 8px;border-radius:4px">{c if c else '—'}</span></td>
          <td style="font-size:12px">
            {'✅ ' + str(adequado) + ' Adequado' if adequado else ''}
            {'  ⚠️ ' + str(desnec) + ' Desnecessário' if desnec else ''}
            {'  — ' + str(na) + ' N/A' if na else ''}
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Dose Certa — Avaliação Grupo B</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; }}
    .header {{ background: #006B5E; color: white; padding: 24px 32px; }}
    .header h1 {{ font-size: 24px; margin-bottom: 4px; }}
    .header p {{ opacity: 0.8; font-size: 14px; }}
    .container {{ max-width: 1300px; margin: 0 auto; padding: 24px 16px; }}
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
    .kappa-table td, .kappa-table th {{ padding: 12px 16px; }}
    .footer {{ text-align: center; padding: 24px; color: #888; font-size: 12px; }}
    .nota {{ background: #fff8e1; border-left: 4px solid #FFC107; padding: 12px 16px; border-radius: 4px; font-size: 13px; color: #555; margin-bottom: 16px; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>👥 Dose Certa — Avaliação Grupo B (Avaliadores Leigos)</h1>
    <p>Dimensões experienciais: Helpfulness, Clarity e Appropriate Deferral · {m['n_avaliadores']} avaliadores · {m['n_prompts']} prompts</p>
  </div>

  <div class="container">

    <!-- Cards -->
    <div class="cards">
      <div class="card">
        <div class="value">{m['n_avaliadores']}</div>
        <div class="label">Avaliadores (Grupo B)</div>
      </div>
      <div class="card">
        <div class="value">{m['n_prompts']}</div>
        <div class="label">Prompts avaliados</div>
      </div>
      <div class="card">
        <div class="value">{m['help_med_geral']}<span style="font-size:18px">/3</span></div>
        <div class="label">Helpfulness médio</div>
      </div>
      <div class="card">
        <div class="value">{m['clarity_med_geral']}<span style="font-size:18px">/5</span></div>
        <div class="label">Clarity médio</div>
      </div>
      <div class="card">
        <div class="value" style="color:#4CAF50">{m['deferral_adequado_pct']}%</div>
        <div class="label">Deferral Adequado</div>
      </div>
      <div class="card">
        <div class="value" style="color:#FFC107">{m['deferral_na_pct']}%</div>
        <div class="label">Deferral N/A</div>
      </div>
      <div class="card">
        <div class="value" style="color:#F44336">{m['deferral_desnecessario_pct']}%</div>
        <div class="label">Deferral Desnecessário</div>
      </div>
    </div>

    <!-- Gráficos -->
    <div class="charts">
      <div class="chart-box">
        <h3>Helpfulness médio por categoria (1–3)</h3>
        <canvas id="chartHelp"></canvas>
      </div>
      <div class="chart-box">
        <h3>Clarity médio por categoria (1–5)</h3>
        <canvas id="chartClarity"></canvas>
      </div>
    </div>

    <!-- Cohen's κ -->
    <div class="section">
      <h2>📐 Concordância entre Avaliadores (Cohen's κ)</h2>
      <div class="nota">
        ⚠️ O κ de Cohen apresenta o <b>Paradoxo do κ</b> quando um avaliador atribui a mesma nota a todos os prompts
        (distribuição muito concentrada). Nesse caso, reporta-se a <b>proporção de concordância direta</b>
        como medida complementar (Feinstein &amp; Cicchetti, 1990).
      </div>
      <table class="kappa-table">
        <tr>
          <th>Dimensão</th>
          <th>Tipo de κ</th>
          <th>Valor κ</th>
          <th>Concordância direta</th>
          <th>Interpretação</th>
        </tr>
        <tr>
          <td><b>Helpfulness</b></td>
          <td>κ simples</td>
          <td>{kappa_badge(m['kappa_help'], m['pct_help'])}</td>
          <td>{m['pct_help']}%</td>
          <td style="font-size:12px;color:#555">Concordância perfeita — ambos deram nota máxima</td>
        </tr>
        <tr>
          <td><b>Clarity</b></td>
          <td>κ ponderado quadrático</td>
          <td>{kappa_badge(m['kappa_clarity'], m['pct_clarity'])}</td>
          <td>{m['pct_clarity']}%</td>
          <td style="font-size:12px;color:#555">1 discordância em 14 prompts (P14: 4 vs 5)</td>
        </tr>
        <tr>
          <td><b>Deferral</b></td>
          <td>κ simples</td>
          <td>{kappa_badge(m['kappa_deferral'], m['pct_deferral'])}</td>
          <td>{m['pct_deferral']}%</td>
          <td style="font-size:12px;color:#555">5 divergências: avaliador 1 marcou Adequado onde avaliador 2 marcou N/A</td>
        </tr>
      </table>
    </div>

    <!-- Tabela completa -->
    <div class="section">
      <h2>📋 Avaliação por prompt</h2>
      <div style="overflow-x:auto">
        <table>
          <tr>
            <th>Prompt</th>
            <th>Pergunta</th>
            <th>Categoria</th>
            <th>Helpfulness (méd)</th>
            <th>Clarity (méd)</th>
            <th>Deferral</th>
          </tr>
          {rows_html}
        </table>
      </div>
    </div>

  </div>

  <div class="footer">
    Dose Certa · TCC 2 · UNISINOS · 2026 · Avaliação Grupo B — Avaliadores Leigos
  </div>

  <script>
    const cats = {json.dumps(cats)};
    const helps = {json.dumps(cat_helps)};
    const claritys = {json.dumps(cat_claritys)};

    new Chart(document.getElementById('chartHelp'), {{
      type: 'bar',
      data: {{
        labels: cats,
        datasets: [{{ label: 'Helpfulness', data: helps,
          backgroundColor: '#006B5E', borderRadius: 6 }}]
      }},
      options: {{
        responsive: true,
        scales: {{ y: {{ min: 0, max: 3, ticks: {{ stepSize: 1 }} }} }},
        plugins: {{ legend: {{ display: false }} }}
      }}
    }});

    new Chart(document.getElementById('chartClarity'), {{
      type: 'bar',
      data: {{
        labels: cats,
        datasets: [{{ label: 'Clarity', data: claritys,
          backgroundColor: '#B5CC18', borderRadius: 6 }}]
      }},
      options: {{
        responsive: true,
        scales: {{ y: {{ min: 0, max: 5, ticks: {{ stepSize: 1 }} }} }},
        plugins: {{ legend: {{ display: false }} }}
      }}
    }});
  </script>
</body>
</html>"""


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    if not CSV_PATH.exists():
        print(f"Erro: {CSV_PATH} nao encontrado.")
        print("Exporte o Google Forms como CSV e salve em data/grupo_b_responses.csv")
        return

    print("Lendo respostas do Grupo B...")
    avaliadores = parse_google_forms_csv(CSV_PATH)
    print(f"  {len(avaliadores)} avaliadores encontrados")

    print("Calculando metricas...")
    m = calc_metrics(avaliadores)

    print("Gerando dashboard HTML...")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    html = gerar_html(m)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nDashboard gerado: {OUTPUT_PATH}")
    print(f"  Helpfulness medio: {m['help_med_geral']}/3")
    print(f"  Clarity medio:     {m['clarity_med_geral']}/5")
    print(f"  Deferral Adequado: {m['deferral_adequado_pct']}%")
    if m['kappa_help'] is not None:
        print(f"  kappa Helpfulness: {m['kappa_help']}")
        print(f"  kappa Clarity:     {m['kappa_clarity']}")
        print(f"  kappa Deferral:    {m['kappa_deferral']}")
    print(f"\nAbra no navegador: open {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
