from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from expedientes import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', views.signout, name='logout'), # Ruta de salida corregida
    path('registro/', views.registro, name='registro'),
    path('', views.dashboard, name='dashboard'),
    path('nuevo-cliente/', views.nuevo_cliente, name='nuevo_cliente'),
    path('cliente/<int:cliente_id>/', views.detalle_cliente, name='detalle_cliente'),
    path('subir-archivo/<int:expediente_id>/', views.subir_archivo, name='subir_archivo'),
    path('autorizar/<int:user_id>/', views.autorizar_usuario, name='autorizar_usuario'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)