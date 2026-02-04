import os
import json
import zipfile
import uuid
from io import BytesIO
from datetime import timedelta, datetime
from decimal import Decimal 
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.text import slugify 
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.conf import settings 
from django.urls import reverse
from email.mime.image import MIMEImage
from .utils_pdf import extraer_datos_constancia
# --- NUEVA LIBRERÍA PARA EL QR ---
import qrcode
# ---------------------------------

from django.db import models
from django.db.models import Sum, Count, Q
from django.db.models.functions import Coalesce

from .utils_sat import timbrar_con_facturama
import base64

# Librerías de Procesamiento de Documentos
from docxtpl import DocxTemplate
import mammoth
from docx import Document as DocumentoWord 
import weasyprint 

# Importación de TODOS los Modelos
from .models import (
    Usuario, Cliente, Carpeta, Expediente, Documento, 
    Tarea, Bitacora, Plantilla, VariableEstandar,
    Servicio, Cotizacion, ItemCotizacion, PlantillaMensaje,
    CuentaPorCobrar, Pago, Evento, CampoAdicional,
    Requisito, Poliza, MovimientoContable, CuentaContable, 
    Factura, DatosFiscales, Remision
)

# ==========================================
# 0. HELPER FUNCTIONS (UTILIDADES)
# ==========================================

def generar_y_guardar_pdf_drive(cotizacion, usuario):
    html = render_to_string('cotizaciones/pdf_template.html', {'c': cotizacion, 'base_url': str(settings.BASE_DIR)})
    pdf_file = weasyprint.HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    
    nombre_archivo = f"Cotizacion_{cotizacion.id}_{slugify(cotizacion.prospecto_empresa or cotizacion.prospecto_nombre)}.pdf"
    cliente = cotizacion.cliente or cotizacion.cliente_convertido

    if cliente:
        carpeta, _ = Carpeta.objects.get_or_create(nombre="Cotizaciones", cliente=cliente, padre=None)
        if not Documento.objects.filter(carpeta=carpeta, nombre_archivo=nombre_archivo).exists():
            doc = Documento(cliente=cliente, carpeta=carpeta, nombre_archivo=nombre_archivo, subido_por=usuario)
            doc.archivo.save(nombre_archivo, ContentFile(pdf_file))
            doc.save()
            
    return pdf_file

# ==========================================
# 1. AUTENTICACIÓN Y PERFIL
# ==========================================

def signout(request):
    logout(request)
    return redirect('login')

def registro(request):
    if request.method == 'POST':
        try:
            if Usuario.objects.filter(username=request.POST.get('username')).exists():
                messages.error(request, "El usuario ya existe.")
                return render(request, 'registro.html')

            Usuario.objects.create_user(
                username=request.POST.get('username'), 
                email=request.POST.get('email'), 
                password=request.POST.get('pass1'),
                first_name=request.POST.get('first_name'), 
                last_name=request.POST.get('last_name'), 
                is_active=False
            )
            return render(request, 'registro_pendiente.html')
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return render(request, 'registro.html')

@login_required
def mi_perfil(request):
    user = request.user
    if request.method == 'POST':
        user.first_name = request.POST.get('first_name')
        user.last_name = request.POST.get('last_name')
        user.email = request.POST.get('email')
        user.telefono = request.POST.get('telefono')
        user.puesto = request.POST.get('puesto')
        if request.FILES.get('avatar'):
            user.avatar = request.FILES['avatar']
        user.save()
        messages.success(request, "Perfil actualizado.")
    return render(request, 'usuarios/mi_perfil.html', {'user': user})

# ==========================================
# 2. GESTIÓN DE USUARIOS (ADMIN)
# ==========================================

@login_required
def gestion_usuarios(request):
    if request.user.rol != 'admin': return redirect('dashboard')
    return render(request, 'gestion_usuarios.html', {'usuarios': Usuario.objects.all().order_by('-date_joined')})

@login_required
def autorizar_usuario(request, user_id):
    if request.user.rol != 'admin': return redirect('dashboard')
    u = get_object_or_404(Usuario, id=user_id)
    u.is_active = True; u.save()
    messages.success(request, "Usuario autorizado.")
    return redirect('gestion_usuarios')

@login_required
def editar_usuario(request, user_id):
    if request.user.rol != 'admin': return redirect('dashboard')
    user_obj = get_object_or_404(Usuario, id=user_id)
    if request.method == 'POST':
        user_obj.rol = request.POST.get('rol')
        user_obj.first_name = request.POST.get('first_name')
        user_obj.last_name = request.POST.get('last_name')
        user_obj.email = request.POST.get('email')
        
        for field in ['can_create_client', 'can_edit_client', 'can_delete_client', 'can_upload_files', 'can_view_documents', 'can_manage_users', 'access_finanzas', 'access_cotizaciones', 'access_contratos', 'access_disenador', 'access_agenda']:
            setattr(user_obj, field, request.POST.get(field) == 'on')
            
        clientes_ids = request.POST.getlist('clientes_asignados')
        user_obj.save()
        
        if user_obj.rol != 'admin': user_obj.clientes_asignados.set(clientes_ids)
        else: user_obj.clientes_asignados.clear()
            
        messages.success(request, "Usuario actualizado.")
        return redirect('gestion_usuarios')
    return render(request, 'usuarios/editar_usuario.html', {'u': user_obj, 'clientes': Cliente.objects.all()})

@login_required
def eliminar_usuario(request, user_id):
    if request.user.rol != 'admin': return redirect('dashboard')
    u = get_object_or_404(Usuario, id=user_id)
    if u != request.user: u.delete()
    return redirect('gestion_usuarios')

# ==========================================
# 3. DASHBOARD Y CLIENTES
# ==========================================

@login_required
def dashboard(request):
    mis_clientes = Cliente.objects.all() if request.user.rol == 'admin' else request.user.clientes_asignados.all()
    
    stats = {
        'total_clientes': mis_clientes.count(),
        'expedientes_activos': Expediente.objects.filter(cliente__in=mis_clientes, estado='abierto').count(),
        'tareas_pendientes': Tarea.objects.filter(cliente__in=mis_clientes, completada=False).count(),
        'docs_subidos': Documento.objects.filter(cliente__in=mis_clientes, en_papelera=False).count()
    }
    hoy = timezone.now().date()
    tareas_criticas = Tarea.objects.filter(cliente__in=mis_clientes, completada=False, fecha_limite__lte=hoy)
    
    clientes = mis_clientes.annotate(urgencias=Count('tareas', filter=Q(tareas__prioridad='alta', tareas__completada=False))).order_by('-urgencias', '-fecha_registro')
    pendientes = Usuario.objects.filter(is_active=False).count() if request.user.rol == 'admin' else 0

    return render(request, 'dashboard.html', {'clientes': clientes, 'stats': stats, 'usuarios_pendientes_conteo': pendientes, 'alertas': {'tareas': tareas_criticas}})

@login_required
def nuevo_cliente(request):
    if not (request.user.rol == 'admin' or request.user.can_create_client): return redirect('dashboard')
    if request.method == 'POST':
        c = Cliente.objects.create(
            nombre_empresa=request.POST.get('nombre_empresa'),
            nombre_contacto=request.POST.get('nombre_contacto'),
            email=request.POST.get('email'),
            telefono=request.POST.get('telefono'),
            logo=request.FILES.get('logo')
        )
        if request.user.rol != 'admin': request.user.clientes_asignados.add(c)
        return redirect('dashboard')
    return render(request, 'nuevo_cliente.html')

@login_required
def eliminar_cliente(request, cliente_id):
    if request.user.rol != 'admin' and not request.user.can_delete_client: return redirect('dashboard')
    get_object_or_404(Cliente, id=cliente_id).delete()
    return redirect('dashboard')

@login_required
def detalle_cliente(request, cliente_id, carpeta_id=None):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    if request.user.rol != 'admin' and cliente not in request.user.clientes_asignados.all(): return redirect('dashboard')

    carpeta_actual = None
    breadcrumbs = []
    if carpeta_id:
        carpeta_actual = get_object_or_404(Carpeta, id=carpeta_id, cliente=cliente)
        crumb = carpeta_actual
        while crumb: breadcrumbs.insert(0, crumb); crumb = crumb.padre

    carpetas = cliente.carpetas_drive.filter(padre=carpeta_actual)
    documentos = cliente.documentos_cliente.filter(carpeta=carpeta_actual, en_papelera=False)

    stats = {'total_docs': cliente.documentos_cliente.filter(en_papelera=False).count(), 'expedientes_activos': cliente.expedientes.filter(estado='abierto').count()}
    requisitos = Requisito.objects.filter(cliente=cliente)
    req_por_cat = {}
    pendientes = 0
    for r in requisitos:
        req_por_cat.setdefault(r.categoria, []).append(r)
        if r.estado == 'pendiente': pendientes += 1

    return render(request, 'detalle_cliente.html', {
        'cliente': cliente, 'carpeta_actual': carpeta_actual, 'breadcrumbs': breadcrumbs,
        'carpetas': carpetas, 'documentos': documentos, 'stats_cliente': stats,
        'historial': Bitacora.objects.filter(cliente=cliente).order_by('-fecha'),
        'requisitos_por_cat': req_por_cat, 'total_pendientes': pendientes,
        'todas_carpetas': cliente.carpetas_drive.all()
    })

@login_required
def editar_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    if request.user.rol != 'admin' and cliente not in request.user.clientes_asignados.all(): return redirect('dashboard')
    
    if request.method == 'POST':
        cliente.nombre_empresa = request.POST.get('nombre_empresa')
        cliente.nombre_contacto = request.POST.get('nombre_contacto')
        cliente.email = request.POST.get('email')
        cliente.telefono = request.POST.get('telefono')
        if request.FILES.get('logo'): cliente.logo = request.FILES['logo']
        
        datos = cliente.datos_extra or {}
        for campo in CampoAdicional.objects.all():
            val = request.POST.get(f"custom_{campo.id}")
            if val: datos[campo.nombre] = val
        cliente.datos_extra = datos
        cliente.save()
        messages.success(request, "Cliente actualizado.")
        return redirect('detalle_cliente', cliente_id=cliente.id)
    return render(request, 'clientes/editar.html', {'c': cliente, 'campos_dinamicos': CampoAdicional.objects.all()})

@login_required
def guardar_datos_fiscales(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    datos_actuales, _ = DatosFiscales.objects.get_or_create(cliente=cliente)
    
    # Contexto inicial (por si solo carga la página)
    context = {
        'c': cliente,
        'datos': datos_actuales,
        # Catálogo básico de regímenes para el select
        'regimenes': [
            {'code': '601', 'name': '601 - General de Ley Personas Morales'},
            {'code': '605', 'name': '605 - Sueldos y Salarios'},
            {'code': '612', 'name': '612 - Personas Físicas con Actividades Empresariales'},
            {'code': '626', 'name': '626 - Régimen Simplificado de Confianza (RESICO)'},
            {'code': '616', 'name': '616 - Sin obligaciones fiscales'},
        ]
    }

    if request.method == 'POST':
        # CASO A: El usuario subió una Constancia (PDF) para auto-llenar
        if 'archivo_constancia' in request.FILES:
            archivo = request.FILES['archivo_constancia']
            if archivo.name.endswith('.pdf'):
                # Extraemos datos
                datos_extraidos = extraer_datos_constancia(archivo)
                
                # Actualizamos temporalmente el objeto 'datos' para que se vea en el formulario
                # OJO: No guardamos en BD todavía, solo prellenamos el form para que el usuario valide
                if datos_extraidos['rfc']: datos_actuales.rfc = datos_extraidos['rfc']
                if datos_extraidos['razon_social']: datos_actuales.razon_social = datos_extraidos['razon_social']
                if datos_extraidos['cp']: datos_actuales.codigo_postal = datos_extraidos['cp']
                if datos_extraidos['regimen']: datos_actuales.regimen_fiscal = datos_extraidos['regimen']
                
                messages.info(request, "¡Datos extraídos de la Constancia! Por favor verifica antes de guardar.")
            else:
                messages.error(request, "Por favor sube un archivo PDF válido.")
        
        # CASO B: El usuario dio click en "Guardar Datos"
        elif 'accion_guardar' in request.POST:
            datos_actuales.razon_social = request.POST.get('razon_social').upper()
            datos_actuales.rfc = request.POST.get('rfc').upper()
            datos_actuales.regimen_fiscal = request.POST.get('regimen_fiscal')
            datos_actuales.codigo_postal = request.POST.get('codigo_postal')
            datos_actuales.uso_cfdi = request.POST.get('uso_cfdi')
            datos_actuales.email_facturacion = request.POST.get('email_facturacion')
            datos_actuales.save()
            messages.success(request, "Datos fiscales actualizados correctamente.")
            return redirect('detalle_cliente', cliente_id=cliente.id)

    return render(request, 'clientes/datos_fiscales_form.html', context)
@login_required
def configurar_campos(request):
    if request.user.rol != 'admin': return redirect('dashboard')
    if request.method == 'POST':
        CampoAdicional.objects.create(nombre=request.POST.get('nombre'), tipo=request.POST.get('tipo'))
    return render(request, 'clientes/configurar_campos.html', {'campos': CampoAdicional.objects.all()})

@login_required
def eliminar_campo_dinamico(request, campo_id):
    if request.user.rol == 'admin': get_object_or_404(CampoAdicional, id=campo_id).delete()
    return redirect('configurar_campos')

# ==========================================
# 4. DRIVE & TAREAS
# ==========================================

@login_required
def crear_carpeta(request, cliente_id):
    if request.method == 'POST':
        padre_id = request.POST.get('padre_id')
        Carpeta.objects.create(nombre=request.POST.get('nombre'), cliente_id=cliente_id, padre_id=padre_id if padre_id else None)
        if padre_id: return redirect('detalle_carpeta', cliente_id=cliente_id, carpeta_id=padre_id)
    return redirect('detalle_cliente', cliente_id=cliente_id)

@login_required
def eliminar_carpeta(request, carpeta_id):
    if request.user.rol == 'admin' or request.user.can_delete_client:
        c = get_object_or_404(Carpeta, id=carpeta_id)
        url = 'detalle_carpeta' if c.padre else 'detalle_cliente'
        kwargs = {'cliente_id': c.cliente.id, 'carpeta_id': c.padre.id} if c.padre else {'cliente_id': c.cliente.id}
        c.delete()
        return redirect(url, **kwargs)
    return redirect('dashboard')

@login_required
def subir_archivo_drive(request, cliente_id):
    if request.method == 'POST':
        cliente = get_object_or_404(Cliente, id=cliente_id)
        carpeta_id = request.POST.get('carpeta_id')
        for f in request.FILES.getlist('archivo'):
            Documento.objects.create(cliente=cliente, carpeta_id=carpeta_id if carpeta_id else None, archivo=f, nombre_archivo=f.name, subido_por=request.user)
        if carpeta_id: return redirect('detalle_carpeta', cliente_id=cliente.id, carpeta_id=carpeta_id)
    return redirect('detalle_cliente', cliente_id=cliente_id)

@login_required
def eliminar_archivo_drive(request, archivo_id):
    doc = get_object_or_404(Documento, id=archivo_id)
    doc.en_papelera = True; doc.fecha_eliminacion = timezone.now(); doc.save()
    url = 'detalle_carpeta' if doc.carpeta else 'detalle_cliente'
    kwargs = {'cliente_id': doc.cliente.id, 'carpeta_id': doc.carpeta.id} if doc.carpeta else {'cliente_id': doc.cliente.id}
    return redirect(url, **kwargs)

@login_required
def ver_papelera(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    Documento.objects.filter(cliente=cliente, en_papelera=True, fecha_eliminacion__lt=timezone.now()-timedelta(days=7)).delete()
    return render(request, 'papelera.html', {'cliente': cliente, 'archivos': Documento.objects.filter(cliente=cliente, en_papelera=True)})

@login_required
def restaurar_archivo(request, archivo_id):
    doc = get_object_or_404(Documento, id=archivo_id)
    doc.en_papelera = False; doc.save()
    return redirect('ver_papelera', cliente_id=doc.cliente.id)

@login_required
def forzar_eliminacion(request, archivo_id):
    get_object_or_404(Documento, id=archivo_id).delete()
    return redirect(request.META.get('HTTP_REFERER'))

@login_required
def descargar_carpeta_zip(request, carpeta_id):
    c = get_object_or_404(Carpeta, id=carpeta_id)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        for d in Documento.objects.filter(carpeta=c, en_papelera=False):
            try: z.writestr(d.nombre_archivo, d.archivo.read())
            except: pass
    buffer.seek(0)
    resp = HttpResponse(buffer, content_type='application/zip')
    resp['Content-Disposition'] = f'attachment; filename="{c.nombre}.zip"'
    return resp

@login_required
def acciones_masivas_drive(request):
    if request.method == 'POST':
        ids = request.POST.getlist('doc_ids')
        accion = request.POST.get('accion')
        docs = Documento.objects.filter(id__in=ids)
        if accion == 'eliminar':
            docs.update(en_papelera=True, fecha_eliminacion=timezone.now())
        elif accion == 'descargar':
            buffer = BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
                for d in docs:
                    try: z.writestr(d.nombre_archivo, d.archivo.read())
                    except: pass
            buffer.seek(0)
            resp = HttpResponse(buffer, content_type='application/zip')
            resp['Content-Disposition'] = 'attachment; filename="seleccion.zip"'
            return resp
    return redirect(request.META.get('HTTP_REFERER'))

@login_required
def preview_archivo(request, documento_id):
    doc = get_object_or_404(Documento, id=documento_id)
    ext = doc.nombre_archivo.split('.')[-1].lower()
    data = {'tipo': 'unknown', 'url': doc.archivo.url, 'nombre': doc.nombre_archivo}
    if ext in ['jpg','png','jpeg']: data['tipo'] = 'imagen'
    elif ext == 'pdf': data['tipo'] = 'pdf'
    elif ext == 'docx':
        try: 
            with doc.archivo.open() as f: data['html'] = mammoth.convert_to_html(f).value; data['tipo'] = 'docx'
        except: pass
    return JsonResponse(data)

@login_required
def mover_archivo(request, documento_id):
    if request.method == 'POST':
        doc = get_object_or_404(Documento, id=documento_id)
        dest = request.POST.get('carpeta_destino')
        doc.carpeta = None if dest == 'raiz' else get_object_or_404(Carpeta, id=dest)
        doc.save()
    return redirect(request.META.get('HTTP_REFERER'))

@login_required
def subir_evidencia_requisito(request, requisito_id):
    if request.method == 'POST':
        req = get_object_or_404(Requisito, id=requisito_id)
        f = request.FILES['archivo']
        carpeta = Carpeta.objects.filter(cliente=req.cliente, nombre__icontains=req.categoria).first()
        doc = Documento.objects.create(cliente=req.cliente, carpeta=carpeta, archivo=f, nombre_archivo=f.name, subido_por=request.user)
        req.estado = 'completado'; req.archivo_asociado = doc; req.save()
        messages.success(request, "Requisito completado.")
        return redirect('detalle_cliente', cliente_id=req.cliente.id)
    return redirect('dashboard')

@login_required
def gestionar_tarea(request, cliente_id):
    if request.method == 'POST':
        Tarea.objects.create(cliente_id=cliente_id, titulo=request.POST.get('titulo'), fecha_limite=request.POST.get('fecha_limite'), prioridad=request.POST.get('prioridad'))
    return redirect('detalle_cliente', cliente_id=cliente_id)

@login_required
def toggle_tarea(request, tarea_id):
    t = get_object_or_404(Tarea, id=tarea_id)
    t.completada = not t.completada; t.save()
    return redirect('detalle_cliente', cliente_id=t.cliente.id)

@login_required
def eliminar_tarea(request, tarea_id):
    t = get_object_or_404(Tarea, id=tarea_id)
    cid = t.cliente.id; t.delete()
    return redirect('detalle_cliente', cliente_id=cid)

@login_required
def editar_tarea(request, tarea_id):
    t = get_object_or_404(Tarea, id=tarea_id)
    if request.method == 'POST':
        t.titulo = request.POST.get('titulo')
        t.fecha_limite = request.POST.get('fecha_limite')
        t.prioridad = request.POST.get('prioridad')
        t.save()
    return redirect('detalle_cliente', cliente_id=t.cliente.id)

@login_required
def crear_expediente(request, cliente_id):
    if request.method == 'POST':
        f = Carpeta.objects.create(nombre=f"EXP {request.POST.get('num_expediente')}: {request.POST.get('titulo')}", cliente_id=cliente_id, es_expediente=True)
        Expediente.objects.create(cliente_id=cliente_id, num_expediente=request.POST.get('num_expediente'), titulo=request.POST.get('titulo'), carpeta=f)
    return redirect('detalle_cliente', cliente_id=cliente_id)

# ==========================================
# 5. COTIZACIONES Y SERVICIOS
# ==========================================

@login_required
def gestion_servicios(request):
    if not request.user.access_cotizaciones: return redirect('dashboard')
    return render(request, 'cotizaciones/servicios.html', {'servicios': Servicio.objects.all()})

@login_required
def guardar_servicio(request):
    if request.method == 'POST':
        sid = request.POST.get('servicio_id')
        s = get_object_or_404(Servicio, id=sid) if sid else Servicio()
        s.nombre = request.POST.get('nombre')
        s.descripcion = request.POST.get('descripcion')
        s.precio_base = request.POST.get('precio')
        s.save()
    return redirect('gestion_servicios')

@login_required
def eliminar_servicio(request, servicio_id):
    get_object_or_404(Servicio, id=servicio_id).delete()
    return redirect('gestion_servicios')

@login_required
def lista_cotizaciones(request):
    if not request.user.access_cotizaciones: return redirect('dashboard')
    return render(request, 'cotizaciones/lista.html', {'cotizaciones': Cotizacion.objects.all().order_by('-fecha_creacion')})

@login_required
def nueva_cotizacion(request):
    clientes = Cliente.objects.all() if request.user.rol == 'admin' else request.user.clientes_asignados.all()
    
    if request.method == 'POST':
        cliente_id = request.POST.get('cliente_id')
        c = Cotizacion.objects.create(
            cliente_id=cliente_id if cliente_id else None,
            prospecto_nombre=request.POST.get('nombre'),
            prospecto_email=request.POST.get('email'),
            prospecto_telefono=request.POST.get('telefono'),
            prospecto_empresa=request.POST.get('empresa'),
            validez_hasta=request.POST.get('validez') or None,
            creado_por=request.user,
            aplicar_iva=request.POST.get('aplicar_iva') == 'on',
            porcentaje_iva=Decimal(request.POST.get('porcentaje_iva') or 0)
        )
        
        s_ids = request.POST.getlist('servicio_id')
        cants = request.POST.getlist('cantidad')
        precios = request.POST.getlist('precio')
        
        for i, sid in enumerate(s_ids):
            if sid:
                ItemCotizacion.objects.create(cotizacion=c, servicio_id=sid, cantidad=int(cants[i] or 1), precio_unitario=Decimal(precios[i] or 0))
        
        c.calcular_totales()
        return redirect('detalle_cotizacion', cotizacion_id=c.id)
    
    return render(request, 'cotizaciones/crear.html', {
        'clientes': clientes, 
        'servicios': [{'id':s.id, 'nombre':s.nombre, 'precio':float(s.precio_base)} for s in Servicio.objects.all()]
    })

@login_required
def detalle_cotizacion(request, cotizacion_id):
    return render(request, 'cotizaciones/detalle.html', {'c': get_object_or_404(Cotizacion, id=cotizacion_id)})

@login_required
def generar_pdf_cotizacion(request, cotizacion_id):
    c = get_object_or_404(Cotizacion, id=cotizacion_id)
    pdf = generar_y_guardar_pdf_drive(c, request.user)
    resp = HttpResponse(pdf, content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="Cotizacion_{c.id}.pdf"'
    return resp

@login_required
def enviar_cotizacion_email(request, cotizacion_id):
    if request.method == 'POST':
        c = get_object_or_404(Cotizacion, id=cotizacion_id)
        if not c.prospecto_email: return redirect('preparar_envio_cotizacion', cotizacion_id=c.id)
        
        try:
            pdf = generar_y_guardar_pdf_drive(c, request.user)
            email = EmailMultiAlternatives(
                subject=request.POST.get('asunto'), body=request.POST.get('mensaje'),
                from_email=settings.DEFAULT_FROM_EMAIL, to=[c.prospecto_email], reply_to=[request.user.email]
            )
            email.attach(f"Cotizacion_{c.id}.pdf", pdf, 'application/pdf')
            email.send()
            c.estado = 'enviada'; c.save()
            messages.success(request, "Enviado.")
        except Exception as e: messages.error(request, str(e))
        return redirect('detalle_cotizacion', cotizacion_id=c.id)
    return redirect('detalle_cotizacion', cotizacion_id=cotizacion_id)

@login_required
def preparar_envio_cotizacion(request, cotizacion_id):
    c = get_object_or_404(Cotizacion, id=cotizacion_id)
    msg = f"Estimado {c.prospecto_nombre},\n\nAdjunto cotización."
    link = request.build_absolute_uri(reverse('generar_pdf_cotizacion', args=[c.id]))
    return render(request, 'cotizaciones/preparar_envio.html', {'c': c, 'msg_email': msg, 'msg_wa': f"Hola, aquí tu cotización: {link}"})

@login_required
def eliminar_cotizacion(request, cotizacion_id):
    if request.user.access_cotizaciones: get_object_or_404(Cotizacion, id=cotizacion_id).delete()
    return redirect('lista_cotizaciones')

# ==========================================
# 6. FINANZAS Y FACTURACIÓN (LÓGICA ACTUALIZADA)
# ==========================================

@login_required
def panel_finanzas(request):
    if not request.user.access_finanzas:
        return redirect('dashboard')

    # 1. Totales Globales
    total_por_cobrar = CuentaPorCobrar.objects.aggregate(t=Sum('saldo_pendiente'))['t'] or 0
    
    # 2. Resumen por Cliente (CORREGIDO)
    clientes_finanzas = Cliente.objects.annotate(
        total_proyectos=Count('cuentas', distinct=True),
        deuda_total=Sum('cuentas__saldo_pendiente'),
        pagado_total=Coalesce(Sum('cuentas__pagos__monto'), 0, output_field=models.DecimalField())
    ).filter(total_proyectos__gt=0).order_by('-deuda_total')

    context = {
        'total_por_cobrar': total_por_cobrar,
        'clientes': clientes_finanzas,
        'now': timezone.now()
    }
    return render(request, 'finanzas/panel.html', context)

@login_required
def finanzas_cliente_detalle(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    cuentas = CuentaPorCobrar.objects.filter(cliente=cliente).order_by('-fecha_emision')
    return render(request, 'finanzas/detalle_cliente.html', {'cliente': cliente, 'cuentas': cuentas})

@login_required
def convertir_a_cliente(request, cotizacion_id):
    c = get_object_or_404(Cotizacion, id=cotizacion_id)
    
    # PROTECCIÓN CONTRA DUPLICADOS (Doble Clic)
    if CuentaPorCobrar.objects.filter(cotizacion=c).exists():
        messages.warning(request, "Este proyecto ya fue convertido anteriormente.")
        # Redirigir al cliente ya convertido (si existe)
        if c.cliente_convertido:
            return redirect('finanzas_cliente_detalle', cliente_id=c.cliente_convertido.id)
        return redirect('dashboard')

    if request.method == 'POST':
        # 1. Crear Cliente
        if c.cliente_convertido: cliente = c.cliente_convertido
        else:
            cliente, _ = Cliente.objects.get_or_create(
                nombre_empresa=c.prospecto_empresa or c.prospecto_nombre,
                defaults={'nombre_contacto': c.prospecto_nombre, 'email': c.prospecto_email, 'telefono': c.prospecto_telefono}
            )
            c.cliente_convertido = cliente; c.estado = 'aceptada'; c.save()
            if request.user.rol != 'admin': request.user.clientes_asignados.add(cliente)

        generar_y_guardar_pdf_drive(c, request.user)

        # 2. Deuda y Pago Anticipo (50%)
        monto_anticipo = c.total * Decimal('0.50')
        cuenta = CuentaPorCobrar.objects.create(
            cliente=cliente, cotizacion=c, concepto=f"Proyecto: Cotización #{c.id}",
            monto_total=c.total, saldo_pendiente=c.total, fecha_vencimiento=c.validez_hasta
        )
        
        Pago.objects.create(
            cuenta=cuenta, monto=monto_anticipo, metodo='transferencia', 
            referencia='Anticipo Automático', registrado_por=request.user
        )

        # 3. Remisión Anticipo Automática
        folio_rem = f"REM-ANT-{int(timezone.now().timestamp())}"
        rem = Remision.objects.create(cliente=cliente, cotizacion=c, folio=folio_rem, monto_total=monto_anticipo)
        html_rem = render_to_string('finanzas/remision_template.html', {'r': rem, 'base_url': str(settings.BASE_DIR)})
        pdf_rem = weasyprint.HTML(string=html_rem, base_url=str(settings.BASE_DIR)).write_pdf()
        rem.archivo_pdf.save(f"Remision_{folio_rem}.pdf", ContentFile(pdf_rem)); rem.save()

        messages.success(request, "Proyecto iniciado y anticipo registrado.")
        return redirect('finanzas_cliente_detalle', cliente_id=cliente.id)
    
    return redirect('detalle_cotizacion', cotizacion_id=c.id)

@login_required
def crear_factura_anticipo(request, cuenta_id):
    """
    Versión DEFINITIVA: 
    - Evita duplicados con sufijo de tiempo.
    - Soporta CFDI 4.0 (CfdiXml).
    - Genera Código QR del SAT para el PDF.
    """
    cuenta = get_object_or_404(CuentaPorCobrar, id=cuenta_id)
    c = cuenta.cotizacion
    
    # --- MEJORA 1: Folio Único (Sufijo de Hora) ---
    sufijo = timezone.now().strftime('%H%M%S')
    folio = f"F-ANT-{c.id}-{sufijo}"
    
    # Evitar duplicados locales
    if Factura.objects.filter(folio_interno=folio).exists():
        messages.warning(request, f"La factura {folio} ya existe localmente.")
        return redirect('finanzas_cliente_detalle', cliente_id=cuenta.cliente.id)

    # 1. Crear el objeto en la BD (Pendiente)
    monto = c.total * Decimal('0.50') 
    fac = Factura.objects.create(
        cliente=cuenta.cliente, 
        folio_interno=folio, 
        monto_total=monto,
        estado_sat='pendiente', 
        uuid=''
    )
    fac.cotizaciones.add(c)

    # 2. Intentar Timbrar con Facturama
    try:
        respuesta_sat = timbrar_con_facturama(fac)
        
        # 3. Guardar respuesta del SAT
        fac.uuid = respuesta_sat['Id'] # El UUID Real
        fac.estado_sat = 'timbrada'
        
        # --- MEJORA 2: Corrección de Etiqueta XML ---
        xml_b64 = respuesta_sat.get('CfdiXml') or respuesta_sat.get('Xml')
        
        if xml_b64:
            xml_content = base64.b64decode(xml_b64)
            fac.archivo_xml.save(f"{fac.uuid}.xml", ContentFile(xml_content))
        
        # ====================================================
        # 4. NUEVO: GENERACIÓN DEL CÓDIGO QR SAT
        # ====================================================
        # URL Oficial: https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?id=UUID&re=RFC_E&rr=RFC_R&tt=TOTAL&fe=SELLO
        
        rfc_emisor = "EKU9003173C9" # RFC Pruebas
        rfc_receptor = fac.cliente.rfc or "XAXX010101000"
        total_str = f"{fac.monto_total:.6f}"
        sello_ultimo_8 = respuesta_sat.get('Complement', {}).get('TaxStamp', {}).get('SatSign', '')[-8:]
        
        if not sello_ultimo_8: 
            sello_ultimo_8 = "12345678" # Fallback

        qr_data = f"https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?id={fac.uuid}&re={rfc_emisor}&rr={rfc_receptor}&tt={total_str}&fe={sello_ultimo_8}"
        
        # Crear imagen QR
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img_qr = qr.make_image(fill='black', back_color='white')
        
        # Guardar en memoria
        buffer_qr = BytesIO()
        img_qr.save(buffer_qr, format="PNG")
        fac.qr_imagen.save(f"qr_{folio}.png", ContentFile(buffer_qr.getvalue()), save=False)
        # ====================================================

        fac.save() # Guardamos XML y QR antes de generar PDF
        
        # 5. Generar PDF Visual (Pasando la URL del QR)
        try:
            html = render_to_string('finanzas/factura_template.html', {
                'f': fac, 
                'base_url': str(settings.BASE_DIR),
                'qr_url': fac.qr_imagen.url if fac.qr_imagen else None
            })
            pdf = weasyprint.HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
            fac.pdf_representacion.save(f"Factura_{folio}.pdf", ContentFile(pdf))
        except Exception as e:
            print(f"Error generando PDF visual: {e}")
        
        fac.save()
        messages.success(request, f"¡Factura Timbrada con Éxito! UUID: {fac.uuid}")

    except Exception as e:
        # Si falló, borramos el intento local
        fac.delete()
        messages.error(request, f"Error al timbrar: {str(e)}")

    return redirect('finanzas_cliente_detalle', cliente_id=cuenta.cliente.id)

@login_required
def registrar_pago(request):
    """Registra pagos y opcionalmente factura el resto."""
    if request.method == 'POST':
        # FIX CRÍTICO: Referencia nunca None
        ref = request.POST.get('referencia') or ""
        
        pago = Pago.objects.create(
            cuenta_id=request.POST.get('cuenta_id'),
            monto=Decimal(request.POST.get('monto')),
            metodo=request.POST.get('metodo'),
            referencia=ref,
            registrado_por=request.user
        )
        
        # Lógica para generar Factura Final si el checkbox está marcado
        if request.POST.get('generar_factura_final') == 'on':
            c = pago.cuenta.cotizacion
            cliente = pago.cuenta.cliente
            folio_fin = f"F-FIN-{c.id}"
            
            # Verificar si ya existe
            if not Factura.objects.filter(folio_interno=folio_fin).exists():
                if not hasattr(cliente, 'datos_fiscales'):
                    messages.warning(request, "Pago registrado, pero faltan datos fiscales para la factura.")
                else:
                    fac = Factura.objects.create(
                        cliente=cliente, folio_interno=folio_fin, monto_total=pago.monto,
                        estado_sat='pendiente', uuid=str(uuid.uuid4()).upper()
                    )
                    fac.cotizaciones.add(c)
                    html = render_to_string('finanzas/factura_template.html', {'f': fac, 'base_url': str(settings.BASE_DIR)})
                    pdf = weasyprint.HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
                    fac.pdf_representacion.save(f"Factura_{folio_fin}.pdf", ContentFile(pdf)); fac.save()
        
        # Generar Remisión Final siempre
        if pago.cuenta.saldo_pendiente <= 0:
            c = pago.cuenta.cotizacion
            folio_rem = f"REM-FIN-{int(timezone.now().timestamp())}"
            rem = Remision.objects.create(cliente=pago.cuenta.cliente, cotizacion=c, folio=folio_rem, monto_total=pago.monto)
            html_rem = render_to_string('finanzas/remision_template.html', {'r': rem, 'base_url': str(settings.BASE_DIR)})
            pdf_rem = weasyprint.HTML(string=html_rem, base_url=str(settings.BASE_DIR)).write_pdf()
            rem.archivo_pdf.save(f"{folio_rem}.pdf", ContentFile(pdf_rem)); rem.save()

        # Asiento Contable
        poliza = Poliza.objects.create(tipo='ingreso', concepto=f"Cobro {pago.cuenta.cliente}", creada_por=request.user, pago_relacionado=pago)
        bancos, _ = CuentaContable.objects.get_or_create(codigo="102-01", defaults={'nombre': 'Bancos', 'tipo': 'activo'})
        MovimientoContable.objects.create(poliza=poliza, cuenta=bancos, debe=pago.monto)
        bancos.saldo_actual += pago.monto; bancos.save()
        
        messages.success(request, "Pago registrado correctamente.")
        return redirect('finanzas_cliente_detalle', cliente_id=pago.cuenta.cliente.id)
        
    return redirect(request.META.get('HTTP_REFERER'))

@login_required
def facturar_multiples(request):
    """Factura Masiva"""
    if request.method == 'POST':
        cliente_id = request.POST.get('cliente_id')
        ids = request.POST.getlist('cuentas_ids')
        cliente = get_object_or_404(Cliente, id=cliente_id)

        if not ids: return redirect('finanzas_cliente_detalle', cliente_id=cliente.id)
        if not hasattr(cliente, 'datos_fiscales'): return redirect(f"/cliente/{cliente.id}/?accion=abrir_fiscal")

        cots = []
        total = 0
        for cid in ids:
            cta = get_object_or_404(CuentaPorCobrar, id=cid)
            if cta.cotizacion: cots.append(cta.cotizacion); total += cta.saldo_pendiente

        folio = f"F-GLOB-{int(timezone.now().timestamp())}"
        fac = Factura.objects.create(cliente=cliente, folio_interno=folio, monto_total=total, estado_sat='pendiente', uuid=str(uuid.uuid4()).upper())
        fac.cotizaciones.set(cots)
        
        html = render_to_string('finanzas/factura_template.html', {'f': fac, 'base_url': str(settings.BASE_DIR)})
        pdf = weasyprint.HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
        fac.pdf_representacion.save(f"Factura_{folio}.pdf", ContentFile(pdf)); fac.save()

        messages.success(request, f"Factura consolidada: ${total:,.2f}")
        return redirect('finanzas_cliente_detalle', cliente_id=cliente.id)
    return redirect('panel_finanzas')

@login_required
def generar_factura_sat(request, cotizacion_id):
    # Simulación Timbrado
    c = get_object_or_404(Cotizacion, id=cotizacion_id)
    for f in c.facturas_asociadas.filter(estado_sat='pendiente'):
        f.estado_sat = 'timbrada'; f.save()
    messages.success(request, "Facturas timbradas.")
    return redirect(request.META.get('HTTP_REFERER'))

@login_required
def libro_contable(request):
    if not request.user.access_finanzas: return redirect('dashboard')
    return render(request, 'finanzas/libro_contable.html', {'polizas': Poliza.objects.all().order_by('-fecha')})

@login_required
def recibo_pago_pdf(request, pago_id): return redirect('panel_finanzas')
@login_required
def previsualizar_factura(request, cotizacion_id): return redirect('panel_finanzas')
@login_required
def crear_factura_faltante(request, cotizacion_id): return redirect('panel_finanzas') # Deprecated
@login_required
def generar_docs_finiquito(request, cuenta_id): return redirect('panel_finanzas') # Deprecated (Merged into registrar_pago)

# ==========================================
# 7. CONTRATOS
# ==========================================

@login_required
def generador_contratos(request, cliente_id):
    if not request.user.access_contratos: return redirect('dashboard')
    cliente = get_object_or_404(Cliente, id=cliente_id)
    
    if request.method == 'GET' and 'plantilla_id' not in request.GET:
        return render(request, 'generador/seleccionar.html', {
            'cliente': cliente,
            'plantillas': Plantilla.objects.all().order_by('-fecha_subida'),
            'glosario': VariableEstandar.objects.all().order_by('clave')
        })

    plantilla = get_object_or_404(Plantilla, id=request.GET.get('plantilla_id') or request.POST.get('plantilla_id'))
    doc = DocxTemplate(plantilla.archivo.path)
    vars_en_doc = doc.get_undeclared_template_variables()
    memoria = cliente.datos_extra if isinstance(cliente.datos_extra, dict) else {}
    formulario = []
    
    mapeo = {
        'cliente.nombre_empresa': cliente.nombre_empresa,
        'cliente.nombre_contacto': cliente.nombre_contacto,
        'cliente.email': cliente.email,
        'cliente.telefono': cliente.telefono,
        'fecha_actual': timezone.now().strftime("%d/%m/%Y"),
    }

    for v in vars_en_doc:
        var_std = VariableEstandar.objects.filter(clave=v).first()
        val = mapeo.get(var_std.campo_bd, '') if var_std and var_std.origen == 'sistema' else memoria.get(v, '')
        formulario.append({'clave': v, 'valor': val, 'descripcion': var_std.descripcion if var_std else "Variable", 'es_automatico': var_std and var_std.origen == 'sistema'})

    if request.method == 'POST':
        contexto = {item['clave']: item['valor'] if item['es_automatico'] else request.POST.get(item['clave'], '').strip() for item in formulario}
        cliente.datos_extra.update(contexto); cliente.save()
        
        doc.render(contexto)
        buffer = BytesIO(); doc.save(buffer); buffer.seek(0)
        
        nombre = request.POST.get('nombre_archivo_salida', '') or f"{plantilla.nombre} - {cliente.nombre_empresa}"
        if not nombre.lower().endswith('.docx'): nombre += ".docx"

        c_contratos, _ = Carpeta.objects.get_or_create(nombre="Contratos Generados", cliente=cliente, padre=None)
        nuevo = Documento(cliente=cliente, carpeta=c_contratos, nombre_archivo=nombre, subido_por=request.user)
        nuevo.archivo.save(nombre, ContentFile(buffer.getvalue())); nuevo.save()
        return redirect('visor_docx', documento_id=nuevo.id)

    return render(request, 'generador/llenar.html', {'cliente': cliente, 'plantilla': plantilla, 'variables': formulario})

@login_required
def visor_docx(request, documento_id):
    doc = get_object_or_404(Documento, id=documento_id)
    html = ""
    try: 
        with doc.archivo.open() as f: html = mammoth.convert_to_html(f).value
    except: pass
    return render(request, 'generador/visor.html', {'doc': doc, 'contenido_html': html})

@login_required
def subir_plantilla(request):
    if request.user.rol == 'admin' and request.method == 'POST':
        Plantilla.objects.create(nombre=request.POST.get('nombre'), archivo=request.FILES.get('archivo'))
    return redirect('dashboard')

@login_required
def diseñador_plantillas(request):
    if not request.user.access_disenador: return redirect('dashboard')
    if request.method == 'POST': pass 
    return render(request, 'generador/diseñador.html')

@csrf_exempt
@login_required
def previsualizar_word_raw(request): return JsonResponse({})
@csrf_exempt
@login_required
def crear_variable_api(request): return JsonResponse({})
@csrf_exempt
def api_convertir_html(request): return JsonResponse({})
@login_required
def eliminar_plantilla(request, plantilla_id): return redirect('dashboard')

# ==========================================
# 8. AGENDA
# ==========================================

@login_required
def agenda_legal(request):
    if not request.user.access_agenda: return redirect('dashboard')
    hoy = timezone.now()
    proximas = Evento.objects.filter(tipo='audiencia', inicio__gte=hoy, usuario=request.user).order_by('inicio')[:5]
    clientes = Cliente.objects.all() if request.user.rol == 'admin' else request.user.clientes_asignados.all()
    return render(request, 'agenda/calendario.html', {'clientes': clientes, 'proximas_audiencias': proximas})

@login_required
def api_eventos(request):
    start, end = request.GET.get('start'), request.GET.get('end')
    qs = Evento.objects.filter(inicio__range=[start, end])
    if request.user.rol != 'admin': qs = qs.filter(Q(usuario=request.user) | Q(cliente__in=request.user.clientes_asignados.all()))
    eventos = []
    for e in qs:
        titulo = f"{e.cliente.nombre_empresa}: {e.titulo}" if e.cliente else e.titulo
        eventos.append({'id': e.id, 'title': titulo, 'start': e.inicio.isoformat(), 'end': e.fin.isoformat() if e.fin else None, 'backgroundColor': e.color_hex, 'extendedProps': {'descripcion': e.descripcion, 'tipo': e.get_tipo_display()}})
    return JsonResponse(eventos, safe=False)

@csrf_exempt
@login_required
def mover_evento_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body); evento = get_object_or_404(Evento, id=data.get('id'))
            if request.user.rol != 'admin' and evento.usuario != request.user: return JsonResponse({'status': 'error', 'msg': 'Sin permiso'})
            evento.inicio = data.get('start')
            if data.get('end'): evento.fin = data.get('end')
            evento.save(); return JsonResponse({'status': 'ok'})
        except Exception as e: return JsonResponse({'status': 'error', 'msg': str(e)})
    return JsonResponse({'status': 'error'})

@login_required
def crear_evento(request):
    if request.method == 'POST':
        inicio = timezone.make_aware(datetime.strptime(f"{request.POST.get('fecha')} {request.POST.get('hora')}", "%Y-%m-%d %H:%M"))
        cliente = get_object_or_404(Cliente, id=request.POST.get('cliente_id')) if request.POST.get('cliente_id') else None
        Evento.objects.create(usuario=request.user, titulo=request.POST.get('titulo'), inicio=inicio, tipo=request.POST.get('tipo'), cliente=cliente, descripcion=request.POST.get('descripcion'))
        messages.success(request, "Evento agendado.")
    return redirect('agenda_legal')

@login_required
def eliminar_evento(request, evento_id):
    evento = get_object_or_404(Evento, id=evento_id)
    if request.user.rol == 'admin' or evento.usuario == request.user:
        evento.delete(); return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'error'}, status=403)