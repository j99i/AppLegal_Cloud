from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout, login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import *
from django.http import JsonResponse

# --- SESIÓN Y REGISTRO ---
def signout(request):
    logout(request)
    return redirect('login')

def registro(request):
    if request.method == 'POST':
        try:
            Usuario.objects.create_user(
                username=request.POST.get('username'),
                email=request.POST.get('email'),
                password=request.POST.get('pass1'),
                is_active=False
            )
            return render(request, 'registro_pendiente.html')
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return render(request, 'registro.html')

# --- GESTIÓN DE USUARIOS (Tus originales) ---
@login_required
def gestion_usuarios(request):
    if request.user.rol != 'admin': return redirect('dashboard')
    usuarios = Usuario.objects.all().order_by('-date_joined')
    return render(request, 'gestion_usuarios.html', {'usuarios': usuarios})

@login_required
def autorizar_usuario(request, user_id):
    user = get_object_or_404(Usuario, id=user_id)
    user.is_active = True
    user.save()
    return redirect('gestion_usuarios')

@login_required
def editar_usuario(request, user_id):
    user_obj = get_object_or_404(Usuario, id=user_id)
    if request.method == 'POST':
        user_obj.rol = request.POST.get('rol')
        user_obj.area = request.POST.get('area')
        user_obj.is_active = request.POST.get('is_active') == 'on'
        user_obj.save()
        return redirect('gestion_usuarios')
    return render(request, 'editar_usuario.html', {'user_obj': user_obj})

# --- CLIENTES Y DASHBOARD ---
@login_required
def dashboard(request):
    stats = {
        'total_clientes': Cliente.objects.count(),
        'expedientes_abiertos': Expediente.objects.filter(estado='abierto').count(),
        'prioridad_critica': Expediente.objects.filter(prioridad=3).count()
    }
    pendientes = Usuario.objects.filter(is_active=False).count()
    return render(request, 'dashboard.html', {
        'clientes': Cliente.objects.all().order_by('-fecha_registro'),
        'stats': stats,
        'usuarios_pendientes_conteo': pendientes
    })

@login_required
def nuevo_cliente(request):
    if request.method == 'POST':
        Cliente.objects.create(
            nombre_empresa=request.POST.get('nombre_empresa'),
            nombre_contacto=request.POST.get('nombre_contacto'),
            email=request.POST.get('email'),
            telefono=request.POST.get('telefono'),
            logo=request.FILES.get('logo')
        )
        return redirect('dashboard')
    return render(request, 'nuevo_cliente.html')

@login_required
def detalle_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    carpetas = cliente.carpetas_drive.filter(padre__isnull=True)
    expedientes = cliente.expedientes.all()
    tareas = cliente.tareas.all().order_by('fecha_limite')
    bitacora = Bitacora.objects.filter(cliente=cliente).order_by('-fecha')[:10]
    return render(request, 'detalle_cliente.html', {
        'cliente': cliente, 'carpetas': carpetas, 'expedientes': expedientes,
        'tareas': tareas, 'bitacora_cliente': bitacora
    })

# --- LEGAL DRIVE Y EXPEDIENTES ---
@login_required
def crear_carpeta(request, cliente_id):
    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        Carpeta.objects.create(nombre=nombre, cliente_id=cliente_id)
    return redirect('detalle_cliente', cliente_id=cliente_id)

@login_required
def crear_expediente(request, cliente_id):
    if request.method == 'POST':
        num = request.POST.get('num_expediente')
        tit = request.POST.get('titulo')
        # Crear Carpeta Automática
        folder = Carpeta.objects.create(nombre=f"EXP {num}: {tit}", cliente_id=cliente_id, es_expediente=True)
        Expediente.objects.create(cliente_id=cliente_id, num_expediente=num, titulo=tit, carpeta=folder)
    return redirect('detalle_cliente', cliente_id=cliente_id)

@login_required
def subir_archivo_drive(request, cliente_id):
    if request.method == 'POST':
        archivo = request.FILES.get('archivo')
        c_id = request.POST.get('carpeta_id')
        Documento.objects.create(
            cliente_id=cliente_id, archivo=archivo, 
            nombre_archivo=archivo.name, carpeta_id=c_id if c_id else None,
            subido_por=request.user
        )
        Bitacora.objects.create(usuario=request.user, cliente_id=cliente_id, accion='subida', descripcion=f"Subió {archivo.name}")
    return redirect('detalle_cliente', cliente_id=cliente_id)

@login_required
def gestionar_tarea(request, cliente_id):
    if request.method == 'POST':
        Tarea.objects.create(
            cliente_id=cliente_id, titulo=request.POST.get('titulo'),
            fecha_limite=request.POST.get('fecha_limite'), prioridad=request.POST.get('prioridad')
        )
    return redirect('detalle_cliente', cliente_id=cliente_id)

@login_required
def eliminar_archivo_drive(request, archivo_id):
    doc = get_object_or_404(Documento, id=archivo_id)
    c_id = doc.cliente.id
    doc.archivo.delete()
    doc.delete()
    return redirect('detalle_cliente', cliente_id=c_id)

@login_required
def eliminar_cliente(request, cliente_id):
    # Verificamos que solo el admin pueda borrar clientes
    if request.user.rol != 'admin':
        messages.error(request, "No tienes permisos para eliminar clientes.")
        return redirect('dashboard')
        
    cliente = get_object_or_404(Cliente, id=cliente_id)
    nombre = cliente.nombre_empresa
    cliente.delete()
    
    messages.success(request, f"El cliente '{nombre}' y todos sus datos han sido eliminados.")
    return redirect('dashboard')