#!/usr/bin/env python3
"""
generate_report.py

Gera um relatório HTML visual a partir dos resultados da avaliação.
Inclui: resumo com métricas-chave, gráficos de barras, tabela detalhada por receita,
análise de erros e comparação por método de produção.

USO:
    python3 generate_report.py
    # Abre results/prescriptions/report.html no seu navegador
"""

import json
from pathlib import Path

RESULTS_DIR  = Path("results/prescriptions")
FULL_JSON    = RESULTS_DIR / "results_full.json"
SUMMARY_JSON = RESULTS_DIR / "metrics_summary.json"
REPORT_PATH  = RESULTS_DIR / "report.html"


def pct_bar(value, color="#006B5E"):
    """Gera uma barra de progresso HTML."""
    if value is None:
        return '<span style="color:#999">N/A</span>'
    w = round(float(value) * 100, 1) if float(value) <= 1 else float(value)
    label = f"{w:.1f}%"
    return f'''<div style="display:flex;align-items:center;gap:8px">
        <div style="width:120px;background:#eee;border-radius:4px;height:14px">
          <div style="width:{w}%;background:{color};border-radius:4px;height:14px"></div>
        </div>
        <span style="font-size:12px;font-weight:600">{label}</span>
      </div>'''


def status_badge(ok):
    if ok is True:
        return '<span style="background:#d1fae5;color:#065f46;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600">✅ OK</span>'
    elif ok is False:
        return '<span style="background:#fee2e2;color:#991b1b;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600">❌ Erro</span>'
    return '<span style="background:#f3f4f6;color:#6b7280;padding:2px 8px;border-radius:12px;font-size:11px">—</span>'


def method_label(m):
    labels = {
        "canva_manual": "🎨 Canva",
        "script": "🤖 Script",
        "manuscrita_real": "✍️ Manuscrita",
        "printed_script_font": "🖋️ Cursiva",
    }
    return labels.get(m, m)


def build_report(all_results, summary):
    successful = [r for r in all_results if r.get("api_success")]
    n = len(successful)
    total = len(all_results)
    failed = [r for r in all_results if not r.get("api_success")]

    overall = summary.get("overall", {})
    psr    = overall.get("prescription_success_rate_pct", 0) or 0
    med_f1 = overall.get("med_f1", 0) or 0

    # Dados para os gráficos (Chart.js)
    # 1. PSR por método
    methods_data = summary.get("by_production_method", {})
    method_labels = [method_label(m) for m in methods_data]
    method_psr    = [methods_data[m].get("prescription_success_rate", 0) or 0 for m in methods_data]
    method_f1     = [round((methods_data[m].get("med_f1") or 0) * 100, 1) for m in methods_data]

    # 2. Recall por campo de medicamento
    field_names  = ["name", "dosage", "route", "frequency"]
    field_labels = ["Nome", "Dosagem", "Via", "Frequência"]
    field_values = [round((overall.get(f"{f}_recall") or 0) * 100, 1) for f in field_names]

    # 3. Distribuição de erros
    all_errors = [e for r in successful for e in r.get("errors", [])]
    err_types = {}
    for e in all_errors:
        t = e.get("error_type", "unknown")
        err_types[t] = err_types.get(t, 0) + 1

    err_labels = list(err_types.keys())
    err_values = [err_types[k] for k in err_labels]

    # Tabela de receitas
    rows = ""
    for r in all_results:
        pid    = r["prescription_id"]
        method = method_label(r.get("production_method", ""))
        n_meds = r.get("num_medications", "")
        adv    = "⚠️" if r.get("adversarial") else ""
        ok     = r.get("all_critical_ok", False)

        if not r.get("api_success"):
            rows += f"""<tr style="background:#fef2f2">
              <td><strong>{pid}</strong></td>
              <td>{method}</td><td>{n_meds}</td><td>{adv}</td>
              <td colspan="6" style="color:#dc2626;font-size:12px">❌ {r.get('api_error','')[:80]}</td>
            </tr>"""
            continue

        sf  = r.get("scalar_fields", {})
        med = r.get("medications", {})

        def cell(field):
            info = sf.get(field, {})
            return status_badge(info.get("matched"))

        f1_val = med.get("f1", 0) or 0
        f1_color = "#065f46" if f1_val >= 0.9 else ("#92400e" if f1_val >= 0.7 else "#991b1b")
        bg = "#f0fdf4" if ok else "#fffbeb"

        rows += f"""<tr style="background:{bg}">
          <td><strong>{pid}</strong></td>
          <td>{method}</td>
          <td style="text-align:center">{n_meds}</td>
          <td style="text-align:center">{adv}</td>
          <td>{cell('patient_name')}</td>
          <td>{cell('prescription_date')}</td>
          <td>{cell('doctor_crm')}</td>
          <td><span style="color:{f1_color};font-weight:700">{f1_val:.2f}</span></td>
          <td>{status_badge(ok)}</td>
        </tr>"""

    # Tabela de erros
    error_rows = ""
    for r in successful:
        for e in r.get("errors", []):
            sev_color = "#fee2e2" if e.get("severity") == "major" else "#fef3c7"
            sev_text  = "🔴 Major" if e.get("severity") == "major" else "🟡 Minor"
            error_rows += f"""<tr style="background:{sev_color}">
              <td>{r['prescription_id']}</td>
              <td>{method_label(r.get('production_method',''))}</td>
              <td>{e.get('med_name','—')}</td>
              <td><code>{e.get('field','')}</code></td>
              <td style="color:#065f46">{e.get('expected','')}</td>
              <td style="color:#991b1b">{e.get('got','—')}</td>
              <td>{e.get('error_type','')}</td>
              <td>{sev_text}</td>
            </tr>"""

    if not error_rows:
        error_rows = '<tr><td colspan="8" style="text-align:center;color:#059669;padding:20px">🎉 Nenhum erro encontrado!</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Dose Certa — Avaliação de Prescrições</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #f8fafc;
      color: #1e293b;
      padding: 32px;
    }}
    h1 {{ font-size: 24px; color: #006B5E; margin-bottom: 4px; }}
    h2 {{ font-size: 16px; color: #334155; margin: 28px 0 12px; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; }}
    .subtitle {{ color: #64748b; font-size: 13px; margin-bottom: 28px; }}

    /* Cartões de métricas */
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 32px; }}
    .card {{
      background: white;
      border-radius: 12px;
      padding: 20px;
      box-shadow: 0 1px 4px rgba(0,0,0,.08);
      border-left: 4px solid #006B5E;
    }}
    .card.warn {{ border-left-color: #f59e0b; }}
    .card.danger {{ border-left-color: #ef4444; }}
    .card-label {{ font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 6px; }}
    .card-value {{ font-size: 32px; font-weight: 800; color: #006B5E; }}
    .card.warn .card-value {{ color: #d97706; }}
    .card.danger .card-value {{ color: #dc2626; }}
    .card-sub {{ font-size: 11px; color: #94a3b8; margin-top: 4px; }}

    /* Gráficos */
    .charts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 32px; }}
    .chart-box {{
      background: white;
      border-radius: 12px;
      padding: 20px;
      box-shadow: 0 1px 4px rgba(0,0,0,.08);
    }}
    .chart-title {{ font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 16px; }}

    /* Tabelas */
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th {{ background: #f1f5f9; padding: 10px 12px; text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: .5px; color: #475569; }}
    td {{ padding: 9px 12px; border-bottom: 1px solid #f1f5f9; vertical-align: middle; }}
    tr:hover {{ background: #f8fafc !important; }}
    .table-wrap {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.08); overflow-x: auto; margin-bottom: 24px; }}

    code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 11px; }}
    .failed-banner {{
      background: #fef2f2;
      border: 1px solid #fecaca;
      border-radius: 8px;
      padding: 12px 16px;
      margin-bottom: 20px;
      font-size: 13px;
      color: #991b1b;
    }}
  </style>
</head>
<body>
  <h1>🔬 Dose Certa — Avaliação de Prescrições</h1>
  <p class="subtitle">Dataset v{summary.get('dataset_version','?')} · {total} receitas · gerado automaticamente</p>

  {'<div class="failed-banner">⚠️ ' + str(len(failed)) + ' receita(s) não avaliada(s) por erro de API: ' + ', '.join(r["prescription_id"] for r in failed) + '. Rode novamente com o backend estável.</div>' if failed else ''}

  <!-- CARTÕES -->
  <div class="cards">
    <div class="card {'warn' if psr < 80 else ''}">
      <div class="card-label">Prescription Success Rate</div>
      <div class="card-value">{psr:.1f}%</div>
      <div class="card-sub">Todos os campos críticos corretos</div>
    </div>
    <div class="card {'warn' if med_f1 < 0.85 else ''}">
      <div class="card-label">Medication F1 (médio)</div>
      <div class="card-value">{med_f1:.2f}</div>
      <div class="card-sub">Recall × Precision de medicamentos</div>
    </div>
    <div class="card">
      <div class="card-label">Receitas avaliadas</div>
      <div class="card-value">{n}/{total}</div>
      <div class="card-sub">Com sucesso via API</div>
    </div>
    <div class="card {'danger' if len(all_errors) > 10 else 'warn' if all_errors else ''}">
      <div class="card-label">Total de erros</div>
      <div class="card-value">{len(all_errors)}</div>
      <div class="card-sub">{sum(1 for e in all_errors if e.get('severity')=='major')} major · {sum(1 for e in all_errors if e.get('severity')=='minor')} minor</div>
    </div>
    <div class="card">
      <div class="card-label">Acurácia nome paciente</div>
      <div class="card-value">{overall.get('patient_name_accuracy_pct',0) or 0:.1f}%</div>
    </div>
    <div class="card">
      <div class="card-label">Acurácia data</div>
      <div class="card-value">{overall.get('date_accuracy_pct',0) or 0:.1f}%</div>
    </div>
    <div class="card">
      <div class="card-label">Acurácia CRM</div>
      <div class="card-value">{overall.get('doctor_crm_accuracy_pct',0) or 0:.1f}%</div>
    </div>
  </div>

  <!-- GRÁFICOS -->
  <div class="charts">
    <div class="chart-box">
      <div class="chart-title">📊 PSR e F1 por método de produção</div>
      <canvas id="chartMethod" height="200"></canvas>
    </div>
    <div class="chart-box">
      <div class="chart-title">🔬 Recall por campo de medicamento</div>
      <canvas id="chartFields" height="200"></canvas>
    </div>
    <div class="chart-box">
      <div class="chart-title">⚠️ Distribuição de tipos de erro</div>
      <canvas id="chartErrors" height="200"></canvas>
    </div>
  </div>

  <!-- TABELA POR RECEITA -->
  <h2>📋 Resultados por receita</h2>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>ID</th><th>Método</th><th># Meds</th><th>Adv</th>
          <th>Nome Paciente</th><th>Data</th><th>CRM</th>
          <th>Med F1</th><th>✅ Todos OK</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>

  <!-- TABELA DE ERROS -->
  <h2>🔍 Análise de erros</h2>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Receita</th><th>Método</th><th>Medicamento</th><th>Campo</th>
          <th>Esperado</th><th>Obtido</th><th>Tipo</th><th>Severidade</th>
        </tr>
      </thead>
      <tbody>{error_rows}</tbody>
    </table>
  </div>

  <script>
    const green  = '#006B5E';
    const accent = '#B5CC18';
    const orange = '#f59e0b';
    const red    = '#ef4444';
    const gray   = '#94a3b8';

    // Gráfico 1 — Por método
    new Chart(document.getElementById('chartMethod'), {{
      type: 'bar',
      data: {{
        labels: {json.dumps(method_labels)},
        datasets: [
          {{ label: 'PSR (%)', data: {json.dumps(method_psr)}, backgroundColor: green + 'cc', borderRadius: 4 }},
          {{ label: 'Med F1 × 100', data: {json.dumps(method_f1)}, backgroundColor: accent + 'cc', borderRadius: 4 }},
        ]
      }},
      options: {{
        responsive: true,
        scales: {{ y: {{ min: 0, max: 100 }} }},
        plugins: {{ legend: {{ position: 'bottom' }} }}
      }}
    }});

    // Gráfico 2 — Por campo
    new Chart(document.getElementById('chartFields'), {{
      type: 'bar',
      data: {{
        labels: {json.dumps(field_labels)},
        datasets: [{{
          label: 'Recall (%)',
          data: {json.dumps(field_values)},
          backgroundColor: [green + 'cc', accent + 'cc', orange + 'cc', '#8b5cf6cc'],
          borderRadius: 4,
        }}]
      }},
      options: {{
        responsive: true,
        indexAxis: 'y',
        scales: {{ x: {{ min: 0, max: 100 }} }},
        plugins: {{ legend: {{ display: false }} }}
      }}
    }});

    // Gráfico 3 — Erros
    new Chart(document.getElementById('chartErrors'), {{
      type: 'doughnut',
      data: {{
        labels: {json.dumps(err_labels) if err_labels else '["Sem erros"]'},
        datasets: [{{
          data: {json.dumps(err_values) if err_values else '[1]'},
          backgroundColor: [red + 'cc', orange + 'cc', '#8b5cf6cc', gray + 'cc'],
        }}]
      }},
      options: {{
        responsive: true,
        plugins: {{ legend: {{ position: 'bottom' }} }}
      }}
    }});
  </script>
</body>
</html>"""
    return html


def main():
    if not FULL_JSON.exists():
        print(f"❌ {FULL_JSON} não encontrado.")
        print("   Rode primeiro: python3 evaluate_prescriptions.py")
        return

    if not SUMMARY_JSON.exists():
        print(f"❌ {SUMMARY_JSON} não encontrado.")
        return

    with open(FULL_JSON, encoding="utf-8") as f:
        all_results = json.load(f)

    with open(SUMMARY_JSON, encoding="utf-8") as f:
        summary = json.load(f)

    html = build_report(all_results, summary)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Relatório gerado: {REPORT_PATH.absolute()}")
    print("   Abre o arquivo no navegador (duplo clique ou drag & drop)")


if __name__ == "__main__":
    main()
