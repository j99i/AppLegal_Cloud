from django.contrib import admin
from django.urls import path, re_path
from django.conf import settings
from django.views.static import serve
from django.contrib.auth import views as auth_views
from expedientes import views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # AUTH
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', views.signout, name='logout'),
    path('registro/', views.registro, name='registro'),
    path('perfil/', views.mi_perfil, name='mi_perfil'),
    path('reset_password/', auth_views.PasswordResetView.as_view(template_name="registration/password_reset.html"), name='password_reset'),
    path('reset_password_sent/', auth_views.PasswordResetDoneView.as_view(template_name="registration/password_reset_done.html"), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name="registration/password_reset_confirm.html"), name='password_reset_confirm'),
    path('reset_password_complete/', auth_views.PasswordResetCompleteView.as_view(template_name="registration/password_reset_complete.html"), name='password_reset_complete'),

    # CORE
    path('', views.dashboard, name='dashboard'),
    path('usuarios/', views.gestion_usuarios, name='gestion_usuarios'),
    path('usuarios/autorizar/<uuid:user_id>/', views.autorizar_usuario, name='autorizar_usuario'),
    path('usuarios/editar/<uuid:user_id>/', views.editar_usuario, name='editar_usuario'),
    path('usuarios/eliminar/<uuid:user_id>/', views.eliminar_usuario, name='eliminar_usuario'),
    
    path('cliente/nuevo/', views.nuevo_cliente, name='nuevo_cliente'),
    path('cliente/eliminar/<uuid:cliente_id>/', views.eliminar_cliente, name='eliminar_cliente'),
    path('cliente/<uuid:cliente_id>/', views.detalle_cliente, name='detalle_cliente'),
    path('cliente/<uuid:cliente_id>/carpeta/<int:carpeta_id>/', views.detalle_cliente, name='detalle_carpeta'),
    path('cliente/editar/<uuid:cliente_id>/', views.editar_cliente, name='editar_cliente'),

    # CONFIGURACIÓN
    path('configuracion/campos/', views.configurar_campos, name='configurar_campos'),
    path('configuracion/campos/eliminar/<int:campo_id>/', views.eliminar_campo_dinamico, name='eliminar_campo_dinamico'),

    # DRIVE
    path('carpeta/crear/<uuid:cliente_id>/', views.crear_carpeta, name='crear_carpeta'),
    path('carpeta/eliminar/<int:carpeta_id>/', views.eliminar_carpeta, name='eliminar_carpeta'),
    path('expediente/crear/<uuid:cliente_id>/', views.crear_expediente, name='crear_expediente'),
    path('archivo/subir/<uuid:cliente_id>/', views.subir_archivo_drive, name='subir_archivo_drive'),
    path('archivo/eliminar/<int:archivo_id>/', views.eliminar_archivo_drive, name='eliminar_archivo_drive'),
    path('drive/zip/<int:carpeta_id>/', views.descargar_carpeta_zip, name='descargar_carpeta_zip'),
    path('drive/acciones-masivas/', views.acciones_masivas_drive, name='acciones_masivas_drive'),
    path('drive/preview/<int:documento_id>/', views.preview_archivo, name='preview_archivo'),

    # TAREAS
    path('tarea/crear/<uuid:cliente_id>/', views.gestionar_tarea, name='gestionar_tarea'),
    path('tarea/toggle/<int:tarea_id>/', views.toggle_tarea, name='toggle_tarea'),
    path('tarea/editar/<int:tarea_id>/', views.editar_tarea, name='editar_tarea'),
    path('tarea/eliminar/<int:tarea_id>/', views.eliminar_tarea, name='eliminar_tarea'),

    # MÓDULOS
    path('contratos/generar/<uuid:cliente_id>/', views.generador_contratos, name='generador_contratos'),
    path('contratos/visor/<int:documento_id>/', views.visor_docx, name='visor_docx'),
    path('plantillas/subir/', views.subir_plantilla, name='subir_plantilla'),
    
    # HERRAMIENTAS Y API
    path('herramientas/disenador/', views.diseñador_plantillas, name='diseñador_plantillas'),
    path('api/previsualizar-word/', views.previsualizar_word_raw, name='previsualizar_word_raw'),
    path('api/crear-variable/', views.crear_variable_api, name='api_crear_variable'),
    path('api/convertir-html/', views.api_convertir_html, name='api_convertir_html'), 

    # COTIZACIONES
    path('cotizaciones/servicios/', views.gestion_servicios, name='gestion_servicios'),
    path('cotizaciones/servicios/guardar/', views.guardar_servicio, name='guardar_servicio'),
    path('cotizaciones/servicios/eliminar/<int:servicio_id>/', views.eliminar_servicio, name='eliminar_servicio'),
    path('cotizaciones/', views.lista_cotizaciones, name='lista_cotizaciones'),
    path('cotizaciones/nueva/', views.nueva_cotizacion, name='nueva_cotizacion'),
    path('cotizaciones/<int:cotizacion_id>/', views.detalle_cotizacion, name='detalle_cotizacion'),
    path('cotizaciones/<int:cotizacion_id>/pdf/', views.generar_pdf_cotizacion, name='pdf_cotizacion'),
    path('cotizaciones/<int:cotizacion_id>/convertir/', views.convertir_a_cliente, name='convertir_cliente'),
    path('cotizaciones/<int:cotizacion_id>/enviar-email/', views.enviar_cotizacion_email, name='enviar_cotizacion_email'),

    # FINANZAS
    path('finanzas/', views.panel_finanzas, name='panel_finanzas'),
    path('finanzas/pagar/', views.registrar_pago, name='registrar_pago'),
    path('finanzas/recibo/<int:pago_id>/', views.recibo_pago_pdf, name='recibo_pago_pdf'),

    # AGENDA
    path('agenda/', views.agenda_legal, name='agenda_legal'),
    path('agenda/api/', views.api_eventos, name='api_eventos'),
    path('agenda/crear/', views.crear_evento, name='crear_evento'),
    path('agenda/eliminar/<int:evento_id>/', views.eliminar_evento, name='eliminar_evento'),
    path('agenda/mover/', views.mover_evento_api, name='mover_evento_api'),

    # MEDIA PARCHE
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]