#!/usr/bin/env python3
"""
generate_eval_template.py

Gera o template CSV para avaliacao manual do Grupo A.
Inclui a resposta completa do chatbot diretamente no CSV,
junto com os criterios MUST/SHOULD/MUST NOT para avaliacao lado a lado.

USO:
    python3 generate_eval_template.py

ENTRADA:
    results/chat/chatbot_responses.json
    gold_answers.json

SAIDA:
    results/chat/chatbot_eval_template.csv
"""

import csv
import json
from pathlib import Path

RESPONSES_PATH    = Path("results/chat/chatbot_responses.json")
GOLD_ANSWERS_PATH = Path("gold_answers.json")
OUTPUT_PATH       = Path("results/chat/chatbot_eval_template.csv")


def main():
    if not RESPONSES_PATH.exists():
        print(f"Erro: {RESPONSES_PATH} nao encontrado. Rode evaluate_chatbot.py primeiro.")
        return
    if not GOLD_ANSWERS_PATH.exists():
        print(f"Erro: {GOLD_ANSWERS_PATH} nao encontrado.")
        return

    with open(RESPONSES_PATH, encoding="utf-8") as f:
        responses = {r["prompt_id"]: r for r in json.load(f)}

    with open(GOLD_ANSWERS_PATH, encoding="utf-8") as f:
        gold = {p["id"]: p for p in json.load(f)["prompts"]}

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        # Identificacao
        "prompt_id",
        "categoria",
        "usuario",
        "contexto_dependente",
        "mensagem",
        "api_success",
        # Resposta completa do chatbot
        "resposta_chatbot",
        # Criterios para avaliacao (referencia — nao editar)
        "criterios_must",
        "criterios_should",
        "criterios_must_not",
        # Campos para preencher
        "must_score",          # ex: "3/4" (quantos MUST foram atendidos)
        "should_score",        # ex: "1/2" (quantos SHOULD foram atendidos — opcional)
        "must_not_violado",    # 0 = nao violou, 1 = violou
        "must_not_qual",       # qual criterio MUST NOT foi violado (se violou)
        "correctness",         # 1 a 5 (Livingston 2025)
        "safety",              # 0 a 3 (AHRQ)
        "context_use",         # 0, 1 ou 2
        "bula_citada",         # 1 = sim, 0 = nao, NA = nao se aplica
        "observacoes",
    ]

    rows = []

    for pid, ga in gold.items():
        resp    = responses.get(pid, {})
        reply   = resp.get("reply", "")
        success = resp.get("success", False)

        must_list     = " | ".join(ga.get("must", []))
        should_list   = " | ".join(ga.get("should", []))
        must_not_list = " | ".join(ga.get("must_not", []))
        n_must        = len(ga.get("must", []))
        n_should      = len(ga.get("should", []))

        rows.append({
            "prompt_id":           pid,
            "categoria":           ga["categoria"],
            "usuario":             ga["usuario"],
            "contexto_dependente": "Sim" if ga["contexto_dependente"] else "Nao",
            "mensagem":            ga["mensagem"],
            "api_success":         "OK" if success else "FALHA",
            "resposta_chatbot":    reply if reply else "SEM RESPOSTA",
            "criterios_must":      must_list,
            "criterios_should":    should_list,
            "criterios_must_not":  must_not_list,
            "must_score":          f"__/{n_must}",    # preencher ex: 3/4
            "should_score":        f"__/{n_should}",  # preencher ex: 1/2
            "must_not_violado":    "",                 # preencher: 0 ou 1
            "must_not_qual":       "",                 # preencher se violou
            "correctness":         "",                 # 1 a 5
            "safety":              "",                 # 0 a 3
            "context_use":         "",                 # 0, 1 ou 2
            "bula_citada":         "",                 # 1, 0 ou NA
            "observacoes":         "",
        })

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    total    = len(rows)
    sucessos = sum(1 for r in rows if r["api_success"] == "OK")
    falhas   = total - sucessos

    print(f"Template gerado: {OUTPUT_PATH}")
    print(f"Total: {total} prompts ({sucessos} com resposta, {falhas} sem)")
    print()
    print("Como preencher:")
    print("  1. Abra o CSV no Excel ou Numbers")
    print("  2. Para cada linha: leia 'resposta_chatbot'")
    print("     e compare com 'criterios_must', 'criterios_should' e 'criterios_must_not'")
    print("  3. Preencha:")
    print("       must_score       ex: 3/4 (quantos criterios MUST foram atendidos)")
    print("       should_score     ex: 1/2 (quantos SHOULD foram atendidos — opcional)")
    print("       must_not_violado 0 (nao violou) ou 1 (violou)")
    print("       must_not_qual    qual criterio MUST NOT foi violado (texto livre)")
    print("       correctness      1 a 5 (Livingston 2025)")
    print("       safety           0 a 3 (AHRQ)")
    print("       context_use      0, 1 ou 2")
    print("       bula_citada      1, 0 ou NA")
    print("       observacoes      texto livre")
    print("  4. Salve como: chatbot_eval_filled.csv")
    print("  5. Rode: python3 generate_chatbot_report.py")


if __name__ == "__main__":
    main()
