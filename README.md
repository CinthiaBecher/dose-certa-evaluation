# dose-certa-evaluation

Avaliação científica do sistema **Dose Certa** — TCC 2 de Cinthia Virtuoso Becher (UNISINOS, Ciência da Computação).

## Sobre

Este repositório contém o dataset, scripts e artefatos utilizados na avaliação científica do sistema Dose Certa, focada em duas capacidades do **Gemini 2.5 Flash** integradas ao sistema:

1. **Interpretação de prescrições médicas** via Vision — extração de campos estruturados a partir de imagens de receitas
2. **Chatbot farmacêutico contextual** — respostas conversacionais com uso do contexto do paciente *(em desenvolvimento)*

A avaliação é feita **através da API do sistema Dose Certa** (não diretamente contra o Gemini), garantindo que os resultados reflitam o comportamento do sistema em uso real — incluindo prompt engineering, validação de schema e tratamento de erros.

## Requisitos

- Python 3.9+
- Playwright com Chromium *(para geração sintética das receitas)*
- Backend do Dose Certa rodando localmente *(para execução da avaliação)*

## Instalação

```bash
# Clonar o repositório
git clone <url> dose-certa-evaluation
cd dose-certa-evaluation

# Instalar dependências
pip install -r requirements.txt
playwright install chromium
```

## Uso

### 1. Gerar receitas sintéticas

```bash
python3 generate_prescriptions.py
```

O script lê o `ground_truth_dataset.json` e produz:

- `images/` — 15 receitas completas (P011-P025)
- `headers/` — 5 cabeçalhos isolados para as receitas manuscritas (P026-P030)

As demais 15 imagens (P001-P010 produzidas no Canva + P026-P030 manuscritas/cursivas) devem ser colocadas manualmente em `images/`.

### 2. Executar avaliação *(em desenvolvimento)*

```bash
# Com o backend Dose Certa rodando em localhost:8000
python3 evaluate_prescriptions.py
```

## Estrutura do dataset

O `ground_truth_dataset.json` contém 30 prescrições sintéticas distribuídas entre:

- **10 receitas Canva manual** (P001-P010) — liberdade criativa visual máxima
- **15 receitas Script Python** (P011-P025) — 10 templates HTML distintos, reprodutível
- **4 receitas manuscritas reais** (P026-P029) — escritas à mão em papel e fotografadas
- **1 receita printed script font** (P030) — fonte cursiva decorativa impressa

Cada receita tem ground truth estruturado com:
- Nome do paciente
- Data da prescrição (ISO 8601)
- Nome e CRM do médico fictício
- Especialidade
- Lista de medicamentos (nome, dosagem, via, frequência, duração, instruções)

10 médicos fictícios distribuem as 30 receitas (3 por médico) em especialidades variadas: Clínica Médica, Cardiologia, Endocrinologia, Geriatria, Ginecologia, Ortopedia, Infectologia, Pneumologia, Neurologia.

## Casos adversariais

10 das 30 receitas incluem casos propositalmente desafiadores:
- Abreviações médicas (VO, SL, 8/8h, SOS, jej.)
- Nomes de medicamentos similares (Losartana/Losartina, Metformina/Metoprolol, Sinvastatina/Sitagliptina)
- Posologias complexas (desmame de corticoide, dose única, uso contínuo)
- Polifarmácia (4-6 medicamentos)
- Formatos de data não-padrão (22/01/25 em vez de 22/01/2025)
- Tipografia decorativa (fonte cursiva impressa)

## Metodologia

A avaliação segue os reporting guidelines:

- **TRIPOD-LLM** — Gallifant et al., *Nature Medicine*, 2025
- **CHART Statement** — Huo et al., *BMJ Medicine*, 2025

Referências adicionais que fundamentam o plano:
- Asgari et al. (2025) — *npj Digital Medicine* — taxonomia hallucination/omission
- Krumdick et al. (2026) — *arXiv:2503.05061* — limitações de LLM-as-Judge
- Livingston et al. (2025) — *JAMIA Open* — framework 5-dimensional
- Ravi et al. (2024) — RxLens multi-agent prescription
- Yuan et al. (2024) — *npj Digital Medicine* — framework QUEST

## Autoria

**Cinthia Virtuoso Becher**
Trabalho de Conclusão de Curso 2 — Bacharelado em Ciência da Computação
Universidade do Vale do Rio dos Sinos (UNISINOS)
2026