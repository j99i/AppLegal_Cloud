import requests
import base64
import json
from django.conf import settings

def timbrar_con_facturama(factura_bd):
    """
    Conexión DIRECTA a Facturama CFDI 4.0
    Corregido: Agregado 'TaxObject' (ObjetoImp)
    """
    
    # URL API
    if settings.FACTURAMA_SANDBOX:
        url_api = "https://apisandbox.facturama.mx/3/cfdis"
    else:
        url_api = "https://api.facturama.mx/3/cfdis"

    # Datos Prueba
    rfc_receptor = "XAXX010101000"
    cp_prueba = "54948" 
    
    precio = float(factura_bd.monto_total)
    
    payload = {
        "CfdiType": "I",
        "PaymentForm": "03",
        "PaymentMethod": "PUE",
        "Currency": "MXN",
        "ExpeditionPlace": cp_prueba,
        "Receiver": {
            "Rfc": rfc_receptor,
            "Name": factura_bd.cliente.nombre_empresa.upper(),
            "CfdiUse": "S01",
            "FiscalRegime": "616",
            "TaxZipCode": cp_prueba
        },
        "Items": [
            {
                "ProductCode": "84111506",
                "TaxObject": "02",  # <--- ¡AQUÍ ESTABA EL FALTANTE! (02 = Sí objeto de impuesto)
                "Description": f"Servicios Profesionales - Ref: {factura_bd.folio_interno}",
                "UnitCode": "E48",
                "Quantity": 1,
                "UnitPrice": precio, 
                "Subtotal": precio,
                "Taxes": [
                    {
                        "Total": 0,
                        "Name": "IVA",
                        "Base": precio,
                        "Rate": 0,
                        "IsRetention": False
                    }
                ],
                "Total": precio
            }
        ]
    }

    try:
        response = requests.post(
            url_api, 
            auth=(settings.FACTURAMA_USER, settings.FACTURAMA_PASS), 
            json=payload,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 201:
            return response.json()
        else:
            error_msg = response.text
            try:
                error_json = response.json()
                if 'Message' in error_json:
                    error_msg = error_json['Message']
                if 'ModelState' in error_json:
                    detalles = []
                    for k, v in error_json['ModelState'].items():
                        detalles.append(f"{k}: {v[0]}")
                    if detalles:
                        error_msg += " -> " + ", ".join(detalles)
            except:
                pass
            raise Exception(f"Rechazo del SAT: {error_msg}")

    except Exception as e:
        print(f"❌ ERROR CONEXIÓN: {e}")
        raise e