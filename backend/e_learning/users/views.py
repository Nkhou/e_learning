# users/views.py
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.http import Http404
from django.core.mail import send_mail
from datetime import timedelta
import random
import string

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.authentication import BasicAuthentication
from django.contrib.auth import authenticate
from django.db.models import Avg, Count, Sum
import logging
from django.templatetags.static import static
import jwt
from django.conf import settings
from django.utils import timezone
from django.db import connection
import secrets
import string
import os
import json
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.contrib.auth import get_user_model

from .models import CustomUser, VerificationCode, Organization, OrganizationDailyStats, Member, Group
from .serializers import (
    CustomUserSerializer,
    OrganizationSerializer,
    GroupSerializer,
    CreateGroupSerializer,
    MemberSerializer,
    AddMemberSerializer,
    UpdateMemberSerializer,
    CustomUserApprovalSerializer,
    VerificationCodeSerializer
)

# Import des modèles de cours si nécessaire pour certaines vues
from cours.models import Course, Subscription, QCMCompletion, TimeTracking
from cours.models import Enrollment  # Utilisé dans VerifyLoginCodeView

logger = logging.getLogger(__name__)
User = get_user_model()

def is_secure_request(request):
    """Check if the request is secure (HTTPS)"""
    return (
        request.is_secure() or
        request.META.get('HTTP_X_FORWARDED_PROTO') == 'https' or
        settings.USE_SSL or
        settings.PRODUCTION
    )

def is_supper_user(request):
    return request.user.privilege == 'A'

def generate_random_password():
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(12))

# Helper Functions
def generate_verification_code(length=6):
    """Generate a random 6-digit verification code"""
    return ''.join(random.choices(string.digits, k=length))

def send_login_code_email(user, code):
    """Send login verification code to user's email"""
    subject = 'Your Login Code - E-Learning Platform'
    message = f"""
Hello {user.first_name} {user.last_name},

Someone requested to sign in to your E-Learning Platform account.

Your verification code is: {code}

This code will expire in 10 minutes.

If you didn't request this code, please ignore this email and your account will remain secure.

Best regards,
E-Learning Platform Team
"""
    
    from_email = settings.EMAIL_HOST_USER
    recipient_list = [user.email]
    
    try:
        send_mail(subject, message, from_email, recipient_list, fail_silently=False)
        return True
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return False

# Health Check Views
class HealthCheckView(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request):
        health_status = {
            'status': 'healthy',
            'timestamp': str(timezone.now()),
            'version': '1.0.0',
            'service': 'course-app-backend',
            'ssl_enabled': is_secure_request(request)
        }
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            health_status['database'] = 'connected'
        except Exception as e:
            health_status['database'] = f'error: {str(e)}'
            health_status['status'] = 'degraded'
        
        return Response(health_status, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([AllowAny])
def simple_health_check(request):
    return Response({
        'status': 'healthy',
        'message': 'Service is running',
        'timestamp': str(timezone.now()),
        'ssl_enabled': is_secure_request(request)
    }, status=status.HTTP_200_OK)

class RegisterView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        try:
            email = request.data.get('email', '').strip().lower()
            first_name = request.data.get('first_name', '').strip()
            last_name = request.data.get('last_name', '').strip()
            privilege = request.data.get('privilege', 'AP').strip().upper()
            approval_status = request.data.get('approval_status', 'pending')
            
            # Check if email already exists
            if CustomUser.objects.filter(email=email).exists():
                return Response(
                    {"error": "Email already in use"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Generate username
            username = f"{first_name.lower()}_{last_name.lower()}"[:150]
            username = ''.join(c for c in username if c.isalnum() or c in '._-')
            
            # Handle Apprenant (AP)
            if privilege == 'AP':
                user_data = {
                    'username': username,
                    'email': email,
                    'first_name': first_name,
                    'last_name': last_name,
                    'privilege': privilege,
                    'approval_status': 'approved'
                }

                serializer = CustomUserSerializer(data=user_data)
                if serializer.is_valid():
                    user = serializer.save()
                    return Response(
                        {
                            "message": "User registered successfully",
                            "username": username,
                            "user_id": user.id
                        },
                        status=status.HTTP_201_CREATED
                    )
                else:
                    print("Serializer errors:", serializer.errors)
                    return Response(
                        {
                            "error": "Invalid data",
                            "details": serializer.errors
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )

            elif privilege == 'F':
                user_data = {
                    'username': username,
                    'email': email,
                    'first_name': first_name,
                    'last_name': last_name,
                    'privilege': privilege,
                    'approval_status': approval_status or 'pending',
                }
                
                serializer = CustomUserSerializer(data=user_data)
                if serializer.is_valid():
                    user = serializer.save()
                    return Response(
                        {
                            "message": "Formateur registered successfully. Awaiting approval.",
                            "username": username,
                            "user_id": user.id,
                            "approval_status": user.approval_status
                        },
                        status=status.HTTP_201_CREATED
                    )
                else:
                    print("Serializer errors:", serializer.errors)
                    return Response(
                        {
                            "error": "Invalid data",
                            "details": serializer.errors
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Handle Organization (O)
            elif privilege == 'O':
                name = request.data.get('name', '').strip()
                organization_type = request.data.get('organization_type', '').strip()
                contact_email = request.data.get('contact_email', '').strip()
                contact_phone = request.data.get('contact_phone', '').strip()
                address = request.data.get('address', '').strip()
                website = request.data.get('website', '').strip()
                
                # Validate required organization fields
                if not all([name, organization_type, contact_email, contact_phone, address]):
                    missing = []
                    if not name: missing.append('name')
                    if not organization_type: missing.append('organization_type')
                    if not contact_email: missing.append('contact_email')
                    if not contact_phone: missing.append('contact_phone')
                    if not address: missing.append('address')
                    
                    return Response(
                        {
                            "error": "Required organization fields are missing",
                            "missing_fields": missing
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                user_data = {
                    'username': username,
                    'email': email,
                    'first_name': first_name,
                    'last_name': last_name,
                    'privilege': privilege,
                    'approval_status': approval_status or 'pending',
                }
                
                serializer = CustomUserSerializer(data=user_data)
                if serializer.is_valid():
                    user = serializer.save()
                    
                    # Create organization
                    org_data = {
                        'user': user.id,
                        'name': name,
                        'organization_type': organization_type,
                        'contact_email': contact_email,
                        'contact_phone': contact_phone,
                        'address': address,
                        'website': website if website else None,
                    }
                    
                    serializer_organization = OrganizationSerializer(data=org_data)
                    if serializer_organization.is_valid():
                        serializer_organization.save()
                        return Response(
                            {
                                "message": "Organization registered successfully. Awaiting approval.",
                                "username": username,
                                "user_id": user.id,
                                "organization_name": name,
                                "approval_status": user.approval_status
                            },
                            status=status.HTTP_201_CREATED
                        )
                    else:
                        # If organization creation fails, delete the user
                        user.delete()
                        print("Organization serializer errors:", serializer_organization.errors)
                        return Response(
                            {
                                "error": "Invalid organization data",
                                "details": serializer_organization.errors
                            },
                            status=status.HTTP_400_BAD_REQUEST
                        )
                else:
                    print("User serializer errors:", serializer.errors)
                    return Response(
                        {
                            "error": "Invalid user data",
                            "details": serializer.errors
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Handle invalid privilege
            else:
                return Response(
                    {
                        "error": "Invalid privilege type",
                        "details": f"Privilege must be one of: AP, F, O. Received: {privilege}"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            print(f"Unexpected error in RegisterView: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {
                    "error": "Internal server error",
                    "details": str(e) if request.user.is_staff else "An error occurred"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class RequestLoginCodeView(APIView):
    """
    Step 1 of login: User provides email, system sends verification code
    
    POST /api/users/request-login-code/
    Body: { "email": "user@example.com" }
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [AllowAny]
    
    def post(self, request):
        try:
            email = request.data.get('email', '').strip().lower()
            
            if not email:
                return Response(
                    {"error": "Email is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if user exists
            try:
                user = CustomUser.objects.get(email=email)
            except CustomUser.DoesNotExist:
                return Response(
                    {"error": "No account found with this email"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Check if user is active
            if user.status != 1:
                return Response(
                    {"error": "This account has been suspended. Please contact support."},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Check if user needs approval (for Formateurs and Organizations)
            if not user.can_access_platform:
                if user.approval_status == 'pending':
                    return Response(
                        {"error": "Your account is pending approval. Please wait for admin approval."},
                        status=status.HTTP_403_FORBIDDEN
                    )
                elif user.approval_status == 'rejected':
                    return Response(
                        {"error": "Your account registration was rejected. Please contact support."},
                        status=status.HTTP_403_FORBIDDEN
                    )
            
            # Invalidate any existing unused codes for this user
            VerificationCode.objects.filter(
                user=user,
                type='2fa',
                used_at__isnull=True
            ).delete()
            
            # Generate new verification code
            code = generate_verification_code()
            expires_at = timezone.now() + timedelta(minutes=10)
            
            # Save verification code
            VerificationCode.objects.create(
                user=user,
                code=code,
                type='2fa',
                expires_at=expires_at
            )
            
            # Send email
            email_sent = send_login_code_email(user, code)
            
            if not email_sent:
                return Response(
                    {"error": "Failed to send verification code. Please try again later."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            return Response(
                {
                    "message": "Verification code sent to your email",
                    "email": email,
                    "expires_in_minutes": 10,
                    "next_step": "verify_code"
                },
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            print(f"Error in RequestLoginCodeView: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"error": "An error occurred. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class VerifyLoginCodeView(APIView):
    """
    Step 2 of login: User provides code, system verifies and returns JWT tokens
    Returns role-specific data based on user privilege
    """
    authentication_classes = []
    permission_classes = [] 
    
    def get_apprenant_data(self, user):
        """Get data specific to Apprenant (Student)"""
        try:
            # Get enrolled courses
            enrollments = Enrollment.objects.filter(
                user=user,
                is_active=True
            ).select_related('course')
            
            enrolled_courses = []
            for enrollment in enrollments:
                course = enrollment.course
                enrolled_courses.append({
                    'id': course.id,
                    'title': course.title,
                    'description': course.description,
                    'progress': enrollment.progress,
                    'enrolled_at': enrollment.enrolled_at,
                    'instructor_name': course.instructor.get_full_name() if course.instructor else None
                })
            
            # Get available courses (not enrolled)
            enrolled_course_ids = [e.course.id for e in enrollments]
            available_courses = Course.objects.exclude(
                id__in=enrolled_course_ids
            ).filter(is_published=True)[:10]
            
            available_courses_data = [{
                'id': course.id,
                'title': course.title,
                'description': course.description,
                'instructor_name': course.instructor.get_full_name() if course.instructor else None,
                'student_count': course.enrollments.count()
            } for course in available_courses]
            
            return {
                'role': 'Apprenant',
                'dashboard_data': {
                    'enrolled_courses': enrolled_courses,
                    'enrolled_courses_count': len(enrolled_courses),
                    'available_courses': available_courses_data,
                    'completed_courses': enrollments.filter(progress=100).count(),
                    'in_progress_courses': enrollments.filter(progress__gt=0, progress__lt=100).count()
                }
            }
        except Exception as e:
            print(f"Error getting apprenant data: {str(e)}")
            return {
                'role': 'Apprenant',
                'dashboard_data': {}
            }
    
    def get_formateur_data(self, user):
        """Get data specific to Formateur (Instructor)"""
        try:
            # Get courses created by this formateur
            my_courses = Course.objects.filter(instructor=user)
            
            courses_data = []
            total_students = 0
            
            for course in my_courses:
                student_count = course.enrollments.filter(is_active=True).count()
                total_students += student_count
                
                courses_data.append({
                    'id': course.id,
                    'title': course.title,
                    'description': course.description,
                    'is_published': course.is_published,
                    'student_count': student_count,
                    'created_at': course.created_at,
                    'updated_at': course.updated_at,
                    'average_progress': course.enrollments.aggregate(
                        avg_progress=Avg('progress')
                    )['avg_progress'] or 0
                })
            
            return {
                'role': 'Formateur',
                'dashboard_data': {
                    'my_courses': courses_data,
                    'total_courses': my_courses.count(),
                    'total_students': total_students,
                    'published_courses': my_courses.filter(is_published=True).count(),
                    'draft_courses': my_courses.filter(is_published=False).count()
                }
            }
        except Exception as e:
            print(f"Error getting formateur data: {str(e)}")
            return {
                'role': 'Formateur',
                'dashboard_data': {}
            }
    
    def get_organisation_data(self, user):
        """Get data specific to Organisation"""
        try:
            # Get organization details
            organization = Organization.objects.filter(user=user).first()
            
            if not organization:
                return {
                    'role': 'Organisation',
                    'dashboard_data': {
                        'error': 'Organization profile not found'
                    }
                }
            
            # Get organization groups
            groups = Group.objects.filter(org=organization)
            
            groups_data = []
            total_members = 0
            
            for group in groups:
                member_count = group.members.count()
                total_members += member_count
                
                groups_data.append({
                    'id': group.id,
                    'name': group.name,
                    'description': group.description,
                    'member_count': member_count,
                    'created_at': group.created_at
                })
            
            return {
                'role': 'Organisation',
                'organization': {
                    'id': organization.id,
                    'name': organization.name,
                    'organization_type': organization.organization_type,
                    'contact_email': organization.contact_email,
                    'contact_phone': organization.contact_phone,
                    'address': organization.address,
                    'website': organization.website
                },
                'dashboard_data': {
                    'groups': groups_data,
                    'total_groups': groups.count(),
                    'total_members': total_members
                }
            }
        except Exception as e:
            print(f"Error getting organisation data: {str(e)}")
            return {
                'role': 'Organisation',
                'dashboard_data': {}
            }
    
    def get_admin_data(self, user):
        """Get data specific to Admin"""
        try:
            # Get platform statistics
            total_users = CustomUser.objects.count()
            total_courses = Course.objects.count()
            
            # Users by privilege
            users_by_privilege = CustomUser.objects.values('privilege').annotate(
                count=Count('id')
            )
            
            # Pending approvals
            pending_formateurs = CustomUser.objects.filter(
                privilege='F',
                approval_status='pending'
            ).count()
            
            pending_organisations = CustomUser.objects.filter(
                privilege='O',
                approval_status='pending'
            ).count()
            
            # Recent registrations
            recent_users = CustomUser.objects.order_by('-date_joined')[:10]
            recent_users_data = [{
                'id': u.id,
                'username': u.username,
                'email': u.email,
                'full_name': u.full_name,
                'privilege': u.privilege,
                'approval_status': u.approval_status,
                'date_joined': u.date_joined
            } for u in recent_users]
            
            return {
                'role': 'Admin',
                'dashboard_data': {
                    'total_users': total_users,
                    'total_courses': total_courses,
                    'users_by_privilege': {item['privilege']: item['count'] for item in users_by_privilege},
                    'pending_approvals': {
                        'formateurs': pending_formateurs,
                        'organisations': pending_organisations,
                        'total': pending_formateurs + pending_organisations
                    },
                    'recent_users': recent_users_data
                }
            }
        except Exception as e:
            print(f"Error getting admin data: {str(e)}")
            return {
                'role': 'Admin',
                'dashboard_data': {}
            }
    
    def post(self, request):
        try:
            email = request.data.get('email', '').strip().lower()
            code = request.data.get('code', '').strip()
            
            if not email or not code:
                return Response(
                    {"error": "Email and code are required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get user
            try:
                user = CustomUser.objects.get(email=email)
            except CustomUser.DoesNotExist:
                return Response(
                    {"error": "Invalid email or code"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get verification code
            try:
                verification = VerificationCode.objects.get(
                    user=user,
                    code=code,
                    type='2fa',
                    used_at__isnull=True
                )
            except VerificationCode.DoesNotExist:
                return Response(
                    {"error": "Invalid or expired verification code"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if code is expired
            if verification.is_expired:
                return Response(
                    {"error": "Verification code has expired. Please request a new one."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Mark code as used
            verification.mark_as_used()
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            refresh_token = str(refresh)
            
            # Update last login
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            
            # Get basic user data
            user_serializer = CustomUserSerializer(user)
            
            # Get role-specific data based on privilege
            role_data = {}
            if user.privilege == 'AP':
                role_data = self.get_apprenant_data(user)
            elif user.privilege == 'F':
                role_data = self.get_formateur_data(user)
            elif user.privilege == 'O':
                role_data = self.get_organisation_data(user)
            elif user.privilege == 'A':
                role_data = self.get_admin_data(user)
            
            # Create response with role-specific data
            response_data = {
                "message": "Login successful",
                "user": user_serializer.data,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "Bearer",
                **role_data  # Merge role-specific data
            }
            
            response = Response(response_data, status=status.HTTP_200_OK)
            
            # Set tokens in HTTP-only cookies
            response.set_cookie(
                key='access_token',
                value=access_token,
                httponly=True,
                secure=settings.USE_SSL,
                samesite='Lax',
                max_age=3600  # 1 hour
            )
            
            response.set_cookie(
                key='refresh_token',
                value=refresh_token,
                httponly=True,
                secure=settings.USE_SSL,
                samesite='Lax',
                max_age=86400 * 30
            )
            
            return response
            
        except Exception as e:
            print(f"Error in VerifyLoginCodeView: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"error": "An error occurred during login"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# Logout View
class LogoutView(APIView):
    def post(self, request):
        response = Response(
            {"message": "Logout successful"},
            status=status.HTTP_200_OK
        )
        
        # Clear cookies
        response.delete_cookie('access_token')
        response.delete_cookie('refresh_token')
        
        return response

# Resend Code View
@method_decorator(csrf_exempt, name='dispatch')
class ResendLoginCodeView(APIView):
    permission_classes = []
    authentication_classes = []
    
    def post(self, request):
        view = RequestLoginCodeView()
        return view.post(request)

# Admin Views
class ApprovedView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            user_id = request.data.get('id')
            approved = request.data.get('approved')
            rejection_reason = request.data.get('rejection_reason', '')
            
            if not user_id:
                return Response(
                    {"error": "user id is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if request.user.privilege != 'A':
                return Response(
                    {"error": "Only admins can approve users"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            try:
                user = CustomUser.objects.get(id=user_id)
            except CustomUser.DoesNotExist:
                return Response(
                    {"error": "User not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            if user.privilege not in ['F', 'O']:
                return Response(
                    {"error": "This user type does not require approval"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if approved in [True, 'approved', 'approve']:
                user.approval_status = 'approved'
                user.approved_by = request.user
                user.approved_at = timezone.now()
                user.rejection_reason = None
                message = "User approved successfully"
                
            elif approved in [False, 'rejected', 'reject']:
                user.approval_status = 'rejected'
                user.rejection_reason = rejection_reason or "No reason provided"
                user.approved_by = request.user
                user.approved_at = timezone.now()
                message = "User rejected"
            else:
                return Response(
                    {"error": "Invalid approval status. Use 'approved' or 'rejected'"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            user.save()
            
            serializer = CustomUserSerializer(user)
            return Response(
                {
                    "message": message,
                    "user": serializer.data
                },
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            print(f"Unexpected error in ApprovedView: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {
                    "error": "Internal server error",
                    "details": str(e) if request.user.is_staff else "An error occurred"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class UpdateUserView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        try:
            user_id = request.data.get('id')
            
            if not user_id:
                return Response(
                    {"error": "User ID is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                user = CustomUser.objects.get(id=user_id)
            except CustomUser.DoesNotExist:
                return Response(
                    {"error": "User not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            if request.user.id != user.id and request.user.privilege != 'A':
                return Response(
                    {"error": "Permission denied. You can only edit your own profile."},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            first_name = request.data.get('first_name')
            last_name = request.data.get('last_name')
            privilege = request.data.get('privilege')
            
            if first_name:
                user.first_name = first_name
            if last_name:
                user.last_name = last_name
            
            if privilege:
                if request.user.privilege != 'A':
                    return Response(
                        {"error": "Only admins can change user privileges"},
                        status=status.HTTP_403_FORBIDDEN
                    )
                
                valid_privileges = ['A', 'AP', 'F', 'O']
                if privilege not in valid_privileges:
                    return Response(
                        {"error": f"Invalid privilege. Must be one of: {', '.join(valid_privileges)}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                user.privilege = privilege
            
            serializer = CustomUserSerializer(user, data=request.data, partial=True)
            
            if serializer.is_valid():
                updated_user = serializer.save()
                return Response(
                    {
                        "message": "User updated successfully",
                        "user": CustomUserSerializer(updated_user).data
                    },
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {
                        "error": "Invalid data",
                        "details": serializer.errors
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

        except Exception as e:
            print(f"Error in UpdateUserView: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"error": "An error occurred. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class SearchUserView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            search_query = request.query_params.get('email', '').strip()
            
            if not search_query:
                return Response(
                    {"error": "Search query is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            users = CustomUser.objects.filter(
                email__icontains=search_query,
                approval_status='approved',
                status=1
            )[:10]
            
            results = []
            for user in users:
                results.append({
                    'id': user.id,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'full_name': user.full_name,
                    'privilege': user.privilege,
                    'privilege_display': user.get_privilege_display()
                })
            
            return Response(
                {
                    "count": len(results),
                    "results": results
                },
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            print(f"Error in SearchUserView: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"error": "An error occurred. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class DeleteRejectedUserView(APIView):
    permission_classes = [IsAuthenticated]
    
    def delete(self, request):
        try:
            if request.user.privilege != 'A':
                return Response(
                    {"error": "Only admins can delete users"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            user_id = request.data.get('id')
            
            if not user_id:
                return Response(
                    {"error": "User ID is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                user = CustomUser.objects.get(id=user_id)
            except CustomUser.DoesNotExist:
                return Response(
                    {"error": "User not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            if user.approval_status != 'rejected':
                return Response(
                    {"error": "Can only delete rejected users"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if user.privilege == 'A':
                return Response(
                    {"error": "Cannot delete admin users"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            user_email = user.email
            user.delete()
            
            return Response(
                {
                    "message": "User deleted successfully",
                    "deleted_user": user_email
                },
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            print(f"Error in DeleteRejectedUserView: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"error": "An error occurred. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class PendingApprovalsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            if request.user.privilege != 'A':
                return Response(
                    {"error": "Only admins can view pending approvals"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            user_type = request.query_params.get('type', None)
            
            queryset = CustomUser.objects.filter(approval_status='pending')
            
            if user_type in ['F', 'O']:
                queryset = queryset.filter(privilege=user_type)
            
            users = queryset.order_by('-approval_requested_at')
            
            serializer = CustomUserSerializer(users, many=True)
            
            return Response(
                {
                    "count": users.count(),
                    "pending_users": serializer.data
                },
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            print(f"Error in PendingApprovalsView: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"error": "An error occurred. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ToggleUserStatusView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            if request.user.privilege != 'A':
                return Response(
                    {"error": "Only admins can change user status"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            user_id = request.data.get('id')
            action = request.data.get('action')
            reason = request.data.get('reason', '')
            
            if not user_id or not action:
                return Response(
                    {"error": "User ID and action are required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                user = CustomUser.objects.get(id=user_id)
            except CustomUser.DoesNotExist:
                return Response(
                    {"error": "User not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            if user.privilege == 'A':
                return Response(
                    {"error": "Cannot modify admin users"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            if action == 'suspend':
                user.suspend_user(reason)
                message = "User suspended successfully"
            elif action == 'activate':
                user.activate_user()
                message = "User activated successfully"
            else:
                return Response(
                    {"error": "Invalid action. Use 'suspend' or 'activate'"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            serializer = CustomUserSerializer(user)
            return Response(
                {
                    "message": message,
                    "user": serializer.data
                },
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            print(f"Error in ToggleUserStatusView: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"error": "An error occurred. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class CreateAdminView(APIView):
    def post(self, request):
        try:
            first_name = request.data.get('first_name')
            last_name = request.data.get('last_name')
            email = request.data.get('email')
            if CustomUser.objects.filter(email=email).exists():
                return Response(
                    {"error": "Email already in use"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            user_data = {
                    'email': email,
                    'first_name': first_name,
                    'last_name': last_name,
                    'privilege': 'A',
                    'approval_status': 'approved'
                }
            serializer = CustomUserSerializer(data=user_data)
            if serializer.is_valid():
                user = serializer.save()
                return Response(
                    {
                        "message": "User registered successfully",
                        "user_id": user.id
                    },
                    status=status.HTTP_201_CREATED
                )
            else:
                print("Serializer errors:", serializer.errors)
                return Response(
                    {
                        "error": "Invalid data",
                        "details": serializer.errors
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception  as e:
            print(f"Unexpected error in CreateAdmin: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {
                    "error": "Internal server error",
                    "details": str(e) if request.user.is_staff else "An error occurred"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# ==================== ORGANIZATION VIEWS ====================

class OrganizationDashboardView(APIView):
    """
    Dashboard complet pour l'organisation
    GET /api/organization/dashboard/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            if request.user.privilege != 'O':
                return Response(
                    {'error': 'Accès réservé aux organisations'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            organization = Organization.objects.filter(user=request.user).first()
            if not organization:
                return Response(
                    {'error': 'Organisation non trouvée'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            organization.update_statistics()
            
            general_stats = self.get_general_stats(organization)
            graph_stats = self.get_graph_stats(organization)
            
            return Response({
                'organization': {
                    'id': organization.id,
                    'name': organization.name,
                    'description': organization.description,
                    'organization_type': organization.organization_type,
                    'created_at': organization.created_at
                },
                'general_stats': general_stats,
                'graph_stats': graph_stats
            })
            
        except Exception as e:
            logger.error(f"Error in OrganizationDashboardView: {str(e)}")
            return Response(
                {'error': 'Erreur lors de la récupération du dashboard'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def get_general_stats(self, organization):
        return {
            'nombre_groupes': organization.total_groups,
            'nombre_membres': organization.total_members,
            'nombre_formations': organization.total_formations,
            'taux_achevement': organization.get_completion_rate(),
            'membres_actifs': organization.get_active_members_count(),
            'membres_inactifs': organization.total_members - organization.get_active_members_count()
        }
    
    def get_graph_stats(self, organization):
        return {
            'membres_actifs_vs_inactifs_par_mois': self.get_monthly_member_stats(organization),
            'formations_en_cours_terminees_pourcentage': self.get_course_progress_stats(organization),
            'taux_achevement_par_groupe_pourcentage': self.get_group_completion_stats(organization),
            'quiz_score_ordre_max': self.get_top_quiz_scores(organization),
            'taux_apprentissage': self.get_learning_rate_stats(organization)
        }
    
    def get_monthly_member_stats(self, organization):
        try:
            six_months_ago = timezone.now() - timedelta(days=180)
            
            daily_stats = OrganizationDailyStats.objects.filter(
                organization=organization,
                date__gte=six_months_ago
            ).order_by('date')
            
            monthly_data = {}
            for stat in daily_stats:
                month_key = stat.date.strftime('%Y-%m')
                if month_key not in monthly_data:
                    monthly_data[month_key] = {
                        'active_members': 0,
                        'inactive_members': 0,
                        'days_count': 0
                    }
                
                monthly_data[month_key]['active_members'] += stat.active_members
                monthly_data[month_key]['inactive_members'] += stat.inactive_members
                monthly_data[month_key]['days_count'] += 1
            
            result = []
            for month, data in monthly_data.items():
                if data['days_count'] > 0:
                    result.append({
                        'month': month,
                        'active_members': round(data['active_members'] / data['days_count']),
                        'inactive_members': round(data['inactive_members'] / data['days_count'])
                    })
            
            result.sort(key=lambda x: x['month'])
            return result[-6:] if len(result) >= 6 else result
            
        except Exception as e:
            logger.error(f"Error in get_monthly_member_stats: {str(e)}")
            return []
    
    def get_course_progress_stats(self, organization):
        try:
            member_user_ids = Member.objects.filter(
                group__org=organization
            ).values_list('user_id', flat=True).distinct()
            
            subscriptions = Subscription.objects.filter(
                user_id__in=member_user_ids,
                is_active=True
            )
            
            total_courses = subscriptions.count()
            in_progress_courses = subscriptions.filter(
                progress_percentage__gt=0,
                progress_percentage__lt=100
            ).count()
            completed_courses = subscriptions.filter(is_completed=True).count()
            
            if total_courses > 0:
                in_progress_pct = (in_progress_courses / total_courses) * 100
                completed_pct = (completed_courses / total_courses) * 100
            else:
                in_progress_pct = completed_pct = 0
            
            return {
                'pourcentage_en_cours': round(in_progress_pct, 2),
                'pourcentage_terminees': round(completed_pct, 2),
                'total_formations': total_courses,
                'en_cours': in_progress_courses,
                'terminees': completed_courses
            }
            
        except Exception as e:
            logger.error(f"Error in get_course_progress_stats: {str(e)}")
            return {'pourcentage_en_cours': 0, 'pourcentage_terminees': 0}
    
    def get_group_completion_stats(self, organization):
        try:
            groups = Group.objects.filter(org=organization)
            
            group_stats = []
            for group in groups:
                members = group.members.all()
                total_members = members.count()
                
                if total_members == 0:
                    completion_rate = 0
                else:
                    completed_courses = 0
                    for member in members:
                        completed_courses += Subscription.objects.filter(
                            user=member.user,
                            is_completed=True
                        ).count()
                    
                    completion_rate = (completed_courses / (total_members * 5)) * 100
                    completion_rate = min(completion_rate, 100)
                
                group_stats.append({
                    'groupe_id': group.id,
                    'nom_groupe': group.name,
                    'taux_achevement': round(completion_rate, 2),
                    'nombre_membres': total_members
                })
            
            return group_stats
            
        except Exception as e:
            logger.error(f"Error in get_group_completion_stats: {str(e)}")
            return []
    
    def get_top_quiz_scores(self, organization):
        try:
            member_user_ids = Member.objects.filter(
                group__org=organization
            ).values_list('user_id', flat=True).distinct()
            
            user_scores = []
            for user_id in member_user_ids[:50]:
                avg_score = QCMCompletion.objects.filter(
                    subscription__user_id=user_id
                ).aggregate(avg_score=Avg('best_score'))['avg_score'] or 0
                
                if avg_score > 0:
                    user = CustomUser.objects.get(id=user_id)
                    user_scores.append({
                        'utilisateur_id': user_id,
                        'nom_complet': user.full_name(),
                        'email': user.email,
                        'score_moyen': round(avg_score, 2)
                    })
            
            user_scores.sort(key=lambda x: x['score_moyen'], reverse=True)
            return user_scores[:10]
            
        except Exception as e:
            logger.error(f"Error in get_top_quiz_scores: {str(e)}")
            return []
    
    def get_learning_rate_stats(self, organization):
        try:
            member_user_ids = Member.objects.filter(
                group__org=organization
            ).values_list('user_id', flat=True).distinct()
            
            total_consecutive_days = 0
            member_count = 0
            
            for user_id in member_user_ids[:50]:
                consecutive_days = self.calculate_consecutive_days(user_id)
                if consecutive_days > 0:
                    total_consecutive_days += consecutive_days
                    member_count += 1
            
            avg_consecutive_days = total_consecutive_days / member_count if member_count > 0 else 0
            
            return {
                'jours_consecutifs_moyens': round(avg_consecutive_days, 2),
                'membres_analyses': member_count
            }
            
        except Exception as e:
            logger.error(f"Error in get_learning_rate_stats: {str(e)}")
            return {'jours_consecutifs_moyens': 0, 'membres_analyses': 0}
    
    def calculate_consecutive_days(self, user_id):
        try:
            thirty_days_ago = timezone.now() - timedelta(days=30)
            
            active_days = TimeTracking.objects.filter(
                user_id=user_id,
                start_time__gte=thirty_days_ago
            ).dates('start_time', 'day').distinct()
            
            if not active_days:
                return 0
            
            active_dates = [day.date() for day in active_days]
            active_dates.sort()
            
            max_consecutive = 1
            current_consecutive = 1
            
            for i in range(1, len(active_dates)):
                if (active_dates[i] - active_dates[i-1]).days == 1:
                    current_consecutive += 1
                    max_consecutive = max(max_consecutive, current_consecutive)
                else:
                    current_consecutive = 1
            
            return max_consecutive
            
        except Exception as e:
            logger.error(f"Error in calculate_consecutive_days: {str(e)}")
            return 0

class OrganizationGroupsView(APIView):
    """
    Gestion des groupes de l'organisation
    GET /api/organization/groups/ - Liste des groupes
    POST /api/organization/groups/ - Créer un groupe
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            if request.user.privilege != 'O':
                return Response(
                    {'error': 'Accès réservé aux organisations'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            organization = Organization.objects.filter(user=request.user).first()
            if not organization:
                return Response(
                    {'error': 'Organisation non trouvée'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            status_filter = request.query_params.get('status')
            groups = Group.objects.filter(org=organization)
            
            if status_filter:
                groups = groups.filter(status=status_filter)
            
            serializer = GroupSerializer(groups, many=True)
            
            return Response({
                'groupes': serializer.data,
                'total_groupes': groups.count(),
                'filtre_statut': status_filter
            })
            
        except Exception as e:
            logger.error(f"Error in OrganizationGroupsView GET: {str(e)}")
            return Response(
                {'error': 'Erreur lors de la récupération des groupes'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def post(self, request):
        try:
            if request.user.privilege != 'O':
                return Response(
                    {'error': 'Accès réservé aux organisations'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            organization = Organization.objects.filter(user=request.user).first()
            if not organization:
                return Response(
                    {'error': 'Organisation non trouvée'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            serializer = CreateGroupSerializer(
                data=request.data,
                context={'organization': organization}
            )
            
            if serializer.is_valid():
                groupe = serializer.save(org=organization)
                organization.update_statistics()
                
                return Response(
                    GroupSerializer(groupe).data,
                    status=status.HTTP_201_CREATED
                )
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Error in OrganizationGroupsView POST: {str(e)}")
            return Response(
                {'error': 'Erreur lors de la création du groupe'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class OrganizationGroupDetailView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get_group(self, organization, group_id):
        try:
            return Group.objects.get(id=group_id, org=organization)
        except Group.DoesNotExist:
            raise Http404
    
    def get(self, request, group_id):
        try:
            if request.user.privilege != 'O':
                return Response(
                    {'error': 'Accès réservé aux organisations'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            organization = Organization.objects.filter(user=request.user).first()
            if not organization:
                return Response(
                    {'error': 'Organisation non trouvée'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            groupe = self.get_group(organization, group_id)
            serializer = GroupSerializer(groupe)
            
            membres = Member.objects.filter(group=groupe)
            membres_serializer = MemberSerializer(membres, many=True)
            
            return Response({
                'groupe': serializer.data,
                'membres': membres_serializer.data,
                'nombre_membres': membres.count()
            })
            
        except Http404:
            return Response(
                {'error': 'Groupe non trouvé'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error in OrganizationGroupDetailView GET: {str(e)}")
            return Response(
                {'error': 'Erreur lors de la récupération du groupe'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def put(self, request, group_id):
        try:
            if request.user.privilege != 'O':
                return Response(
                    {'error': 'Accès réservé aux organisations'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            organization = Organization.objects.filter(user=request.user).first()
            if not organization:
                return Response(
                    {'error': 'Organisation non trouvée'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            groupe = self.get_group(organization, group_id)
            serializer = CreateGroupSerializer(
                groupe,
                data=request.data,
                partial=True,
                context={'organization': organization}
            )
            
            if serializer.is_valid():
                serializer.save()
                return Response(GroupSerializer(groupe).data)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        except Http404:
            return Response(
                {'error': 'Groupe non trouvé'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error in OrganizationGroupDetailView PUT: {str(e)}")
            return Response(
                {'error': 'Erreur lors de la modification du groupe'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def delete(self, request, group_id):
        try:
            if request.user.privilege != 'O':
                return Response(
                    {'error': 'Accès réservé aux organisations'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            organization = Organization.objects.filter(user=request.user).first()
            if not organization:
                return Response(
                    {'error': 'Organisation non trouvé'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            groupe = self.get_group(organization, group_id)
            
            if groupe.members.count() > 0:
                return Response(
                    {'error': 'Impossible de supprimer un groupe contenant des membres'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            groupe.delete()
            organization.update_statistics()
            
            return Response(
                {'message': 'Groupe supprimé avec succès'},
                status=status.HTTP_200_OK
            )
            
        except Http404:
            return Response(
                {'error': 'Groupe non trouvé'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error in OrganizationGroupDetailView DELETE: {str(e)}")
            return Response(
                {'error': 'Erreur lors de la suppression du groupe'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def patch(self, request, group_id):
        try:
            if request.user.privilege != 'O':
                return Response(
                    {'error': 'Accès réservé aux organisations'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            organization = Organization.objects.filter(user=request.user).first()
            if not organization:
                return Response(
                    {'error': 'Organisation non trouvé'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            groupe = self.get_group(organization, group_id)
            
            action = request.data.get('action')
            if action == 'activate':
                groupe.status = 'active'
                message = 'Groupe activé'
            elif action == 'deactivate':
                groupe.status = 'inactive'
                message = 'Groupe désactivé'
            elif action == 'archive':
                groupe.status = 'archived'
                message = 'Groupe archivé'
            else:
                return Response(
                    {'error': 'Action invalide. Utilisez "activate", "deactivate" ou "archive".'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            groupe.save()
            
            return Response({
                'message': message,
                'groupe': GroupSerializer(groupe).data
            })
            
        except Http404:
            return Response(
                {'error': 'Groupe non trouvé'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error in OrganizationGroupDetailView PATCH: {str(e)}")
            return Response(
                {'error': 'Erreur lors du changement de statut'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class OrganizationMembersView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            if request.user.privilege != 'O':
                return Response(
                    {'error': 'Accès réservé aux organisations'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            organization = Organization.objects.filter(user=request.user).first()
            if not organization:
                return Response(
                    {'error': 'Organisation non trouvée'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            status_filter = request.query_params.get('status')
            groupe_filter = request.query_params.get('groupe_id')
            
            membres_query = Member.objects.filter(group__org=organization)
            
            if status_filter:
                membres_query = membres_query.filter(status=status_filter)
            
            if groupe_filter:
                membres_query = membres_query.filter(group_id=groupe_filter)
            
            user_ids = membres_query.values_list('user_id', flat=True).distinct()
            membres = []
            
            for user_id in user_ids:
                member_record = Member.objects.filter(
                    user_id=user_id,
                    group__org=organization
                ).first()
                
                if member_record:
                    membres.append(member_record)
            
            serializer = MemberSerializer(membres, many=True)
            
            membres_actifs = []
            for membre in membres[:10]:
                if membre.is_active():
                    membres_actifs.append(membre)
            
            membres_actifs_serializer = MemberSerializer(membres_actifs, many=True)
            
            return Response({
                'membres': serializer.data,
                'total_membres': len(membres),
                'membres_actifs': membres_actifs_serializer.data,
                'filtres': {
                    'statut': status_filter,
                    'groupe_id': groupe_filter
                }
            })
            
        except Exception as e:
            logger.error(f"Error in OrganizationMembersView: {str(e)}")
            return Response(
                {'error': 'Erreur lors de la récupération des membres'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class AddMemberByEmailView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            if request.user.privilege != 'O':
                return Response(
                    {'error': 'Accès réservé aux organisations'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            organization = Organization.objects.filter(user=request.user).first()
            if not organization:
                return Response(
                    {'error': 'Organisation non trouvée'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            serializer = AddMemberSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            email = serializer.validated_data['email']
            role = serializer.validated_data['role']
            
            try:
                user = CustomUser.objects.get(email=email)
            except CustomUser.DoesNotExist:
                return Response(
                    {'error': f'Aucun utilisateur trouvé avec l\'email {email}'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            groupe = Group.objects.filter(org=organization).first()
            if not groupe:
                return Response(
                    {'error': 'Votre organisation n\'a pas encore de groupe. Créez d\'abord un groupe.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if Member.objects.filter(user=user, group=groupe).exists():
                return Response(
                    {'error': 'Cet utilisateur est déjà membre de ce groupe'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            membre = Member.objects.create(
                user=user,
                group=groupe,
                role=role,
                status='active',
                last_active_at=timezone.now()
            )
            
            organization.update_statistics()
            self.send_welcome_email(membre, organization)
            
            return Response(
                MemberSerializer(membre).data,
                status=status.HTTP_201_CREATED
            )
            
        except Exception as e:
            logger.error(f"Error in AddMemberByEmailView: {str(e)}")
            return Response(
                {'error': 'Erreur lors de l\'ajout du membre'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def send_welcome_email(self, member, organization):
        try:
            subject = f'Bienvenue dans l\'organisation {organization.name}'
            message = f"""
Bonjour {member.user.first_name} {member.user.last_name},

Vous avez été ajouté à l'organisation "{organization.name}" dans le groupe "{member.group.name}" en tant que {member.get_role_display()}.

Vous pouvez maintenant accéder aux formations assignées à votre groupe.

Cordialement,
L'équipe de {organization.name}
"""
            
            from_email = settings.EMAIL_HOST_USER
            recipient_list = [member.user.email]
            
            send_mail(subject, message, from_email, recipient_list, fail_silently=True)
            
        except Exception as e:
            logger.error(f"Error sending welcome email: {str(e)}")

class OrganizationMemberDetailView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get_member(self, organization, member_id):
        try:
            return Member.objects.get(id=member_id, group__org=organization)
        except Member.DoesNotExist:
            raise Http404
    
    def get(self, request, member_id):
        try:
            if request.user.privilege != 'O':
                return Response(
                    {'error': 'Accès réservé aux organisations'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            organization = Organization.objects.filter(user=request.user).first()
            if not organization:
                return Response(
                    {'error': 'Organisation non trouvée'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            membre = self.get_member(organization, member_id)
            serializer = MemberSerializer(membre)
            
            stats = {
                'cours_inscrits': Subscription.objects.filter(user=membre.user).count(),
                'cours_termines': Subscription.objects.filter(user=membre.user, is_completed=True).count(),
                'temps_total_apprentissage': TimeTracking.objects.filter(
                    user=membre.user
                ).aggregate(total=Sum('duration'))['total'] or 0,
                'score_moyen_quiz': QCMCompletion.objects.filter(
                    subscription__user=membre.user
                ).aggregate(avg=Avg('best_score'))['avg'] or 0
            }
            
            return Response({
                'membre': serializer.data,
                'statistiques': stats
            })
            
        except Http404:
            return Response(
                {'error': 'Membre non trouvé'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error in OrganizationMemberDetailView GET: {str(e)}")
            return Response(
                {'error': 'Erreur lors de la récupération du membre'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def put(self, request, member_id):
        try:
            if request.user.privilege != 'O':
                return Response(
                    {'error': 'Accès réservé aux organisations'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            organization = Organization.objects.filter(user=request.user).first()
            if not organization:
                return Response(
                    {'error': 'Organisation non trouvée'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            membre = self.get_member(organization, member_id)
            
            nouveau_groupe_id = request.data.get('groupe_id')
            if nouveau_groupe_id:
                try:
                    nouveau_groupe = Group.objects.get(id=nouveau_groupe_id, org=organization)
                    
                    if Member.objects.filter(user=membre.user, group=nouveau_groupe).exists():
                        return Response(
                            {'error': 'Cet utilisateur est déjà membre de ce groupe'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    
                    membre.group = nouveau_groupe
                    membre.save()
                    
                except Group.DoesNotExist:
                    return Response(
                        {'error': 'Groupe non trouvé'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            
            serializer = UpdateMemberSerializer(membre, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(MemberSerializer(membre).data)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        except Http404:
            return Response(
                {'error': 'Membre non trouvé'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error in OrganizationMemberDetailView PUT: {str(e)}")
            return Response(
                {'error': 'Erreur lors de la modification du membre'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def delete(self, request, member_id):
        try:
            if request.user.privilege != 'O':
                return Response(
                    {'error': 'Accès réservé aux organisations'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            organization = Organization.objects.filter(user=request.user).first()
            if not organization:
                return Response(
                    {'error': 'Organisation non trouvée'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            membre = self.get_member(organization, member_id)
            membre.delete()
            
            organization.update_statistics()
            
            return Response(
                {'message': 'Membre retiré avec succès'},
                status=status.HTTP_200_OK
            )
            
        except Http404:
            return Response(
                {'error': 'Membre non trouvé'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error in OrganizationMemberDetailView DELETE: {str(e)}")
            return Response(
                {'error': 'Erreur lors du retrait du membre'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def patch(self, request, member_id):
        try:
            if request.user.privilege != 'O':
                return Response(
                    {'error': 'Accès réservé aux organisations'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            organization = Organization.objects.filter(user=request.user).first()
            if not organization:
                return Response(
                    {'error': 'Organisation non trouvée'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            membre = self.get_member(organization, member_id)
            
            action = request.data.get('action')
            if action == 'activate':
                membre.status = 'active'
                membre.last_active_at = timezone.now()
                message = 'Membre activé'
            elif action == 'suspend':
                membre.status = 'suspended'
                message = 'Membre suspendu'
            elif action == 'make_admin':
                membre.role = 'admin'
                message = 'Membre promu administrateur'
            elif action == 'make_moderator':
                membre.role = 'moderator'
                message = 'Membre promu modérateur'
            elif action == 'make_member':
                membre.role = 'member'
                message = 'Membre rétrogradé membre'
            else:
                return Response(
                    {'error': 'Action invalide'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            membre.save()
            
            return Response({
                'message': message,
                'membre': MemberSerializer(membre).data
            })
            
        except Http404:
            return Response(
                {'error': 'Membre non trouvé'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error in OrganizationMemberDetailView PATCH: {str(e)}")
            return Response(
                {'error': 'Erreur lors du changement de statut'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class OrganizationFormationsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            if request.user.privilege != 'O':
                return Response(
                    {'error': 'Accès réservé aux organisations'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            organization = Organization.objects.filter(user=request.user).first()
            if not organization:
                return Response(
                    {'error': 'Organisation non trouvée'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            groupe_filter = request.query_params.get('groupe_id')
            
            formations = Course.objects.all()[:50]
            
            formations_data = []
            for formation in formations:
                membres_org = Member.objects.filter(group__org=organization)
                user_ids = membres_org.values_list('user_id', flat=True).distinct()
                
                subscriptions = Subscription.objects.filter(
                    course=formation,
                    user_id__in=user_ids,
                    is_active=True
                )
                
                total_inscrits = subscriptions.count()
                termines = subscriptions.filter(is_completed=True).count()
                
                taux_achevement = (termines / total_inscrits * 100) if total_inscrits > 0 else 0
                
                score_moyen = subscriptions.aggregate(avg=Avg('total_score'))['avg'] or 0
                
                formations_data.append({
                    'id': formation.id,
                    'titre': formation.title_of_course,
                    'createur': formation.creator.username,
                    'date_creation': formation.created_at,
                    'nombre_inscrits': total_inscrits,
                    'nombre_termines': termines,
                    'taux_achevement': round(taux_achevement, 2),
                    'score_moyen': round(score_moyen, 2)
                })
            
            return Response({
                'formations': formations_data,
                'total_formations': len(formations_data),
                'filtre': {'groupe_id': groupe_filter}
            })
            
        except Exception as e:
            logger.error(f"Error in OrganizationFormationsView: {str(e)}")
            return Response(
                {'error': 'Erreur lors de la récupération des formations'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )