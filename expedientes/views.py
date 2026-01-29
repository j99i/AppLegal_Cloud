import os
import json
import zipfile
from io import BytesIO
from datetime import timedelta
from decimal import Decimal 
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.text import slugify # <--- IMPORTANTE: Para nombres de archivo limpios
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.conf import settings 

# Librerías para Documentos
from docxtpl import DocxTemplate
import mammoth
from docx import Document as DocumentoWord 
import weasyprint # Importar aquí para uso general si es necesario

# Importación de Modelos
from .models import (
    Usuario, Cliente, Carpeta, Expediente, Documento, 
    Tarea, Bitacora, Plantilla, VariableEstandar,
    Servicio, Cotizacion, ItemCotizacion, PlantillaMensaje,
    CuentaPorCobrar, Pago, Evento, CampoAdicional
)

# ==========================================
# 1. AUTENTICACIÓN Y PERFIL
# ==========================================

def signout(request):
    logout(request)
    return redirect('login')

def registro(request):
    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        username = request.POST.get('username')
        email = request.POST.get('email')
        pass1 = request.POST.get('pass1')
        pass2 = request.POST.get('pass2')

        if pass1 != pass2:
            messages.error(request, "Las contraseñas no coinciden.")
            return render(request, 'registro.html')

        if Usuario.objects.filter(username=username).exists():
            messages.error(request, "El usuario ya existe.")
            return render(request, 'registro.html')

        try:
            Usuario.objects.create_user(
                username=username, email=email, password=pass1,
                first_name=first_name, last_name=last_name, is_active=False
            )
            return render(request, 'registro_pendiente.html')
        except Exception as e:
            messages.error(request, f"Error del sistema: {e}")

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
        messages.success(request, "Perfil actualizado correctamente.")
        return redirect('mi_perfil')
    return render(request, 'usuarios/mi_perfil.html', {'user': user})

# ==========================================
# 2. GESTIÓN DE USUARIOS (ADMIN)
# ==========================================

@login_required
def gestion_usuarios(request):
    if request.user.rol != 'admin': return redirect('dashboard')
    usuarios = Usuario.objects.all().order_by('-date_joined')
    return render(request, 'gestion_usuarios.html', {'usuarios': usuarios})

@login_required
def autorizar_usuario(request, user_id):
    if request.user.rol != 'admin': return redirect('dashboard')
    user = get_object_or_404(Usuario, id=user_id)
    user.is_active = True
    user.save()
    messages.success(request, f"Usuario {user.username} autorizado.")
    return redirect('gestion_usuarios')

@login_required
def editar_usuario(request, user_id):
    if request.user.rol != 'admin': return redirect('dashboard')
    user_obj = get_object_or_404(Usuario, id=user_id)
    clientes_disponibles = Cliente.objects.all().order_by('nombre_empresa')
    
    if request.method == 'POST':
        user_obj.rol = request.POST.get('rol')
        user_obj.first_name = request.POST.get('first_name') or ""
        user_obj.last_name = request.POST.get('last_name') or ""
        user_obj.email = request.POST.get('email')
        user_obj.telefono = request.POST.get('telefono') or None
        user_obj.puesto = request.POST.get('puesto') or None
        
        # Permisos booleanos
        user_obj.can_create_client = request.POST.get('can_create_client') == 'on'
        user_obj.can_edit_client = request.POST.get('can_edit_client') == 'on'
        user_obj.can_delete_client = request.POST.get('can_delete_client') == 'on'
        user_obj.can_upload_files = request.POST.get('can_upload_files') == 'on'
        user_obj.can_view_documents = request.POST.get('can_view_documents') == 'on'
        user_obj.can_manage_users = request.POST.get('can_manage_users') == 'on'

        # Accesos a módulos
        user_obj.access_finanzas = request.POST.get('access_finanzas') == 'on'
        user_obj.access_cotizaciones = request.POST.get('access_cotizaciones') == 'on'
        user_obj.access_contratos = request.POST.get('access_contratos') == 'on'
        user_obj.access_disenador = request.POST.get('access_disenador') == 'on'
        user_obj.access_agenda = request.POST.get('access_agenda') == 'on'
        
        clientes_ids = request.POST.getlist('clientes_asignados')
        user_obj.save()
        
        if user_obj.rol != 'admin':
            user_obj.clientes_asignados.set(clientes_ids)
        else:
            user_obj.clientes_asignados.clear()
            
        messages.success(request, f"Permisos de {user_obj.username} actualizados.")
        return redirect('gestion_usuarios')

    return render(request, 'usuarios/editar_usuario.html', {'u': user_obj, 'clientes': clientes_disponibles})

@login_required
def eliminar_usuario(request, user_id):
    if request.user.rol != 'admin': return redirect('dashboard')
    u = get_object_or_404(Usuario, id=user_id)
    if u == request.user:
        messages.error(request, "No puedes eliminarte a ti mismo.")
        return redirect('gestion_usuarios')
    u.delete()
    messages.success(request, "Usuario eliminado.")
    return redirect('gestion_usuarios')

# ==========================================
# 3. DASHBOARD Y CLIENTES
# ==========================================

@login_required
def dashboard(request):
    if request.user.rol == 'admin':
        mis_clientes = Cliente.objects.all()
    else:
        mis_clientes = request.user.clientes_asignados.all()

    stats = {
        'total_clientes': mis_clientes.count(),
        'expedientes_activos': Expediente.objects.filter(cliente__in=mis_clientes, estado='abierto').count(),
        'tareas_pendientes': Tarea.objects.filter(cliente__in=mis_clientes, completada=False).count(),
        'docs_subidos': Documento.objects.filter(cliente__in=mis_clientes).count()
    }
    
    hoy = timezone.now().date()
    tareas_criticas = Tarea.objects.filter(cliente__in=mis_clientes, completada=False, fecha_limite__lte=hoy)
    
    clientes = mis_clientes.annotate(
        num_expedientes=Count('expedientes', distinct=True),
        urgencias=Count('tareas', filter=Q(tareas__prioridad='alta', tareas__completada=False), distinct=True)
    ).order_by('-urgencias', '-fecha_registro')

    pendientes = 0
    if request.user.rol == 'admin':
        pendientes = Usuario.objects.filter(is_active=False).count()

    return render(request, 'dashboard.html', {
        'clientes': clientes,
        'stats': stats,
        'usuarios_pendientes_conteo': pendientes,
        'now': timezone.now(),
        'alertas': {'tareas': tareas_criticas} 
    })

@login_required
def nuevo_cliente(request):
    if not (request.user.rol == 'admin' or request.user.can_create_client):
        return redirect('dashboard')
    if request.method == 'POST':
        c = Cliente.objects.create(
            nombre_empresa=request.POST.get('nombre_empresa'),
            nombre_contacto=request.POST.get('nombre_contacto'),
            email=request.POST.get('email'),
            telefono=request.POST.get('telefono'),
            logo=request.FILES.get('logo')
        )
        if request.user.rol != 'admin':
            request.user.clientes_asignados.add(c)
        return redirect('dashboard')
    return render(request, 'nuevo_cliente.html')

@login_required
def eliminar_cliente(request, cliente_id):
    if request.user.rol != 'admin' and not request.user.can_delete_client:
        return redirect('dashboard')
    cliente = get_object_or_404(Cliente, id=cliente_id)
    cliente.delete()
    messages.success(request, "Cliente eliminado.")
    return redirect('dashboard')

@login_required
def detalle_cliente(request, cliente_id, carpeta_id=None):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    
    if request.user.rol != 'admin' and cliente not in request.user.clientes_asignados.all():
        messages.error(request, "⛔ Acceso Denegado.")
        return redirect('dashboard')

    carpeta_actual = None
    breadcrumbs = []
    
    if carpeta_id:
        carpeta_actual = get_object_or_404(Carpeta, id=carpeta_id, cliente=cliente)
        crumb = carpeta_actual
        while crumb:
            breadcrumbs.insert(0, crumb)
            crumb = crumb.padre

    if carpeta_actual:
        carpetas = cliente.carpetas_drive.filter(padre=carpeta_actual)
        documentos = cliente.documentos_cliente.filter(carpeta=carpeta_actual)
    else:
        carpetas = cliente.carpetas_drive.filter(padre__isnull=True)
        documentos = cliente.documentos_cliente.filter(carpeta__isnull=True)

    stats_cliente = {
        'total_docs': cliente.documentos_cliente.count(),
        'expedientes_activos': cliente.expedientes.filter(estado='abierto').count(),
    }
    
    historial = Bitacora.objects.filter(cliente=cliente).select_related('usuario').order_by('-fecha')

    return render(request, 'detalle_cliente.html', {
        'cliente': cliente,
        'carpeta_actual': carpeta_actual,
        'breadcrumbs': breadcrumbs,
        'carpetas': carpetas,
        'documentos': documentos,
        'stats_cliente': stats_cliente,
        'historial': historial
    })

@login_required
def editar_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    if request.user.rol != 'admin' and cliente not in request.user.clientes_asignados.all():
        return redirect('dashboard')

    campos_dinamicos = CampoAdicional.objects.all()

    if request.method == 'POST':
        cliente.nombre_empresa = request.POST.get('nombre_empresa')
        cliente.nombre_contacto = request.POST.get('nombre_contacto')
        cliente.email = request.POST.get('email')
        cliente.telefono = request.POST.get('telefono')
        
        if request.FILES.get('logo'):
            cliente.logo = request.FILES['logo']

        datos_nuevos = cliente.datos_extra or {}
        for campo in campos_dinamicos:
            valor = request.POST.get(f"custom_{campo.id}")
            if valor:
                datos_nuevos[campo.nombre] = valor
        
        cliente.datos_extra = datos_nuevos
        cliente.save()
        Bitacora.objects.create(usuario=request.user, cliente=cliente, accion='edicion', descripcion="Actualizó datos.")
        messages.success(request, "Cliente actualizado.")
        return redirect('detalle_cliente', cliente_id=cliente.id)

    return render(request, 'clientes/editar.html', {
        'c': cliente,
        'campos_dinamicos': campos_dinamicos,
        'datos_existentes': cliente.datos_extra
    })

# ==========================================
# 4. CONFIGURACIÓN Y DRIVE
# ==========================================

@login_required
def configurar_campos(request):
    if request.user.rol != 'admin': return redirect('dashboard')
    campos = CampoAdicional.objects.all()
    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        if not CampoAdicional.objects.filter(nombre__iexact=nombre).exists():
            CampoAdicional.objects.create(nombre=nombre, tipo=request.POST.get('tipo'))
            messages.success(request, f"Campo '{nombre}' agregado.")
        return redirect('configurar_campos')
    return render(request, 'clientes/configurar_campos.html', {'campos': campos})

@login_required
def eliminar_campo_dinamico(request, campo_id):
    if request.user.rol != 'admin': return redirect('dashboard')
    get_object_or_404(CampoAdicional, id=campo_id).delete()
    return redirect('configurar_campos')

@login_required
def crear_carpeta(request, cliente_id):
    if request.method == 'POST':
        padre_id = request.POST.get('padre_id')
        padre = get_object_or_404(Carpeta, id=padre_id) if padre_id else None
        Carpeta.objects.create(nombre=request.POST.get('nombre'), cliente_id=cliente_id, padre=padre)
        if padre: return redirect('detalle_carpeta', cliente_id=cliente_id, carpeta_id=padre.id)
    return redirect('detalle_cliente', cliente_id=cliente_id)

@login_required
def eliminar_carpeta(request, carpeta_id):
    if not (request.user.can_delete_client or request.user.rol == 'admin'): return redirect('dashboard')
    c = get_object_or_404(Carpeta, id=carpeta_id)
    url_destino = 'detalle_carpeta' if c.padre else 'detalle_cliente'
    kwargs = {'cliente_id': c.cliente.id}
    if c.padre: kwargs['carpeta_id'] = c.padre.id
    c.delete()
    return redirect(url_destino, **kwargs)

@login_required
def crear_expediente(request, cliente_id):
    if request.method == 'POST':
        f = Carpeta.objects.create(nombre=f"EXP {request.POST.get('num_expediente')}: {request.POST.get('titulo')}", cliente_id=cliente_id, es_expediente=True)
        Expediente.objects.create(cliente_id=cliente_id, num_expediente=request.POST.get('num_expediente'), titulo=request.POST.get('titulo'), carpeta=f)
    return redirect('detalle_cliente', cliente_id=cliente_id)

@login_required
def subir_archivo_drive(request, cliente_id):
    if not (request.user.can_upload_files or request.user.rol == 'admin'): return redirect('detalle_cliente', cliente_id=cliente_id)
    if request.method == 'POST':
        cliente = get_object_or_404(Cliente, id=cliente_id)
        archivos = request.FILES.getlist('archivo')
        carpeta_raiz_id = request.POST.get('carpeta_id')
        carpeta_raiz = get_object_or_404(Carpeta, id=carpeta_raiz_id) if carpeta_raiz_id else None
        
        count = 0
        for f in archivos:
            Documento.objects.create(cliente_id=cliente_id, archivo=f, nombre_archivo=f.name, carpeta=carpeta_raiz, subido_por=request.user)
            count += 1
        
        ubicacion = carpeta_raiz.nombre if carpeta_raiz else "Raíz"
        Bitacora.objects.create(usuario=request.user, cliente=cliente, accion='subida', descripcion=f"Subió {count} archivos en '{ubicacion}'.")
        if carpeta_raiz: return redirect('detalle_carpeta', cliente_id=cliente_id, carpeta_id=carpeta_raiz.id)
    return redirect('detalle_cliente', cliente_id=cliente_id)

@login_required
def eliminar_archivo_drive(request, archivo_id):
    doc = get_object_or_404(Documento, id=archivo_id)
    if not (request.user.can_delete_client or request.user.rol == 'admin'): return redirect('detalle_cliente', cliente_id=doc.cliente.id)
    c_id, padre_id = doc.cliente.id, doc.carpeta.id if doc.carpeta else None
    Bitacora.objects.create(usuario=request.user, cliente=doc.cliente, accion='eliminacion', descripcion=f"Eliminó {doc.nombre_archivo}")
    doc.archivo.delete(); doc.delete()
    if padre_id: return redirect('detalle_carpeta', cliente_id=c_id, carpeta_id=padre_id)
    return redirect('detalle_cliente', cliente_id=c_id)

@login_required
def descargar_carpeta_zip(request, carpeta_id):
    carpeta = get_object_or_404(Carpeta, id=carpeta_id)
    if request.user.rol != 'admin' and carpeta.cliente not in request.user.clientes_asignados.all():
        return HttpResponse("Acceso Denegado", status=403)
    
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file in Documento.objects.filter(carpeta=carpeta):
            try: zip_file.writestr(file.nombre_archivo, file.archivo.read())
            except: pass
    
    Bitacora.objects.create(usuario=request.user, cliente=carpeta.cliente, accion='descarga', descripcion=f"Descargó ZIP: {carpeta.nombre}")
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{carpeta.nombre}.zip"'
    return response

@login_required
def acciones_masivas_drive(request):
    if request.method == 'POST':
        accion = request.POST.get('accion')
        doc_ids = request.POST.getlist('doc_ids')
        docs = Documento.objects.filter(id__in=doc_ids)
        if not docs: return redirect(request.META.get('HTTP_REFERER'))
        
        cliente = docs.first().cliente
        if accion == 'eliminar':
            if not (request.user.can_delete_client or request.user.rol == 'admin'): return redirect(request.META.get('HTTP_REFERER'))
            count = docs.count()
            for doc in docs: doc.archivo.delete(); doc.delete()
            Bitacora.objects.create(usuario=request.user, cliente=cliente, accion='eliminacion', descripcion=f"Eliminó {count} archivos masivamente.")
            messages.success(request, f"Se eliminaron {count} archivos.")
        
        elif accion == 'descargar':
            buffer = BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for doc in docs:
                    try: zip_file.writestr(doc.nombre_archivo, doc.archivo.read())
                    except: pass
            Bitacora.objects.create(usuario=request.user, cliente=cliente, accion='descarga', descripcion=f"Descargó selección ZIP.")
            buffer.seek(0)
            response = HttpResponse(buffer, content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="Seleccion.zip"'
            return response
            
    return redirect(request.META.get('HTTP_REFERER'))

@login_required
def preview_archivo(request, documento_id):
    doc = get_object_or_404(Documento, id=documento_id)
    ext = doc.nombre_archivo.split('.')[-1].lower()
    data = {'tipo': 'unknown', 'url': doc.archivo.url, 'nombre': doc.nombre_archivo}
    if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']: data['tipo'] = 'imagen'
    elif ext == 'pdf': data['tipo'] = 'pdf'
    elif ext == 'docx':
        data['tipo'] = 'docx'
        try:
            with doc.archivo.open() as f: data['html'] = mammoth.convert_to_html(f).value
        except: data['html'] = "Error de lectura."
    return JsonResponse(data)

# ==========================================
# 5. TAREAS
# ==========================================

@login_required
def gestionar_tarea(request, cliente_id):
    if request.method == 'POST':
        Tarea.objects.create(
            cliente_id=cliente_id, titulo=request.POST.get('titulo'),
            fecha_limite=request.POST.get('fecha_limite'), prioridad=request.POST.get('prioridad')
        )
    return redirect('detalle_cliente', cliente_id=cliente_id)

@login_required
def toggle_tarea(request, tarea_id):
    t = get_object_or_404(Tarea, id=tarea_id)
    t.completada = not t.completada
    t.save()
    return redirect('detalle_cliente', cliente_id=t.cliente.id)

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
def eliminar_tarea(request, tarea_id):
    t = get_object_or_404(Tarea, id=tarea_id)
    c_id = t.cliente.id
    t.delete()
    return redirect('detalle_cliente', cliente_id=c_id)

# ==========================================
# 6. CONTRATOS Y DISEÑADOR
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
        val = ""
        auto = False
        desc = "Variable"
        tipo = "text"

        if var_std:
            desc = var_std.descripcion
            if var_std.tipo == 'fecha': tipo = 'date'
            if var_std.origen == 'sistema':
                val = mapeo.get(var_std.campo_bd, '')
                auto = True
            else: val = memoria.get(v, '')
        else: val = memoria.get(v, '')

        formulario.append({'clave': v, 'valor': val, 'descripcion': desc, 'es_automatico': auto, 'tipo': tipo})

    if request.method == 'POST':
        contexto = {}
        nuevos_datos = {}
        for item in formulario:
            if item['es_automatico']: val = item['valor']
            else:
                val = request.POST.get(item['clave'], '').strip()
                nuevos_datos[item['clave']] = val
            contexto[item['clave']] = val
            
        cliente.datos_extra.update(nuevos_datos)
        cliente.save(update_fields=['datos_extra'])
        
        doc.render(contexto)
        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        
        nombre = request.POST.get('nombre_archivo_salida', '').strip() or f"{plantilla.nombre} - {cliente.nombre_empresa}"
        if not nombre.lower().endswith('.docx'): nombre += ".docx"

        c_contratos, _ = Carpeta.objects.get_or_create(nombre="Contratos Generados", cliente=cliente, padre=None)
        nuevo = Documento(cliente=cliente, carpeta=c_contratos, nombre_archivo=nombre, subido_por=request.user)
        nuevo.archivo.save(nombre, ContentFile(buffer.getvalue()))
        nuevo.save()
        Bitacora.objects.create(usuario=request.user, cliente=cliente, accion='generacion', descripcion=f"Generó contrato: {nombre}")
        return redirect('visor_docx', documento_id=nuevo.id)

    return render(request, 'generador/llenar.html', {'cliente': cliente, 'plantilla': plantilla, 'variables': formulario})

@login_required
def visor_docx(request, documento_id):
    doc = get_object_or_404(Documento, id=documento_id)
    html = ""
    if doc.nombre_archivo.endswith('.docx'):
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
    
    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        archivo = request.FILES.get('archivo_base')
        data_reemplazos = request.POST.get('reemplazos')

        if archivo and nombre:
            try:
                doc = DocumentoWord(archivo)
                if data_reemplazos:
                    lista = json.loads(data_reemplazos)
                    for item in lista:
                        original = item.get('texto_original', '')
                        variable = "{{ " + item.get('variable', '') + " }}" 
                        for p in doc.paragraphs:
                            if original in p.text: p.text = p.text.replace(original, variable)
                        for table in doc.tables:
                            for row in table.rows:
                                for cell in row.cells:
                                    for p in cell.paragraphs:
                                        if original in p.text: p.text = p.text.replace(original, variable)

                buffer = BytesIO()
                doc.save(buffer)
                buffer.seek(0)
                nombre_archivo = nombre if nombre.endswith('.docx') else f"{nombre}.docx"
                nueva_plantilla = Plantilla(nombre=nombre)
                nueva_plantilla.archivo.save(nombre_archivo, ContentFile(buffer.getvalue()))
                nueva_plantilla.save()
                messages.success(request, f"¡Plantilla '{nombre}' guardada!")
            except Exception as e:
                messages.error(request, f"Error: {e}")
            return redirect('dashboard')
    return render(request, 'generador/diseñador.html', {'glosario': VariableEstandar.objects.all().order_by('clave')})

@csrf_exempt
@login_required
def previsualizar_word_raw(request):
    if request.method == 'POST' and request.FILES.get('archivo'):
        try:
            f = request.FILES['archivo']
            result = mammoth.convert_to_html(f)
            return JsonResponse({'html': result.value})
        except Exception as e:
            return JsonResponse({'status': 'error', 'msg': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'msg': 'No se envió archivo'}, status=400)

@csrf_exempt
@login_required
def crear_variable_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            clave = data.get('clave')
            descripcion = data.get('descripcion', '')
            tipo = data.get('tipo', 'texto')
            if not clave: return JsonResponse({'status': 'error', 'msg': 'Falta la clave'}, status=400)
            variable, created = VariableEstandar.objects.get_or_create(clave=clave, defaults={'descripcion': descripcion, 'tipo': tipo})
            return JsonResponse({'status': 'ok', 'id': str(variable.id), 'clave': variable.clave, 'created': created})
        except Exception as e:
            return JsonResponse({'status': 'error', 'msg': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'msg': 'Método no permitido'}, status=405)

@csrf_exempt
def api_convertir_html(request):
    import weasyprint 
    if request.method == 'POST':
        try:
            try: data = json.loads(request.body); html_content = data.get('html', '')
            except: html_content = request.POST.get('html', '')
            if not html_content: return JsonResponse({'error': 'No content'}, status=400)
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="documento_diseñado.pdf"'
            base_url = request.build_absolute_uri('/')
            weasyprint.HTML(string=html_content, base_url=base_url).write_pdf(response)
            return response
        except Exception as e: return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)

# ==========================================
# 7. COTIZACIONES Y SERVICIOS
# ==========================================

@login_required
def gestion_servicios(request):
    if not request.user.access_cotizaciones: return redirect('dashboard')
    servicios = Servicio.objects.all().order_by('nombre')
    return render(request, 'cotizaciones/servicios.html', {'servicios': servicios})

@login_required
def guardar_servicio(request):
    if request.method == 'POST':
        s_id = request.POST.get('servicio_id')
        s = get_object_or_404(Servicio, id=s_id) if s_id else Servicio()
        
        s.nombre = request.POST.get('nombre')
        s.descripcion = request.POST.get('descripcion')
        s.precio_base = request.POST.get('precio')
        
        # Guardar lista de campos dinámicos (Nombre: Valor)
        nombres = request.POST.getlist('campo_nombre[]')
        valores = request.POST.getlist('campo_valor[]')
        
        estructura = []
        for nombre, valor in zip(nombres, valores):
            if nombre.strip():
                estructura.append({'nombre': nombre.strip(), 'valor': valor.strip()})
        
        s.campos_dinamicos = estructura
        s.save()
        messages.success(request, "Servicio actualizado correctamente.")
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
    if not request.user.access_cotizaciones: return redirect('dashboard')
    if request.method == 'POST':
        c = Cotizacion.objects.create(
            prospecto_nombre=request.POST.get('nombre'),
            prospecto_email=request.POST.get('email'),
            prospecto_telefono=request.POST.get('telefono'),
            prospecto_empresa=request.POST.get('empresa'),
            validez_hasta=request.POST.get('validez') or None,
            creado_por=request.user
        )
        
        s_ids = request.POST.getlist('servicio_id')
        cants = request.POST.getlist('cantidad')
        precios = request.POST.getlist('precio')
        descs = request.POST.getlist('descripcion')
        
        # Recogemos las respuestas llenadas por el abogado
        extras_json = request.POST.getlist('valores_adicionales_json[]')

        for i in range(len(s_ids)):
            if s_ids[i]:
                item = ItemCotizacion.objects.create(
                    cotizacion=c, 
                    servicio_id=s_ids[i], 
                    cantidad=int(cants[i] or 1),
                    precio_unitario=Decimal(precios[i] or 0), 
                    descripcion_personalizada=descs[i]
                )
                if i < len(extras_json) and extras_json[i]:
                    try:
                        item.valores_adicionales = json.loads(extras_json[i])
                        item.save()
                    except: pass
        c.calcular_totales()
        return redirect('detalle_cotizacion', cotizacion_id=c.id)
    return render(request, 'cotizaciones/crear.html', {'servicios': Servicio.objects.all()})

@login_required
def detalle_cotizacion(request, cotizacion_id):
    c = get_object_or_404(Cotizacion, id=cotizacion_id)
    return render(request, 'cotizaciones/detalle.html', {'c': c, 'plantillas_ws': PlantillaMensaje.objects.filter(tipo='whatsapp')})

@login_required
def generar_pdf_cotizacion(request, cotizacion_id):
    import weasyprint
    c = get_object_or_404(Cotizacion, id=cotizacion_id)
    html = render_to_string('cotizaciones/pdf_template.html', {'c': c, 'base_url': request.build_absolute_uri('/')})
    response = HttpResponse(content_type='application/pdf')
    weasyprint.HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf(response)
    return response

@login_required
def convertir_a_cliente(request, cotizacion_id):
    c = get_object_or_404(Cotizacion, id=cotizacion_id)
    if c.cliente_convertido: return redirect('detalle_cliente', cliente_id=c.cliente_convertido.id)
    cli = Cliente.objects.create(nombre_empresa=c.prospecto_empresa or c.prospecto_nombre, nombre_contacto=c.prospecto_nombre, email=c.prospecto_email, telefono=c.prospecto_telefono)
    if request.user.rol != 'admin': request.user.clientes_asignados.add(cli)
    Carpeta.objects.create(nombre="Documentos Generales", cliente=cli)
    Carpeta.objects.create(nombre="Contratos", cliente=cli)
    CuentaPorCobrar.objects.create(cliente=cli, cotizacion=c, concepto=f"Cotización #{c.id}", monto_total=c.total, saldo_pendiente=c.total, fecha_vencimiento=c.validez_hasta)
    c.estado, c.cliente_convertido = 'aceptada', cli
    c.save()
    return redirect('panel_finanzas')

# ----------------------------------------------------
# FUNCIÓN DE CORREO ACTUALIZADA (RESEND + NOMBRE INTELIGENTE)
# ----------------------------------------------------
@login_required
def enviar_cotizacion_email(request, cotizacion_id):
    import weasyprint 
    
    if request.method == 'POST':
        c = get_object_or_404(Cotizacion, id=cotizacion_id)
        
        # 1. Lógica de Nombres Inteligentes
        nombre_cliente = c.prospecto_empresa if c.prospecto_empresa else c.prospecto_nombre
        fecha_str = timezone.now().strftime("%d-%m-%Y")
        
        # "Cotización_CocaCola_29-01-2026.pdf" (El slugify limpia espacios y caracteres raros)
        nombre_archivo_pdf = f"Cotizacion_{slugify(nombre_cliente)}_{fecha_str}.pdf"
        asunto_default = f"Cotización {nombre_cliente}"

        # 2. Configuración Email
        email_destino = c.prospecto_email
        email_abogado = request.user.email
        # Resend requiere un remitente verificado (o onboarding@resend.dev si es prueba)
        remitente_oficial = settings.DEFAULT_FROM_EMAIL 

        if not email_destino:
            messages.error(request, "El cliente no tiene email registrado.")
            return redirect('detalle_cotizacion', cotizacion_id=cotizacion_id)

        asunto = request.POST.get('asunto', asunto_default)
        mensaje = request.POST.get('mensaje', 'Adjunto encontrará la propuesta de servicios legales solicitada.')

        try:
            # 3. Generar PDF (Usando BASE_DIR para evitar bloqueos)
            html = render_to_string('cotizaciones/pdf_template.html', {
                'c': c, 
                'base_url': str(settings.BASE_DIR) 
            })
            
            pdf_file = weasyprint.HTML(
                string=html, 
                base_url=str(settings.BASE_DIR)
            ).write_pdf()

            # 4. Construir el Correo
            email = EmailMultiAlternatives(
                subject=asunto,
                body=mensaje,
                from_email=remitente_oficial,
                to=[email_destino],
                reply_to=[email_abogado] if email_abogado else None
            )
            
            # Adjuntamos el PDF con el nuevo nombre cool
            email.attach(nombre_archivo_pdf, pdf_file, 'application/pdf')
            
            email.send()

            c.estado = 'enviada'
            c.save()
            messages.success(request, f"Cotización enviada a {nombre_cliente} ({email_destino}).")

        except Exception as e:
            print(f"Error enviando: {e}")
            messages.error(request, f"Error técnico: {str(e)}")

    return redirect('detalle_cotizacion', cotizacion_id=cotizacion_id)

# ==========================================
# 8. FINANZAS
# ==========================================

@login_required
def panel_finanzas(request):
    if not request.user.access_finanzas: return redirect('dashboard')
    cuentas = CuentaPorCobrar.objects.all().order_by('-fecha_emision')
    return render(request, 'finanzas/panel.html', {'cuentas': cuentas, 'total_por_cobrar': sum(c.saldo_pendiente for c in cuentas), 'total_cobrado': sum(c.monto_pagado for c in cuentas)})

@login_required
def registrar_pago(request):
    if request.method == 'POST':
        Pago.objects.create(
            cuenta_id=request.POST.get('cuenta_id'), monto=Decimal(request.POST.get('monto')),
            metodo=request.POST.get('metodo'), referencia=request.POST.get('referencia'), registrado_por=request.user
        )
    return redirect('panel_finanzas')

@login_required
def recibo_pago_pdf(request, pago_id):
    import weasyprint
    p = get_object_or_404(Pago, id=pago_id)
    html = render_to_string('finanzas/recibo_template.html', {'p': p, 'base_url': request.build_absolute_uri('/')})
    response = HttpResponse(content_type='application/pdf')
    weasyprint.HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf(response)
    return response

# ==========================================
# 9. AGENDA
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
    if not request.user.access_agenda: return JsonResponse([], safe=False)
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
        inicio = timezone.make_aware(timezone.datetime.strptime(f"{request.POST.get('fecha')} {request.POST.get('hora')}", "%Y-%m-%d %H:%M"))
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