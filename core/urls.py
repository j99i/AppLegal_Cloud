from django.contrib import admin
from django.urls import path, re_path
from django.conf import settings
from django.views.static import serve
from django.contrib.auth import views as auth_views
from expedientes import views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # ==========================================
    # AUTENTICACIÓN
    # ==========================================
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', views.signout, name='logout'),
    path('registro/', views.registro, name='registro'),
    path('perfil/', views.mi_perfil, name='mi_perfil'),
    path('reset_password/', auth_views.PasswordResetView.as_view(template_name="registration/password_reset.html"), name='password_reset'),
    path('reset_password_sent/', auth_views.PasswordResetDoneView.as_view(template_name="registration/password_reset_done.html"), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name="registration/password_reset_confirm.html"), name='password_reset_confirm'),
    path('reset_password_complete/', auth_views.PasswordResetCompleteView.as_view(template_name="registration/password_reset_complete.html"), name='password_reset_complete'),

    # ==========================================
    # DASHBOARD & USUARIOS
    # ==========================================
    path('', views.dashboard, name='dashboard'),
    path('usuarios/', views.gestion_usuarios, name='gestion_usuarios'),
    path('usuarios/autorizar/<int:user_id>/', views.autorizar_usuario, name='autorizar_usuario'),
    path('usuarios/editar/<int:user_id>/', views.editar_usuario, name='editar_usuario'),
    path('usuarios/eliminar/<int:user_id>/', views.eliminar_usuario, name='eliminar_usuario'),
    
    # ==========================================
    # CLIENTES
    # ==========================================
    path('cliente/nuevo/', views.nuevo_cliente, name='nuevo_cliente'),
    path('cliente/eliminar/<int:cliente_id>/', views.eliminar_cliente, name='eliminar_cliente'),
    path('cliente/<int:cliente_id>/', views.detalle_cliente, name='detalle_cliente'),
    path('cliente/<int:cliente_id>/carpeta/<int:carpeta_id>/', views.detalle_cliente, name='detalle_carpeta'),
    path('cliente/editar/<int:cliente_id>/', views.editar_cliente, name='editar_cliente'),
    path('cliente/fiscal/<int:cliente_id>/', views.guardar_datos_fiscales, name='guardar_datos_fiscales'),

    # ==========================================
    # CONFIGURACIÓN
    # ==========================================
    path('configuracion/campos/', views.configurar_campos, name='configurar_campos'),
    path('configuracion/campos/eliminar/<int:campo_id>/', views.eliminar_campo_dinamico, name='eliminar_campo_dinamico'),

    # ==========================================
    # DRIVE & ARCHIVOS
    # ==========================================
    path('carpeta/crear/<int:cliente_id>/', views.crear_carpeta, name='crear_carpeta'),
    path('carpeta/eliminar/<int:carpeta_id>/', views.eliminar_carpeta, name='eliminar_carpeta'),
    path('expediente/crear/<int:cliente_id>/', views.crear_expediente, name='crear_expediente'),
    path('archivo/subir/<int:cliente_id>/', views.subir_archivo_drive, name='subir_archivo_drive'),
    path('archivo/eliminar/<int:archivo_id>/', views.eliminar_archivo_drive, name='eliminar_archivo_drive'),
    path('archivo/mover/<int:documento_id>/', views.mover_archivo, name='mover_archivo'),
    path('drive/zip/<int:carpeta_id>/', views.descargar_carpeta_zip, name='descargar_carpeta_zip'),
    path('drive/acciones-masivas/', views.acciones_masivas_drive, name='acciones_masivas_drive'),
    path('drive/preview/<int:documento_id>/', views.preview_archivo, name='preview_archivo'),
    path('requisito/subir/<int:requisito_id>/', views.subir_evidencia_requisito, name='subir_evidencia_requisito'),

    # PAPELERA
    path('papelera/<int:cliente_id>/', views.ver_papelera, name='ver_papelera'),
    path('archivo/restaurar/<int:archivo_id>/', views.restaurar_archivo, name='restaurar_archivo'),
    path('archivo/forzar-delete/<int:archivo_id>/', views.forzar_eliminacion, name='forzar_eliminacion'),

    # ==========================================
    # TAREAS & AGENDA
    # ==========================================
    path('tarea/crear/<int:cliente_id>/', views.gestionar_tarea, name='gestionar_tarea'),
    path('tarea/toggle/<int:tarea_id>/', views.toggle_tarea, name='toggle_tarea'),
    path('tarea/editar/<int:tarea_id>/', views.editar_tarea, name='editar_tarea'),
    path('tarea/eliminar/<int:tarea_id>/', views.eliminar_tarea, name='eliminar_tarea'),
    
    path('agenda/', views.agenda_legal, name='agenda_legal'),
    path('agenda/api/', views.api_eventos, name='api_eventos'),
    path('agenda/crear/', views.crear_evento, name='crear_evento'),
    path('agenda/eliminar/<int:evento_id>/', views.eliminar_evento, name='eliminar_evento'),
    path('agenda/mover/', views.mover_evento_api, name='mover_evento_api'),

    # ==========================================
    # CONTRATOS & PLANTILLAS
    # ==========================================
    path('contratos/generar/<int:cliente_id>/', views.generador_contratos, name='generador_contratos'),
    path('contratos/visor/<int:documento_id>/', views.visor_docx, name='visor_docx'),
    path('plantillas/subir/', views.subir_plantilla, name='subir_plantilla'),
    path('plantillas/eliminar/<int:plantilla_id>/', views.eliminar_plantilla, name='eliminar_plantilla'),
    path('herramientas/disenador/', views.diseñador_plantillas, name='diseñador_plantillas'),
    path('api/previsualizar-word/', views.previsualizar_word_raw, name='previsualizar_word_raw'),
    path('api/crear-variable/', views.crear_variable_api, name='api_crear_variable'),
    path('api/convertir-html/', views.api_convertir_html, name='api_convertir_html'), 

    # ==========================================
    # COTIZACIONES (CORREGIDO)
    # ==========================================
    # Gestión de servicios
    path('cotizaciones/servicios/', views.gestion_servicios, name='gestion_servicios'),
    path('cotizaciones/servicios/guardar/', views.guardar_servicio, name='guardar_servicio'),
    path('cotizaciones/servicios/eliminar/<int:servicio_id>/', views.eliminar_servicio, name='eliminar_servicio'),
    
    # Gestión de Cotizaciones
    path('cotizaciones/', views.lista_cotizaciones, name='lista_cotizaciones'),
    path('cotizaciones/nueva/', views.nueva_cotizacion, name='nueva_cotizacion'),
    path('cotizaciones/<int:cotizacion_id>/', views.detalle_cotizacion, name='detalle_cotizacion'),
    path('cotizaciones/eliminar/<int:cotizacion_id>/', views.eliminar_cotizacion, name='eliminar_cotizacion'),
    
    # Items de Cotización (Usa <int:id> porque así está en views.py)
    path('cotizaciones/<int:id>/agregar-item/', views.agregar_item_cotizacion, name='agregar_item_cotizacion'),
    path('cotizaciones/eliminar-item/<int:item_id>/', views.eliminar_item_cotizacion, name='eliminar_item_cotizacion'),

    # Acciones
    path('cotizaciones/<int:cotizacion_id>/pdf/', views.generar_pdf_cotizacion, name='generar_pdf_cotizacion'),
    path('cotizaciones/<int:cotizacion_id>/email/', views.enviar_cotizacion_email, name='enviar_cotizacion_accion'), # Renombrado para evitar conflicto
    path('cotizaciones/<int:cotizacion_id>/preparar-envio/', views.preparar_envio_cotizacion, name='preparar_envio_cotizacion'),
    path('cotizaciones/<int:cotizacion_id>/enviar-email/', views.enviar_cotizacion_email, name='enviar_cotizacion_email'),
    
    # Conversión (Cierre de Trato) - ESTA ES LA CLAVE QUE FALLABA
    path('cotizaciones/convertir/<int:cotizacion_id>/', views.convertir_a_cliente, name='convertir_a_cliente'),

    # ==========================================
    # FINANZAS & FACTURACIÓN
    # ==========================================
    path('finanzas/', views.panel_finanzas, name='panel_finanzas'),
    path('finanzas/cliente/<int:cliente_id>/', views.finanzas_cliente_detalle, name='finanzas_cliente_detalle'),
    path('finanzas/configurar-emisor/', views.guardar_datos_emisor, name='guardar_datos_emisor'),
    
    # Pagos
    path('finanzas/pagar/', views.registrar_pago, name='registrar_pago'), 
    path('finanzas/recibo/<int:pago_id>/', views.recibo_pago_pdf, name='recibo_pago_pdf'),
    
    # Contabilidad
    path('finanzas/contabilidad/', views.libro_contable, name='libro_contable'),
    
    # Facturación
    path('finanzas/facturar-multiples/', views.facturar_multiples, name='facturar_multiples'),
    path('finanzas/facturar-anticipo/<int:cuenta_id>/', views.crear_factura_anticipo, name='crear_factura_anticipo'),
    path('finanzas/crear-factura-anticipo/<int:cotizacion_id>/', views.crear_factura_faltante, name='crear_factura_faltante'),
    path('finanzas/finiquito/<int:cuenta_id>/', views.generar_docs_finiquito, name='generar_docs_finiquito'),

    # SAT API
    path('facturacion/previsualizar/<int:cotizacion_id>/', views.previsualizar_factura, name='previsualizar_factura'),
    path('facturacion/timbrar/<int:cotizacion_id>/', views.generar_factura_sat, name='generar_factura_sat'),

    # MEDIA (Solo desarrollo)
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]