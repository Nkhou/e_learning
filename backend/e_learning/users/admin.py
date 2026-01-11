from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import (
    CustomUser,
    VerificationCode,
    Organization,
    Group,
    Member,
    UserThemeStats,
    OrganizationDailyStats,
)


class CustomUserAdmin(UserAdmin):
    list_display = (
        'username', 'email', 'first_name', 'last_name', 
        'privilege', 'status', 'approval_status', 'is_staff', 'is_active'
    )
    list_filter = (
        'privilege', 'status', 'is_staff', 'is_superuser', 
        'is_active', 'approval_status', 'accept_conditions'
    )
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('id',)
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'email')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
        (_('User Status'), {
            'fields': ('privilege', 'status', 'suspended_at', 'suspension_reason', 'accept_conditions')
        }),
        (_('Approval Info'), {
            'fields': ('approval_status', 'approval_requested_at', 'approved_at', 'approved_by', 'rejection_reason')
        }),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'email', 
                      'first_name', 'last_name', 'privilege', 'status', 'accept_conditions'),
        }),
    )
    
    readonly_fields = ('last_login', 'date_joined', 'suspended_at', 'approval_requested_at', 'approved_at')
    
    def get_status_display(self, obj):
        return obj.get_status_display()
    get_status_display.short_description = 'Status'


class VerificationCodeAdmin(admin.ModelAdmin):
    list_display = ('user', 'type', 'code', 'created_at', 'expires_at', 'is_expired', 'is_used')
    list_filter = ('type', 'created_at', 'expires_at')
    search_fields = ('user__username', 'user__email', 'code')
    readonly_fields = ('created_at', 'used_at')
    ordering = ('-created_at',)


class OrganizationAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'user', 'organization_type', 'contact_email', 
        'total_members', 'total_groups', 'total_formations', 'created_at'
    )
    list_filter = ('organization_type', 'created_at')
    search_fields = ('name', 'user__username', 'user__email', 'contact_email')
    readonly_fields = ('created_at', 'updated_at', 'total_members', 'total_groups', 'total_formations')
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('user', 'name', 'description', 'organization_type')
        }),
        (_('Contact Information'), {
            'fields': ('contact_email', 'contact_phone', 'address', 'website')
        }),
        (_('Statistics'), {
            'fields': ('total_members', 'total_groups', 'total_formations'),
            'classes': ('collapse',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.update_statistics()


class MemberInline(admin.TabularInline):
    model = Member
    extra = 0
    fields = ('user', 'role', 'status', 'joined_at', 'last_active_at')
    readonly_fields = ('joined_at', 'last_active_at')


class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'org', 'status', 'member_count', 'active_member_count', 'created_at')
    list_filter = ('status', 'created_at', 'org')
    search_fields = ('name', 'org__name', 'description')
    readonly_fields = ('created_at', 'updated_at', 'member_count', 'active_member_count', 'formation_count')
    inlines = [MemberInline]
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('org', 'name', 'description', 'status')
        }),
        (_('Statistics'), {
            'fields': ('member_count', 'active_member_count', 'formation_count'),
            'classes': ('collapse',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


class MemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'group', 'role', 'status', 'joined_at', 'last_active_at')
    list_filter = ('role', 'status', 'joined_at')
    search_fields = ('user__username', 'user__email', 'group__name', 'group__org__name')
    readonly_fields = ('joined_at', 'last_active_at')
    
    fieldsets = (
        (_('Member Information'), {
            'fields': ('user', 'group', 'role', 'status')
        }),
        (_('Activity'), {
            'fields': ('joined_at', 'last_active_at')
        }),
    )


class UserThemeStatsAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'tag', 'strength_level', 'completed_contents', 
        'total_contents', 'average_score', 'updated_at'
    )
    list_filter = ('strength_level', 'updated_at')
    search_fields = ('user__username', 'tag__name')
    readonly_fields = ('updated_at',)
    ordering = ('-updated_at',)


class OrganizationDailyStatsAdmin(admin.ModelAdmin):
    list_display = (
        'organization', 'date', 'active_members', 'inactive_members',
        'courses_started', 'courses_completed', 'total_learning_time'
    )
    list_filter = ('date', 'organization')
    search_fields = ('organization__name',)
    readonly_fields = ('date',)
    ordering = ('-date',)
    
    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing an existing object
            return self.readonly_fields + ('organization',)
        return self.readonly_fields


# Register all models
admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(VerificationCode, VerificationCodeAdmin)
admin.site.register(Organization, OrganizationAdmin)
admin.site.register(Group, GroupAdmin)
admin.site.register(Member, MemberAdmin)
admin.site.register(UserThemeStats, UserThemeStatsAdmin)
admin.site.register(OrganizationDailyStats, OrganizationDailyStatsAdmin)