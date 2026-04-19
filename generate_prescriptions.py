#!/usr/bin/env python3
"""
generate_prescriptions.py

Gera imagens de receitas médicas sintéticas a partir do ground_truth_dataset.json.
Usa 10 templates HTML distintos (um por médico fictício) e Playwright para
renderizar HTML → PNG.

Produz:
- 15 receitas completas (production_method == "script")

Dataset: Dose Certa — TCC 2 — Cinthia Virtuoso Becher
Versão: 1.0

USO:
    pip install playwright
    playwright install chromium
    python generate_prescriptions.py

SAÍDAS:
    images/               — 15 receitas completas (P011-P025)
"""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright


# ==============================================================================
# CONFIGURAÇÃO: perfis visuais de cada médico
# ==============================================================================
# Cada médico tem seu "timbre" — estilo visual consistente que imita o fato de
# que médicos reais têm receituários próprios (logos, cores, fontes, layouts).
#
# Isso aumenta a diversidade visual do dataset de teste, tornando a avaliação
# do Gemini mais robusta (não está sendo testado num único layout).

DOCTOR_STYLES = {
    "Dr. Ricardo Almeida": {
        "style_name": "Clínico Tradicional",
        "font_body": "'Helvetica Neue', Arial, sans-serif",
        "font_size_body": "12pt",
        "header_layout": "centered",
        "primary_color": "#1a1a1a",
        "accent_color": "#333333",
        "paper_color": "#ffffff",
        "use_logo": False,
        "border_style": "none",
        "logo_icon": None,
        "address": "Rua das Acácias, 245 - Sala 302 - Porto Alegre/RS",
        "phone": "(51) 3224-5678",
        "numbered_meds": False,
    },
    "Dra. Juliana Costa": {
        "style_name": "Cardiologia Formal",
        "font_body": "Georgia, 'Times New Roman', serif",
        "font_size_body": "11pt",
        "header_layout": "centered",
        "primary_color": "#8b0000",
        "accent_color": "#8b0000",
        "paper_color": "#ffffff",
        "use_logo": True,
        "border_style": "double-top",
        "logo_icon": "♥",
        "address": "Av. Paulista, 1578 - 12º andar - São Paulo/SP",
        "phone": "(11) 3141-2200",
        "numbered_meds": True,
    },
    "Dr. Fernando Oliveira": {
        "style_name": "Endocrinologia Moderna",
        "font_body": "'Segoe UI', Roboto, sans-serif",
        "font_size_body": "11pt",
        "header_layout": "left-with-logo",
        "primary_color": "#003366",
        "accent_color": "#0066cc",
        "paper_color": "#ffffff",
        "use_logo": True,
        "border_style": "thin-left",
        "logo_icon": "FO",
        "address": "Rua da Bahia, 820 - Centro - Belo Horizonte/MG",
        "phone": "(31) 3273-4411",
        "numbered_meds": False,
    },
    "Dra. Patrícia Souza": {
        "style_name": "Clínica Moderna Minimalista",
        "font_body": "'Lato', 'Helvetica Neue', sans-serif",
        "font_size_body": "11pt",
        "header_layout": "two-column-left",
        "primary_color": "#2a5c3e",
        "accent_color": "#4a8a6b",
        "paper_color": "#fdfdfd",
        "use_logo": False,
        "border_style": "none",
        "logo_icon": None,
        "address": "Rua Padre Chagas, 410 - Moinhos de Vento - Porto Alegre/RS",
        "phone": "(51) 3330-9900",
        "numbered_meds": False,
    },
    "Dr. Marcos Lima": {
        "style_name": "Geriatria Clássica",
        "font_body": "'Times New Roman', Georgia, serif",
        "font_size_body": "13pt",
        "header_layout": "centered",
        "primary_color": "#2c2c2c",
        "accent_color": "#5a5a5a",
        "paper_color": "#faf8f3",
        "use_logo": False,
        "border_style": "double-separator",
        "logo_icon": None,
        "address": "Rua Duque de Caxias, 1120 - Centro Histórico - Porto Alegre/RS",
        "phone": "(51) 3212-3400",
        "numbered_meds": True,
    },
    "Dra. Beatriz Mendes": {
        "style_name": "Ginecologia Feminina",
        "font_body": "'Montserrat', 'Helvetica Neue', sans-serif",
        "font_size_body": "11pt",
        "header_layout": "centered",
        "primary_color": "#8b3a62",
        "accent_color": "#c27aa0",
        "paper_color": "#ffffff",
        "use_logo": True,
        "border_style": "rounded-box",
        "logo_icon": "BM",
        "address": "Rua Visconde de Pirajá, 550 - Ipanema - Rio de Janeiro/RJ",
        "phone": "(21) 2511-6677",
        "numbered_meds": False,
    },
    "Dr. Thiago Ferreira": {
        "style_name": "Ortopedia Clínica",
        "font_body": "'Helvetica Neue', Arial, sans-serif",
        "font_size_body": "11pt",
        "header_layout": "left",
        "primary_color": "#1e3a1e",
        "accent_color": "#2a5c2a",
        "paper_color": "#ffffff",
        "use_logo": False,
        "border_style": "double-bottom",
        "logo_icon": None,
        "address": "Rua XV de Novembro, 780 - Centro - Curitiba/PR",
        "phone": "(41) 3225-8800",
        "numbered_meds": False,
    },
    "Dra. Camila Ribeiro": {
        "style_name": "Infectologia Relatório",
        "font_body": "Calibri, 'Trebuchet MS', sans-serif",
        "font_size_body": "11pt",
        "header_layout": "header-box",
        "primary_color": "#1a1a1a",
        "accent_color": "#666666",
        "paper_color": "#ffffff",
        "use_logo": False,
        "border_style": "thin-all",
        "logo_icon": None,
        "address": "Av. Beira Mar, 3400 - Jurerê - Florianópolis/SC",
        "phone": "(48) 3024-5500",
        "numbered_meds": False,
    },
    "Dr. Leonardo Santos": {
        "style_name": "Pneumologia SUS",
        "font_body": "Arial, sans-serif",
        "font_size_body": "11pt",
        "header_layout": "simple-top",
        "primary_color": "#000000",
        "accent_color": "#000000",
        "paper_color": "#ffffff",
        "use_logo": False,
        "border_style": "horizontal-lines",
        "logo_icon": None,
        "address": "Posto de Saúde Central - Rua Independência, 120 - Porto Alegre/RS",
        "phone": "(51) 3211-0000",
        "numbered_meds": False,
    },
    "Dra. Sofia Nogueira": {
        "style_name": "Neurologia Sóbria",
        "font_body": "Georgia, 'Palatino Linotype', serif",
        "font_size_body": "11pt",
        "header_layout": "centered",
        "primary_color": "#2a2a2a",
        "accent_color": "#4a4a4a",
        "paper_color": "#fafafa",
        "use_logo": False,
        "border_style": "symmetric",
        "logo_icon": None,
        "address": "Rua General Câmara, 240 - Centro - Porto Alegre/RS",
        "phone": "(51) 3286-7700",
        "numbered_meds": True,
    },
}

# Receitas que devem usar FONTE HANDWRITING (Caveat/Kalam) no corpo
HANDWRITING_PRESCRIPTIONS = {"P016", "P017", "P018", "P019", "P020"}

# Receitas com nome de medicamento abreviado (pegadinha adversarial)
NAME_OVERRIDES = {
    "P014": {"Losartana Potássica": "Losartana Potáss."},
}


# ==============================================================================
# GERADOR DE HTML
# ==============================================================================

def build_html(prescription: dict, style: dict) -> str:
    """Constrói o HTML de uma receita com o estilo do médico."""
    gt = prescription["ground_truth"]
    prescription_id = prescription["prescription_id"]
    use_handwriting = prescription_id in HANDWRITING_PRESCRIPTIONS
    name_overrides = NAME_OVERRIDES.get(prescription_id, {})

    # Formata a data
    date_parts = gt["prescription_date"].split("-")
    date_formatted = f"{date_parts[2]}/{date_parts[1]}/{date_parts[0]}"

    # Monta a lista de medicamentos
    meds_html = ""
    for i, med in enumerate(gt["medications"], start=1):
        name = name_overrides.get(med["name"], med["name"])
        marker = f"{i})" if style["numbered_meds"] else "•"

        duration_text = ""
        if med.get("duration_days"):
            duration_text = f" — {med['duration_days']} dias"
        elif med.get("duration_days") is None and "uso contínuo" not in (med.get("instructions") or "").lower():
            duration_text = ""

        route_display = {
            "oral": "VO",
            "sublingual": "SL",
            "inalatória": "INAL",
            "intramuscular": "IM",
            "subcutânea": "SC",
        }.get(med.get("route", ""), med.get("route", ""))

        meds_html += f"""
        <div class="medication">
            <div class="med-line-1">
                <span class="med-marker">{marker}</span>
                <span class="med-name">{name}</span>
                <span class="med-dose">{med.get('dosage', '')}</span>
            </div>
            <div class="med-line-2">
                {route_display} — {med.get('frequency', '')}{duration_text}
            </div>
            <div class="med-line-3">
                {med.get('instructions', '') or ''}
            </div>
        </div>
        """

    # Monta o cabeçalho conforme o layout
    header_html = _build_header(gt, style)

    # CSS dinâmico
    css = _build_css(style, use_handwriting)

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <link href="https://fonts.googleapis.com/css2?family=Lato:wght@300;400;700&family=Montserrat:wght@400;600&family=Caveat:wght@400;600&family=Kalam:wght@400;700&family=Homemade+Apple&display=swap" rel="stylesheet">
    <style>
        {css}
    </style>
</head>
<body>
    <div class="prescription-container">
        {header_html}
        <div class="patient-info">
            <div class="patient-name">
                <span class="label">Paciente:</span>
                <span class="value">{gt['patient_name']}</span>
            </div>
            <div class="date">
                <span class="label">Data:</span>
                <span class="value">{date_formatted}</span>
            </div>
        </div>
        <div class="rx-section">
            <div class="rx-symbol">℞</div>
            <div class="medications">
                {meds_html}
            </div>
        </div>
        <div class="signature-section">
            <div class="signature-line"></div>
            <div class="signature-name">{gt['doctor_name']}</div>
            <div class="signature-crm">{gt['doctor_crm']}</div>
        </div>
    </div>
</body>
</html>"""

    return html


def _build_header(gt: dict, style: dict) -> str:
    """Constrói o cabeçalho conforme o layout do médico."""
    doctor_name = gt["doctor_name"]
    doctor_crm = gt["doctor_crm"]
    specialty = gt.get("doctor_specialty", "")
    address = style["address"]
    phone = style["phone"]
    logo_icon = style.get("logo_icon")

    # Logo/ícone opcional
    logo_html = ""
    if style["use_logo"] and logo_icon:
        logo_html = f'<div class="logo">{logo_icon}</div>'

    layout = style["header_layout"]

    if layout == "centered":
        return f"""
        <div class="header header-centered">
            {logo_html}
            <div class="doctor-name">{doctor_name}</div>
            <div class="specialty">{specialty}</div>
            <div class="crm">{doctor_crm}</div>
            <div class="contact">{address} · {phone}</div>
        </div>
        """

    elif layout == "left":
        return f"""
        <div class="header header-left">
            {logo_html}
            <div class="doctor-info">
                <div class="doctor-name">{doctor_name}</div>
                <div class="specialty">{specialty}</div>
                <div class="crm">{doctor_crm}</div>
                <div class="contact">{address}</div>
                <div class="contact">Tel: {phone}</div>
            </div>
        </div>
        """

    elif layout == "left-with-logo":
        return f"""
        <div class="header header-left-logo">
            {logo_html}
            <div class="doctor-info">
                <div class="doctor-name">{doctor_name}</div>
                <div class="specialty">{specialty}</div>
                <div class="crm">{doctor_crm}</div>
                <div class="contact">{address}</div>
                <div class="contact">Tel: {phone}</div>
            </div>
        </div>
        """

    elif layout == "two-column-left":
        return f"""
        <div class="header header-two-col">
            <div class="doctor-info">
                <div class="doctor-name">{doctor_name}</div>
                <div class="specialty">{specialty}</div>
            </div>
            <div class="contact-info">
                <div class="crm">{doctor_crm}</div>
                <div class="contact">{address}</div>
                <div class="contact">{phone}</div>
            </div>
        </div>
        """

    elif layout == "header-box":
        return f"""
        <div class="header header-box">
            <div class="doctor-name">{doctor_name}</div>
            <div class="specialty-crm">{specialty} · {doctor_crm}</div>
            <div class="contact">{address} · {phone}</div>
        </div>
        """

    elif layout == "simple-top":
        return f"""
        <div class="header header-simple">
            <div class="doctor-name">{doctor_name}</div>
            <div class="crm">{doctor_crm} — {specialty}</div>
            <div class="contact">{address}</div>
        </div>
        """

    else:
        # Fallback
        return f"""
        <div class="header header-centered">
            <div class="doctor-name">{doctor_name}</div>
            <div class="specialty">{specialty}</div>
            <div class="crm">{doctor_crm}</div>
        </div>
        """


def _build_css(style: dict, use_handwriting: bool) -> str:
    """Constrói o CSS baseado no estilo do médico."""
    font_body = style["font_body"]
    font_size = style["font_size_body"]
    primary = style["primary_color"]
    accent = style["accent_color"]
    paper = style["paper_color"]
    border_style = style["border_style"]

    # Body font: handwriting se aplicável
    body_font = "'Caveat', cursive" if use_handwriting else font_body
    body_size = "16pt" if use_handwriting else font_size
    body_lineheight = "1.6" if use_handwriting else "1.4"

    # Borders
    border_css = {
        "none": "",
        "double-top": f"border-top: 3px double {accent};",
        "thin-left": f"border-left: 4px solid {accent}; padding-left: 15px;",
        "double-separator": f"border-bottom: 3px double {accent}; padding-bottom: 12px;",
        "rounded-box": f"border: 1px solid {accent}; border-radius: 12px; padding: 15px;",
        "double-bottom": f"border-bottom: 3px double {accent};",
        "thin-all": f"border: 1px solid #cccccc; padding: 12px; border-radius: 4px;",
        "horizontal-lines": f"border-bottom: 2px solid {accent}; padding-bottom: 8px;",
        "symmetric": f"border-top: 1px solid {accent}; border-bottom: 1px solid {accent}; padding: 10px 0;",
    }.get(border_style, "")

    return f"""
    @page {{
        size: A5;
        margin: 0;
    }}
    * {{
        box-sizing: border-box;
        margin: 0;
        padding: 0;
    }}
    body {{
        font-family: {font_body};
        font-size: {font_size};
        color: {primary};
        background: {paper};
        padding: 35px 30px;
        line-height: 1.4;
    }}
    .prescription-container {{
        width: 100%;
        min-height: 700px;
        display: flex;
        flex-direction: column;
    }}

    /* HEADER */
    .header {{
        {border_css}
        margin-bottom: 18px;
    }}
    .header-centered {{
        text-align: center;
    }}
    .header-left {{
        text-align: left;
    }}
    .header-left-logo {{
        display: flex;
        align-items: center;
        gap: 15px;
    }}
    .header-two-col {{
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 20px;
    }}
    .header-two-col .contact-info {{
        text-align: right;
        font-size: 9pt;
    }}
    .header-box {{
        background: #f5f5f5;
        padding: 14px 18px;
        text-align: center;
    }}
    .header-simple {{
        text-align: left;
    }}

    .logo {{
        width: 48px;
        height: 48px;
        border-radius: 50%;
        background: {accent};
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 20pt;
        font-weight: bold;
        margin: 0 auto 8px;
        flex-shrink: 0;
    }}
    .header-left-logo .logo {{
        margin: 0;
    }}

    .doctor-name {{
        font-size: 14pt;
        font-weight: bold;
        color: {primary};
        margin-bottom: 3px;
    }}
    .specialty {{
        font-size: 10pt;
        color: {accent};
        font-style: italic;
        margin-bottom: 3px;
    }}
    .crm {{
        font-size: 10pt;
        color: {primary};
        margin-bottom: 5px;
    }}
    .specialty-crm {{
        font-size: 10pt;
        color: {accent};
        margin-bottom: 5px;
    }}
    .contact {{
        font-size: 9pt;
        color: #555;
        line-height: 1.3;
    }}

    /* PATIENT INFO */
    .patient-info {{
        display: flex;
        justify-content: space-between;
        border-bottom: 1px solid #ccc;
        padding: 10px 0;
        margin-bottom: 20px;
        font-size: 11pt;
    }}
    .patient-info .label {{
        color: #555;
        margin-right: 5px;
    }}
    .patient-info .value {{
        font-weight: 600;
        color: {primary};
    }}

    /* RX SECTION */
    .rx-section {{
        display: flex;
        gap: 12px;
        flex-grow: 1;
        margin-bottom: 25px;
    }}
    .rx-symbol {{
        font-size: 28pt;
        color: {accent};
        font-weight: bold;
        line-height: 1;
        padding-top: 3px;
    }}
    .medications {{
        flex-grow: 1;
        font-family: {body_font};
        font-size: {body_size};
        line-height: {body_lineheight};
    }}
    .medication {{
        margin-bottom: 16px;
    }}
    .med-line-1 {{
        display: flex;
        gap: 8px;
        font-weight: {'400' if use_handwriting else '600'};
        margin-bottom: 2px;
    }}
    .med-marker {{
        flex-shrink: 0;
        min-width: 20px;
    }}
    .med-name {{
        flex-grow: 1;
    }}
    .med-dose {{
        font-weight: {'400' if use_handwriting else '700'};
    }}
    .med-line-2 {{
        margin-left: 28px;
        font-size: {'14pt' if use_handwriting else '10pt'};
        color: {'inherit' if use_handwriting else '#555'};
        margin-bottom: 2px;
    }}
    .med-line-3 {{
        margin-left: 28px;
        font-size: {'13pt' if use_handwriting else '9pt'};
        color: {'inherit' if use_handwriting else '#777'};
        font-style: {'normal' if use_handwriting else 'italic'};
    }}

    /* SIGNATURE */
    .signature-section {{
        margin-top: 30px;
        text-align: center;
    }}
    .signature-line {{
        width: 220px;
        height: 1px;
        background: {primary};
        margin: 40px auto 6px;
    }}
    .signature-name {{
        font-size: 10pt;
        font-weight: 600;
        color: {primary};
    }}
    .signature-crm {{
        font-size: 9pt;
        color: {accent};
    }}
    """


# ==============================================================================
# RENDERIZAÇÃO COM PLAYWRIGHT
# ==============================================================================

async def render_html_to_png(page, html: str, output_path: Path):
    """Renderiza HTML para PNG."""
    await page.set_content(html, wait_until="networkidle")
    # Espera fontes do Google Fonts carregarem
    await page.wait_for_timeout(1500)
    await page.screenshot(
        path=str(output_path),
        full_page=True,
        omit_background=False,
    )


async def main():
    # Caminhos
    script_dir = Path(__file__).parent
    dataset_path = script_dir / "ground_truth_dataset.json"
    images_dir = script_dir / "images"

    images_dir.mkdir(exist_ok=True)

    # Carrega o dataset
    if not dataset_path.exists():
        print(f"❌ ERRO: {dataset_path} não encontrado.")
        print(f"   Garanta que o ground_truth_dataset.json está na mesma pasta do script.")
        return

    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    all_prescriptions = data["prescriptions"]
    script_prescriptions = [p for p in all_prescriptions if p["production_method"] == "script"]

    print(f"📋 Dataset carregado: {len(all_prescriptions)} receitas")
    print(f"   • {len(script_prescriptions)} via script (vou gerar)")
    print()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(
            viewport={"width": 800, "height": 1130},  # A5-ish
            device_scale_factor=2,  # Qualidade 2x (retina)
        )
        page = await context.new_page()

        # ============================================
        # 1. Gerar as 15 receitas completas (script)
        # ============================================
        print("🎨 Gerando receitas via script...")
        for prescription in script_prescriptions:
            doctor_name = prescription["ground_truth"]["doctor_name"]
            style = DOCTOR_STYLES.get(doctor_name)

            if not style:
                print(f"   ⚠️  {prescription['prescription_id']}: médico '{doctor_name}' sem estilo definido — pulando")
                continue

            html = build_html(prescription, style)
            output_path = images_dir / f"{prescription['prescription_id']}.png"
            await render_html_to_png(page, html, output_path)
            print(f"   ✓ {prescription['prescription_id']}.png ({style['style_name']})")

        await context.close()
        await browser.close()

    print()
    print("✅ Concluído!")
    print(f"   Receitas completas: {images_dir.absolute()}")


if __name__ == "__main__":
    asyncio.run(main())
