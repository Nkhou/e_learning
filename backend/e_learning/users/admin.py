from django.contrib import admin

from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import (
    CustomUser,
    VerificationCode,
    Organization,
    Group,
    Member,
)

class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'first_name', 'last_name', 
                   'privilege', 'status', 'suspended_at', 'is_staff', 'is_active', 'suspension_reason', 'approval_status', 'accept_conditions', 'approval_requested_at', 'approved_at', 'approved_by', 'rejection_reason')
    list_filter = ('privilege', 'status', 'is_staff', 'is_superuser', 'is_active', 'approval_status', 'accept_conditions', 'approval_requested_at', 'approved_at', 'approved_by', 'rejection_reason')
    search_fields = ('first_name', 'last_name', 'email')
    ordering = ('id',)
    fieldsets = (
        (None, {'fields': ('password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'email')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
        (_('Additional info'), {'fields': ('privilege', 'status', 'suspended_at', 'suspension_reason')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('password1', 'password2', 'email', 
                      'first_name', 'last_name', 'privilege', 'status'),
        }),
    )
    
    def get_status_display(self, obj):
        return obj.get_status_display()
    get_status_display.short_description = 'Status'

class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'description', 'organization_type', 'contact_email', 'contact_phone', 'address', 'website')
    list_filter = ('is_active', 'is_completed', 'subscribed_at')
    search_fields = ('user__username', 'course__title_of_course')
    readonly_fields = ('subscribed_at', 'completed_at')
    fields = ('user', 'course', 'is_active', 'total_score', 'progress_percentage', 
              'total_time_spent', 'is_completed', 'completed_at')
