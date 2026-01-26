from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Cliente, Expediente, Documento, Usuario, Bitacora

def signout(request):
    """Cierra la sesión de forma segura evitando el error 405"""
    logout(request)
    return redirect('login')

@login_required
def dashboard(request):
    stats = {
        'total_clientes': Cliente.objects.count(),
        'expedientes_abiertos': Expediente.objects.filter(estado='abierto').count(),
        'prioridad_critica': Expediente.objects.filter(prioridad=3).count()
    }
    context = {
        'clientes': Cliente.objects.all().order_by('-fecha_registro'),
        'stats': stats,
    }
    if request.user.rol == 'admin' or request.user.can_manage_users:
        context['usuarios_pendientes'] = Usuario.objects.filter(is_active=False)
    return render(request, 'dashboard.html', context)

def registro(request):
    if request.method == 'POST':
        Usuario.objects.create_user(
            username=request.POST.get('username'),
            email=request.POST.get('email'),
            password=request.POST.get('pass1'),
            is_active=False
        )
        return render(request, 'registro_pendiente.html')
    return render(request, 'registro.html')

@login_required
def detalle_cliente(request, cliente_id):
    if not request.user.can_view_documents:
        messages.error(request, "Acceso denegado a expedientes.")
        return redirect('dashboard')
    cliente = get_object_or_404(Cliente, id=cliente_id)
    expedientes = cliente.expedientes.all()
    return render(request, 'detalle_cliente.html', {'cliente': cliente, 'expedientes': expedientes})

@login_required
def nuevo_cliente(request):
    if not request.user.can_create_client:
        messages.error(request, "No tienes permiso para registrar clientes.")
        return redirect('dashboard')
    if request.method == 'POST':
        Cliente.objects.create(
            nombre_empresa=request.POST.get('nombre_empresa'),
            nombre_contacto=request.POST.get('nombre_contacto'),
            email=request.POST.get('email'),
            logo=request.FILES.get('logo')
        )
        return redirect('dashboard')
    return render(request, 'nuevo_cliente.html')

@login_required
def subir_archivo(request, expediente_id):
    if not request.user.can_upload_files:
        messages.error(request, "No tienes permiso para subir archivos.")
        return redirect('dashboard')
    if request.method == 'POST':
        expediente = get_object_or_404(Expediente, id=expediente_id)
        Documento.objects.create(
            expediente=expediente,
            archivo=request.FILES.get('archivo'),
            nombre_archivo=request.POST.get('nombre_archivo'),
            subido_por=request.user
        )
        return redirect('detalle_cliente', cliente_id=expediente.cliente.id)

@login_required
def autorizar_usuario(request, user_id):
    if request.user.rol == 'admin' or request.user.can_manage_users:
        u = get_object_or_404(Usuario, id=user_id)
        u.is_active = True
        u.save()
        messages.success(request, f"Acceso concedido a {u.username}")
    return redirect('dashboard')