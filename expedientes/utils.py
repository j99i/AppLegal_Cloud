# ==========================================
# EXPEDIENTES/UTILS.PY - FUNCIONES UTILITARIAS
# ==========================================
import logging
from django.http import HttpResponse
from django.template.loader import render_to_string
import weasyprint

logger = logging.getLogger(__name__)


def generar_pdf_response(request, template_name, context, filename, disposition='inline'):
    """
    Genera un HttpResponse con un PDF renderizado desde un template HTML.
    
    Uso:
        return generar_pdf_response(request, 'cotizaciones/pdf_template.html', {'c': cotizacion}, 'Cotizacion_1.pdf')
    
    Args:
        request:       HttpRequest de Django (necesario para build_absolute_uri).
        template_name: Ruta del template HTML a renderizar.
        context:       Diccionario de contexto para el template.
        filename:      Nombre del archivo PDF de salida.
        disposition:   'inline' para ver en navegador, 'attachment' para forzar descarga.
    
    Returns:
        HttpResponse con content_type 'application/pdf'.
    """
    try:
        base_url = request.build_absolute_uri('/')
        
        # Inyectar base_url en el contexto para que los templates puedan usarlo
        context['base_url'] = base_url
        
        html_string = render_to_string(template_name, context)
        
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
        
        weasyprint.HTML(string=html_string, base_url=base_url).write_pdf(response)
        
        return response
    
    except Exception as e:
        logger.error(f"Error generando PDF '{filename}' con template '{template_name}': {e}")
        raise


def generar_pdf_bytes(request, template_name, context):
    """
    Genera el contenido de un PDF como bytes (útil para adjuntar en correos o guardar en BD).
    
    Uso:
        pdf_content = generar_pdf_bytes(request, 'cotizaciones/pdf_template.html', {'c': cotizacion})
        email.attach('archivo.pdf', pdf_content, 'application/pdf')
    
    Args:
        request:       HttpRequest de Django.
        template_name: Ruta del template HTML.
        context:       Diccionario de contexto.
    
    Returns:
        bytes con el contenido del PDF.
    """
    try:
        base_url = request.build_absolute_uri('/')
        context['base_url'] = base_url
        
        html_string = render_to_string(template_name, context)
        pdf_bytes = weasyprint.HTML(string=html_string, base_url=base_url).write_pdf()
        
        return pdf_bytes
    
    except Exception as e:
        logger.error(f"Error generando PDF bytes con template '{template_name}': {e}")
        raise