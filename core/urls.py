from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from expedientes import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', views.signout, name='logout'),
    path('registro/', views.registro, name='registro'),
    path('', views.dashboard, name='dashboard'),
    path('nuevo-cliente/', views.nuevo_cliente, name='nuevo_cliente'),
    
    # Usuarios (UUID)
    path('usuarios/', views.gestion_usuarios, name='gestion_usuarios'),
    path('autorizar/<str:user_id>/', views.autorizar_usuario, name='autorizar_usuario'),
    path('editar-usuario/<str:user_id>/', views.editar_usuario, name='editar_usuario'),

    # Cliente y Drive (TODO CON STR PARA UUID)
    path('cliente/<str:cliente_id>/', views.detalle_cliente, name='detalle_cliente'),
    path('cliente/<str:cliente_id>/nueva-carpeta/', views.crear_carpeta, name='crear_carpeta'),
    path('cliente/<str:cliente_id>/nuevo-expediente/', views.crear_expediente, name='crear_expediente'),
    path('cliente/<str:cliente_id>/subir-drive/', views.subir_archivo_drive, name='subir_archivo_drive'),
    path('cliente/<str:cliente_id>/gestionar-tarea/', views.gestionar_tarea, name='gestionar_tarea'),
    path('cliente/<str:cliente_id>/eliminar/', views.eliminar_cliente, name='eliminar_cliente'),
    
    # Archivos (Siguen siendo INT porque son IDs internos de la BD)
    path('archivo/eliminar/<int:archivo_id>/', views.eliminar_archivo_drive, name='eliminar_archivo'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)