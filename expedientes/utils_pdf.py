import pdfplumber
import re

def extraer_datos_constancia(ruta_archivo):
    """
    Versión MEJORADA:
    - Valida que la Razón Social no sea una etiqueta (como 'Régimen Capital').
    - Busca en la misma línea y en la siguiente.
    """
    datos = {
        'rfc': '',
        'razon_social': '',
        'cp': '',
        'regimen': ''
    }
    
    try:
        with pdfplumber.open(ruta_archivo) as pdf:
            page = pdf.pages[0]
            text = page.extract_text()
            lines = text.split('\n')
            
            # 1. BUSCAR RFC (Mejorado para capturar espacios raros)
            match_rfc = re.search(r'RFC:?\s?([A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3})', text)
            if match_rfc:
                datos['rfc'] = match_rfc.group(1)

            # 2. BUSCAR RAZÓN SOCIAL (Lógica Inteligente)
            for i, line in enumerate(lines):
                if "Denominación/Razón Social" in line:
                    # CASO A: El nombre está en la misma línea (ej. "Razón Social: EMPRESA SA")
                    parts = line.split(':')
                    if len(parts) > 1 and len(parts[1].strip()) > 3:
                        candidate = parts[1].strip()
                    # CASO B: Está en la línea de abajo
                    elif i + 1 < len(lines):
                        candidate = lines[i+1].strip()
                    else:
                        candidate = ""

                    # FILTRO DE SEGURIDAD:
                    # Si capturamos una etiqueta del SAT por error, la descartamos
                    forbidden = ["Régimen", "Capital", "Fecha", "Datos", "RFC"]
                    if any(bad in candidate for bad in forbidden):
                        # Intentamos con la siguiente línea por si acaso hubo un salto raro
                        if i + 2 < len(lines):
                             candidate = lines[i+2].strip()
                    
                    # Si pasó el filtro, lo guardamos
                    if not any(bad in candidate for bad in forbidden):
                        datos['razon_social'] = candidate
                    break
            
            # 3. BUSCAR CÓDIGO POSTAL
            match_cp = re.search(r'Código Postal:?\s?(\d{5})', text)
            if match_cp:
                datos['cp'] = match_cp.group(1)

            # 4. BUSCAR RÉGIMEN FISCAL
            regimenes_map = {
                "General de Ley": "601",
                "Personas Morales con Fines": "603",
                "Sueldos y Salarios": "605",
                "Arrendamiento": "606",
                "Actividades Empresariales": "612",
                "Incorporación Fiscal": "621",
                "Simplificado de Confianza": "626",
                "RESICO": "626"
            }
            
            # Buscamos en todo el texto (unimos líneas para buscar frases completas)
            full_text_flat = " ".join(lines)
            for key, val in regimenes_map.items():
                if key in full_text_flat:
                    datos['regimen'] = val
                    break

    except Exception as e:
        print(f"Error leyendo PDF: {e}")
    
    return datos