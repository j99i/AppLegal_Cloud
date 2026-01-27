import uuid
from decimal import Decimal
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import FileExtensionValidator
from django.utils import timezone

# ==========================================
# 1. USUARIOS Y PERMISOS
# ==========================================
class Usuario(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Perfil (Con null=True para evitar errores de base de datos)
    avatar = models.ImageField(upload_to='avatares/', null=True, blank=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    puesto = models.CharField(max_length=100, blank=True, null=True)

    # Roles
    CHOICES_ROL = (('admin', 'Administrador Master'), ('analista_sr', 'Abogado Senior'), ('analista_jr', 'Abogado Junior'))
    rol = models.CharField(max_length=20, choices=CHOICES_ROL, default='analista_jr', db_index=True)
    area = models.CharField(max_length=100, blank=True, null=True)
    
    # Permisos Operativos
    can_create_client = models.BooleanField(default=False, verbose_name="Crear Clientes")
    can_edit_client = models.BooleanField(default=False, verbose_name="Editar Clientes")
    can_delete_client = models.BooleanField(default=False, verbose_name="Eliminar Clientes")
    can_view_documents = models.BooleanField(default=True, verbose_name="Ver Documentos")
    can_upload_files = models.BooleanField(default=False, verbose_name="Subir Archivos")
    can_manage_users = models.BooleanField(default=False, verbose_name="Gestionar Usuarios")

    # Permisos de Módulos (Switches)
    access_finanzas = models.BooleanField(default=False, verbose_name="Acceso Finanzas")
    access_cotizaciones = models.BooleanField(default=False, verbose_name="Acceso Cotizaciones")
    access_contratos = models.BooleanField(default=False, verbose_name="Acceso Contratos")
    access_disenador = models.BooleanField(default=False, verbose_name="Acceso Diseñador")
    access_agenda = models.BooleanField(default=False, verbose_name="Acceso Agenda")

    # Seguridad Granular
    clientes_asignados = models.ManyToManyField('Cliente', blank=True, related_name='abogados_asignados')

    def save(self, *args, **kwargs):
        if self.rol == 'admin':
            self.is_staff = True
            self.is_superuser = True
            # Admin tiene TODO
            self.can_create_client = True
            self.can_edit_client = True
            self.can_delete_client = True
            self.can_upload_files = True
            self.can_manage_users = True
            self.access_finanzas = True
            self.access_cotizaciones = True
            self.access_contratos = True
            self.access_disenador = True
            self.access_agenda = True
        super().save(*args, **kwargs)

# ==========================================
# 2. CLIENTE Y CAMPOS DINÁMICOS
# ==========================================
class Cliente(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre_empresa = models.CharField(max_length=200, unique=True, db_index=True) # Optimizado
    nombre_contacto = models.CharField(max_length=200)
    telefono = models.CharField(max_length=20, blank=True)
    email = models.EmailField()
    logo = models.ImageField(upload_to='logos_clientes/', null=True, blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    datos_extra = models.JSONField(default=dict, blank=True) 

    def __str__(self):
        return self.nombre_empresa

class CampoAdicional(models.Model):
    TIPOS = (('text', 'Texto Corto'), ('textarea', 'Texto Largo'), ('date', 'Fecha'), ('number', 'Número'))
    nombre = models.CharField(max_length=100)
    tipo = models.CharField(max_length=20, choices=TIPOS, default='text')
    obligatorio = models.BooleanField(default=False)

# ==========================================
# 3. DRIVE
# ==========================================
class Carpeta(models.Model):
    nombre = models.CharField(max_length=255, db_index=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='carpetas_drive')
    padre = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subcarpetas')
    es_expediente = models.BooleanField(default=False)
    creada_el = models.DateTimeField(auto_now_add=True)

class Expediente(models.Model):
    ESTADOS = (('abierto', 'Abierto'), ('pausado', 'En Pausa'), ('finalizado', 'Finalizado'))
    cliente = models.ForeignKey(Cliente, related_name='expedientes', on_delete=models.CASCADE)
    carpeta = models.OneToOneField(Carpeta, on_delete=models.CASCADE, null=True, blank=True)
    num_expediente = models.CharField(max_length=50, unique=True, db_index=True)
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='abierto', db_index=True)
    prioridad = models.IntegerField(choices=((1, 'Baja'), (2, 'Media'), (3, 'Crítica')), default=2)
    creado_el = models.DateTimeField(auto_now_add=True)

class Documento(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='documentos_cliente')
    carpeta = models.ForeignKey(Carpeta, on_delete=models.CASCADE, related_name='documentos', null=True, blank=True)
    archivo = models.FileField(upload_to='drive_legal/%Y/%m/%d/')
    nombre_archivo = models.CharField(max_length=255, db_index=True)
    fecha_subida = models.DateTimeField(auto_now_add=True)
    subido_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True)

# ==========================================
# 4. GESTIÓN (TAREAS Y BITÁCORA)
# ==========================================
class Tarea(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='tareas')
    titulo = models.CharField(max_length=255)
    fecha_limite = models.DateField(db_index=True) # CLAVE PARA RECORDATORIOS
    completada = models.BooleanField(default=False, db_index=True)
    prioridad = models.CharField(max_length=10, default='media')
    creada_el = models.DateTimeField(auto_now_add=True)

class Bitacora(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    accion = models.CharField(max_length=50)
    descripcion = models.TextField()
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)

class Plantilla(models.Model):
    nombre = models.CharField(max_length=100)
    archivo = models.FileField(upload_to='plantillas_word/', validators=[FileExtensionValidator(allowed_extensions=['docx'])])
    fecha_subida = models.DateTimeField(auto_now_add=True)

class VariableEstandar(models.Model):
    clave = models.CharField(max_length=100, unique=True)
    descripcion = models.CharField(max_length=255)
    tipo = models.CharField(max_length=20, default='texto')
    origen = models.CharField(max_length=20, default='usuario')
    campo_bd = models.CharField(max_length=100, blank=True, null=True)

# ==========================================
# 5. COTIZACIONES
# ==========================================
class Servicio(models.Model):
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    precio_base = models.DecimalField(max_digits=10, decimal_places=2)

class PlantillaMensaje(models.Model):
    TIPOS = (('email', 'Correo'), ('whatsapp', 'WhatsApp'))
    tipo = models.CharField(max_length=20, choices=TIPOS)
    asunto = models.CharField(max_length=200, blank=True)
    cuerpo = models.TextField()
    imagen_cabecera = models.ImageField(upload_to='plantillas_img/', blank=True, null=True)

class Cotizacion(models.Model):
    ESTADOS = (('borrador', 'Borrador'), ('enviada', 'Enviada'), ('aceptada', 'Aceptada'), ('rechazada', 'Rechazada'))
    prospecto_nombre = models.CharField(max_length=200)
    prospecto_email = models.EmailField()
    prospecto_telefono = models.CharField(max_length=20)
    prospecto_empresa = models.CharField(max_length=200, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    validez_hasta = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='borrador')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    impuestos = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cliente_convertido = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True)
    creado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True)

    def calcular_totales(self):
        self.subtotal = sum(item.total for item in self.items.all())
        self.impuestos = self.subtotal * Decimal('0.16')
        self.total = self.subtotal + self.impuestos
        self.save()

class ItemCotizacion(models.Model):
    cotizacion = models.ForeignKey(Cotizacion, related_name='items', on_delete=models.CASCADE)
    servicio = models.ForeignKey(Servicio, on_delete=models.SET_NULL, null=True)
    descripcion_personalizada = models.TextField(blank=True)
    cantidad = models.IntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):
        self.total = self.cantidad * self.precio_unitario
        super().save(*args, **kwargs)
        self.cotizacion.calcular_totales()

# ==========================================
# 6. FINANZAS
# ==========================================
class CuentaPorCobrar(models.Model):
    ESTADOS = (('pendiente', 'Pendiente'), ('parcial', 'Parcial'), ('pagado', 'Pagado'))
    cliente = models.ForeignKey(Cliente, related_name='cuentas', on_delete=models.CASCADE)
    cotizacion = models.OneToOneField(Cotizacion, on_delete=models.SET_NULL, null=True, blank=True)
    concepto = models.CharField(max_length=200)
    monto_total = models.DecimalField(max_digits=12, decimal_places=2)
    monto_pagado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    saldo_pendiente = models.DecimalField(max_digits=12, decimal_places=2)
    fecha_emision = models.DateTimeField(auto_now_add=True)
    fecha_vencimiento = models.DateField(null=True, blank=True, db_index=True) # CLAVE PARA RECORDATORIOS
    estado = models.CharField(max_length=20, choices=ESTADOS, default='pendiente', db_index=True)

    def save(self, *args, **kwargs):
        self.saldo_pendiente = self.monto_total - self.monto_pagado
        self.estado = 'pagado' if self.saldo_pendiente <= 0 else ('parcial' if self.monto_pagado > 0 else 'pendiente')
        super().save(*args, **kwargs)

class Pago(models.Model):
    METODOS = (('transferencia', 'Transferencia'), ('efectivo', 'Efectivo'), ('tarjeta', 'Tarjeta'), ('cheque', 'Cheque'))
    cuenta = models.ForeignKey(CuentaPorCobrar, related_name='pagos', on_delete=models.CASCADE)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    fecha_pago = models.DateField(default=timezone.now)
    metodo = models.CharField(max_length=20, choices=METODOS)
    referencia = models.CharField(max_length=100, blank=True)
    comprobante = models.FileField(upload_to='comprobantes_pago/', null=True, blank=True)
    registrado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.cuenta.monto_pagado = sum(p.monto for p in self.cuenta.pagos.all())
        self.cuenta.save()

# ==========================================
# 7. AGENDA
# ==========================================
class Evento(models.Model):
    TIPOS = (('audiencia', 'Audiencia'), ('vencimiento', 'Vencimiento'), ('reunion', 'Reunión'), ('tramite', 'Trámite'), ('personal', 'Personal'))
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, null=True, blank=True, related_name='eventos')
    titulo = models.CharField(max_length=200)
    inicio = models.DateTimeField(db_index=True) # CLAVE PARA RECORDATORIOS
    fin = models.DateTimeField(null=True, blank=True)
    tipo = models.CharField(max_length=20, choices=TIPOS, default='reunion')
    descripcion = models.TextField(blank=True)
    completado = models.BooleanField(default=False)

    @property
    def color_hex(self):
        colores = {'audiencia': '#ef4444', 'vencimiento': '#f59e0b', 'reunion': '#3b82f6', 'tramite': '#10b981', 'personal': '#6b7280'}
        return colores.get(self.tipo, '#3b82f6')