import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models

class Usuario(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    CHOICES_ROL = (
        ('admin', 'Administrador Master'), 
        ('analista_sr', 'Analista Senior'), 
        ('analista_jr', 'Analista Junior')
    )
    rol = models.CharField(max_length=20, choices=CHOICES_ROL, default='analista_jr')
    area = models.CharField(max_length=100, blank=True, null=True)
    
    # Permisos granulares originales
    can_create_client = models.BooleanField(default=False)
    can_edit_client = models.BooleanField(default=False)
    can_delete_client = models.BooleanField(default=False)
    can_view_documents = models.BooleanField(default=True)
    can_upload_files = models.BooleanField(default=False)
    can_manage_users = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.rol == 'admin':
            self.is_staff = True
            self.is_superuser = True
            self.can_create_client = True
            self.can_edit_client = True
            self.can_delete_client = True
            self.can_upload_files = True
            self.can_manage_users = True
        super().save(*args, **kwargs)

class Cliente(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre_empresa = models.CharField(max_length=200, unique=True)
    nombre_contacto = models.CharField(max_length=200)
    telefono = models.CharField(max_length=20, blank=True)
    email = models.EmailField()
    logo = models.ImageField(upload_to='logos_clientes/', null=True, blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre_empresa

class Carpeta(models.Model):
    nombre = models.CharField(max_length=255)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='carpetas_drive')
    padre = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subcarpetas')
    es_expediente = models.BooleanField(default=False)
    creada_el = models.DateTimeField(auto_now_add=True)

class Expediente(models.Model):
    ESTADOS = (('abierto', 'Abierto'), ('pausado', 'En Pausa'), ('finalizado', 'Finalizado'))
    cliente = models.ForeignKey(Cliente, related_name='expedientes', on_delete=models.CASCADE)
    carpeta = models.OneToOneField(Carpeta, on_delete=models.CASCADE, null=True, blank=True)
    num_expediente = models.CharField(max_length=50, unique=True)
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='abierto')
    prioridad = models.IntegerField(choices=((1, 'Baja'), (2, 'Media'), (3, 'Crítica')), default=2)
    creado_el = models.DateTimeField(auto_now_add=True)

class Documento(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='documentos_cliente')
    carpeta = models.ForeignKey(Carpeta, on_delete=models.CASCADE, related_name='documentos', null=True, blank=True)
    archivo = models.FileField(upload_to='drive_legal/%Y/%m/%d/')
    nombre_archivo = models.CharField(max_length=255)
    fecha_subida = models.DateTimeField(auto_now_add=True)
    subido_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True)

class Tarea(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='tareas')
    titulo = models.CharField(max_length=255)
    fecha_limite = models.DateField()
    completada = models.BooleanField(default=False)
    prioridad = models.CharField(max_length=10, default='media')
    creada_el = models.DateTimeField(auto_now_add=True)

class Bitacora(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    accion = models.CharField(max_length=50)
    descripcion = models.TextField()
    fecha = models.DateTimeField(auto_now_add=True)