from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from .models import (
    Cliente, Carpeta, Requisito, Documento, 
    Pago, Poliza, MovimientoContable, CuentaContable
)

# ==============================================================================
# 1. AUTOMATIZACIÓN AL CREAR CLIENTE (Genera Carpetas y Semáforos en Rojo)
# ==============================================================================
@receiver(post_save, sender=Cliente)
def crear_estructura_inicial_cliente(sender, instance, created, **kwargs):
    if created:
        estructura_requisitos = {
            "Licencia": [
                "Acta Constitutiva",
                "Poder Notarial",
                "Constancia de Situación Fiscal",
                "INE Representante"
            ],
            "Funcionamiento": [
                "Uso de Suelo",
                "Predial Actualizado",
                "Croquis de Ubicación",
                "VoBo de Ecología (si aplica)"
            ],
            "Protección Civil": [
                "Visto Bueno de Bomberos",
                "Dictamen Eléctrico",
                "Programa Interno de PC",
                "Capacitación de Personal",
                "Póliza de Seguro RC"
            ],
            "Cotizaciones": [] 
        }

        for carpeta_nombre, lista_papeles in estructura_requisitos.items():
            Carpeta.objects.get_or_create(
                nombre=carpeta_nombre,
                cliente=instance,
                padre=None,
                es_expediente=False
            )

            for papel in lista_papeles:
                Requisito.objects.create(
                    cliente=instance,
                    categoria=carpeta_nombre,
                    nombre=papel,
                    estado='pendiente'
                )

# ==============================================================================
# 2. SEGURIDAD: SI VA A PAPELERA -> SEMÁFORO ROJO
# ==============================================================================
@receiver(post_save, sender=Documento)
def actualizar_requisito_papelera(sender, instance, **kwargs):
    if instance.en_papelera:
        requisitos = Requisito.objects.filter(archivo_asociado=instance)
        for req in requisitos:
            req.estado = 'pendiente'
            req.archivo_asociado = None
            req.save()

# ==============================================================================
# 3. SEGURIDAD: SI SE BORRA DEFINITIVO -> SEMÁFORO ROJO
# ==============================================================================
@receiver(pre_delete, sender=Documento)
def reactivar_requisito_borrado_total(sender, instance, **kwargs):
    requisitos = Requisito.objects.filter(archivo_asociado=instance)
    for req in requisitos:
        req.estado = 'pendiente'
        req.archivo_asociado = None
        req.save()

# ==============================================================================
# 4. CONTABILIDAD AUTOMÁTICA (El Contador Digital)
# ==============================================================================
@receiver(post_save, sender=Pago)
def generar_poliza_ingreso_automatico(sender, instance, created, **kwargs):
    """
    Cada vez que se registra un PAGO, se crea una Póliza de Ingreso.
    Asiento: Cargo a Bancos / Abono a Clientes.
    """
    if created:
        try:
            # 1. Intentamos obtener las cuentas contables BASE
            # NOTA: Debes crear estas cuentas en tu Admin de Django primero
            cuenta_bancos = CuentaContable.objects.get(codigo="102-01-000") # Ejemplo: Banamex
            cuenta_clientes = CuentaContable.objects.get(codigo="105-01-000") # Clientes Nacionales
            
            # 2. Crear la Póliza (Cabecera)
            nombre_cliente = instance.cuenta.cliente.nombre_empresa
            poliza = Poliza.objects.create(
                tipo='ingreso',
                concepto=f"Cobro a {nombre_cliente} - Ref: {instance.referencia}",
                pago_relacionado=instance,
                creada_por=instance.registrado_por
            )

            # 3. Movimiento 1: CARGO A BANCOS (Entra Dinero)
            MovimientoContable.objects.create(
                poliza=poliza,
                cuenta=cuenta_bancos,
                debe=instance.monto,
                haber=0,
                referencia=f"Pago {instance.metodo}"
            )
            
            # Actualizar saldo cuenta bancos
            cuenta_bancos.saldo_actual += instance.monto
            cuenta_bancos.save()

            # 4. Movimiento 2: ABONO A CLIENTES (Disminuye deuda)
            MovimientoContable.objects.create(
                poliza=poliza,
                cuenta=cuenta_clientes,
                debe=0,
                haber=instance.monto,
                referencia=f"Cobro factura"
            )
            
            # Actualizar saldo cuenta clientes (Abono resta en activos, pero simplifiquemos saldo por ahora)
            cuenta_clientes.saldo_actual -= instance.monto 
            cuenta_clientes.save()

            print(f"✅ Póliza de Ingreso #{poliza.id} generada automáticamente para {nombre_cliente}")

        except CuentaContable.DoesNotExist:
            print("⚠️ ADVERTENCIA CONTABLE: No se generó la póliza porque faltan las cuentas '102-01-000' o '105-01-000' en el sistema.")
        except Exception as e:
            print(f"❌ ERROR CONTABLE: {str(e)}")