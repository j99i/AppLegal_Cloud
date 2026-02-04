from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from decimal import Decimal

# ==========================================
# 1. USUARIOS Y CLIENTES
# ==========================================

class Usuario(AbstractUser):
    telefono = models.CharField(max_length=20, blank=True, null=True)
    puesto = models.CharField(max_length=100, blank=True, null=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    
    # Roles y Permisos
    rol = models.CharField(max_length=20, choices=[('admin', 'Administrador'), ('abogado', 'Abogado/Gestor'), ('cliente', 'Cliente')], default='abogado')
    clientes_asignados = models.ManyToManyField('Cliente', blank=True, related_name='abogados_asignados')
    
    # Permisos Granulares
    can_create_client = models.BooleanField(default=False)
    can_edit_client = models.BooleanField(default=False)
    can_delete_client = models.BooleanField(default=False)
    can_upload_files = models.BooleanField(default=True)
    can_view_documents = models.BooleanField(default=True)
    can_manage_users = models.BooleanField(default=False)
    
    # Accesos a Módulos
    access_finanzas = models.BooleanField(default=False)
    access_cotizaciones = models.BooleanField(default=True)
    access_contratos = models.BooleanField(default=True)
    access_disenador = models.BooleanField(default=False)
    access_agenda = models.BooleanField(default=True)

class Cliente(models.Model):
    nombre_empresa = models.CharField(max_length=200)
    nombre_contacto = models.CharField(max_length=200)
    email = models.EmailField()
    telefono = models.CharField(max_length=20)
    logo = models.ImageField(upload_to='logos_clientes/', blank=True, null=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    datos_extra = models.JSONField(default=dict, blank=True) # Campos dinámicos

    def __str__(self):
        return self.nombre_empresa
    
    @property
    def saldo_total_pendiente(self):
        total = self.cuentas.aggregate(t=models.Sum('saldo_pendiente'))['t']
        return total or 0

class DatosFiscales(models.Model):
    cliente = models.OneToOneField(Cliente, on_delete=models.CASCADE, related_name='datos_fiscales')
    razon_social = models.CharField(max_length=255)
    rfc = models.CharField(max_length=20)
    regimen_fiscal = models.CharField(max_length=100) # Código SAT (ej. 601)
    codigo_postal = models.CharField(max_length=10)
    uso_cfdi = models.CharField(max_length=100, default='G03') # Código SAT
    email_facturacion = models.EmailField(blank=True, null=True)

class CampoAdicional(models.Model):
    nombre = models.CharField(max_length=100)
    tipo = models.CharField(max_length=50, choices=[('texto', 'Texto'), ('fecha', 'Fecha'), ('numero', 'Número')])

# ==========================================
# 2. DRIVE (GESTIÓN DOCUMENTAL)
# ==========================================

class Carpeta(models.Model):
    nombre = models.CharField(max_length=200)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='carpetas_drive')
    padre = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subcarpetas')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    es_expediente = models.BooleanField(default=False)

    def __str__(self):
        return self.nombre

class Expediente(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='expedientes')
    carpeta = models.OneToOneField(Carpeta, on_delete=models.CASCADE, null=True, blank=True)
    num_expediente = models.CharField(max_length=50)
    titulo = models.CharField(max_length=200)
    estado = models.CharField(max_length=20, default='abierto', choices=[('abierto', 'Abierto'), ('cerrado', 'Cerrado'), ('suspendido', 'Suspendido')])
    fecha_apertura = models.DateTimeField(auto_now_add=True)

class Documento(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='documentos_cliente')
    carpeta = models.ForeignKey(Carpeta, on_delete=models.CASCADE, null=True, blank=True, related_name='documentos')
    archivo = models.FileField(upload_to='drive_clientes/')
    nombre_archivo = models.CharField(max_length=255)
    subido_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True)
    fecha_subida = models.DateTimeField(auto_now_add=True)
    
    # Papelera
    en_papelera = models.BooleanField(default=False)
    fecha_eliminacion = models.DateTimeField(null=True, blank=True)

# ==========================================
# 3. GESTIÓN (TAREAS Y BITÁCORA)
# ==========================================

class Tarea(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='tareas')
    titulo = models.CharField(max_length=200)
    fecha_limite = models.DateField(null=True, blank=True)
    prioridad = models.CharField(max_length=20, choices=[('baja', 'Baja'), ('media', 'Media'), ('alta', 'Alta')], default='media')
    completada = models.BooleanField(default=False)

class Bitacora(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    usuario = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True)
    accion = models.CharField(max_length=255)
    descripcion = models.TextField()
    fecha = models.DateTimeField(auto_now_add=True)

class Requisito(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='requisitos')
    nombre = models.CharField(max_length=200)
    categoria = models.CharField(max_length=100)
    estado = models.CharField(max_length=20, default='pendiente', choices=[('pendiente', 'Pendiente'), ('completado', 'Completado')])
    archivo_asociado = models.ForeignKey(Documento, on_delete=models.SET_NULL, null=True, blank=True)

# ==========================================
# 4. COTIZACIONES
# ==========================================

class Servicio(models.Model):
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    precio_base = models.DecimalField(max_digits=10, decimal_places=2)
    campos_dinamicos = models.JSONField(default=list, blank=True) 

    def __str__(self):
        return self.nombre

class Cotizacion(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True)
    prospecto_nombre = models.CharField(max_length=200, blank=True, null=True)
    prospecto_empresa = models.CharField(max_length=200, blank=True, null=True)
    prospecto_email = models.EmailField(blank=True, null=True)
    prospecto_telefono = models.CharField(max_length=20, blank=True, null=True)
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    validez_hasta = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=20, default='pendiente', choices=[('pendiente', 'Pendiente'), ('enviada', 'Enviada'), ('aceptada', 'Aceptada'), ('rechazada', 'Rechazada')])
    
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    iva = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    creado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True)
    cliente_convertido = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name='origen_cotizacion')
    
    aplicar_iva = models.BooleanField(default=True)
    porcentaje_iva = models.DecimalField(max_digits=5, decimal_places=2, default=16.00)

    def calcular_totales(self):
        self.subtotal = sum(item.subtotal for item in self.items.all())
        if self.aplicar_iva:
            self.iva = self.subtotal * (self.porcentaje_iva / 100)
        else:
            self.iva = 0
        self.total = self.subtotal + self.iva
        self.save()

class ItemCotizacion(models.Model):
    cotizacion = models.ForeignKey(Cotizacion, on_delete=models.CASCADE, related_name='items')
    servicio = models.ForeignKey(Servicio, on_delete=models.CASCADE)
    descripcion_personalizada = models.TextField(blank=True, null=True)
    cantidad = models.IntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    valores_adicionales = models.JSONField(default=dict, blank=True)

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario

class PlantillaMensaje(models.Model):
    nombre = models.CharField(max_length=100)
    asunto = models.CharField(max_length=200)
    cuerpo = models.TextField()

# ==========================================
# 5. GENERADOR DE CONTRATOS
# ==========================================

class VariableEstandar(models.Model):
    clave = models.CharField(max_length=100, unique=True)
    descripcion = models.CharField(max_length=200)
    origen = models.CharField(max_length=50, choices=[('sistema', 'Automático del Sistema'), ('manual', 'Entrada Manual')], default='manual')
    campo_bd = models.CharField(max_length=100, blank=True, null=True)

class Plantilla(models.Model):
    nombre = models.CharField(max_length=200)
    archivo = models.FileField(upload_to='plantillas_contratos/')
    fecha_subida = models.DateTimeField(auto_now_add=True)
    variables_detectadas = models.JSONField(default=list, blank=True)

# ==========================================
# 6. FINANZAS Y CONTABILIDAD
# ==========================================

class CuentaContable(models.Model):
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=100)
    tipo = models.CharField(max_length=20, choices=[('activo','Activo'), ('pasivo','Pasivo'), ('capital','Capital'), ('ingreso','Ingreso'), ('gasto','Gasto')])
    saldo_actual = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

class Poliza(models.Model):
    tipo = models.CharField(max_length=20, choices=[('ingreso','Ingreso'), ('egreso','Egreso'), ('diario','Diario')])
    fecha = models.DateField(auto_now_add=True)
    concepto = models.CharField(max_length=255)
    creada_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True)
    pago_relacionado = models.ForeignKey('Pago', on_delete=models.SET_NULL, null=True, blank=True)

class CuentaPorCobrar(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='cuentas')
    cotizacion = models.ForeignKey(Cotizacion, on_delete=models.SET_NULL, null=True, blank=True)
    concepto = models.CharField(max_length=255)
    monto_total = models.DecimalField(max_digits=12, decimal_places=2)
    saldo_pendiente = models.DecimalField(max_digits=12, decimal_places=2)
    fecha_emision = models.DateTimeField(auto_now_add=True)
    fecha_vencimiento = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=20, default='pendiente', choices=[('pendiente', 'Pendiente'), ('pagada', 'Pagada'), ('vencida', 'Vencida')])

class Pago(models.Model):
    cuenta = models.ForeignKey(CuentaPorCobrar, on_delete=models.CASCADE, related_name='pagos')
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    fecha_pago = models.DateTimeField(auto_now_add=True)
    metodo = models.CharField(max_length=50)
    referencia = models.CharField(max_length=100, blank=True, null=True)
    registrado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        total_pagado = sum(p.monto for p in self.cuenta.pagos.all())
        self.cuenta.saldo_pendiente = self.cuenta.monto_total - total_pagado
        if self.cuenta.saldo_pendiente <= 0:
            self.cuenta.estado = 'pagada'
            self.cuenta.saldo_pendiente = 0
        else:
            self.cuenta.estado = 'pendiente'
        self.cuenta.save()

class MovimientoContable(models.Model):
    poliza = models.ForeignKey(Poliza, on_delete=models.CASCADE, related_name='movimientos')
    cuenta = models.ForeignKey(CuentaContable, on_delete=models.CASCADE)
    debe = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    haber = models.DecimalField(max_digits=12, decimal_places=2, default=0)

class Remision(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    cotizacion = models.ForeignKey(Cotizacion, on_delete=models.CASCADE)
    folio = models.CharField(max_length=50, unique=True)
    monto_total = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_emision = models.DateTimeField(auto_now_add=True)
    archivo_pdf = models.FileField(upload_to='remisiones/')

class Factura(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    cotizaciones = models.ManyToManyField(Cotizacion, related_name='facturas_asociadas')
    folio_interno = models.CharField(max_length=50, unique=True)
    monto_total = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Datos del SAT
    uuid = models.CharField(max_length=50, blank=True, null=True)
    estado_sat = models.CharField(max_length=20, default='pendiente')
    
    # Archivos
    pdf_representacion = models.FileField(upload_to='pdf_sat/%Y/%m/', null=True, blank=True)
    # IMPORTANTE: Estos dos campos son necesarios para el código QR y XML que ya tenemos
    archivo_xml = models.FileField(upload_to='xml_sat/%Y/%m/', null=True, blank=True)
    qr_imagen = models.ImageField(upload_to='facturas/qr/', blank=True, null=True)

    fecha_timbrado = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.folio_interno} - {self.cliente}"

# ==========================================
# 7. AGENDA
# ==========================================

class Evento(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='eventos')
    titulo = models.CharField(max_length=200)
    inicio = models.DateTimeField()
    fin = models.DateTimeField(null=True, blank=True)
    descripcion = models.TextField(blank=True, null=True)
    tipo = models.CharField(max_length=20, choices=[('audiencia', 'Audiencia'), ('reunion', 'Reunión'), ('vencimiento', 'Vencimiento'), ('personal', 'Personal')], default='reunion')
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True)

    @property
    def color_hex(self):
        colores = {
            'audiencia': '#ef4444',
            'reunion': '#3b82f6',
            'vencimiento': '#f59e0b',
            'personal': '#10b981'
        }
        return colores.get(self.tipo, '#6b7280')