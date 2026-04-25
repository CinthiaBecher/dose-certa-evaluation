#!/usr/bin/env python3
"""
generate_eval_template.py

Gera o template CSV para avaliação manual do Grupo A.
Cruza as respostas do chatbot com os gold answers e cria
uma linha por prompt com colunas para preencher.

USO:
    python3 generate_eval_template.py

ENTRADA:
    results/chat/chatbot_responses.json
    gold_answers.json

SAÍDA:
    results/chat/chatbot_eval_template.csv  — abrir no Excel/Numbers para preencher
"""

import csv
import json
from pathlib import Path

RESPONSES_PATH    = Path("results/chat/chatbot_responses.json")
GOLD_ANSWERS_PATH = Path("gold_answers.json")
OUTPUT_PATH       = Path("results/chat/chatbot_eval_template.csv")

def main():
    if not RESPONSES_PATH.exists():
        print(f"❌ {RESPONSES_PATH} não encontrado. Rode evaluate_chatbot.py primeiro.")
        return
    if not GOLD_ANSWERS_PATH.exists():
        print(f"❌ {GOLD_ANSWERS_PATH} não encontrado.")
        return

    with open(RESPONSES_PATH, encoding="utf-8") as f:
        responses = {r["prompt_id"]: r for r in json.load(f)}

    with open(GOLD_ANSWERS_PATH, encoding="utf-8") as f:
        gold = {p["id"]: p for p in json.load(f)["prompts"]}

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "prompt_id",
        "categoria",
        "usuario",
        "pegadinha",
        "mensagem",
        "api_success",
        # Resposta do chatbot (preview)
        "reply_preview",
        # Critérios MUST (preencher: 1=atendido, 0=não atendido)
        "must_criterios",      # lista dos critérios MUST (referência)
        "must_score",          # ex: "3/3" ou "2/3"
        # Critérios MUST NOT
        "must_not_criterios",  # lista dos critérios MUST NOT (referência)
        "must_not_violado",    # 0=não violou, 1=violou
        "must_not_qual",       # qual MUST NOT foi violado (texto livre)
        # Dimensões de avaliação Grupo A
        "correctness",         # 1-5 (Livingston 2025)
        "safety",              # 0-3 (AHRQ)
        "context_use",         # 0-2
        "bula_citada",         # 1=sim, 0=não, NA=não se aplica
        # Observações
        "observacoes",
    ]

    rows = []
    for pid, ga in gold.items():
        resp = responses.get(pid, {})
        reply = resp.get("reply", "")
        success = resp.get("success", False)

        must_list = " | ".join(ga.get("must", []))
        must_not_list = " | ".join(ga.get("must_not", []))
        n_must = len(ga.get("must", []))

        rows.append({
            "prompt_id":         pid,
            "categoria":         ga["categoria"],
            "usuario":           ga["usuario"],
            "pegadinha":         "Sim" if ga["pegadinha"] else "Não",
            "mensagem":          ga["mensagem"],
            "api_success":       "✅" if success else "❌ FALHA",
            "reply_preview":     reply[:300].replace("\n", " ") if reply else "— SEM RESPOSTA —",
            "must_criterios":    must_list,
            "must_score":        f"__/{n_must}",   # preencher: ex 3/3
            "must_not_criterios": must_not_list,
            "must_not_violado":  "",               # preencher: 0 ou 1
            "must_not_qual":     "",               # preencher se violou
            "correctness":       "",               # preencher: 1-5
            "safety":            "",               # preencher: 0-3
            "context_use":       "",               # preencher: 0-2
            "bula_citada":       "",               # preencher: 1, 0 ou NA
            "observacoes":       "",
        })

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Estatísticas
    total = len(rows)
    sucessos = sum(1 for r in rows if r["api_success"] == "✅")
    falhas = total - sucessos

    print(f"✅ Template gerado: {OUTPUT_PATH}")
    print(f"   Total de prompts: {total}")
    print(f"   Com resposta:     {sucessos}")
    print(f"   Sem resposta:     {falhas} (❌ — preencher após re-rodar o script)")
    print()
    print("📋 Como preencher o CSV:")
    print("   1. Abra no Excel ou Numbers")
    print("   2. Para cada linha, leia a 'reply_preview'")
    print("   3. Compare com os critérios em 'must_criterios' e 'must_not_criterios'")
    print("   4. Preencha must_score (ex: 3/3), must_not_violado (0/1), correctness (1-5), safety (0-3), context_use (0-2)")
    print("   5. Salve como chatbot_eval_filled.csv")
    print("   6. Rode: python3 generate_chatbot_report.py")


if __name__ == "__main__":
    main()
