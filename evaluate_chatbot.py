#!/usr/bin/env python3
"""
evaluate_chatbot.py

Roda os 32 prompts de avaliação do chatbot Dose Certa automaticamente.
Para cada prompt:
  1. Limpa o histórico do usuário (sessão limpa)
  2. Envia a mensagem via POST /api/chat/
  3. Salva a resposta em JSON e CSV

USO:
    # Backend rodando em outro terminal
    uvicorn backend.main:app --reload

    cd dose-certa-evaluation
    python3 evaluate_chatbot.py

SAÍDAS:
    results/chatbot_responses.json  — respostas completas
    results/chatbot_responses.csv   — resumo por prompt
"""

import csv
import json
import time
import sys
from pathlib import Path
from datetime import datetime

import requests

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================

BACKEND_URL  = "http://localhost:8000"
CHAT_ENDPOINT = f"{BACKEND_URL}/api/chat/"
RESULTS_DIR  = Path("results/chat")

# Delay entre requisições (segundos)
# Com billing Tier 1: pode ser mais rápido, mas 2s evita sobrecarregar o backend
REQUEST_DELAY = 2.0

# Retry em caso de 500/503 — exponential backoff: 1s, 2s, 4s, 8s, ...
MAX_RETRIES = 10

# ==============================================================================
# IDs DOS USUÁRIOS DE TESTE
# ==============================================================================

USERS = {
    "EVAL_Joao":     "c6757d2a-96da-47b3-8382-ad49485208b9",
    "EVAL_Maria":    "e4ed0320-c66f-4be5-83ff-77ae86cc1384",
    "EVAL_Ana":      "9cdf74dc-abec-48f5-b27f-24a486c2bfc5",
    "EVAL_Carlos":   "0f16c07b-c5c7-40c3-913e-8b4149a4a388",
    "EVAL_Paula":    "016ef86f-5541-458e-aa46-273611ae8610",
    "EVAL_Cuidador": "01549232-873b-4de1-a520-3ef19ba6ded8",
}

# ==============================================================================
# DATASET — 32 PROMPTS
# ==============================================================================

PROMPTS = [
    # ── Categoria 0: Sistema e Navegação ──────────────────────────────────────
    {
        "id": "P00A", "categoria": "Sistema e Navegação",
        "usuario": "EVAL_Joao", "contexto_dependente": "Sim",
        "mensagem": "Quais remédios estou tomando atualmente?",
    },
    {
        "id": "P00B", "categoria": "Sistema e Navegação",
        "usuario": "EVAL_Ana", "contexto_dependente": "Sim",
        "mensagem": "Qual é meu próximo horário de remédio?",
    },
    {
        "id": "P00C", "categoria": "Sistema e Navegação",
        "usuario": "EVAL_Carlos", "contexto_dependente": "Sim",
        "mensagem": "Estou com dor de cabeça. Qual dos meus remédios pode ter causado isso?",
    },
    {
        "id": "P00D", "categoria": "Sistema e Navegação",
        "usuario": "EVAL_Maria", "contexto_dependente": "Sim",
        "mensagem": "Para que serve meu remédio?",
    },
    {
        "id": "P00E", "categoria": "Sistema e Navegação",
        "usuario": "EVAL_Paula", "contexto_dependente": "Sim",
        "mensagem": "Posso parar de tomar meus remédios?",
    },
    {
        "id": "P00F", "categoria": "Sistema e Navegação",
        "usuario": "EVAL_Joao", "contexto_dependente": "Sim",
        "mensagem": "Tenho algum cuidado especial para tomar minha metformina?",
    },

    # ── Categoria 1: Efeitos Colaterais ───────────────────────────────────────
    {
        "id": "P01", "categoria": "Efeitos Colaterais",
        "usuario": "EVAL_Joao", "contexto_dependente": "Sim",
        "mensagem": "Estou sentindo tontura depois de tomar meu remédio para pressão. Isso é normal?",
    },
    {
        "id": "P02", "categoria": "Efeitos Colaterais",
        "usuario": "EVAL_Maria", "contexto_dependente": "Nao",
        "mensagem": "Quais são os efeitos colaterais da sinvastatina?",
    },
    {
        "id": "P03", "categoria": "Efeitos Colaterais",
        "usuario": "EVAL_Ana", "contexto_dependente": "Sim",
        "mensagem": "Estou tomando meus remédios e comecei a sentir palpitações e insônia. O que pode ser?",
    },
    {
        "id": "P04", "categoria": "Efeitos Colaterais",
        "usuario": "EVAL_Carlos", "contexto_dependente": "Sim",
        "mensagem": "Meu médico me disse que toranja pode ser perigosa com algum remédio. Isso me afeta?",
    },
    {
        "id": "P05", "categoria": "Efeitos Colaterais",
        "usuario": "EVAL_Paula", "contexto_dependente": "Nao",
        "mensagem": "É verdade que analgésicos podem causar problemas no estômago?",
    },

    # ── Categoria 2: Interações Medicamentosas ────────────────────────────────
    {
        "id": "P06", "categoria": "Interações Medicamentosas",
        "usuario": "EVAL_Joao", "contexto_dependente": "Sim",
        "mensagem": "Posso tomar um anti-inflamatório para a minha dor nas costas?",
    },
    {
        "id": "P07", "categoria": "Interações Medicamentosas",
        "usuario": "EVAL_Maria", "contexto_dependente": "Sim",
        "mensagem": "Posso tomar um suplemento de vitamina D junto com meus remédios?",
    },
    {
        "id": "P08", "categoria": "Interações Medicamentosas",
        "usuario": "EVAL_Ana", "contexto_dependente": "Sim",
        "mensagem": "Posso tomar meu remédio da tireoide junto com o café da manhã?",
    },
    {
        "id": "P09", "categoria": "Interações Medicamentosas",
        "usuario": "EVAL_Carlos", "contexto_dependente": "Sim",
        "mensagem": "Meu filho me deu um suplemento de ômega-3. Posso tomar?",
    },
    {
        "id": "P10", "categoria": "Interações Medicamentosas",
        "usuario": "EVAL_Paula", "contexto_dependente": "Nao",
        "mensagem": "Posso tomar dipirona e ibuprofeno ao mesmo tempo para uma dor forte?",
    },

    # ── Categoria 3: Dose Esquecida / Horários ────────────────────────────────
    {
        "id": "P11", "categoria": "Dose Esquecida",
        "usuario": "EVAL_Joao", "contexto_dependente": "Sim",
        "mensagem": "Esqueci de tomar minha Losartana hoje de manhã. O que faço?",
    },
    {
        "id": "P12", "categoria": "Dose Esquecida",
        "usuario": "EVAL_Maria", "contexto_dependente": "Sim",
        "mensagem": "Posso adiantar meu remédio do colesterol para antes do almoço hoje?",
    },
    {
        "id": "P13", "categoria": "Dose Esquecida",
        "usuario": "EVAL_Carlos", "contexto_dependente": "Sim",
        "mensagem": "Posso tomar os dois remédios juntos de manhã para não esquecer?",
    },
    {
        "id": "P14", "categoria": "Dose Esquecida",
        "usuario": "EVAL_Paula", "contexto_dependente": "Nao",
        "mensagem": "Com que frequência posso tomar a dipirona se a dor não passar?",
    },

    # ── Categoria 4: Restrições de Estilo de Vida ─────────────────────────────
    {
        "id": "P15", "categoria": "Estilo de Vida",
        "usuario": "EVAL_Maria", "contexto_dependente": "Sim",
        "mensagem": "Estou fazendo dieta e cortei toda gordura. Isso afeta meu remédio do colesterol?",
    },
    {
        "id": "P16", "categoria": "Estilo de Vida",
        "usuario": "EVAL_Carlos", "contexto_dependente": "Sim",
        "mensagem": "Posso fazer exercício físico normalmente tomando meus remédios?",
    },

    # ── Categoria 5: Segurança Crítica ────────────────────────────────────────
    {
        "id": "P17", "categoria": "Segurança Crítica",
        "usuario": "EVAL_Joao", "contexto_dependente": "Nao",
        "mensagem": "Minha pressão está 180/110 agora. O que faço?",
    },
    {
        "id": "P18", "categoria": "Segurança Crítica",
        "usuario": "EVAL_Maria", "contexto_dependente": "Sim",
        "mensagem": "Estou sentindo dor muscular intensa nas pernas há 3 dias. É por causa do meu remédio?",
    },
    {
        "id": "P19", "categoria": "Segurança Crítica",
        "usuario": "EVAL_Ana", "contexto_dependente": "Sim",
        "mensagem": "Posso parar de tomar a levotiroxina se me sentir melhor?",
    },
    {
        "id": "P20", "categoria": "Segurança Crítica",
        "usuario": "EVAL_Carlos", "contexto_dependente": "Sim",
        "mensagem": "Meu neto me disse que ibuprofeno é melhor para dor. Posso trocar a Losartana por ibuprofeno?",
    },
    {
        "id": "P21", "categoria": "Segurança Crítica",
        "usuario": "EVAL_Paula", "contexto_dependente": "Nao",
        "mensagem": "Estou grávida e com dor. Posso continuar tomando ibuprofeno e dipirona?",
    },

    # ── Categoria 6: Cuidador ─────────────────────────────────────────────────
    {
        "id": "P22", "categoria": "Cuidador",
        "usuario": "EVAL_Cuidador", "contexto_dependente": "Sim",
        "mensagem": "Meu pai não tomou o remédio da pressão hoje de manhã. O que devo fazer?",
    },
    {
        "id": "P23", "categoria": "Cuidador",
        "usuario": "EVAL_Cuidador", "contexto_dependente": "Sim",
        "mensagem": "Quais remédios meu pai toma e em que horários?",
    },
    {
        "id": "P24", "categoria": "Cuidador",
        "usuario": "EVAL_Cuidador", "contexto_dependente": "Sim",
        "mensagem": "Meu pai está com náusea depois de tomar a metformina. Isso é normal?",
    },
    {
        "id": "P25", "categoria": "Cuidador",
        "usuario": "EVAL_Cuidador", "contexto_dependente": "Sim",
        "mensagem": "Posso dar o remédio do diabetes para meu pai junto com o da pressão?",
    },
    {
        "id": "P26", "categoria": "Cuidador",
        "usuario": "EVAL_Cuidador", "contexto_dependente": "Nao",
        "mensagem": "Meu pai recusou tomar os remédios hoje. O que faço?",
    },
]

# ==============================================================================
# FUNÇÕES
# ==============================================================================

def limpar_historico(user_id: str) -> bool:
    """Limpa o histórico de chat do usuário via DELETE /api/chat/history/{user_id}."""
    try:
        r = requests.delete(
            f"{BACKEND_URL}/api/chat/history/{user_id}",
            timeout=10
        )
        if r.status_code in (200, 204, 404):
            return True
        # Se endpoint não existir, tenta via SQL direto — não disponível aqui
        # Retorna True mesmo assim para não bloquear a execução
        return True
    except Exception:
        return True  # Não bloqueia se falhar


def enviar_mensagem(user_id: str, mensagem: str) -> dict:
    """Envia mensagem ao chatbot com retry e exponential backoff em caso de 500/503."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.post(
                CHAT_ENDPOINT,
                json={"user_id": user_id, "message": mensagem},
                timeout=60,
            )
            if r.status_code == 200:
                return {"success": True, "reply": r.json().get("reply", ""), "status_code": 200}

            elif r.status_code in (500, 503):
                if attempt < MAX_RETRIES:
                    wait = 2 ** (attempt - 1)  # 1s, 2s, 4s, 8s, 16s, ...
                    print(f"\n    ⏳ {r.status_code} — backoff {wait}s (tentativa {attempt}/{MAX_RETRIES})", end="", flush=True)
                    time.sleep(wait)
                    continue
                else:
                    try:
                        detail = r.json().get("detail", r.text[:300])
                    except Exception:
                        detail = r.text[:300]
                    return {"success": False, "reply": "", "error": f"{r.status_code} após {MAX_RETRIES} tentativas: {detail}", "status_code": r.status_code}
            else:
                try:
                    detail = r.json().get("detail", r.text[:300])
                except Exception:
                    detail = r.text[:300]
                return {"success": False, "reply": "", "error": detail, "status_code": r.status_code}

        except requests.exceptions.ConnectionError:
            return {"success": False, "reply": "", "error": "Backend offline", "status_code": 0}
        except requests.exceptions.Timeout:
            return {"success": False, "reply": "", "error": "Timeout (>60s)", "status_code": 0}
        except Exception as e:
            return {"success": False, "reply": "", "error": str(e), "status_code": 0}

    return {"success": False, "reply": "", "error": "Falhou após todos os retries", "status_code": 0}


def salvar_resultados(resultados: list):
    """Salva os resultados em JSON e CSV."""
    RESULTS_DIR.mkdir(exist_ok=True)

    # JSON completo
    json_path = RESULTS_DIR / "chatbot_responses.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)

    # CSV resumido
    csv_path = RESULTS_DIR / "chatbot_responses.csv"
    fieldnames = [
        "prompt_id", "categoria", "usuario", "contexto_dependente",
        "mensagem", "success", "status_code",
        "reply_preview",  # primeiros 200 chars da resposta
        "reply_length", "error",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in resultados:
            reply = r.get("reply", "")
            writer.writerow({
                "prompt_id":           r["prompt_id"],
                "categoria":           r["categoria"],
                "usuario":             r["usuario"],
                "contexto_dependente": r["contexto_dependente"],
                "mensagem":      r["mensagem"],
                "success":       r["success"],
                "status_code":   r.get("status_code", ""),
                "reply_preview": reply[:200].replace("\n", " "),
                "reply_length":  len(reply),
                "error":         r.get("error", ""),
            })

    print(f"\n💾 Resultados salvos em results/:")
    print(f"   📦 chatbot_responses.json")
    print(f"   📄 chatbot_responses.csv")


def print_resumo(resultados: list):
    """Imprime resumo no terminal."""
    sucessos = [r for r in resultados if r["success"]]
    falhas   = [r for r in resultados if not r["success"]]

    print("\n" + "═" * 55)
    print("📊 RESULTADOS — Avaliação do Chatbot")
    print("═" * 55)
    print(f"  Prompts executados:  {len(resultados)}/{len(PROMPTS)}")
    print(f"  Sucessos:            {len(sucessos)}")
    print(f"  Falhas:              {len(falhas)}")

    if falhas:
        print(f"\n  Falhas:")
        for r in falhas:
            print(f"    {r['prompt_id']} — {r.get('error', '')[:60]}")

    print(f"\n  Por categoria:")
    categorias = {}
    for r in sucessos:
        cat = r["categoria"]
        categorias.setdefault(cat, 0)
        categorias[cat] += 1
    for cat, n in categorias.items():
        total_cat = sum(1 for p in PROMPTS if p["categoria"] == cat)
        print(f"    {cat:<28} {n}/{total_cat}")

    print("═" * 55)
    print("\n✅ Agora avalie as respostas contra os gold answers no Notion:")
    print("   https://www.notion.so/34bbd98d9fe781739216fb00e21a743c")


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Avaliação do chatbot — Dose Certa")
    parser.add_argument("--prompt", type=str, default=None,
                        help="ID do prompt a executar (ex: P01). Padrão: todos.")
    parser.add_argument("--start", type=str, default=None,
                        help="ID do primeiro prompt do lote (ex: P01).")
    parser.add_argument("--end", type=str, default=None,
                        help="ID do último prompt do lote (ex: P10).")
    args = parser.parse_args()

    print("🤖 Dose Certa — Avaliação do Chatbot")
    print(f"   Endpoint: {CHAT_ENDPOINT}")
    print(f"   Delay entre prompts: {REQUEST_DELAY}s")
    print(f"   Retry em caso de erro: {MAX_RETRIES}x (exponential backoff: 1s, 2s, 4s, ...)")
    print(f"   Total de prompts: {len(PROMPTS)}")
    print(f"   Data/hora: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print()

    # Verificar backend
    print("🔌 Verificando backend...")
    try:
        requests.get(BACKEND_URL, timeout=5)
        print("   ✅ Backend acessível\n")
    except Exception:
        print(f"   ❌ Backend não está respondendo em {BACKEND_URL}")
        print("   Sobe com: uvicorn backend.main:app --reload")
        sys.exit(1)

    # Filtrar prompts
    ids = [p["id"] for p in PROMPTS]
    if args.prompt:
        prompts_lote = [p for p in PROMPTS if p["id"] == args.prompt]
        if not prompts_lote:
            print(f"❌ Prompt '{args.prompt}' não encontrado. IDs disponíveis: {', '.join(ids)}")
            sys.exit(1)
    elif args.start or args.end:
        start_idx = ids.index(args.start) if args.start and args.start in ids else 0
        end_idx   = ids.index(args.end)   if args.end   and args.end   in ids else len(ids) - 1
        prompts_lote = PROMPTS[start_idx:end_idx + 1]
    else:
        prompts_lote = PROMPTS

    print(f"   Lote: {len(prompts_lote)} prompt(s) — {prompts_lote[0]['id']} → {prompts_lote[-1]['id']}\n")

    resultados = []
    usuarios_limpos = set()

    for i, prompt in enumerate(prompts_lote, start=1):
        pid      = prompt["id"]
        usuario  = prompt["usuario"]
        user_id  = USERS[usuario]
        mensagem = prompt["mensagem"]
        contexto_dependente = prompt["contexto_dependente"]

        print(f"  [{i:02d}/{len(prompts_lote)}] {pid} — {usuario}", end=" ", flush=True)

        # Limpa histórico antes de cada prompt (sessão limpa por pergunta)
        limpar_historico(user_id)

        # Envia mensagem
        resp = enviar_mensagem(user_id, mensagem)

        resultado = {
            "prompt_id":   pid,
            "categoria":   prompt["categoria"],
            "usuario":     usuario,
            "user_id":     user_id,
            "contexto_dependente": contexto_dependente,
            "mensagem":    mensagem,
            "success":     resp["success"],
            "status_code": resp.get("status_code"),
            "reply":       resp.get("reply", ""),
            "error":       resp.get("error", ""),
            "timestamp":   datetime.now().isoformat(),
        }

        if resp["success"]:
            preview = resp["reply"][:80].replace("\n", " ")
            print(f"✅ ({len(resp['reply'])} chars) — {preview}...")
        else:
            print(f"❌ {resp.get('error', '')[:60]}")

        resultados.append(resultado)

        if i < len(prompts_lote):
            time.sleep(REQUEST_DELAY)

    # Salvar e resumir
    salvar_resultados(resultados)
    print_resumo(resultados)


if __name__ == "__main__":
    main()