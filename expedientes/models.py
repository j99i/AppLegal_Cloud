from django.contrib.auth.models import AbstractUser
from django.db import models

class Usuario(AbstractUser):
    CHOICES_ROL = (('admin', 'Administrador Master'), ('analista_sr', 'Analista Senior'), ('analista_jr', 'Analista Junior'))
    rol = models.CharField(max_length=20, choices=CHOICES_ROL, default='analista_jr')
    area = models.CharField(max_length=100, blank=True, null=True)
    can_create_client = models.BooleanField(default=False)
    can_edit_client = models.BooleanField(default=False)
    can_delete_client = models.BooleanField(default=False)
    can_view_documents = models.BooleanField(default=True)
    can_upload_files = models.BooleanField(default=False)
    can_manage_users = models.BooleanField(default=False)

class Cliente(models.Model):
    nombre_empresa = models.CharField(max_length=200, unique=True)
    nombre_contacto = models.CharField(max_length=200)
    telefono = models.CharField(max_length=20, blank=True)
    email = models.EmailField()
    logo = models.ImageField(upload_to='logos_clientes/', null=True, blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

class Expediente(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='expedientes')
    titulo = models.CharField(max_length=250)
    num_expediente = models.CharField(max_length=100, unique=True)
    estado = models.CharField(max_length=20, choices=(('abierto', 'Abierto'), ('en_proceso', 'En Proceso'), ('cerrado', 'Cerrado')), default='abierto')
    prioridad = models.IntegerField(default=1) 
    creado_el = models.DateTimeField(auto_now_add=True)

class Documento(models.Model):
    expediente = models.ForeignKey(Expediente, on_delete=models.CASCADE, related_name='documentos')
    archivo = models.FileField(upload_to='expedientes_digitales/')
    nombre_archivo = models.CharField(max_length=255)
    subido_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True)
    fecha_subida = models.DateTimeField(auto_now_add=True)

class Bitacora(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    accion = models.CharField(max_length=255)
    fecha = models.DateTimeField(auto_now_add=True)
    descripcion = models.TextField()