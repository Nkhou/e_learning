# cours/views.py
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
import logging
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
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db.models import Count, Avg, Q, F, Sum, Max, OuterRef
from django.db.models.functions import TruncMonth, TruncWeek, TruncDate
from datetime import timedelta, datetime
from django.contrib.auth import get_user_model
from rest_framework import viewsets
from rest_framework.decorators import action
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import models
import csv
from io import TextIOWrapper
from django.contrib.sessions.models import Session

from .models import (
    Course, Module, CourseContent, Subscription, QCM, 
    QCMCompletion, QCMAttempt, QCMOption, VideoContent, PDFContent, ContentType, 
    TimeTracking, UserThemeStats, CourseTag, DetailedTimeTracking, 
    Notification, Tag, FavoriteCourse, Enrollment, QCMCompletion
)
from .serializers import (
    CourseSerializer, CourseCreateSerializer, CourseDetailSerializer,
    ModuleSerializer, ModuleCreateSerializer, CourseContentSerializer, CourseContentCreateSerializer,
    SubscriptionSerializer, QCMAttemptSerializer, 
    QCMCompletionSerializer, PDFContentSerializer, VideoContentSerializer, QCMSerializer,
    QCMOptionCreateSerializer, QCMContentCreateSerializer, PDFContentCreateSerializer,
    VideoContentCreateSerializer, ModuleWithContentsSerializer, FavoriteCourseSerializer, 
    FavoriteCourseCreateSerializer, NotificationSerializer, 
    TagSerializer
)

from users.serializers import UserThemeStatsSerializer
# Import des modèles users si nécessaire
from users.models import CustomUser

logger = logging.getLogger(__name__)
User = get_user_model()

# Utility functions
def is_secure_request(request):
    """Check if the request is secure (HTTPS)"""
    return (
        request.is_secure() or
        request.META.get('HTTP_X_FORWARDED_PROTO') == 'https' or
        settings.USE_SSL or
        settings.PRODUCTION
    )

def generate_random_password():
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(12))

# ==================== AUTHENTICATION VIEWS ====================

class LoginView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        try:
            if request.content_type == 'application/json':
                try:
                    data = json.loads(request.body)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parse error: {e}")
                    return Response(
                        {"error": f"Invalid JSON format: {str(e)}"}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                data = request.data
            
            email = data.get('email')
            password = data.get('password')
            
            if not email or not password:
                return Response(
                    {"error": "Email and password are required."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                user_obj = User.objects.get(email=email)
            except User.DoesNotExist:
                return Response(
                    {"error": "Invalid credentials."}, 
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            user = authenticate(request, username=user_obj.username, password=password)
            if user is None:
                return Response(
                    {"error": "Invalid credentials."}, 
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            if user.status == 2:
                return Response(
                    {"error": "Votre compte est suspendu. Contactez l'administrateur."}, 
                    status=status.HTTP_403_FORBIDDEN
                )

            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            
            response = Response({
                'refresh': str(refresh),
                'access': access_token,
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'username': user.username,
                    'privilege': user.privilege
                }
            }, status=status.HTTP_200_OK)
            
            response.set_cookie(
                key='accessToken',
                value=access_token,
                httponly=True,
                secure=False,
                samesite='Lax',
                max_age=60 * 60 * 24
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return Response(
                {"error": "An internal server error occurred."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class LogoutView(APIView):
    def post(self, request):
        response = Response({"message": "Logged out"}, status=200)
        response.delete_cookie('accessToken')
        return response

# ==================== MARK AS COMPLETED VIEWS ====================

class MarkContentCompletedView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, content_id):
        try:
            content = get_object_or_404(CourseContent, id=content_id)
            user = request.user
            
            if user.privilege != 'AP':
                return Response(
                    {'error': 'Seuls les apprenants peuvent marquer des contenus comme complétés'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            course = content.module.course
            subscription = Subscription.objects.filter(
                user=user,
                course=course,
                is_active=True
            ).first()
            
            if not subscription:
                return Response(
                    {'error': 'Vous devez être inscrit à ce cours pour marquer des contenus comme complétés'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if content.status != 1:
                return Response(
                    {'error': 'Ce contenu n\'est pas disponible'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if content.module.status != 1:
                return Response(
                    {'error': 'Ce module n\'est pas disponible'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not subscription.completed_contents.filter(id=content.id).exists():
                subscription.completed_contents.add(content)
                
                content.completed_count = F('completed_count') + 1
                content.save()
                content.refresh_from_db()
                
                subscription.calculate_progress_percentage()
                subscription.update_completion_status()
                
                user.update_strength_levels()
                
                return Response({
                    'success': True,
                    'message': f'Contenu "{content.title}" marqué comme complété',
                    'content': {
                        'id': content.id,
                        'title': content.title,
                        'completed': True
                    },
                    'subscription': {
                        'progress_percentage': subscription.progress_percentage,
                        'completed_contents_count': subscription.completed_contents.count(),
                        'is_completed': subscription.is_completed
                    }
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'message': 'Contenu déjà complété',
                    'content': {
                        'id': content.id,
                        'title': content.title,
                        'completed': True
                    },
                    'subscription': {
                        'progress_percentage': subscription.progress_percentage,
                        'completed_contents_count': subscription.completed_contents.count()
                    }
                }, status=status.HTTP_200_OK)
                
        except CourseContent.DoesNotExist:
            return Response(
                {'error': 'Contenu non trouvé'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error marking content as completed: {str(e)}")
            return Response(
                {'error': f'Erreur: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class MarkVideoCompletedView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, course_id):
        try:
            course = get_object_or_404(Course, id=course_id)
            user = request.user
            content_id = request.data.get('content_id')
            
            if not content_id:
                return Response(
                    {'error': 'content_id est requis'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if user.privilege != 'AP':
                return Response(
                    {'error': 'Seuls les apprenants peuvent marquer des vidéos comme complétées'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            content = get_object_or_404(
                CourseContent, 
                id=content_id, 
                module__course=course
            )
            
            if content.content_type.name != 'video':
                return Response(
                    {'error': 'Ce contenu n\'est pas une vidéo'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            mark_view = MarkContentCompletedView()
            mark_view.request = request
            return mark_view.post(request, content_id)
            
        except Exception as e:
            logger.error(f"Error marking video as completed: {str(e)}")
            return Response(
                {'error': f'Erreur: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class MarkPDFCompletedView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, course_id):
        try:
            course = get_object_or_404(Course, id=course_id)
            user = request.user
            content_id = request.data.get('content_id')
            
            if not content_id:
                return Response(
                    {'error': 'content_id est requis'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if user.privilege != 'AP':
                return Response(
                    {'error': 'Seuls les apprenants peuvent marquer des PDFs comme complétés'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            content = get_object_or_404(
                CourseContent, 
                id=content_id, 
                module__course=course
            )
            
            if content.content_type.name != 'pdf':
                return Response(
                    {'error': 'Ce contenu n\'est pas un PDF'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            mark_view = MarkContentCompletedView()
            mark_view.request = request
            return mark_view.post(request, content_id)
            
        except Exception as e:
            logger.error(f"Error marking PDF as completed: {str(e)}")
            return Response(
                {'error': f'Erreur: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class CheckContentCompletionView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, content_id):
        try:
            content = get_object_or_404(CourseContent, id=content_id)
            user = request.user
            
            course = content.module.course
            subscription = Subscription.objects.filter(
                user=user,
                course=course,
                is_active=True
            ).first()
            
            is_completed = False
            if subscription:
                is_completed = subscription.completed_contents.filter(id=content.id).exists()
            
            return Response({
                'content_id': content.id,
                'title': content.title,
                'is_completed': is_completed,
                'course_id': course.id,
                'course_title': course.title_of_course
            }, status=status.HTTP_200_OK)
            
        except CourseContent.DoesNotExist:
            return Response(
                {'error': 'Contenu non trouvé'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error checking content completion: {str(e)}")
            return Response(
                {'error': f'Erreur: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class GetCompletedContentsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, course_id):
        try:
            course = get_object_or_404(Course, id=course_id)
            user = request.user
            
            subscription = Subscription.objects.filter(
                user=user,
                course=course,
                is_active=True
            ).first()
            
            if not subscription:
                return Response({
                    'completed_contents': [],
                    'count': 0,
                    'message': 'Non inscrit à ce cours'
                }, status=status.HTTP_200_OK)
            
            completed_contents = subscription.completed_contents.filter(
                module__course=course
            ).select_related('content_type', 'module').order_by('module__order', 'order')
            
            completed_data = []
            for content in completed_contents:
                completed_data.append({
                    'id': content.id,
                    'title': content.title,
                    'content_type': content.content_type.name,
                    'module_id': content.module.id,
                    'module_title': content.module.title,
                    'completed_at': timezone.now()
                })
            
            return Response({
                'course_id': course.id,
                'course_title': course.title_of_course,
                'completed_contents': completed_data,
                'count': len(completed_data),
                'total_contents': CourseContent.objects.filter(
                    module__course=course,
                    module__status=1,
                    status=1
                ).count(),
                'progress_percentage': subscription.progress_percentage
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting completed contents: {str(e)}")
            return Response(
                {'error': f'Erreur: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# ==================== CHECK AUTHENTICATION VIEW ====================

class CheckAuthentificationView(APIView):
    def get(self, request):
        try:
            token = request.COOKIES.get('accessToken')
            
            if not token:
                auth_header = request.headers.get('Authorization')
                if auth_header and auth_header.startswith('Bearer '):
                    token = auth_header.split(' ')[1]
            
            if not token:
                return Response({
                    'authenticated': False, 
                    'message': 'No token'
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            UserById_ = CustomUser.objects.filter(id=payload.get('user_id')).first()

            if UserById_ and UserById_.status == 2:
                return Response({
                    'authenticated': False,
                    'message': 'Votre compte est suspendu'
                }, status=status.HTTP_403_FORBIDDEN)
            
            user = {
                "user_id": payload.get('user_id'),
                "username": UserById_.username,
                "firstname": UserById_.first_name,
                "lastName": UserById_.last_name,
                "email": UserById_.email,
                "privilege": UserById_.privilege,
                "status": UserById_.status,
                "status_display": "Actif" if UserById_.status == 1 else "Suspendu",
                "approval_status": UserById_.approval_status,
                "needs_approval": UserById_.needs_approval,
                "can_access_platform": UserById_.can_access_platform
            }
            
            return Response({
                'authenticated': True, 
                'user': user
            }, status=status.HTTP_200_OK)

        except jwt.ExpiredSignatureError:
            request.delete_cookie('accessToken')
            return Response({
                'authenticated': False, 
                'message': 'Token expired'
            }, status=status.HTTP_401_UNAUTHORIZED)
        except jwt.InvalidTokenError:
            return Response({
                'authenticated': False, 
                'message': 'Invalid token'
            }, status=status.HTTP_401_UNAUTHORIZED)

# ==================== COURSE VIEWS ====================

class CourseList(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        
        base_query = Q(status=1)
        
        if user.is_authenticated:
            if user.privilege in ['F', 'A']:
                base_query = Q(status__in=[0, 1])
        
        courses = Course.objects.filter(base_query)\
            .select_related('creator')\
            .prefetch_related('modules')\
            .annotate(
                subscribers_count=Count(
                    'course_subscriptions', 
                    filter=Q(course_subscriptions__is_active=True),
                    distinct=True
                )
            )
        
        serializer = CourseSerializer(courses, many=True, context={'request': request})
        return Response(serializer.data)
    
    def post(self, request):
        print(f"User creating course: {request.user} (ID: {request.user.id})")
        print(f"Request data keys: {request.data.keys()}")
        print(f"Files: {request.FILES}")
        
        data = request.data.copy()
        
        if 'image' in request.FILES:
            data['image'] = request.FILES['image']
        
        if 'status' not in data:
            data['status'] = 0
        
        print(f"Final data being sent to serializer: {data}")
        
        serializer = CourseCreateSerializer(
            data=data, 
            context={'request': request}
        )
        
        if serializer.is_valid():
            print("Serializer is valid")
            try:
                course = serializer.save()
                print(f"Course created successfully: {course.title_of_course} (ID: {course.id})")
                print(f"Course creator: {course.creator} (ID: {course.creator.id})")
                
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            except Exception as e:
                print(f"Error in serializer.save(): {str(e)}")
                import traceback
                traceback.print_exc()
                return Response(
                    {'error': f'Failed to save course: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        else:
            print(f"Serializer errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CourseDetail(APIView):
    permission_classes = [AllowAny]
    
    def get_object(self, pk):
        return get_object_or_404(Course, pk=pk)
    
    def get(self, request, pk):
        try:
            course = self.get_object(pk)
            
            user = request.user
            if course.status == 0 and not (user.is_authenticated and 
                                            (user.privilege in ['F', 'A'] or user == course.creator)):
                return Response(
                    {'error': 'Ce cours est en brouillon et non accessible'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            serializer = CourseDetailSerializer(course, context={'request': request})
            return Response(serializer.data)
            
        except Exception as e:
            print(f"Error in CourseDetail view: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {'error': f'Internal server error: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class MyCourses(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response([], status=status.HTTP_200_OK)
        
        courses = Course.objects.filter(creator=request.user)
        serializer = CourseSerializer(courses, many=True, context={'request': request})
        return Response(serializer.data)

# ==================== SUBSCRIPTION VIEWS ====================

class SubscribeToCourse(APIView):
    def post(self, request, pk):
        course = get_object_or_404(Course, pk=pk)
        user = request.user
        
        subscription, created = Subscription.objects.get_or_create(
            user=user,
            course=course,
            defaults={'is_active': True}
        )
        
        if not created:
            subscription.is_active = True
            subscription.save()
        
        return Response(
            {'message': 'Subscribed successfully', 'subscription_id': subscription.id},
            status=status.HTTP_201_CREATED
        )

class UnsubscribeFromCourse(APIView):
    def post(self, request, pk):
        course = get_object_or_404(Course, pk=pk)
        user = request.user
        
        try:
            subscription = Subscription.objects.get(user=user, course=course)
            subscription.is_active = False
            subscription.save()
            
            return Response({'message': 'Unsubscribed successfully'})
        except Subscription.DoesNotExist:
            return Response(
                {'error': 'You are not subscribed to this course'},
                status=status.HTTP_400_BAD_REQUEST
            )

class CheckSubscription(APIView):
    def get(self, request, pk):
        try:
            course = get_object_or_404(Course, pk=pk)
            user = request.user
            
            if not user.is_authenticated:
                return Response({
                    'error': 'Authentication required'
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            subscription = Subscription.objects.filter(
                user=user, 
                course=course,
                is_active=True
            ).first()
            
            is_subscribed = subscription is not None
            
            progress_data = self.calculate_progress_active_only(course, subscription)
            
            response_data = {
                'id': course.id,
                'title': course.title_of_course,
                'description': course.description,
                'image': course.image.url if course.image and hasattr(course.image, 'url') else None,
                'creator_username': course.creator.username if course.creator else 'Unknown',
                'creator_first_name': course.creator.first_name if course.creator else '',
                'creator_last_name': course.creator.last_name if course.creator else '',
                'created_at': course.created_at.isoformat() if course.created_at else None,
                'updated_at': course.updated_at.isoformat() if course.updated_at else None,
                'is_subscribed': is_subscribed,
                'progress_percentage': progress_data['progress_percentage'],
                'total_time_spent': progress_data['total_time_spent'],
                'estimated_duration': course.estimated_duration or 0,
                'min_required_time': course.min_required_time or 0,
                'active_content_stats': progress_data['content_stats']
            }
            
            if is_subscribed and subscription:
                response_data['subscription_id'] = subscription.id
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Course.DoesNotExist:
            return Response({
                'error': 'Course not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'error': f'An error occurred: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def calculate_progress_active_only(self, course, subscription):
        active_modules = Module.objects.filter(course=course, status=1)
        
        total_active_contents = 0
        completed_active_contents = 0
        
        for module in active_modules:
            module_active_contents = CourseContent.objects.filter(
                module=module, 
                status=1
            )
            total_active_contents += module_active_contents.count()
            
            if subscription:
                completed_active_contents += subscription.completed_contents.filter(
                    id__in=module_active_contents.values_list('id', flat=True)
                ).count()
        
        if total_active_contents > 0:
            progress_percentage = round((completed_active_contents / total_active_contents) * 100, 2)
        else:
            progress_percentage = 0
        
        total_time_spent = subscription.total_time_spent if subscription else 0
        
        return {
            'progress_percentage': progress_percentage,
            'total_time_spent': total_time_spent,
            'content_stats': {
                'total_active_contents': total_active_contents,
                'completed_active_contents': completed_active_contents,
                'total_active_modules': active_modules.count()
            }
        }

class MySubscriptions(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            print("Starting MySubscriptions API call...")
            
            subscriptions = Subscription.objects.filter(
                user=request.user, 
                is_active=True
            ).select_related('course', 'course__creator')
            
            print(f"Found {subscriptions.count()} subscriptions for user {request.user.id}")
            
            courses_data = []
            for subscription in subscriptions:
                try:
                    course = subscription.course
                    print(f"Processing course: {course.title_of_course} (ID: {course.id})")
                    
                    total_contents = CourseContent.objects.filter(
                        module__course=course,
                        module__status=1,
                        status=1
                    ).count()
                    
                    completed_contents = subscription.completed_contents.filter(
                        module__course=course,
                        module__status=1,
                        status=1
                    ).count()
                    
                    progress_percentage = (completed_contents / total_contents * 100) if total_contents > 0 else 0
                    
                    course_data = {
                        'id': course.id,
                        'title_of_course': course.title_of_course,
                        'description': course.description or '',
                        'image_url': course.image.url if course.image else None,
                        'creator_username': course.creator.username,
                        'creator_first_name': course.creator.first_name or '',
                        'creator_last_name': course.creator.last_name or '',
                        'created_at': course.created_at,
                        'updated_at': course.updated_at,
                        'status': course.status,
                        'status_display': course.get_status_display(),
                        'is_subscribed': True,
                        'is_favorited': course.get_is_favorited(request.user),
                        'progress_percentage': progress_percentage,
                        'total_score': subscription.total_score or 0,
                        'is_completed': subscription.is_completed or False,
                        'total_time_spent': subscription.total_time_spent or 0,
                        'module_count': course.get_active_module_count(),
                        'total_time_required_minutes': course.get_total_time_required_minutes(),
                        'total_time_required_hours': course.get_total_time_required_hours(),
                        'subscriber_count': course.get_subscriber_count()
                    }
                    courses_data.append(course_data)
                    print(f"Successfully processed course: {course.title_of_course}")
                    
                except Exception as course_error:
                    print(f"Error processing course {subscription.course.id}: {str(course_error)}")
                    continue
            
            print(f"Successfully processed {len(courses_data)} courses")
            return Response(courses_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error in MySubscriptions: {str(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            
            return Response(
                {'error': 'Failed to fetch subscribed courses', 'details': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# ==================== QCM VIEWS ====================

class SubmitQCM(APIView):
    def post(self, request, pk):
        try:
            course = get_object_or_404(Course, pk=pk)
            user = request.user
            content_id = request.data.get('content_id')
            question_answers = request.data.get('question_answers', {})
            time_taken = request.data.get('time_taken', 0)
            
            print(f"🔍 QCM Submission - Course: {course.id}, Content: {content_id}")
            print(f"🔍 Question Answers: {question_answers}")
            
            content = get_object_or_404(
                CourseContent, 
                id=content_id, 
                module__course=course,
                module__status=1,
                status=1
            )
            
            if content.content_type.name.lower() != 'qcm':
                return Response({'error': 'Content is not a QCM'}, status=400)
            
            qcm = content.qcm
            if not qcm:
                return Response({'error': 'QCM not found for this content'}, status=404)
            
            subscription, created = Subscription.objects.get_or_create(
                user=user,
                course=course,
                defaults={'is_active': True}
            )
            
            total_score = 0
            max_score = qcm.total_points
            question_results = []
            passed_questions = 0
            
            print(f"🔍 QCM has {qcm.questions.count()} questions")
            
            for question in qcm.questions.all().prefetch_related('options'):
                selected_option_ids = question_answers.get(str(question.id), [])
                selected_options = QCMOption.objects.filter(
                    id__in=selected_option_ids, 
                    question=question
                )
                
                print(f"🔍 Question {question.id}: {selected_options.count()} options selected")
                
                correct_options = question.options.filter(is_correct=True)
                total_correct = correct_options.count()
                selected_correct = selected_options.filter(is_correct=True).count()
                selected_incorrect = selected_options.filter(is_correct=False).count()
                
                if question.question_type == 'single':
                    is_correct = (selected_correct == 1 and selected_incorrect == 0 and 
                                 selected_options.count() == 1)
                    question_score = question.points if is_correct else 0
                    print('question_score', question_score)
                    
                else:
                    if total_correct > 0:
                        raw_score = max(0, selected_correct - selected_incorrect)
                        question_score = (raw_score / total_correct) * question.points
                    else:
                        question_score = 0
                
                question_passed = question_score >= (question.points * 0.8)
                if question_passed:
                    passed_questions += 1
                
                total_score += question_score
                
                question_results.append({
                    'question_id': question.id,
                    'question_text': question.question,
                    'question_type': question.question_type,
                    'points': question.points,
                    'score_earned': round(question_score, 2),
                    'max_score': question.points,
                    'is_passed': question_passed,
                    'correct_options': list(correct_options.values_list('id', flat=True)),
                    'selected_options': list(selected_options.values_list('id', flat=True)),
                    'feedback': self.get_question_feedback(question_score, question.points)
                })
            
            overall_percentage = (total_score / max_score * 100) if max_score > 0 else 0
            is_passed = overall_percentage >= qcm.passing_score
            points_earned = total_score if is_passed else 0
            
            print(f"🔍 Overall Score: {total_score}/{max_score} ({overall_percentage}%) - Passed: {is_passed}")
            
            attempt_number = self.get_next_attempt_number(user, qcm)
            
            attempt = QCMAttempt.objects.create(
                user=user,
                qcm=qcm,
                score=overall_percentage,
                points_earned=points_earned,
                is_passed=is_passed,
                attempt_number=attempt_number,
                time_taken=time_taken,
                completed_at=timezone.now()
            )
            
            all_selected_option_ids = []
            for question_id, option_ids in question_answers.items():
                all_selected_option_ids.extend(option_ids)
            
            selected_options = QCMOption.objects.filter(id__in=all_selected_option_ids)
            attempt.selected_options.set(selected_options)
            
            qcm_completion, created = QCMCompletion.objects.get_or_create(
                subscription=subscription,
                qcm=qcm,
                defaults={
                    'best_score': overall_percentage,
                    'points_earned': points_earned,
                    'is_passed': is_passed,
                    'attempts_count': 1,
                    'last_attempt': timezone.now()
                }
            )
            
            if not created:
                qcm_completion.attempts_count += 1
                if overall_percentage > qcm_completion.best_score:
                    qcm_completion.best_score = overall_percentage
                    qcm_completion.points_earned = points_earned
                    qcm_completion.is_passed = is_passed
                qcm_completion.last_attempt = timezone.now()
                qcm_completion.save()
            
            if is_passed:
                mark_view = MarkContentCompletedView()
                mark_view.request = request
                mark_response = mark_view.post(request, content_id)
                
                if mark_response.status_code == 200:
                    mark_data = mark_response.data
                else:
                    if not subscription.completed_contents.filter(id=content.id).exists():
                        subscription.completed_contents.add(content)
                    
                    active_contents = CourseContent.objects.filter(
                        module__course=course,
                        module__status=1,
                        status=1
                    )
                    total_active_contents = active_contents.count()
                    
                    completed_active_contents = subscription.completed_contents.filter(
                        id__in=active_contents.values_list('id', flat=True)
                    )
                    completed_count = completed_active_contents.count()
                    
                    progress_percentage = (completed_count / total_active_contents * 100) if total_active_contents > 0 else 0
                    
                    subscription.progress_percentage = progress_percentage
                    subscription.save()
                    
                    subscription.update_total_score()
                    subscription.update_completion_status()
            
            response_data = {
                'attempt_id': attempt.id,
                'overall_score': round(total_score, 2),
                'max_score': max_score,
                'percentage': round(overall_percentage, 2),
                'is_passed': is_passed,
                'points_earned': points_earned,
                'passed_questions': passed_questions,
                'total_questions': qcm.questions.count(),
                'question_results': question_results,
                'feedback': self.get_overall_feedback(overall_percentage, qcm.passing_score),
                'progress_percentage': subscription.progress_percentage,
                'total_score': subscription.total_score,
                'is_completed': subscription.is_completed,
                'qcm_completion_id': qcm_completion.id,
                'attempts_remaining': max(0, qcm.max_attempts - qcm_completion.attempts_count),
                'can_retry': qcm_completion.attempts_count < qcm.max_attempts and not is_passed
            }
            
            return Response(response_data, status=201)
                
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=404)
        except CourseContent.DoesNotExist:
            return Response({'error': 'Content not found or not active'}, status=404)
        except Subscription.DoesNotExist:
            return Response({'error': 'Subscription not found. Please subscribe to the course first.'}, status=404)
        except Exception as e:
            print(f"❌ Error in SubmitQCM: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({'error': f'Internal server error: {str(e)}'}, status=500)

    def get_next_attempt_number(self, user, qcm):
        last_attempt = QCMAttempt.objects.filter(user=user, qcm=qcm).order_by('-attempt_number').first()
        return last_attempt.attempt_number + 1 if last_attempt else 1
    
    def get_question_feedback(self, score_earned, max_score):
        percentage = (score_earned / max_score * 100) if max_score > 0 else 0
        
        if percentage >= 100:
            return "Perfect! All correct."
        elif percentage >= 80:
            return "Excellent! Almost perfect."
        elif percentage >= 60:
            return "Good effort! Mostly correct."
        elif percentage >= 40:
            return "Not bad, but needs improvement."
        else:
            return "Keep studying this topic."
    
    def get_overall_feedback(self, overall_percentage, passing_score):
        if overall_percentage >= passing_score:
            if overall_percentage >= 90:
                return "Outstanding performance! You've mastered this material."
            elif overall_percentage >= 80:
                return "Excellent work! You have a strong understanding."
            else:
                return "Congratulations! You passed the quiz."
        else:
            if overall_percentage >= passing_score * 0.8:
                return "Close! Review the material and try again."
            elif overall_percentage >= passing_score * 0.6:
                return "Good effort. Study the topics you missed and retry."
            else:
                return "Take time to review the material before trying again."

# ==================== TIME TRACKING VIEWS ====================

class TimeTrackingRecordView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        try:
            course = get_object_or_404(Course, pk=pk)
            user = request.user
            content_id = request.data.get('content_id')
            duration = request.data.get('duration')
            session_type = request.data.get('session_type', 'content')

            if not duration:
                return Response(
                    {'error': 'Duration is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            subscription, created = Subscription.objects.get_or_create(
                user=user,
                course=course,
                defaults={'is_active': True}
            )

            subscription.total_time_spent = F('total_time_spent') + duration
            subscription.save()
            subscription.refresh_from_db()

            time_tracking = None
            if content_id:
                try:
                    content = CourseContent.objects.get(id=content_id, module__course=course)
                    time_tracking = TimeTracking.objects.create(
                        user=user,
                        course=course,
                        module=content.module,
                        content=content,
                        start_time=timezone.now() - timedelta(seconds=duration),
                        end_time=timezone.now(),
                        duration=duration,
                        session_type=session_type
                    )
                except CourseContent.DoesNotExist:
                    pass
            subscription.update_completion_status()

            response_data = {
                'message': 'Time recorded successfully',
                'total_time_spent': subscription.total_time_spent,
                'progress_percentage': subscription.progress_percentage,
                'is_completed': subscription.is_completed,
                'completion_requirements': subscription.get_completion_requirements()
            }

            if time_tracking:
                response_data['time_tracking_id'] = time_tracking.id

            return Response(response_data, status=status.HTTP_200_OK)

        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

# ==================== FAVORITE COURSE VIEWS ====================

class FavoriteCourseViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FavoriteCourseSerializer
    
    def get_queryset(self):
        return FavoriteCourse.objects.filter(user=self.request.user).select_related(
            'course', 'course__creator'
        )
    
    def get_serializer_class(self):
        if self.action == 'create':
            return FavoriteCourseCreateSerializer
        return FavoriteCourseSerializer
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        
        return Response({
            'count': queryset.count(),
            'results': serializer.data
        })
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            favorite = serializer.save()
            return Response(
                FavoriteCourseSerializer(favorite, context={'request': request}).data,
                status=status.HTTP_201_CREATED
            )
        except serializers.ValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response(
            {'message': 'Course removed from favorites'},
            status=status.HTTP_204_NO_CONTENT
        )
    
    @action(detail=False, methods=['post'], url_path='toggle')
    def toggle_favorite(self, request):
        course_id = request.data.get('course_id')
        
        if not course_id:
            return Response(
                {'error': 'course_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            course = Course.objects.get(id=course_id, status=1)
        except Course.DoesNotExist:
            return Response(
                {'error': 'Active course not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        favorite = FavoriteCourse.objects.filter(
            user=request.user,
            course=course
        ).first()
        
        if favorite:
            favorite.delete()
            return Response({
                'message': 'Course removed from favorites',
                'is_favorited': False
            })
        else:
            favorite = FavoriteCourse.objects.create(
                user=request.user,
                course=course
            )
            return Response({
                'message': 'Course added to favorites',
                'is_favorited': True,
                'favorite': FavoriteCourseSerializer(favorite, context={'request': request}).data
            }, status=status.HTTP_201_CREATED)

# ==================== NOTIFICATION VIEWS ====================

class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            notifications = Notification.objects.filter(
                user=request.user
            ).select_related(
                'related_course',
                'related_module', 
                'related_content'
            ).order_by('-created_at')[:50]
            
            serializer = NotificationSerializer(notifications, many=True)
            
            unread_count = Notification.objects.filter(
                user=request.user,
                is_read=False
            ).count()
            
            return Response({
                'notifications': serializer.data,
                'unread_count': unread_count,
                'total_count': notifications.count()
            })
            
        except Exception as e:
            logger.error(f"Error fetching notifications: {str(e)}")
            return Response(
                {'error': 'Failed to fetch notifications'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class NotificationMarkAsReadView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, notification_id):
        try:
            notification = get_object_or_404(
                Notification, 
                id=notification_id, 
                user=request.user
            )
            
            notification.is_read = True
            notification.save()
            
            return Response({
                'message': 'Notification marked as read',
                'notification_id': notification.id
            })
            
        except Exception as e:
            logger.error(f"Error marking notification as read: {str(e)}")
            return Response(
                {'error': 'Failed to mark notification as read'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class NotificationMarkAllAsReadView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            updated_count = Notification.objects.filter(
                user=request.user,
                is_read=False
            ).update(is_read=True)
            
            return Response({
                'message': f'{updated_count} notifications marked as read',
                'updated_count': updated_count
            })
            
        except Exception as e:
            logger.error(f"Error marking all notifications as read: {str(e)}")
            return Response(
                {'error': 'Failed to mark notifications as read'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class NotificationUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            unread_count = Notification.objects.filter(
                user=request.user,
                is_read=False
            ).count()
            
            return Response({
                'unread_count': unread_count
            })
            
        except Exception as e:
            logger.error(f"Error fetching unread count: {str(e)}")
            return Response(
                {'error': 'Failed to fetch unread count'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# ==================== COURSE FILTERS VIEW ====================

class AllCoursesView(APIView):
    """
    Vue complète pour afficher tous les cours sans département :
    - Filtres par tags, difficulté, durée, popularité
    - Recherche avancée
    - Pagination intelligente
    - Affichage conditionnel (horizontal/vertical)
    - Statistiques enrichies
    - Système de recommandation par similarité
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        GET /api/courses/all/
        Récupère tous les cours avec filtres avancés
        """
        try:
            search_query = request.GET.get('search', '').strip()
            difficulty = request.GET.get('difficulty', '').strip().lower()
            duration_filter = request.GET.get('duration', '').strip()
            tags = request.GET.getlist('tags', [])
            content_types = request.GET.getlist('content_types', [])
            sort_by = request.GET.get('sort', '-created_at')
            page = int(request.GET.get('page', 1))
            page_size = int(request.GET.get('page_size', 12))
            user_privilege = request.user.privilege
            
            base_query = Q()
            
            if user_privilege in ['F', 'A']:
                status_filter = request.GET.get('status', None)
                if status_filter is not None:
                    base_query &= Q(status=int(status_filter))
            else:
                base_query &= Q(status=1)
            
            if search_query:
                search_terms = search_query.split()
                search_q = Q()
                for term in search_terms:
                    search_q |= Q(title_of_course__icontains=term)
                    search_q |= Q(description__icontains=term)
                    search_q |= Q(creator__username__icontains=term)
                    search_q |= Q(creator__first_name__icontains=term)
                    search_q |= Q(creator__last_name__icontains=term)
                    search_q |= Q(tags__tag__name__icontains=term)
                base_query &= search_q
            
            if difficulty in ['debutant', 'intermediaire', 'avance']:
                pass
            
            if duration_filter:
                pass
            
            if tags:
                tag_ids = [int(tag) for tag in tags if tag.isdigit()]
                if tag_ids:
                    base_query &= Q(tags__tag_id__in=tag_ids)
            
            if content_types:
                content_types_q = Q()
                for ct in content_types:
                    if ct in ['pdf', 'video', 'qcm', 'text', 'audio', 'image']:
                        content_types_q |= Q(modules__contents__content_type__name=ct)
                if content_types_q:
                    base_query &= content_types_q
            
            courses = Course.objects.filter(base_query)\
                .select_related('creator')\
                .prefetch_related(
                    'modules',
                    'tags__tag',
                    'course_subscriptions',
                    'modules__contents__content_type'
                )\
                .annotate(
                    subscriber_count=Count(
                        'course_subscriptions',
                        filter=Q(course_subscriptions__is_active=True),
                        distinct=True
                    ),
                    module_count=Count('modules', distinct=True),
                    content_count=Count('modules__contents', distinct=True),
                    estimated_duration_total=Sum('modules__contents__estimated_duration'),
                    min_required_time_total=Sum('modules__contents__min_required_time'),
                    tag_count=Count('tags', distinct=True),
                    last_content_date=Max('modules__contents__created_at'),
                    pdf_count=Count('modules__contents', 
                                   filter=Q(modules__contents__content_type__name='pdf'), 
                                   distinct=True),
                    video_count=Count('modules__contents', 
                                     filter=Q(modules__contents__content_type__name='video'), 
                                     distinct=True),
                    qcm_count=Count('modules__contents', 
                                   filter=Q(modules__contents__content_type__name='qcm'), 
                                   distinct=True),
                    avg_completion_rate=Avg(
                        'course_subscriptions__progress_percentage',
                        filter=Q(course_subscriptions__is_active=True)
                    ),
                    avg_score=Avg(
                        'course_subscriptions__total_score',
                        filter=Q(course_subscriptions__is_active=True)
                    )
                )\
                .order_by(sort_by)\
                .distinct()
            
            if difficulty in ['debutant', 'intermediaire', 'avance']:
                filtered_courses = []
                for course in courses:
                    course_difficulty = self.calculate_difficulty(course)
                    if course_difficulty == difficulty:
                        filtered_courses.append(course)
                courses = filtered_courses
            
            if duration_filter:
                duration_filtered = []
                for course in courses:
                    duration_hours = (course.estimated_duration_total or 0) / 60
                    
                    if duration_filter == 'short' and duration_hours <= 1:
                        duration_filtered.append(course)
                    elif duration_filter == 'medium' and 1 < duration_hours <= 5:
                        duration_filtered.append(course)
                    elif duration_filter == 'long' and duration_hours > 5:
                        duration_filtered.append(course)
                    elif duration_filter == 'very_long' and duration_hours > 10:
                        duration_filtered.append(course)
                
                courses = duration_filtered
            
            total_courses = len(courses)
            display_mode = self.determine_display_mode(total_courses, page_size)
            
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_courses = courses[start_idx:end_idx]
            
            subscribed_course_ids = set()
            if user_privilege != 'A':
                subscribed_course_ids = set(
                    Subscription.objects.filter(
                        user=request.user,
                        is_active=True
                    ).values_list('course_id', flat=True)
                )
            
            favorite_course_ids = set(
                FavoriteCourse.objects.filter(
                    user=request.user
                ).values_list('course_id', flat=True)
            )
            
            courses_data = []
            for course in paginated_courses:
                course_data = self.serialize_course(
                    course, 
                    request,
                    subscribed_course_ids,
                    favorite_course_ids,
                    display_mode
                )
                courses_data.append(course_data)
            
            available_tags = self.get_available_tags(courses)
            stats = self.get_courses_statistics(courses, request.user)
            recommended_courses = self.get_recommended_courses(
                request.user, 
                courses_data,
                paginated_courses
            )
            
            response_data = {
                'courses': courses_data,
                'pagination': {
                    'current_page': page,
                    'total_pages': (total_courses + page_size - 1) // page_size,
                    'total_courses': total_courses,
                    'has_next': end_idx < total_courses,
                    'has_previous': start_idx > 0,
                    'page_size': page_size,
                    'next_page_number': page + 1 if end_idx < total_courses else None,
                    'previous_page_number': page - 1 if start_idx > 0 else None
                },
                'filters': {
                    'search': search_query,
                    'difficulty': difficulty,
                    'duration': duration_filter,
                    'tags': tags,
                    'content_types': content_types,
                    'sort_by': sort_by
                },
                'display_mode': display_mode,
                'metadata': {
                    'available_tags': available_tags,
                    'available_difficulties': self.get_available_difficulties(),
                    'available_durations': self.get_available_durations(),
                    'available_content_types': self.get_available_content_types(),
                    'sort_options': self.get_sort_options(),
                    'total_filtered': total_courses,
                    'user_privilege': user_privilege,
                    'filter_summary': self.get_filter_summary(
                        search_query, difficulty, duration_filter, 
                        tags, content_types, total_courses
                    )
                },
                'statistics': stats,
                'recommendations': recommended_courses if len(courses_data) > 0 else [],
                'quick_stats': {
                    'courses_with_video': sum(1 for c in courses if c.video_count > 0),
                    'courses_with_qcm': sum(1 for c in courses if c.qcm_count > 0),
                    'free_courses': sum(1 for c in courses if not hasattr(c, 'price') or c.price == 0),
                    'high_rated_courses': sum(1 for c in courses if getattr(c, 'avg_score', 0) >= 80),
                    'popular_courses': sum(1 for c in courses if getattr(c, 'subscriber_count', 0) > 50)
                }
            }
            
            if display_mode == 'horizontal':
                response_data['pagination'] = None
                response_data['metadata'] = {
                    'available_tags': available_tags,
                    'total_filtered': total_courses
                }
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error in AllCoursesView: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {'error': f'Erreur lors de la récupération des cours: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def calculate_difficulty(self, course):
        difficulty_score = 0
        
        estimated_duration = getattr(course, 'estimated_duration_total', 0) or 0
        if estimated_duration > 600:
            difficulty_score += 3
        elif estimated_duration > 300:
            difficulty_score += 2
        elif estimated_duration > 60:
            difficulty_score += 1
        
        content_count = getattr(course, 'content_count', 0) or 0
        if content_count > 30:
            difficulty_score += 3
        elif content_count > 15:
            difficulty_score += 2
        elif content_count > 5:
            difficulty_score += 1
        
        qcm_count = getattr(course, 'qcm_count', 0) or 0
        if qcm_count > 10:
            difficulty_score += 2
        elif qcm_count > 5:
            difficulty_score += 1
        
        completion_rate = getattr(course, 'avg_completion_rate', 100) or 100
        if completion_rate < 50:
            difficulty_score += 2
        elif completion_rate < 70:
            difficulty_score += 1
        
        if difficulty_score >= 8:
            return 'avance'
        elif difficulty_score >= 4:
            return 'intermediaire'
        else:
            return 'debutant'
    
    def determine_display_mode(self, total_courses, page_size):
        if total_courses <= 4:
            return 'horizontal'
        elif total_courses <= page_size:
            return 'compact'
        else:
            return 'vertical'
    
    def serialize_course(self, course, request, subscribed_course_ids, favorite_course_ids, display_mode):
        from .serializers import CourseSerializer
        
        serializer = CourseSerializer(course, context={'request': request})
        course_data = serializer.data
        
        course_data['display_mode'] = display_mode
        course_data['is_subscribed'] = course.id in subscribed_course_ids
        course_data['is_favorited'] = course.id in favorite_course_ids
        
        if hasattr(course, 'subscriber_count'):
            course_data['subscriber_count'] = course.subscriber_count
            course_data['popularity'] = self.calculate_popularity_level(course.subscriber_count)
        
        if hasattr(course, 'module_count'):
            course_data['module_count'] = course.module_count
        
        if hasattr(course, 'content_count'):
            course_data['content_count'] = course.content_count
        
        if hasattr(course, 'estimated_duration_total'):
            course_data['estimated_duration_total'] = course.estimated_duration_total or 0
            course_data['estimated_duration_hours'] = round((course.estimated_duration_total or 0) / 60, 1)
            course_data['duration_category'] = self.get_duration_category(course.estimated_duration_total or 0)
        
        if hasattr(course, 'min_required_time_total'):
            course_data['min_required_time_total'] = course.min_required_time_total or 0
        
        if hasattr(course, 'pdf_count'):
            course_data['has_pdf'] = course.pdf_count > 0
        
        if hasattr(course, 'video_count'):
            course_data['has_video'] = course.video_count > 0
            course_data['video_count'] = course.video_count
        
        if hasattr(course, 'qcm_count'):
            course_data['has_qcm'] = course.qcm_count > 0
            course_data['qcm_count'] = course.qcm_count
        
        course_data['difficulty'] = self.calculate_difficulty(course)
        course_data['difficulty_score'] = self.calculate_difficulty_score(course)
        
        if hasattr(course, 'tags'):
            from .serializers import TagSerializer
            course_tags = [ct.tag for ct in course.tags.all()]
            course_data['tags'] = TagSerializer(course_tags, many=True).data
            course_data['primary_tag'] = course_tags[0].name if course_tags else None
        
        if course.id in subscribed_course_ids:
            subscription = Subscription.objects.filter(
                user=request.user,
                course=course,
                is_active=True
            ).first()
            
            if subscription:
                course_data['user_progress'] = {
                    'progress_percentage': subscription.progress_percentage,
                    'total_score': subscription.total_score,
                    'is_completed': subscription.is_completed,
                    'total_time_spent': subscription.total_time_spent,
                    'time_spent_hours': round(subscription.total_time_spent / 3600, 1) if subscription.total_time_spent else 0,
                    'completed_contents_count': subscription.completed_contents.count(),
                    'started_at': subscription.subscribed_at.isoformat() if subscription.subscribed_at else None,
                    'last_activity': self.get_last_activity(request.user, course)
                }
        
        course_data['badges'] = self.get_course_badges(course)
        course_data['quality_score'] = self.calculate_quality_score(course)
        
        if request.user.is_authenticated:
            course_data['compatibility_score'] = self.calculate_compatibility_score(course, request.user)
        
        if display_mode == 'horizontal':
            course_data.pop('description', None)
            course_data.pop('content_structure', None)
        
        return course_data
    
    def calculate_popularity_level(self, subscriber_count):
        if subscriber_count > 100:
            return 'very_popular'
        elif subscriber_count > 50:
            return 'popular'
        elif subscriber_count > 20:
            return 'growing'
        else:
            return 'new'
    
    def get_duration_category(self, duration_minutes):
        if duration_minutes <= 60:
            return 'short'
        elif duration_minutes <= 300:
            return 'medium'
        elif duration_minutes <= 600:
            return 'long'
        else:
            return 'very_long'
    
    def calculate_difficulty_score(self, course):
        score = 0
        
        estimated_duration = getattr(course, 'estimated_duration_total', 0) or 0
        if estimated_duration > 600:
            score += 3
        elif estimated_duration > 300:
            score += 2
        elif estimated_duration > 60:
            score += 1
        
        content_count = getattr(course, 'content_count', 0) or 0
        if content_count > 30:
            score += 3
        elif content_count > 15:
            score += 2
        elif content_count > 5:
            score += 1
        
        qcm_count = getattr(course, 'qcm_count', 0) or 0
        if qcm_count > 10:
            score += 2
        elif qcm_count > 5:
            score += 1
        
        completion_rate = getattr(course, 'avg_completion_rate', 100) or 100
        if completion_rate < 50:
            score += 2
        elif completion_rate < 70:
            score += 1
        
        return min(score, 10)
    
    def get_last_activity(self, user, course):
        try:
            last_tracking = DetailedTimeTracking.objects.filter(
                user=user,
                content__module__course=course
            ).order_by('-end_time').first()
            
            if last_tracking:
                return {
                    'date': last_tracking.end_time.isoformat(),
                    'content_title': last_tracking.content.title,
                    'content_type': last_tracking.content.content_type.name
                }
        except:
            pass
        return None
    
    def get_course_badges(self, course):
        badges = []
        
        subscriber_count = getattr(course, 'subscriber_count', 0) or 0
        if subscriber_count > 100:
            badges.append({'type': 'very_popular', 'label': 'Très populaire', 'color': 'gold', 'icon': '🔥'})
        elif subscriber_count > 50:
            badges.append({'type': 'popular', 'label': 'Populaire', 'color': 'silver', 'icon': '👍'})
        
        if course.created_at and (timezone.now() - course.created_at).days < 7:
            badges.append({'type': 'new', 'label': 'Nouveau', 'color': 'green', 'icon': '🆕'})
        
        if hasattr(course, 'last_content_date') and course.last_content_date:
            if (timezone.now() - course.last_content_date).days < 30:
                badges.append({'type': 'updated', 'label': 'Récemment mis à jour', 'color': 'blue', 'icon': '🔄'})
        
        content_count = getattr(course, 'content_count', 0) or 0
        if content_count > 20:
            badges.append({'type': 'comprehensive', 'label': 'Complet', 'color': 'purple', 'icon': '📚'})
        
        if course.creator and hasattr(course.creator, 'is_verified') and course.creator.is_verified:
            badges.append({'type': 'certified', 'label': 'Certifié', 'color': 'orange', 'icon': '✅'})
        
        quality_score = self.calculate_quality_score(course)
        if quality_score >= 8:
            badges.append({'type': 'high_quality', 'label': 'Haute qualité', 'color': 'red', 'icon': '⭐'})
        
        estimated_duration = getattr(course, 'estimated_duration_total', 0) or 0
        if estimated_duration <= 60:
            badges.append({'type': 'quick', 'label': 'Rapide', 'color': 'teal', 'icon': '⚡'})
        
        return badges
    
    def calculate_quality_score(self, course):
        score = 0
        
        content_count = getattr(course, 'content_count', 0) or 0
        if content_count > 20:
            score += 3
        elif content_count > 10:
            score += 2
        elif content_count > 5:
            score += 1
        
        type_count = 0
        if getattr(course, 'pdf_count', 0) > 0:
            type_count += 1
        if getattr(course, 'video_count', 0) > 0:
            type_count += 1
        if getattr(course, 'qcm_count', 0) > 0:
            type_count += 1
        
        if type_count >= 3:
            score += 3
        elif type_count == 2:
            score += 2
        elif type_count == 1:
            score += 1
        
        subscriber_count = getattr(course, 'subscriber_count', 0) or 0
        if subscriber_count > 50:
            score += 2
        elif subscriber_count > 20:
            score += 1
        
        completion_rate = getattr(course, 'avg_completion_rate', 0) or 0
        if completion_rate > 80:
            score += 2
        elif completion_rate > 60:
            score += 1
        
        return min(score, 10)
    
    def calculate_compatibility_score(self, course, user):
        score = 0
        
        user_subscriptions = Subscription.objects.filter(
            user=user,
            is_active=True
        ).select_related('course')
        
        if user_subscriptions.exists():
            user_tag_ids = set()
            for sub in user_subscriptions:
                user_tag_ids.update(sub.course.tags.values_list('tag_id', flat=True))
            
            course_tag_ids = set(course.tags.values_list('tag_id', flat=True))
            
            if user_tag_ids and course_tag_ids:
                common_tags = user_tag_ids.intersection(course_tag_ids)
                similarity = len(common_tags) / len(user_tag_ids.union(course_tag_ids))
                score += similarity * 50
        
        user_avg_progress = user_subscriptions.aggregate(
            avg=Avg('progress_percentage')
        )['avg'] or 0
        
        course_difficulty = self.calculate_difficulty_score(course)
        
        if user_avg_progress > 80 and course_difficulty <= 7:
            score += 30
        elif user_avg_progress > 60 and course_difficulty <= 5:
            score += 20
        elif user_avg_progress > 40 and course_difficulty <= 3:
            score += 10
        
        creator_courses_count = user_subscriptions.filter(
            course__creator=course.creator
        ).count()
        
        if creator_courses_count > 0:
            score += min(creator_courses_count * 5, 20)
        
        return min(score, 100)
    
    def get_available_tags(self, courses):
        from .models import CourseTag, Tag
        
        tag_stats = {}
        for course in courses:
            for course_tag in course.tags.all():
                tag_id = course_tag.tag.id
                if tag_id not in tag_stats:
                    tag_stats[tag_id] = {
                        'tag': course_tag.tag,
                        'count': 0,
                        'popularity': 0
                    }
                tag_stats[tag_id]['count'] += 1
        
        max_count = max([stats['count'] for stats in tag_stats.values()]) if tag_stats else 1
        
        for stats in tag_stats.values():
            stats['popularity'] = (stats['count'] / max_count) * 100
        
        sorted_tags = sorted(tag_stats.values(), key=lambda x: x['popularity'], reverse=True)
        
        from .serializers import TagSerializer
        result = []
        for stats in sorted_tags[:20]:
            tag_data = TagSerializer(stats['tag']).data
            tag_data['course_count'] = stats['count']
            tag_data['popularity_percentage'] = round(stats['popularity'], 1)
            result.append(tag_data)
        
        return result
    
    def get_available_difficulties(self):
        return [
            {'value': 'debutant', 'label': 'Débutant', 'description': 'Pour commencer'},
            {'value': 'intermediaire', 'label': 'Intermédiaire', 'description': 'Connaissances de base requises'},
            {'value': 'avance', 'label': 'Avancé', 'description': 'Pour experts'}
        ]
    
    def get_available_durations(self):
        return [
            {'value': 'short', 'label': 'Court (< 1h)', 'max_minutes': 60},
            {'value': 'medium', 'label': 'Moyen (1-5h)', 'min_minutes': 61, 'max_minutes': 300},
            {'value': 'long', 'label': 'Long (5-10h)', 'min_minutes': 301, 'max_minutes': 600},
            {'value': 'very_long', 'label': 'Très long (> 10h)', 'min_minutes': 601}
        ]
    
    def get_available_content_types(self):
        return [
            {'value': 'pdf', 'label': 'Documents PDF', 'icon': '📄'},
            {'value': 'video', 'label': 'Vidéos', 'icon': '🎥'},
            {'value': 'qcm', 'label': 'Quiz/QCM', 'icon': '❓'},
            {'value': 'text', 'label': 'Textes', 'icon': '📝'},
            {'value': 'audio', 'label': 'Audios', 'icon': '🎧'},
            {'value': 'image', 'label': 'Images', 'icon': '🖼️'}
        ]
    
    def get_sort_options(self):
        return [
            {'value': '-created_at', 'label': 'Plus récent', 'icon': '🆕'},
            {'value': '-subscriber_count', 'label': 'Plus populaire', 'icon': '🔥'},
            {'value': '-avg_score', 'label': 'Mieux noté', 'icon': '⭐'},
            {'value': 'estimated_duration_total', 'label': 'Durée (court → long)', 'icon': '⏱️'},
            {'value': '-estimated_duration_total', 'label': 'Durée (long → court)', 'icon': '⏱️'},
            {'value': 'title_of_course', 'label': 'Titre (A-Z)', 'icon': '🔤'},
            {'value': '-title_of_course', 'label': 'Titre (Z-A)', 'icon': '🔤'},
            {'value': '-last_content_date', 'label': 'Récemment mis à jour', 'icon': '🔄'},
            {'value': 'difficulty_score', 'label': 'Difficulté (facile → difficile)', 'icon': '📈'},
            {'value': '-difficulty_score', 'label': 'Difficulté (difficile → facile)', 'icon': '📉'}
        ]
    
    def get_filter_summary(self, search, difficulty, duration, tags, content_types, total):
        summary = []
        
        if search:
            summary.append(f"Recherche: '{search}'")
        
        if difficulty:
            difficulty_map = {
                'debutant': 'Débutant',
                'intermediaire': 'Intermédiaire',
                'avance': 'Avancé'
            }
            summary.append(f"Difficulté: {difficulty_map.get(difficulty, difficulty)}")
        
        if duration:
            duration_map = {
                'short': 'Court (< 1h)',
                'medium': 'Moyen (1-5h)',
                'long': 'Long (5-10h)',
                'very_long': 'Très long (> 10h)'
            }
            summary.append(f"Durée: {duration_map.get(duration, duration)}")
        
        if tags:
            summary.append(f"Tags: {len(tags)} sélectionné(s)")
        
        if content_types:
            summary.append(f"Types: {len(content_types)} sélectionné(s)")
        
        summary.append(f"Résultats: {total} cours")
        
        return summary
    
    def get_courses_statistics(self, courses, user):
        if not courses:
            return {
                'total_courses': 0,
                'stats_by_difficulty': {},
                'stats_by_duration': {},
                'content_type_distribution': {},
                'user_specific': {}
            }
        
        difficulty_stats = {}
        for course in courses:
            difficulty = self.calculate_difficulty(course)
            if difficulty not in difficulty_stats:
                difficulty_stats[difficulty] = 0
            difficulty_stats[difficulty] += 1
        
        duration_stats = {'short': 0, 'medium': 0, 'long': 0, 'very_long': 0}
        for course in courses:
            duration = self.get_duration_category(getattr(course, 'estimated_duration_total', 0) or 0)
            duration_stats[duration] += 1
        
        content_type_stats = {
            'courses_with_video': sum(1 for c in courses if getattr(c, 'video_count', 0) > 0),
            'courses_with_qcm': sum(1 for c in courses if getattr(c, 'qcm_count', 0) > 0),
            'courses_with_pdf': sum(1 for c in courses if getattr(c, 'pdf_count', 0) > 0)
        }
        
        stats = {
            'total_courses': len(courses),
            'stats_by_difficulty': difficulty_stats,
            'stats_by_duration': duration_stats,
            'content_type_distribution': content_type_stats,
            'average_subscribers': sum(getattr(c, 'subscriber_count', 0) for c in courses) / len(courses) if courses else 0,
            'average_duration': sum(getattr(c, 'estimated_duration_total', 0) or 0 for c in courses) / len(courses) / 60 if courses else 0,
            'total_subscribers': sum(getattr(c, 'subscriber_count', 0) for c in courses),
            'user_specific': {}
        }
        
        if user.privilege in ['F', 'A']:
            user_courses = [c for c in courses if c.creator == user]
            stats['user_specific'] = {
                'my_courses': len(user_courses),
                'my_subscribers': sum(getattr(c, 'subscriber_count', 0) for c in user_courses),
                'my_average_subscribers': sum(getattr(c, 'subscriber_count', 0) for c in user_courses) / len(user_courses) if user_courses else 0
            }
        else:
            subscribed_ids = set(
                Subscription.objects.filter(
                    user=user,
                    is_active=True
                ).values_list('course_id', flat=True)
            )
            
            enrolled_courses = [c for c in courses if c.id in subscribed_ids]
            
            stats['user_specific'] = {
                'enrolled_courses': len(enrolled_courses),
                'completed_courses': sum(1 for c in enrolled_courses if Subscription.objects.filter(
                    user=user,
                    course=c,
                    is_completed=True
                ).exists()),
                'in_progress_courses': sum(1 for c in enrolled_courses if Subscription.objects.filter(
                    user=user,
                    course=c,
                    progress_percentage__gt=0,
                    progress_percentage__lt=100
                ).exists()),
                'average_progress': Subscription.objects.filter(
                    user=user,
                    course__in=enrolled_courses
                ).aggregate(avg=Avg('progress_percentage'))['avg'] or 0 if enrolled_courses else 0
            }
        
        return stats
    
    def get_recommended_courses(self, user, current_courses_data, current_courses_list):
        if not current_courses_data or not current_courses_list:
            return []
        
        try:
            current_course_ids = [course['id'] for course in current_courses_data[:5]]
            
            from .models import CourseTag
            tag_ids = CourseTag.objects.filter(
                course_id__in=current_course_ids
            ).values_list('tag_id', flat=True).distinct()
            
            similar_courses = Course.objects.filter(
                tags__tag_id__in=tag_ids,
                status=1
            ).exclude(id__in=current_course_ids)\
             .annotate(
                 common_tags=Count('tags__tag_id', filter=Q(tags__tag_id__in=tag_ids)),
                 subscriber_count=Count('course_subscriptions')
             )\
             .order_by('-common_tags', '-subscriber_count')\
             .select_related('creator')[:5]
            
            if similar_courses.count() < 3:
                user_subscriptions = Subscription.objects.filter(
                    user=user,
                    is_active=True
                ).values_list('course_id', flat=True)
                
                if user_subscriptions:
                    user_tag_ids = CourseTag.objects.filter(
                        course_id__in=user_subscriptions
                    ).values_list('tag_id', flat=True).distinct()
                    
                    if user_tag_ids:
                        history_based = Course.objects.filter(
                            tags__tag_id__in=user_tag_ids,
                            status=1
                        ).exclude(id__in=current_course_ids)\
                         .exclude(id__in=user_subscriptions)\
                         .annotate(
                             common_tags=Count('tags__tag_id', filter=Q(tags__tag_id__in=user_tag_ids))
                         )\
                         .order_by('-common_tags')[:5 - similar_courses.count()]
                        
                        similar_courses = list(similar_courses) + list(history_based)
            
            if len(similar_courses) < 5:
                popular_courses = Course.objects.filter(
                    status=1
                ).exclude(id__in=current_course_ids)\
                 .annotate(subscriber_count=Count('course_subscriptions'))\
                 .order_by('-subscriber_count')[:5 - len(similar_courses)]
                
                similar_courses = list(similar_courses) + list(popular_courses)
            
            from .serializers import CourseSerializer
            from django.http import HttpRequest
            from rest_framework.request import Request
            
            dummy_request = Request(HttpRequest())
            dummy_request.user = user
            
            recommended_data = []
            for course in similar_courses:
                recommendation_score = self.calculate_recommendation_score(course, user, current_courses_list)
                
                serializer = CourseSerializer(course, context={'request': dummy_request})
                course_data = serializer.data
                course_data['recommendation_score'] = recommendation_score
                course_data['recommendation_reasons'] = self.get_recommendation_reasons(
                    course, 
                    user, 
                    current_courses_list, 
                    recommendation_score
                )
                
                recommended_data.append(course_data)
            
            recommended_data.sort(key=lambda x: x['recommendation_score'], reverse=True)
            
            return recommended_data[:5]
            
        except Exception as e:
            logger.error(f"Error getting recommended courses: {str(e)}")
            return []
    
    def calculate_recommendation_score(self, course, user, current_courses):
        score = 0
        
        current_tags = set()
        for c in current_courses[:3]:
            current_tags.update(c.tags.values_list('tag_id', flat=True))
        
        course_tags = set(course.tags.values_list('tag_id', flat=True))
        
        if current_tags and course_tags:
            common_tags = current_tags.intersection(course_tags)
            similarity = len(common_tags) / len(current_tags.union(course_tags))
            score += similarity * 40
        
        subscriber_count = getattr(course, 'subscriber_count', 0) or 0
        if subscriber_count > 50:
            score += 20
        elif subscriber_count > 20:
            score += 10
        elif subscriber_count > 5:
            score += 5
        
        user_subscriptions = Subscription.objects.filter(
            user=user,
            is_active=True
        ).count()
        
        if user_subscriptions > 0:
            creator_followed = Subscription.objects.filter(
                user=user,
                course__creator=course.creator,
                is_active=True
            ).exists()
            
            if creator_followed:
                score += 20
        
        quality_score = self.calculate_quality_score(course)
        score += (quality_score / 10) * 20
        
        return min(score, 100)
    
    def get_recommendation_reasons(self, course, user, current_courses, score):
        reasons = []
        
        if score >= 80:
            reasons.append("Très similaire aux cours que vous consultez")
        elif score >= 60:
            reasons.append("Similaire à vos centres d'intérêt")
        
        subscriber_count = getattr(course, 'subscriber_count', 0) or 0
        if subscriber_count > 50:
            reasons.append("Très populaire parmi les apprenants")
        
        user_follows_creator = Subscription.objects.filter(
            user=user,
            course__creator=course.creator,
            is_active=True
        ).exists()
        
        if user_follows_creator:
            reasons.append("Du même formateur que vos cours suivis")
        
        quality_score = self.calculate_quality_score(course)
        if quality_score >= 8:
            reasons.append("Contenu de haute qualité")
        
        difficulty = self.calculate_difficulty(course)
        if difficulty == 'debutant':
            reasons.append("Parfait pour les débutants")
        elif difficulty == 'intermediaire':
            reasons.append("Idéal pour progresser")
        
        return reasons[:3]

class CourseFiltersView(APIView):
    """
    Vue pour récupérer tous les filtres disponibles
    Utile pour peupler les dropdowns/checkboxes dans le frontend
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            from .models import Tag
            
            tags = Tag.objects.annotate(
                course_count=Count('coursetag', distinct=True)
            ).order_by('-course_count')
            
            from .serializers import TagSerializer
            tags_data = TagSerializer(tags, many=True).data
            
            for tag_data, tag in zip(tags_data, tags):
                tag_data['course_count'] = tag.course_count
            
            total_courses = Course.objects.filter(status=1).count()
            
            if request.user.privilege in ['F', 'A']:
                my_courses_count = Course.objects.filter(
                    creator=request.user
                ).count()
            else:
                my_courses_count = 0
            
            return Response({
                'tags': tags_data[:50],
                'difficulties': [
                    {'value': 'debutant', 'label': 'Débutant', 'icon': '👶'},
                    {'value': 'intermediaire', 'label': 'Intermédiaire', 'icon': '📚'},
                    {'value': 'avance', 'label': 'Avancé', 'icon': '🎓'}
                ],
                'durations': [
                    {'value': 'short', 'label': 'Court (< 1h)', 'icon': '⚡'},
                    {'value': 'medium', 'label': 'Moyen (1-5h)', 'icon': '⏱️'},
                    {'value': 'long', 'label': 'Long (5-10h)', 'icon': '📖'},
                    {'value': 'very_long', 'label': 'Très long (> 10h)', 'icon': '📚'}
                ],
                'content_types': [
                    {'value': 'pdf', 'label': 'PDF', 'icon': '📄'},
                    {'value': 'video', 'label': 'Vidéo', 'icon': '🎥'},
                    {'value': 'qcm', 'label': 'QCM', 'icon': '❓'},
                    {'value': 'text', 'label': 'Texte', 'icon': '📝'},
                    {'value': 'audio', 'label': 'Audio', 'icon': '🎧'},
                    {'value': 'image', 'label': 'Image', 'icon': '🖼️'}
                ],
                'sort_options': [
                    {'value': '-created_at', 'label': 'Plus récent', 'icon': '🆕'},
                    {'value': '-subscriber_count', 'label': 'Plus populaire', 'icon': '🔥'},
                    {'value': 'title_of_course', 'label': 'Titre A-Z', 'icon': '🔤'},
                    {'value': '-title_of_course', 'label': 'Titre Z-A', 'icon': '🔤'},
                    {'value': 'estimated_duration_total', 'label': 'Durée croissante', 'icon': '⏱️'},
                    {'value': '-estimated_duration_total', 'label': 'Durée décroissante', 'icon': '⏱️'}
                ],
                'statistics': {
                    'total_courses': total_courses,
                    'my_courses_count': my_courses_count,
                    'enrolled_courses_count': Subscription.objects.filter(
                        user=request.user,
                        is_active=True
                    ).count() if request.user.is_authenticated else 0
                },
                'quick_filters': [
                    {'type': 'popular', 'label': 'Populaires', 'query': '?sort=-subscriber_count'},
                    {'type': 'new', 'label': 'Nouveautés', 'query': '?sort=-created_at'},
                    {'type': 'quick', 'label': 'Rapides', 'query': '?duration=short'},
                    {'type': 'comprehensive', 'label': 'Complets', 'query': '?content_types=pdf&content_types=video&content_types=qcm'}
                ]
            })
            
        except Exception as e:
            logger.error(f"Error in CourseFiltersView: {str(e)}")
            return Response(
                {'error': 'Erreur lors de la récupération des filtres'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ConditionalCoursesDisplayView(APIView):
    """
    Vue optimisée pour l'affichage conditionnel
    Retourne les données formatées selon le mode d'affichage
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            display_mode = request.GET.get('display_mode', 'auto')
            limit = int(request.GET.get('limit', 12))
            
            if request.user.privilege in ['F', 'A']:
                courses = Course.objects.filter(status__in=[0, 1, 2])
            else:
                courses = Course.objects.filter(status=1)
            
            search = request.GET.get('search', '')
            if search:
                courses = courses.filter(
                    Q(title_of_course__icontains=search) |
                    Q(description__icontains=search)
                )
            
            if display_mode == 'auto':
                total_courses = courses.count()
                if total_courses <= 4:
                    display_mode = 'horizontal'
                elif total_courses <= 8:
                    display_mode = 'compact'
                else:
                    display_mode = 'vertical'
            
            if display_mode == 'horizontal':
                courses = courses[:4]
                page_size = 4
            elif display_mode == 'compact':
                courses = courses[:8]
                page_size = 8
            else:
                page = int(request.GET.get('page', 1))
                page_size = int(request.GET.get('page_size', 12))
                start_idx = (page - 1) * page_size
                courses = courses[start_idx:start_idx + page_size]
            
            from .serializers import CourseSerializer
            
            context = {
                'request': request,
                'display_mode': display_mode,
                'is_condensed': display_mode in ['horizontal', 'compact']
            }
            
            serializer = CourseSerializer(courses, many=True, context=context)
            courses_data = serializer.data
            
            response_data = {
                'display_mode': display_mode,
                'courses': courses_data,
                'display_config': {
                    'items_per_row': 4 if display_mode == 'horizontal' else 3 if display_mode == 'compact' else 1,
                    'show_descriptions': display_mode != 'horizontal',
                    'show_stats': display_mode != 'horizontal',
                    'show_progress': True,
                    'show_actions': display_mode != 'compact'
                }
            }
            
            if display_mode == 'vertical':
                total_courses = Course.objects.filter(status=1).count()
                if search:
                    total_courses = Course.objects.filter(
                        Q(title_of_course__icontains=search) |
                        Q(description__icontains=search),
                        status=1
                    ).count()
                
                response_data['pagination'] = {
                    'current_page': page,
                    'total_pages': (total_courses + page_size - 1) // page_size,
                    'total_courses': total_courses,
                    'page_size': page_size
                }
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error in ConditionalCoursesDisplayView: {str(e)}")
            return Response(
                {'error': f'Erreur: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# ==================== PERMISSION CLASSES ====================

class IsSuperUser(IsAuthenticated):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.privilege == 'A')

class IsFormateur(IsAuthenticated):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.privilege == 'F')

class IsApprenant(IsAuthenticated):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.privilege == 'AP')

class IsOrganizationOwner(IsAuthenticated):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.privilege == 'O')