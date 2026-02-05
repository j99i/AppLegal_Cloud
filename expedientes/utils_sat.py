import requests
import base64
import json
from django.conf import settings

def timbrar_con_facturama(factura_bd):
    """
    Conexión a Facturama CFDI 4.0 con Desglose de Impuestos, Descuentos y Redondeo
    """
    
    # 1. CONFIGURACIÓN DE URL
    if settings.FACTURAMA_SANDBOX:
        url_api = "https://apisandbox.facturama.mx/3/cfdis"
    else:
        url_api = "https://api.facturama.mx/3/cfdis"

    cliente = factura_bd.cliente

    # 2. VALIDACIONES DE DATOS
    rfc_receptor = cliente.rfc if cliente.rfc else "XAXX010101000"
    cp_receptor = cliente.codigo_postal if cliente.codigo_postal else "54948"
    regimen = cliente.regimen_fiscal if cliente.regimen_fiscal else "616"
    uso = cliente.uso_cfdi if cliente.uso_cfdi else "S01"
    nombre_fiscal = cliente.razon_social if cliente.razon_social else cliente.nombre_empresa.upper()

    # 3. MATEMÁTICA INVERSA (Cálculo con Descuentos)
    # El 'monto_total' en BD es lo que el cliente PAGA FINALMENTE (Neto).
    # El 'descuento' en BD es dinero que se le perdonó antes de impuestos.
    
    gran_total_pagar = float(factura_bd.monto_total)
    monto_descuento = float(factura_bd.descuento)

    # Paso A: Obtener la Base Gravable (El subtotal neto sobre el que se calcula IVA)
    # Fórmula: Base = TotalPagar / 1.16
    base_gravable = gran_total_pagar / 1.16
    
    # Paso B: Calcular el Subtotal Real (Precio de Lista antes de descuento)
    # Fórmula: Subtotal = Base + Descuento
    subtotal_real = base_gravable + monto_descuento
    
    # Paso C: Redondeos a 2 decimales (OBLIGATORIO PARA SAT)
    subtotal_redondeado = round(subtotal_real, 2)
    descuento_redondeado = round(monto_descuento, 2)
    base_redondeada = round(subtotal_redondeado - descuento_redondeado, 2) # Debe coincidir
    
    # Paso D: Calcular IVA sobre la base ya descontada
    iva_calculado = base_redondeada * 0.16
    iva_redondeado = round(iva_calculado, 2)
    
    # Paso E: Total de Línea (Para el XML)
    total_linea = round(base_redondeada + iva_redondeado, 2)

    cp_expedicion = "54948" 
    
    # 4. CONSTRUCCIÓN DEL PAYLOAD
    payload = {
        "CfdiType": "I",
        "PaymentForm": "03",
        "PaymentMethod": "PUE",
        "Currency": "MXN",
        "ExpeditionPlace": cp_expedicion,
        "Receiver": {
            "Rfc": rfc_receptor,
            "Name": nombre_fiscal,
            "CfdiUse": uso,
            "FiscalRegime": regimen,
            "TaxZipCode": cp_receptor
        },
        "Items": [
            {
                "ProductCode": "84111506",
                "TaxObject": "02",
                "Description": f"Servicios Profesionales - Folio: {factura_bd.folio_interno}",
                "UnitCode": "E48",
                "Quantity": 1,
                
                # VALORES CALCULADOS
                "UnitPrice": subtotal_redondeado, # Precio de lista
                "Discount": descuento_redondeado, # Descuento aplicado
                "Subtotal": subtotal_redondeado,  # Subtotal línea
                
                "Taxes": [
                    {
                        "Total": iva_redondeado,
                        "Name": "IVA",
                        "Base": base_redondeada, # Base tras descuento
                        "Rate": 0.16,
                        "IsRetention": False
                    }
                ],
                "Total": total_linea
            }
        ]
    }

    # 5. ENVÍO
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
            error_msg = f"Status {response.status_code}: {response.text}"
            try:
                error_json = response.json()
                if 'Message' in error_json: error_msg = error_json['Message']
                if 'ModelState' in error_json:
                    detalles = [f"{k}: {v[0]}" for k, v in error_json['ModelState'].items()]
                    if detalles: error_msg += " -> " + ", ".join(detalles)
            except: pass
            raise Exception(error_msg)

    except Exception as e:
        print(f"❌ ERROR CONEXIÓN: {e}")
        raise e