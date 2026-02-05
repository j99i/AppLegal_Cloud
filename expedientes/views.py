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
import qrcode
from num2words import num2words
from django.db import models
from django.db.models import Sum, Count, Q
from django.db.models.functions import Coalesce

# IMPORTACIÓN DE MODELOS
from .models import (
    Usuario, Cliente, Carpeta, Expediente, Documento, 
    Tarea, Bitacora, Plantilla, VariableEstandar,
    Servicio, Cotizacion, ItemCotizacion, PlantillaMensaje,
    CuentaPorCobrar, Pago, Evento, CampoAdicional,
    Requisito, Poliza, MovimientoContable, CuentaContable, 
    Factura, Remision, DatosEmisor
)

from .utils_sat import timbrar_con_facturama
import base64
from docxtpl import DocxTemplate
import mammoth
import weasyprint 

# ==========================================
# 0. HELPER FUNCTIONS
# ==========================================

def generar_y_guardar_pdf_drive(cotizacion, usuario):
    html = render_to_string('cotizaciones/pdf_template.html', {'c': cotizacion, 'base_url': str(settings.BASE_DIR)})
    pdf_file = weasyprint.HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    
    nombre_empresa = cotizacion.cliente.nombre_empresa if cotizacion.cliente else (cotizacion.prospecto_empresa or "Prospecto")
    nombre_archivo = f"Cotizacion_{cotizacion.id}_{slugify(nombre_empresa)}.pdf"
    cliente = cotizacion.cliente

    if cliente:
        carpeta, _ = Carpeta.objects.get_or_create(nombre="Cotizaciones", cliente=cliente, padre=None)
        if not Documento.objects.filter(carpeta=carpeta, nombre_archivo=nombre_archivo).exists():
            doc = Documento(cliente=cliente, carpeta=carpeta, nombre_archivo=nombre_archivo, subido_por=usuario)
            doc.archivo.save(nombre_archivo, ContentFile(pdf_file))
            doc.save()
            
    return pdf_file

def generar_factura_liquidacion_automatica(request, pago, cuenta, descuento_input=0):
    cliente = cuenta.cliente
    c = cuenta.cotizacion
    sufijo = timezone.now().strftime('%H%M%S')
    folio = f"F-FIN-{c.id}-{sufijo}"
    
    try:
        descuento_aplicado = Decimal(descuento_input)
    except:
        descuento_aplicado = Decimal('0.00')

    fac = Factura.objects.create(
        cliente=cliente,
        folio_interno=folio,
        monto_total=pago.monto,
        descuento=descuento_aplicado, 
        estado_sat='pendiente',
        uuid=''
    )
    fac.cotizaciones.add(c)
    
    try:
        respuesta_sat = timbrar_con_facturama(fac)
        fac.uuid = respuesta_sat['Id']
        fac.estado_sat = 'timbrada'
        
        xml_b64 = respuesta_sat.get('CfdiXml') or respuesta_sat.get('Xml')
        if xml_b64:
            xml_content = base64.b64decode(xml_b64)
            fac.archivo_xml.save(f"{fac.uuid}.xml", ContentFile(xml_content))

        emisor = DatosEmisor.objects.first() or DatosEmisor(razon_social="DEMO", rfc="XAXX010101000")
        sello = respuesta_sat.get('Complement', {}).get('TaxStamp', {}).get('SatSign', '')[-8:]
        qr_data = f"https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?id={fac.uuid}&re={emisor.rfc}&rr={fac.cliente.rfc}&tt={fac.monto_total:.6f}&fe={sello}"
        
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(qr_data)
        qr.make(fit=True)
        buffer_qr = BytesIO()
        qr.make_image(fill='black', back_color='white').save(buffer_qr, format="PNG")
        fac.qr_imagen.save(f"qr_{folio}.png", ContentFile(buffer_qr.getvalue()), save=True)

        base_url_clean = str(settings.BASE_DIR).replace('\\', '/')
        qr_path = f"file:///{base_url_clean}/media/{fac.qr_imagen.name}"
        
        total_float = float(fac.monto_total)
        descuento_float = float(fac.descuento)
        
        base_neta = total_float / 1.16
        subtotal = base_neta + descuento_float
        iva = base_neta * 0.16
        
        cantidad_letra = num2words(total_float, lang='es').upper()
        parte_decimal = f"{int((total_float - int(total_float)) * 100):02d}/100 M.N."
        
        html = render_to_string('finanzas/factura_template.html', {
            'f': fac, 
            'base_url': base_url_clean,
            'qr_url': qr_path,
            'emisor': emisor,
            'cifras': {
                'subtotal': subtotal, 
                'descuento': descuento_float, 
                'iva': iva, 
                'total': total_float,
                'letras': f"({cantidad_letra} PESOS {parte_decimal})"
            }
        })
        pdf = weasyprint.HTML(string=html, base_url=base_url_clean).write_pdf()
        fac.pdf_representacion.save(f"Factura_{folio}.pdf", ContentFile(pdf))
        fac.save()
        
        messages.success(request, f"✅ Factura Final generada: {folio}")
        
    except Exception as e:
        fac.delete()
        messages.error(request, f"⚠️ Pago registrado, pero error al facturar: {str(e)}")

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
# 2. GESTIÓN DE USUARIOS
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
    if request.user.rol != 'admin' and cliente not in request.user.clientes_asignados.all():
        return redirect('dashboard')
    
    if request.method == 'POST':
        cliente.nombre_empresa = request.POST.get('nombre_empresa')
        cliente.nombre_contacto = request.POST.get('nombre_contacto')
        cliente.email = request.POST.get('email')
        cliente.telefono = request.POST.get('telefono')
        
        cliente.razon_social = request.POST.get('razon_social', '').upper()
        cliente.rfc = request.POST.get('rfc', '').upper()
        cliente.regimen_fiscal = request.POST.get('regimen_fiscal')
        cliente.codigo_postal = request.POST.get('codigo_postal')
        cliente.uso_cfdi = request.POST.get('uso_cfdi')
        cliente.email_facturacion = request.POST.get('email_facturacion')

        if request.FILES.get('logo'):
            cliente.logo = request.FILES['logo']
        
        datos = cliente.datos_extra or {}
        for campo in CampoAdicional.objects.all():
            val = request.POST.get(f"custom_{campo.id}")
            if val: datos[campo.nombre] = val
        cliente.datos_extra = datos
        
        cliente.save()
        messages.success(request, "Información actualizada correctamente.")
        return redirect('detalle_cliente', cliente_id=cliente.id)
        
    return render(request, 'clientes/editar.html', {'c': cliente, 'campos_dinamicos': CampoAdicional.objects.all()})

@login_required
def guardar_datos_fiscales(request, cliente_id):
    return redirect('editar_cliente', cliente_id=cliente_id)

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
    
    context = {
        'cotizaciones': Cotizacion.objects.all().order_by('-fecha_creacion'),
        'clientes': Cliente.objects.all().order_by('nombre_empresa')
    }
    return render(request, 'cotizaciones/lista.html', context)

@login_required
def detalle_cotizacion(request, cotizacion_id):
    return render(request, 'cotizaciones/detalle.html', {'c': get_object_or_404(Cotizacion, id=cotizacion_id)})
@login_required
def nueva_cotizacion(request):
    if request.method == 'POST':
        # 1. Recibir datos del cliente
        cliente_id = request.POST.get('cliente_id')
        nombre = request.POST.get('nombre')
        empresa = request.POST.get('empresa')
        email = request.POST.get('email')
        telefono = request.POST.get('telefono')
        validez = request.POST.get('validez')

        # 2. Crear la Cotización (AGREGADO: creado_por)
        c = Cotizacion.objects.create(
            cliente_id=cliente_id if cliente_id else None,
            prospecto_nombre=nombre,
            prospecto_empresa=empresa,
            prospecto_email=email,
            prospecto_telefono=telefono,
            validez_hasta=validez if validez else (timezone.now().date() + timedelta(days=15)),
            
            creado_por=request.user,  # <--- ESTA LÍNEA ES VITAL
            
            estado='borrador',
            titulo_proyecto=f"Proyecto {empresa if empresa else nombre}"
        )

        # 3. Recibir listas de items
        servicios_ids = request.POST.getlist('servicio_id')
        cantidades = request.POST.getlist('cantidad')
        precios = request.POST.getlist('precio')
        descripciones = request.POST.getlist('descripcion_item')

        total_acumulado = 0

        # 4. Procesar items
        for i, servicio_id in enumerate(servicios_ids):
            # Guardamos si hay servicio seleccionado o descripción escrita
            if servicio_id or (len(descripciones) > i and descripciones[i]):
                cant = int(cantidades[i]) if cantidades[i] else 1
                prec = Decimal(precios[i]) if precios[i] else 0
                
                # Calculamos subtotal solo para el total general
                subt = cant * prec
                total_acumulado += subt
                
                ItemCotizacion.objects.create(
                    cotizacion=c,
                    servicio_id=servicio_id if servicio_id else None,
                    # Usamos 'descripcion_personalizada' que es el nombre correcto en tu BD
                    descripcion_personalizada=descripciones[i] if len(descripciones) > i else "", 
                    cantidad=cant,
                    precio_unitario=prec
                    # NOTA: No guardamos 'subtotal' aquí porque es autocalculado en el modelo
                )

        # 5. Guardar total y redirigir
        c.total = total_acumulado
        c.save()

        messages.success(request, "Cotización creada exitosamente.")
        return redirect('detalle_cotizacion', cotizacion_id=c.id)

    # GET: Mostrar formulario
    context = {
        'clientes': Cliente.objects.all().order_by('nombre_empresa'),
        'servicios': Servicio.objects.all().order_by('nombre')
    }
    return render(request, 'cotizaciones/crear.html', context)

@login_required
def agregar_item_cotizacion(request, id):
    cotizacion = get_object_or_404(Cotizacion, id=id)
    if request.method == 'POST':
        descripcion = request.POST.get('descripcion')
        cantidad = int(request.POST.get('cantidad', 1))
        precio = Decimal(request.POST.get('precio', '0.00'))
        
        subtotal = cantidad * precio
        
        ItemCotizacion.objects.create(
            cotizacion=cotizacion,
            descripcion=descripcion,
            cantidad=cantidad,
            precio_unitario=precio,
            subtotal=subtotal
        )
        
        cotizacion.total = sum(item.subtotal for item in cotizacion.items.all())
        cotizacion.save()
        messages.success(request, "Concepto agregado.")
    
    return redirect('detalle_cotizacion', cotizacion_id=cotizacion.id)

@login_required
def eliminar_item_cotizacion(request, item_id):
    item = get_object_or_404(ItemCotizacion, id=item_id)
    cotizacion = item.cotizacion
    item.delete()
    
    cotizacion.total = sum(i.subtotal for i in cotizacion.items.all())
    cotizacion.save()
    
    messages.success(request, "Concepto eliminado.")
    return redirect('detalle_cotizacion', cotizacion_id=cotizacion.id)

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
        
        # LÓGICA INTELIGENTE: Detectar email destino
        email_destino = c.cliente.email if c.cliente else c.prospecto_email
        
        if not email_destino: 
            messages.error(request, "Este cliente/prospecto no tiene email registrado.")
            return redirect('preparar_envio_cotizacion', cotizacion_id=c.id)
        
        try:
            pdf = generar_y_guardar_pdf_drive(c, request.user)
            email = EmailMultiAlternatives(
                subject=request.POST.get('asunto'), 
                body=request.POST.get('mensaje'),
                from_email=settings.DEFAULT_FROM_EMAIL, 
                to=[email_destino], 
                reply_to=[request.user.email]
            )
            email.attach(f"Cotizacion_{c.id}.pdf", pdf, 'application/pdf')
            email.send()
            
            c.estado = 'enviada'
            c.save()
            messages.success(request, f"Correo enviado a {email_destino}")
        except Exception as e: 
            messages.error(request, f"Error al enviar: {str(e)}")
            
        return redirect('detalle_cotizacion', cotizacion_id=c.id)
        
    return redirect('detalle_cotizacion', cotizacion_id=cotizacion_id)
@login_required
def preparar_envio_cotizacion(request, cotizacion_id):
    c = get_object_or_404(Cotizacion, id=cotizacion_id)
    
    # LÓGICA INTELIGENTE: Detectar nombre
    if c.cliente:
        nombre = c.cliente.nombre_contacto
    else:
        nombre = c.prospecto_nombre or "Cliente"

    msg = f"Estimado {nombre},\n\nAdjunto le envío la cotización solicitada."
    
    link = request.build_absolute_uri(reverse('generar_pdf_cotizacion', args=[c.id]))
    
    return render(request, 'cotizaciones/preparar_envio.html', {
        'c': c, 
        'msg_email': msg, 
        'msg_wa': f"Hola {nombre}, aquí tienes tu cotización: {link}"
    })

@login_required
def eliminar_cotizacion(request, cotizacion_id):
    if request.user.access_cotizaciones: get_object_or_404(Cotizacion, id=cotizacion_id).delete()
    return redirect('lista_cotizaciones')

@login_required
def convertir_a_cliente(request, cotizacion_id):
    c = get_object_or_404(Cotizacion, id=cotizacion_id)
    
    # Validación para no duplicar cuentas
    if CuentaPorCobrar.objects.filter(cotizacion=c).exists():
        messages.warning(request, "Este proyecto ya fue cerrado anteriormente.")
        # Si ya existe el cliente, redirigir a sus finanzas
        cliente_redir = c.cliente if c.cliente else Cliente.objects.filter(nombre_empresa=c.prospecto_empresa).first()
        if cliente_redir:
            return redirect('finanzas_cliente_detalle', cliente_id=cliente_redir.id)
        return redirect('detalle_cotizacion', cotizacion_id=c.id)

    if request.method == 'POST':
        # ---------------------------------------------------------
        # PASO 1: ASEGURAR QUE EXISTA UN CLIENTE REAL
        # ---------------------------------------------------------
        if c.cliente:
            # Caso A: Ya era un cliente registrado
            cliente_final = c.cliente
        else:
            # Caso B: Es un prospecto, hay que convertirlo a Cliente HOY
            # Usamos nombre de empresa si tiene, si no, el nombre del contacto
            nombre_final = c.prospecto_empresa if c.prospecto_empresa else c.prospecto_nombre
            
            cliente_final = Cliente.objects.create(
                nombre_empresa=nombre_final,
                nombre_contacto=c.prospecto_nombre,
                email=c.prospecto_email,
                telefono=c.prospecto_telefono
                # Aquí puedes agregar fecha_registro=timezone.now() si tu modelo lo requiere
            )
            
            # ¡IMPORTANTE! Vinculamos la cotización al nuevo cliente para siempre
            c.cliente = cliente_final
            
            # Asignar el cliente al usuario actual (opcional, según tu lógica de permisos)
            if request.user.rol != 'admin':
                request.user.clientes_asignados.add(cliente_final)

        # Actualizamos estado de la cotización
        c.estado = 'aceptada'
        c.save()

        # ---------------------------------------------------------
        # PASO 2: CREAR CUENTA POR COBRAR (Usando cliente_final)
        # ---------------------------------------------------------
        requiere_factura = request.POST.get('requiere_factura') # 'si' o 'no'

        cuenta = CuentaPorCobrar.objects.create(
            cliente=cliente_final,  # <--- AHORA SIEMPRE TIENE VALOR
            cotizacion=c,
            concepto=f"Proyecto Cotización #{c.id} - {c.titulo_proyecto}",
            monto_total=c.total,
            saldo_pendiente=c.total,
            fecha_vencimiento=c.validez_hasta,
            estado='pendiente'
        )

        # ---------------------------------------------------------
        # PASO 3: ANTICIPO (50%)
        # ---------------------------------------------------------
        monto_anticipo = c.total * Decimal('0.50')

        if requiere_factura == 'si':
            sufijo = timezone.now().strftime('%H%M%S')
            Factura.objects.create(
                cliente=cliente_final,
                folio_interno=f"F-ANT-{c.id}-{sufijo}",
                monto_total=monto_anticipo,
                estado_sat='pendiente'
            ).cotizaciones.add(c)
            
            messages.success(request, f"¡Nuevo Cliente '{cliente_final.nombre_empresa}' creado! Factura de anticipo lista.")

        else:
            folio_rem = f"REM-{c.id}-{int(timezone.now().timestamp())}"
            Remision.objects.create(
                cliente=cliente_final, 
                cotizacion=c, 
                folio=folio_rem, 
                monto_total=monto_anticipo
            )
            messages.success(request, f"¡Nuevo Cliente '{cliente_final.nombre_empresa}' creado! Remisión generada.")

        # Redirigir a las finanzas del (ahora sí) cliente
        return redirect('finanzas_cliente_detalle', cliente_id=cliente_final.id)
    
    return redirect('detalle_cotizacion', cotizacion_id=c.id)
# ==========================================
# 6. FINANZAS Y FACTURACIÓN
# ==========================================

@login_required
def panel_finanzas(request):
    if not request.user.access_finanzas:
        return redirect('dashboard')

    total_por_cobrar = CuentaPorCobrar.objects.aggregate(t=Sum('saldo_pendiente'))['t'] or 0
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
def crear_factura_anticipo(request, cuenta_id):
    cuenta = get_object_or_404(CuentaPorCobrar, id=cuenta_id)
    c = cuenta.cotizacion
    cliente = cuenta.cliente

    if request.method != 'POST':
        return redirect('finanzas_cliente_detalle', cliente_id=cliente.id)

    if not cliente.rfc or not cliente.razon_social:
        messages.error(request, "Error: El cliente no tiene RFC configurado.")
        return redirect('finanzas_cliente_detalle', cliente_id=cliente.id)
    
    sufijo = timezone.now().strftime('%H%M%S')
    folio = f"F-ANT-{c.id}-{sufijo}"
    
    if Factura.objects.filter(folio_interno=folio).exists():
        return redirect('finanzas_cliente_detalle', cliente_id=cuenta.cliente.id)

    monto_original = c.total * Decimal('0.50') 
    
    descuento_input = request.POST.get('descuento', '0')
    try: descuento_aplicado = Decimal(descuento_input)
    except: descuento_aplicado = Decimal('0.00')

    monto_final_a_pagar = monto_original - descuento_aplicado

    if monto_final_a_pagar < 0:
        messages.error(request, "Error: El descuento no puede ser mayor al total.")
        return redirect('finanzas_cliente_detalle', cliente_id=cliente.id)

    fac = Factura.objects.create(
        cliente=cuenta.cliente, 
        folio_interno=folio, 
        monto_total=monto_final_a_pagar,
        descuento=descuento_aplicado,
        estado_sat='pendiente', 
        uuid=''
    )
    fac.cotizaciones.add(c)

    try:
        respuesta_sat = timbrar_con_facturama(fac)
        fac.uuid = respuesta_sat['Id']
        fac.estado_sat = 'timbrada'
        
        xml_b64 = respuesta_sat.get('CfdiXml') or respuesta_sat.get('Xml')
        if xml_b64:
            xml_content = base64.b64decode(xml_b64)
            fac.archivo_xml.save(f"{fac.uuid}.xml", ContentFile(xml_content))
        
        emisor = DatosEmisor.objects.first() or DatosEmisor(razon_social="DEMO", rfc="XAXX010101000")
        qr_data = f"https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?id={fac.uuid}&re={emisor.rfc}&rr={fac.cliente.rfc}&tt={fac.monto_total:.6f}&fe={respuesta_sat.get('Complement', {}).get('TaxStamp', {}).get('SatSign', '')[-8:]}"
        
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(qr_data); qr.make(fit=True)
        buffer_qr = BytesIO()
        qr.make_image(fill='black', back_color='white').save(buffer_qr, format="PNG")
        fac.qr_imagen.save(f"qr_{folio}.png", ContentFile(buffer_qr.getvalue()), save=True)
        
        base_url_clean = str(settings.BASE_DIR).replace('\\', '/')
        qr_path = f"file:///{base_url_clean}/media/{fac.qr_imagen.name}" if fac.qr_imagen else None

        total_float = float(fac.monto_total)
        descuento_float = float(fac.descuento)
        base = total_float / 1.16
        subtotal = base + descuento_float
        iva = base * 0.16
        
        cantidad_letra = num2words(total_float, lang='es').upper()
        parte_decimal = f"{int((total_float - int(total_float)) * 100):02d}/100 M.N."
        texto_final = f"({cantidad_letra} PESOS {parte_decimal})"

        html = render_to_string('finanzas/factura_template.html', {
            'f': fac, 'base_url': base_url_clean, 'qr_url': qr_path, 'emisor': emisor,
            'cifras': {
                'subtotal': subtotal, 'descuento': descuento_float, 'iva': iva,
                'total': total_float, 'letras': texto_final
            }
        })
        pdf = weasyprint.HTML(string=html, base_url=base_url_clean).write_pdf()
        fac.pdf_representacion.save(f"Factura_{folio}.pdf", ContentFile(pdf))
        fac.save()
        messages.success(request, f"Factura timbrada con descuento de ${descuento_float}.")
    except Exception as e:
        fac.delete()
        messages.error(request, f"Error SAT: {str(e)}")

    return redirect('finanzas_cliente_detalle', cliente_id=cuenta.cliente.id)

@login_required
def registrar_pago(request):
    if request.method == 'POST':
        cuenta_id = request.POST.get('cuenta_id')
        monto = Decimal(request.POST.get('monto'))
        metodo = request.POST.get('metodo')
        ref = request.POST.get('referencia')
        
        usuario_pide_factura = request.POST.get('generar_factura_final') == 'on'
        descuento_factura = request.POST.get('descuento_final', '0')
        
        cuenta = get_object_or_404(CuentaPorCobrar, id=cuenta_id)
        
        pago = Pago.objects.create(
            cuenta=cuenta, monto=monto, metodo=metodo, referencia=ref
        )
        
        cuenta.saldo_pendiente -= monto
        if cuenta.saldo_pendiente <= 0:
            cuenta.saldo_pendiente = 0
            cuenta.estado = 'pagada'
        cuenta.save()

        tiene_anticipo = Factura.objects.filter(cotizaciones=cuenta.cotizacion, estado_sat='timbrada').exists()

        if tiene_anticipo:
            generar_factura_liquidacion_automatica(request, pago, cuenta, descuento_factura)
        elif usuario_pide_factura:
            generar_factura_liquidacion_automatica(request, pago, cuenta, descuento_factura)
        else:
            messages.success(request, "Pago registrado. Recibo generado.")

        return redirect('finanzas_cliente_detalle', cliente_id=cuenta.cliente.id)
        
    return redirect('panel_finanzas')

@login_required
def generar_factura_sat(request, cotizacion_id):
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
def recibo_pago_pdf(request, pago_id):
    pago = get_object_or_404(Pago, id=pago_id)
    html = render_to_string('finanzas/recibo_template.html', {
        'pago': pago, 'base_url': str(settings.BASE_DIR), 'cliente': pago.cuenta.cliente
    })
    pdf = weasyprint.HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="Recibo_Pago_{pago.id}.pdf"'
    return response

@login_required
def facturar_multiples(request):
    if request.method == 'POST':
        ids = request.POST.getlist('cuentas_ids')
        messages.info(request, f"Opción de facturación masiva en construcción. Se recibieron {len(ids)} elementos.")
    return redirect('panel_finanzas')

@login_required
def previsualizar_factura(request, cotizacion_id): return redirect('panel_finanzas')
@login_required
def crear_factura_faltante(request, cotizacion_id): return redirect('panel_finanzas')
@login_required
def generar_docs_finiquito(request, cuenta_id): return redirect('panel_finanzas')

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

@login_required
def guardar_datos_emisor(request):
    if request.user.rol != 'admin':
        messages.error(request, "Acceso denegado.")
        return redirect('panel_finanzas')
        
    if request.method == 'POST':
        emisor, _ = DatosEmisor.objects.get_or_create(id=1)
        emisor.razon_social = request.POST.get('razon_social')
        emisor.rfc = request.POST.get('rfc')
        emisor.regimen_fiscal = request.POST.get('regimen_fiscal')
        emisor.codigo_postal = request.POST.get('codigo_postal')
        emisor.direccion = request.POST.get('direccion')
        emisor.save()
        messages.success(request, "Datos del Despacho actualizados.")
        
    return redirect('panel_finanzas')