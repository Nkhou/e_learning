# users/serializers.py - Version complète corrigée

import string
import secrets
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    CustomUser, 
    VerificationCode, 
    Organization, 
    Group, 
    Member,
    UserThemeStats,
    OrganizationDailyStats
)

User = get_user_model()

# ==================== USER SERIALIZERS ====================
def generate_random_password():
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(12))
class CustomUserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    is_active_user = serializers.BooleanField(read_only=True)
    can_access_platform = serializers.BooleanField(read_only=True)
    needs_approval = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'privilege', 'status', 'approval_status', 'date_joined', 'last_login',
            'is_active_user', 'can_access_platform', 'needs_approval',
            'approval_requested_at', 'approved_at', 'rejection_reason'
        ]
        extra_kwargs = {
            'password': {'write_only': True}
        }
    
    def get_full_name(self, obj):
        return obj.full_name()
    
    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data.get('password',generate_random_password()),
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            privilege=validated_data.get('privilege', 'AP'),
            approval_status=validated_data.get('approval_status', 'approved'),
        )
        return user

class CustomUserApprovalSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'first_name', 'last_name', 'privilege', 
                  'approval_status', 'approval_requested_at', 'rejection_reason']
        read_only_fields = ['email', 'first_name', 'last_name', 'privilege']

class VerificationCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = VerificationCode
        fields = ['id', 'user', 'code', 'type', 'expires_at', 'created_at', 'used_at']
        read_only_fields = ['user', 'created_at']

# ==================== ORGANIZATION SERIALIZERS ====================

class OrganizationSerializer(serializers.ModelSerializer):
    user = CustomUserSerializer(read_only=True)
    
    class Meta:
        model = Organization
        fields = [
            'id', 'user', 'name', 'description', 'organization_type',
            'contact_email', 'contact_phone', 'address', 'website',
            'total_members', 'total_groups', 'total_formations',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['user', 'total_members', 'total_groups', 
                          'total_formations', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        # Le user est défini dans la vue
        return Organization.objects.create(**validated_data)

class GroupSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(source='members.count', read_only=True)
    active_member_count = serializers.IntegerField(read_only=True)
    formation_count = serializers.IntegerField(read_only=True)
    is_active_group = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Group
        fields = [
            'id', 'org', 'name', 'description', 'status',
            'member_count', 'active_member_count', 'formation_count',
            'is_active_group', 'created_at', 'updated_at'
        ]
        read_only_fields = ['org', 'created_at', 'updated_at']

class CreateGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['name', 'description', 'status']
    
    def create(self, validated_data):
        org = self.context.get('organization')
        if not org:
            raise serializers.ValidationError("Organization is required")
        
        return Group.objects.create(org=org, **validated_data)

class MemberSerializer(serializers.ModelSerializer):
    user = CustomUserSerializer(read_only=True)
    group_name = serializers.CharField(source='group.name', read_only=True)
    organization_name = serializers.CharField(source='group.org.name', read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Member
        fields = [
            'id', 'user', 'group', 'group_name', 'organization_name',
            'role', 'status', 'joined_at', 'last_active_at', 'is_active'
        ]
        read_only_fields = ['user', 'group', 'joined_at', 'last_active_at']

class AddMemberSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Member.MEMBER_ROLE_CHOICES, default='member')
    
    def validate_email(self, value):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Aucun utilisateur trouvé avec cet email")
        return value

class UpdateMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Member
        fields = ['role', 'status']

# ==================== STATISTICS SERIALIZERS ====================

class UserThemeStatsSerializer(serializers.ModelSerializer):
    tag_name = serializers.CharField(source='tag.name', read_only=True)
    
    class Meta:
        model = UserThemeStats
        fields = [
            'id', 'tag', 'tag_name', 'total_time_spent', 'average_score',
            'completed_contents', 'total_contents', 'strength_level', 'updated_at'
        ]
        read_only_fields = ['user', 'updated_at']

class OrganizationDailyStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationDailyStats
        fields = [
            'id', 'organization', 'date', 'active_members', 'inactive_members',
            'total_learning_time', 'courses_started', 'courses_completed'
        ]
        read_only_fields = ['organization']