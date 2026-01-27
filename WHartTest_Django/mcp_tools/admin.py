from django.contrib import admin

# Register your models here.
from .models import RemoteMCPConfig

@admin.register(RemoteMCPConfig)
class RemoteMCPConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'transport', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active', 'transport')
    search_fields = ('name', 'url')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('name', 'url', 'transport', 'headers', 'is_active')
        }),
    )
