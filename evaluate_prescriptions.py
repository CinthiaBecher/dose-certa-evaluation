#!/usr/bin/env python3
"""
evaluate_prescriptions.py

Avalia a acurácia do endpoint POST /api/prescriptions/interpret do sistema Dose Certa.
Para cada uma das 30 receitas do dataset, envia a imagem ao backend e compara
o JSON retornado com o ground truth documentado em ground_truth_dataset.json.

Métricas calculadas (inspiradas em RxLens, Ravi et al. 2024):
  - Field Recall / Precision / F1 por campo
  - Exact Match (CRM, datas) e Fuzzy Match (nomes, similaridade >= 0.85)
  - Prescription Success Rate (% receitas com TODOS os campos críticos corretos)
  - Taxonomia de erros (Asgari et al. 2025):
      tipo: hallucination / omission / wrong_extraction / fabrication
      severidade: major / minor

USO:
    # 1. Subir o backend Dose Certa
    uvicorn main:app --reload   (em outra aba do terminal, dentro do repo dose-certa)

    # 2. Rodar este script
    cd dose-certa-evaluation
    python3 evaluate_prescriptions.py

SAÍDAS:
    results/results_prescriptions.csv   — métricas por receita
    results/metrics_summary.json        — métricas agregadas
    results/error_analysis.csv          — erros classificados por tipo e severidade
"""

import csv
import json
import re
import sys
import time
from pathlib import Path

import argparse
import requests
from difflib import SequenceMatcher

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================

BACKEND_URL  = "http://localhost:8000"
ENDPOINT     = f"{BACKEND_URL}/api/prescriptions/interpret"
DATASET_PATH = Path("ground_truth_dataset.json")
IMAGES_DIR   = Path("images")
RESULTS_DIR  = Path("results/prescriptions")

# Campos críticos — erro aqui é sempre MAJOR (impacta conduta clínica)
CRITICAL_FIELDS = {"patient_name", "prescription_date", "doctor_crm"}

# Campos de medicamento críticos
CRITICAL_MED_FIELDS = {"name", "dosage", "route", "frequency", "instructions", "duration_days"}

# Limiar de similaridade para Fuzzy Match
FUZZY_THRESHOLD = 0.85

# Delay entre requisições (segundos)
REQUEST_DELAY = 1.0  # billing ativo, 1000 RPM

# Retry em caso de 500 — exponential backoff: 1s, 2s, 4s, 8s, ...
MAX_RETRIES = 10


# ==============================================================================
# UTILS DE COMPARAÇÃO
# ==============================================================================

def normalize(text) -> str:
    """Normaliza string para comparação: lowercase, sem espaços extras,
    e colapsa espaço entre número e unidade (ex: '50 mg' → '50mg')."""
    if text is None:
        return ""
    s = re.sub(r"\s+", " ", str(text).lower().strip())
    s = re.sub(r"(\d)\s+([a-zA-Zµμ])", r"\1\2", s)
    return s


def exact_match(expected, got) -> bool:
    return normalize(expected) == normalize(got)


def fuzzy_match(expected, got) -> float:
    """Retorna similaridade entre 0.0 e 1.0."""
    a = normalize(expected)
    b = normalize(got)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def is_match(expected, got, use_fuzzy: bool = False) -> bool:
    if use_fuzzy:
        return fuzzy_match(expected, got) >= FUZZY_THRESHOLD
    return exact_match(expected, got)


def normalize_date(date_str) -> str:
    """
    Normaliza datas para comparação. Formato alvo: DD/MM/YYYY.
    Aceita: DD/MM/YYYY (padrão), YYYY-MM-DD (fallback API), DD/MM/YY (ano curto)
    """
    if not date_str:
        return ""
    s = str(date_str).strip()

    # Já está em DD/MM/YYYY — padrão esperado
    if re.match(r"^\d{2}/\d{2}/\d{4}$", s):
        return s

    # API retornou YYYY-MM-DD — converte para DD/MM/YYYY
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"

    # Ano com 2 dígitos DD/MM/YY → DD/MM/20YY
    m = re.match(r"^(\d{2})/(\d{2})/(\d{2})$", s)
    if m:
        return f"{m.group(1)}/{m.group(2)}/20{m.group(3)}"

    return normalize(s)


# ==============================================================================
# AVALIAÇÃO DE CAMPOS ESCALARES
# ==============================================================================

def classify_error(expected, got, matched: bool):
    if matched:
        return None
    if expected is None and got is not None:
        return "hallucination"
    if expected is not None and got is None:
        return "omission"
    if expected is not None and got is not None:
        return "wrong_extraction"
    return None


def evaluate_scalar_fields(gt: dict, pred: dict) -> dict:
    fields = ["patient_name", "prescription_date", "doctor_name", "doctor_crm"]
    results = {}

    for field in fields:
        expected = gt.get(field)
        got      = pred.get(field)

        if field == "prescription_date":
            exp_norm = normalize_date(expected)
            got_norm = normalize_date(got)
            matched  = exp_norm == got_norm
            sim      = 1.0 if matched else 0.0
        elif field in ("patient_name", "doctor_name"):
            sim     = fuzzy_match(expected, got)
            matched = sim >= FUZZY_THRESHOLD
        else:
            matched = exact_match(expected, got)
            sim     = 1.0 if matched else fuzzy_match(expected, got)

        is_critical = field in CRITICAL_FIELDS
        results[field] = {
            "expected":   expected,
            "got":        got,
            "matched":    matched,
            "similarity": round(sim, 3),
            "critical":   is_critical,
            "error_type": classify_error(expected, got, matched),
            "severity":   "major" if (not matched and is_critical) else ("minor" if not matched else None),
        }
    return results


# ==============================================================================
# AVALIAÇÃO DE MEDICAMENTOS
# ==============================================================================

def match_medications(gt_meds: list, pred_meds: list) -> dict:
    matched_pairs  = []
    unmatched_gt   = list(gt_meds)
    unmatched_pred = list(pred_meds)
    errors         = []

    for gt_med in gt_meds:
        best_sim   = 0.0
        best_match = None
        for pred_med in unmatched_pred:
            sim = fuzzy_match(gt_med.get("name"), pred_med.get("name"))
            if sim > best_sim:
                best_sim   = sim
                best_match = pred_med

        if best_match and best_sim >= FUZZY_THRESHOLD:
            matched_pairs.append((gt_med, best_match))
            unmatched_gt.remove(gt_med)
            unmatched_pred.remove(best_match)

    for gt_med in unmatched_gt:
        errors.append({
            "med_name":   gt_med.get("name"),
            "field":      "name",
            "expected":   gt_med.get("name"),
            "got":        None,
            "error_type": "omission",
            "severity":   "major",
        })

    for pred_med in unmatched_pred:
        errors.append({
            "med_name":   pred_med.get("name"),
            "field":      "name",
            "expected":   None,
            "got":        pred_med.get("name"),
            "error_type": "hallucination",
            "severity":   "major",
        })

    field_hits   = {f: 0 for f in CRITICAL_MED_FIELDS}
    field_totals = {f: 0 for f in CRITICAL_MED_FIELDS}

    for gt_med, pred_med in matched_pairs:
        for field in CRITICAL_MED_FIELDS:
            expected = gt_med.get(field)
            got      = pred_med.get(field)
            if field == "duration_days":
                # None==None é match; assimetria é mismatch
                field_totals[field] += 1
                if expected is None and got is None:
                    matched = True
                elif expected is None or got is None:
                    matched = False
                else:
                    matched = is_match(str(expected), str(got))
            else:
                if expected is None:
                    continue
                field_totals[field] += 1
                use_fuzzy = field in ("name", "instructions")
                matched   = is_match(expected, got, use_fuzzy=use_fuzzy)
            if matched:
                field_hits[field] += 1
            else:
                errors.append({
                    "med_name":   gt_med.get("name"),
                    "field":      field,
                    "expected":   expected,
                    "got":        got,
                    "error_type": classify_error(expected, got, matched),
                    "severity":   (
                        "minor" if field == "instructions"
                        else "minor" if (field == "route" and got is None)
                        else "major"
                    ),
                })

    field_recall = {}
    for f in CRITICAL_MED_FIELDS:
        total = field_totals[f]
        field_recall[f] = round(field_hits[f] / total, 3) if total > 0 else None

    n_gt      = len(gt_meds)
    n_pred    = len(pred_meds)
    n_matched = len(matched_pairs)

    recall    = round(n_matched / n_gt,   3) if n_gt   > 0 else 0.0
    precision = round(n_matched / n_pred, 3) if n_pred > 0 else 0.0
    f1 = round(
        2 * precision * recall / (precision + recall), 3
    ) if (precision + recall) > 0 else 0.0

    return {
        "recall":       recall,
        "precision":    precision,
        "f1":           f1,
        "field_recall": field_recall,
        "n_gt":         n_gt,
        "n_pred":       n_pred,
        "n_matched":    n_matched,
        "errors":       errors,
    }


# ==============================================================================
# CHAMADA AO BACKEND (COM RETRY)
# ==============================================================================

def call_backend(image_path: Path, pid: str) -> tuple:
    """
    Chama o endpoint do backend com retry e exponential backoff em caso de 500.
    Retorna (pred_dict, error_str).
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(image_path, "rb") as f:
                response = requests.post(
                    ENDPOINT,
                    files={"file": (f"{pid}.png", f, "image/png")},
                    timeout=60,
                )

            if response.status_code == 200:
                return response.json(), None

            elif response.status_code == 500:
                if attempt < MAX_RETRIES:
                    wait = 2 ** (attempt - 1)  # 1s, 2s, 4s, 8s, ...
                    print(f"\n    ⏳ 500 — backoff {wait}s (tentativa {attempt}/{MAX_RETRIES})", end="")
                    time.sleep(wait)
                    continue
                else:
                    try:
                        detail = response.json().get("detail", response.text[:200])
                    except Exception:
                        detail = response.text[:200]
                    return None, f"500 após {MAX_RETRIES} tentativas: {detail}"

            else:
                return None, f"HTTP {response.status_code}: {response.text[:200]}"

        except requests.exceptions.ConnectionError:
            return None, "Backend não está rodando em localhost:8000"
        except requests.exceptions.Timeout:
            return None, "Timeout (>60s)"
        except Exception as e:
            return None, str(e)

    return None, "Falhou após todos os retries"


# ==============================================================================
# AVALIAÇÃO DE UMA RECEITA
# ==============================================================================

def evaluate_prescription(prescription: dict) -> dict:
    pid        = prescription["prescription_id"]
    gt         = prescription["ground_truth"]
    image_path = IMAGES_DIR / f"{pid}.png"

    result = {
        "prescription_id":   pid,
        "production_method": prescription.get("production_method"),
        "num_medications":   prescription.get("num_medications"),
        "complexity":        prescription.get("complexity"),
        "adversarial":       prescription.get("adversarial_notes") is not None,
        "api_success":       False,
        "api_error":         None,
        "scalar_fields":     {},
        "medications":       {},
        "all_critical_ok":   False,
        "errors":            [],
    }

    if not image_path.exists():
        result["api_error"] = f"Imagem não encontrada: {image_path}"
        print(f"  ⚠️  {pid}: imagem não encontrada")
        return result

    pred, error = call_backend(image_path, pid)

    if error:
        result["api_error"] = error
        return result

    result["api_success"] = True

    scalar = evaluate_scalar_fields(gt, pred)
    result["scalar_fields"] = scalar

    med_eval = match_medications(
        gt.get("medications", []),
        pred.get("medications", []),
    )
    result["medications"] = med_eval
    result["errors"]      = list(med_eval["errors"])

    for field, info in scalar.items():
        if info["error_type"]:
            result["errors"].append({
                "med_name":   None,
                "field":      field,
                "expected":   info["expected"],
                "got":        info["got"],
                "error_type": info["error_type"],
                "severity":   info["severity"],
            })

    scalar_ok = all(scalar[f]["matched"] for f in CRITICAL_FIELDS if f in scalar)
    meds_ok   = med_eval["recall"] == 1.0 and med_eval["precision"] == 1.0
    # Todos os campos críticos de medicamento com recall 1.0 (instructions é minor, não entra)
    fr = med_eval.get("field_recall", {})
    no_major_route_error = not any(
        e["field"] == "route" and e.get("severity") == "major"
        for e in med_eval["errors"]
    )
    med_fields_ok = all(
        fr.get(f) == 1.0
        for f in ("name", "dosage", "frequency", "duration_days")
        if fr.get(f) is not None
    ) and no_major_route_error
    result["all_critical_ok"] = scalar_ok and meds_ok and med_fields_ok

    return result


# ==============================================================================
# SALVAR RESULTADOS
# ==============================================================================

def save_results(all_results: list):
    RESULTS_DIR.mkdir(exist_ok=True)

    # CSV por receita
    csv_path = RESULTS_DIR / "results_prescriptions.csv"
    fieldnames = [
        "prescription_id", "production_method", "num_medications",
        "complexity", "adversarial", "api_success", "api_error",
        "patient_name_ok", "prescription_date_ok", "doctor_name_ok", "doctor_crm_ok",
        "med_recall", "med_precision", "med_f1",
        "name_recall", "dosage_recall", "route_recall", "frequency_recall",
        "instructions_recall", "duration_days_recall",
        "all_critical_ok",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in all_results:
            sf  = r.get("scalar_fields", {})
            med = r.get("medications", {})
            fr  = med.get("field_recall", {})
            writer.writerow({
                "prescription_id":      r["prescription_id"],
                "production_method":    r["production_method"],
                "num_medications":      r["num_medications"],
                "complexity":           r["complexity"],
                "adversarial":          r["adversarial"],
                "api_success":          r["api_success"],
                "api_error":            r.get("api_error", ""),
                "patient_name_ok":      sf.get("patient_name",        {}).get("matched", ""),
                "prescription_date_ok": sf.get("prescription_date",   {}).get("matched", ""),
                "doctor_name_ok":       sf.get("doctor_name",         {}).get("matched", ""),
                "doctor_crm_ok":        sf.get("doctor_crm",          {}).get("matched", ""),
                "med_recall":           med.get("recall",    ""),
                "med_precision":        med.get("precision", ""),
                "med_f1":               med.get("f1",        ""),
                "name_recall":          fr.get("name",          ""),
                "dosage_recall":        fr.get("dosage",        ""),
                "route_recall":         fr.get("route",         ""),
                "frequency_recall":     fr.get("frequency",     ""),
                "instructions_recall":  fr.get("instructions",  ""),
                "duration_days_recall": fr.get("duration_days", ""),
                "all_critical_ok":      r["all_critical_ok"],
            })

    # Métricas agregadas
    successful = [r for r in all_results if r["api_success"]]
    n = len(successful)

    def avg(values):
        vals = [v for v in values if v is not None and v != ""]
        return round(sum(vals) / len(vals), 3) if vals else None

    def pct(values):
        vals = [v for v in values if isinstance(v, bool)]
        return round(sum(vals) / len(vals) * 100, 1) if vals else None

    methods = {}
    for method in ["canva_manual", "script", "manuscrita_real", "printed_script_font"]:
        group = [r for r in successful if r.get("production_method") == method]
        if group:
            methods[method] = {
                "n": len(group),
                "prescription_success_rate": pct([r["all_critical_ok"] for r in group]),
                "med_recall":    avg([r["medications"].get("recall")    for r in group]),
                "med_precision": avg([r["medications"].get("precision") for r in group]),
                "med_f1":        avg([r["medications"].get("f1")        for r in group]),
            }

    summary = {
        "dataset_version": "2.1",
        "total_prescriptions": len(all_results),
        "api_successful": n,
        "api_failed": len(all_results) - n,
        "overall": {
            "prescription_success_rate_pct": pct([r["all_critical_ok"] for r in successful]),
            "med_recall":        avg([r["medications"].get("recall")    for r in successful]),
            "med_precision":     avg([r["medications"].get("precision") for r in successful]),
            "med_f1":            avg([r["medications"].get("f1")        for r in successful]),
            "patient_name_accuracy_pct":  pct([r["scalar_fields"].get("patient_name",       {}).get("matched") for r in successful]),
            "date_accuracy_pct":          pct([r["scalar_fields"].get("prescription_date",  {}).get("matched") for r in successful]),
            "doctor_crm_accuracy_pct":    pct([r["scalar_fields"].get("doctor_crm",         {}).get("matched") for r in successful]),
            "name_recall":      avg([r["medications"].get("field_recall", {}).get("name")      for r in successful]),
            "dosage_recall":    avg([r["medications"].get("field_recall", {}).get("dosage")    for r in successful]),
            "route_recall":          avg([r["medications"].get("field_recall", {}).get("route")          for r in successful]),
            "frequency_recall":      avg([r["medications"].get("field_recall", {}).get("frequency")      for r in successful]),
            "instructions_recall":   avg([r["medications"].get("field_recall", {}).get("instructions")   for r in successful]),
            "duration_days_recall":  avg([r["medications"].get("field_recall", {}).get("duration_days")  for r in successful]),
        },
        "by_production_method": methods,
    }

    metrics_path = RESULTS_DIR / "metrics_summary.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # Erros detalhados
    error_path = RESULTS_DIR / "error_analysis.csv"
    error_fields = [
        "prescription_id", "production_method", "complexity", "adversarial",
        "med_name", "field", "expected", "got", "error_type", "severity",
    ]
    with open(error_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=error_fields)
        writer.writeheader()
        for r in all_results:
            for err in r.get("errors", []):
                writer.writerow({
                    "prescription_id":  r["prescription_id"],
                    "production_method":r["production_method"],
                    "complexity":       r["complexity"],
                    "adversarial":      r["adversarial"],
                    "med_name":         err.get("med_name", ""),
                    "field":            err.get("field", ""),
                    "expected":         err.get("expected", ""),
                    "got":              err.get("got", ""),
                    "error_type":       err.get("error_type", ""),
                    "severity":         err.get("severity", ""),
                })

    # Salvar JSON completo para o relatório HTML
    full_path = RESULTS_DIR / "results_full.json"
    with open(full_path, "w", encoding="utf-8") as f:
        # Serializar com tratamento de tipos não-serializáveis
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n💾 Resultados salvos em results/:")
    print(f"   📄 results_prescriptions.csv")
    print(f"   📊 metrics_summary.json")
    print(f"   🔍 error_analysis.csv")
    print(f"   📦 results_full.json  (para o relatório HTML)")


def print_summary(all_results: list):
    successful = [r for r in all_results if r["api_success"]]
    n = len(successful)
    if n == 0:
        print("\n⚠️  Nenhuma receita avaliada com sucesso.")
        return

    psr    = sum(r["all_critical_ok"] for r in successful) / n * 100
    med_f1 = sum(r["medications"].get("f1", 0) or 0 for r in successful) / n

    print("\n" + "═" * 55)
    print("📊 RESULTADOS — Avaliação de Prescrições")
    print("═" * 55)
    print(f"  Receitas avaliadas:         {n}/{len(all_results)}")
    if len(all_results) > n:
        failed = [r["prescription_id"] for r in all_results if not r["api_success"]]
        print(f"  Falhas de API:              {', '.join(failed)}")
    print(f"  Prescription Success Rate:  {psr:.1f}%")
    print(f"  Medication F1 (médio):      {med_f1:.3f}")

    print("\n  Por campo escalar:")
    for field in ["patient_name", "prescription_date", "doctor_name", "doctor_crm"]:
        hits = sum(1 for r in successful if r["scalar_fields"].get(field, {}).get("matched"))
        print(f"    {field:<22} {hits}/{n} ({hits/n*100:.1f}%)")

    print("\n  Por campo de medicamento (recall médio):")
    for field in ["name", "dosage", "route", "frequency", "instructions", "duration_days"]:
        vals = [
            r["medications"].get("field_recall", {}).get(field)
            for r in successful
            if r["medications"].get("field_recall", {}).get(field) is not None
        ]
        if vals:
            print(f"    {field:<22} {sum(vals)/len(vals):.3f}")

    print("\n  Por método de produção:")
    for method in ["canva_manual", "script", "manuscrita_real", "printed_script_font"]:
        group = [r for r in successful if r.get("production_method") == method]
        if group:
            psr_g = sum(r["all_critical_ok"] for r in group) / len(group) * 100
            print(f"    {method:<28} PSR {psr_g:.1f}% (n={len(group)})")

    total_errors = sum(len(r.get("errors", [])) for r in successful)
    major = sum(1 for r in successful for e in r.get("errors", []) if e.get("severity") == "major")
    print(f"\n  Total de erros:             {total_errors}")
    print(f"    Major (impacto clínico):  {major}")
    print(f"    Minor (cosmético):        {total_errors - major}")
    print("═" * 55)
    print("\n💡 Rode python3 generate_report.py para o relatório HTML visual")


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Avaliação de prescrições — Dose Certa")
    parser.add_argument(
        "--start", type=str, default=None,
        help="ID da primeira receita a avaliar (ex: P001). Padrão: primeira do dataset."
    )
    parser.add_argument(
        "--end", type=str, default=None,
        help="ID da última receita a avaliar (ex: P015). Padrão: última do dataset."
    )
    args = parser.parse_args()

    print("🔬 Dose Certa — Avaliação de Prescrições")
    print(f"   Endpoint: {ENDPOINT}")
    print(f"   Delay entre requisições: {REQUEST_DELAY}s (~{60/REQUEST_DELAY:.0f} RPM)")
    print(f"   Retry em caso de erro: {MAX_RETRIES}x (exponential backoff: 1s, 2s, 4s, ...)")
    if args.start or args.end:
        print(f"   Lote: {args.start or 'início'} → {args.end or 'fim'}")
    print()

    if not DATASET_PATH.exists():
        print(f"❌ {DATASET_PATH} não encontrado.")
        sys.exit(1)
    if not IMAGES_DIR.exists():
        print(f"❌ Pasta {IMAGES_DIR} não encontrada.")
        sys.exit(1)

    print("🔌 Verificando backend...")
    try:
        requests.get(BACKEND_URL, timeout=5)
        print("   ✅ Backend acessível\n")
    except Exception:
        print(f"   ❌ Backend não está respondendo em {BACKEND_URL}")
        print("   Sobe o backend com: uvicorn main:app --reload")
        sys.exit(1)

    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    prescriptions = data["prescriptions"]

    # Filtrar por --start e --end
    ids = [p["prescription_id"] for p in prescriptions]
    start_idx = ids.index(args.start) if args.start and args.start in ids else 0
    end_idx   = ids.index(args.end)   if args.end   and args.end   in ids else len(ids) - 1
    prescriptions_lote = prescriptions[start_idx:end_idx + 1]

    total_dataset = len(prescriptions)
    print(f"📋 Dataset: {total_dataset} receitas (v{data.get('dataset_version', '?')})")
    print(f"   Lote atual: {len(prescriptions_lote)} receitas ({prescriptions_lote[0]['prescription_id']} → {prescriptions_lote[-1]['prescription_id']})")
    print(f"   Tempo estimado: ~{len(prescriptions_lote) * REQUEST_DELAY / 60:.0f} minutos\n")

    # Carregar resultados anteriores se existirem (para juntar lotes)
    full_json = RESULTS_DIR / "results_full.json"
    previous_results = []
    if full_json.exists():
        with open(full_json, encoding="utf-8") as f:
            previous_results = json.load(f)
        prev_ids = {r["prescription_id"] for r in previous_results}
        # Remove resultados do lote atual (serão re-avaliados)
        previous_results = [r for r in previous_results if r["prescription_id"] not in {p["prescription_id"] for p in prescriptions_lote}]
        if previous_results:
            print(f"   ℹ️  Mantendo {len(previous_results)} resultado(s) de lote(s) anterior(es)\n")

    all_results_lote = []
    for i, prescription in enumerate(prescriptions_lote, start=1):
        pid = prescription["prescription_id"]
        global_idx = ids.index(pid) + 1
        print(f"  [{i:02d}/{len(prescriptions_lote)}] {pid} (#{global_idx}/{total_dataset})", end=" ", flush=True)
        result = evaluate_prescription(prescription)

        if result["api_success"]:
            icon = "✅" if result["all_critical_ok"] else "⚠️ "
            f1   = result["medications"].get("f1", 0)
            print(f"{icon} F1={f1:.2f}")
        else:
            print(f"❌ {result['api_error'][:80]}")

        all_results_lote.append(result)
        if i < len(prescriptions_lote):
            time.sleep(REQUEST_DELAY)

    # Juntar com lotes anteriores e ordenar por ID
    all_results_combined = previous_results + all_results_lote
    all_results_combined.sort(key=lambda r: r["prescription_id"])

    save_results(all_results_combined)
    print_summary(all_results_combined)


if __name__ == "__main__":
    main()