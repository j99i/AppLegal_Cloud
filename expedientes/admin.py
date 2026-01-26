from django.contrib import admin
from django.contrib.auth.models import Group
from django.contrib.auth.admin import UserAdmin
from .models import Usuario, Cliente, Expediente

admin.site.unregister(Group)

@admin.register(Usuario)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Roles y Permisos', {'fields': ('rol', 'area', 'can_create_client', 'can_edit_client', 'can_delete_client', 'can_view_documents', 'can_upload_files', 'can_manage_users')}),
    )
    list_display = ('username', 'rol', 'is_active')

admin.site.register(Cliente)
admin.site.register(Expediente)