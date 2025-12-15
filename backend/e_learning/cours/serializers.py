from rest_framework import serializers
from users.models import CustomUser, VerificationCode, Organization, Group, Member
from .models import (
    Course, Module, CourseContent, VideoContent, PDFContent, 
    QCM, QCMQuestion, QCMOption, ContentType, Subscription, TimeTracking,
    Enrollment, ContentProgress, QCMCompletion, QCMAttempt, FavoriteCourse, Tag
)
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import get_user_model
from django.db.models import Sum, Avg, Count
from django.shortcuts import get_object_or_404

User = get_user_model()


def safe_int(value):
    """Safely convert value to int, returns 0 if conversion fails"""
    try:
        return int(value) if value is not None else 0
    except (ValueError, TypeError):
        return 0


def safe_float(value):
    """Safely convert value to float, returns 0.0 if conversion fails"""
    try:
        return float(value) if value is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


def safe_percentage(numerator, denominator):
    """Safely calculate percentage, returns 0 if denominator is 0"""
    if denominator == 0:
        return 0
    try:
        return round((numerator / denominator) * 100, 2)
    except (ValueError, TypeError):
        return 0


class QCMOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QCMOption
        fields = ['id', 'text', 'is_correct', 'order']


class QCMOptionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = QCMOption
        fields = ['text', 'is_correct', 'order']


class QCMQuestionSerializer(serializers.ModelSerializer):
    options = QCMOptionSerializer(many=True, read_only=True)
    
    class Meta:
        model = QCMQuestion
        fields = ['id', 'question', 'question_type', 'points', 'order', 'options']


class QCMQuestionCreateSerializer(serializers.ModelSerializer):
    options = QCMOptionCreateSerializer(many=True)
    
    class Meta:
        model = QCMQuestion
        fields = ['question', 'question_type', 'points', 'order', 'options']


class QCMSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source='course_content.title', required=False)
    caption = serializers.CharField(source='course_content.caption', required=False)
    order = serializers.IntegerField(source='course_content.order', required=False)
    status = serializers.IntegerField(source='course_content.status', required=False)
    status_display = serializers.CharField(source='course_content.status_display', read_only=True)
    estimated_duration = serializers.IntegerField(source='course_content.estimated_duration', required=False)
    min_required_time = serializers.IntegerField(source='course_content.min_required_time', required=False)
    questions = QCMQuestionSerializer(many=True, read_only=True)
    total_points = serializers.SerializerMethodField()
    questions_count = serializers.SerializerMethodField()
    
    class Meta:
        model = QCM
        fields = [
            'id', 'title', 'caption', 'order', 'status', 'status_display',
            'estimated_duration', 'min_required_time', 
            'passing_score', 'max_attempts', 'time_limit',
            'questions', 'total_points', 'questions_count'
        ]
        read_only_fields = ['id']
    
    def get_total_points(self, obj):
        return sum(question.points for question in obj.questions.all())
    
    def get_questions_count(self, obj):
        return obj.questions.count()


class PDFContentSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source='course_content.title', required=False)
    caption = serializers.CharField(source='course_content.caption', required=False)
    order = serializers.IntegerField(source='course_content.order', required=False)
    status = serializers.IntegerField(source='course_content.status', required=False)
    status_display = serializers.CharField(source='course_content.status_display', read_only=True)
    estimated_duration = serializers.IntegerField(source='course_content.estimated_duration', required=False)
    min_required_time = serializers.IntegerField(source='course_content.min_required_time', required=False)
    
    class Meta:
        model = PDFContent
        fields = [
            'id', 'pdf_file', 'page_count', 'estimated_reading_time',
            'title', 'caption', 'order', 'status', 'status_display',
            'estimated_duration', 'min_required_time'
        ]
        read_only_fields = ['id']


class VideoContentSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source='course_content.title', required=False)
    caption = serializers.CharField(source='course_content.caption', required=False)
    order = serializers.IntegerField(source='course_content.order', required=False)
    status = serializers.IntegerField(source='course_content.status', required=False)
    status_display = serializers.CharField(source='course_content.status_display', read_only=True)
    estimated_duration = serializers.IntegerField(source='course_content.estimated_duration', required=False)
    min_required_time = serializers.IntegerField(source='course_content.min_required_time', required=False)
    
    class Meta:
        model = VideoContent
        fields = [
            'id', 'video_file', 'duration',
            'title', 'caption', 'order', 'status', 'status_display',
            'estimated_duration', 'min_required_time'
        ]
        read_only_fields = ['id']

class QCMAttemptSerializer(serializers.ModelSerializer):
    selected_option_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True
    )
    
    class Meta:
        model = QCMAttempt
        fields = ['id', 'user', 'qcm', 'selected_option_ids', 'time_taken', 
                 'attempt_number', 'score', 'is_passed', 'completed_at']
        read_only_fields = ['id', 'user', 'qcm', 'score', 'is_passed', 'completed_at']
class QCMCompletionSerializer(serializers.ModelSerializer):
    qcm_title = serializers.CharField(source='qcm.question', read_only=True)
    
    class Meta:
        model = QCMCompletion
        fields = ['qcm', 'qcm_title', 'best_score', 'points_earned', 'is_passed', 'attempts_count', 'last_attempt']
class ModuleWithContentsSerializer(serializers.ModelSerializer):
    contents = serializers.SerializerMethodField()
    content_stats = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Module
        fields = [
            'id', 'title', 'description', 'order', 'status', 'status_display',
            'estimated_duration', 'min_required_time', 'created_at', 'updated_at',
            'contents', 'content_stats'
        ]
    
    def get_contents(self, obj):
        contents = obj.contents.all().order_by('order')
        request = self.context.get('request')
        subscription = self.context.get('subscription')
        
        return CourseContentSerializer(
            contents, 
            many=True, 
            context={'request': request, 'subscription': subscription}
        ).data
    
    def get_content_stats(self, obj):
        """Calculate comprehensive content statistics for a module"""
        course = obj.course

        # DEBUG: Check what subscriptions exist 
        all_subscriptions = Subscription.objects.filter(course=course, is_active=True)
        print(f"DEBUG - Course: {course.id}, All active subscriptions: {all_subscriptions.count()}")

        completed_subscriptions = Subscription.objects.filter(
            course=course, 
            is_active=True, 
            is_completed=True
        )
        print(f"DEBUG - Completed subscriptions: {completed_subscriptions.count()}")

        # Print details of each subscription
        for sub in completed_subscriptions:
            print(f"DEBUG - Completed subscription: User {sub.user.id}, Completed: {sub.is_completed}")

        total_enrolled = safe_int(all_subscriptions.count())
        total_completed = safe_int(completed_subscriptions.count())

        print(f"DEBUG - Final counts - Enrolled: {total_enrolled}, Completed: {total_completed}")


        # Calculate completion rate (percentage of enrolled users who completed)
        completion_rate = safe_percentage(total_completed, total_enrolled)

        # Course structure counts
        total_modules = safe_int(Module.objects.filter(course=course).count())
        total_contents_course = safe_int(CourseContent.objects.filter(module__course=course).count())

        # Average progress of all active users
        progress_result = Subscription.objects.filter(
            course=course, 
            is_active=True
        ).aggregate(avg_progress=Avg('progress_percentage'))
        average_progress = safe_float(progress_result.get('avg_progress', 0))

        # Time tracking statistics
        time_result = TimeTracking.objects.filter(course=course).aggregate(
            avg_time=Avg('duration'),
            total_time=Sum('duration')
        )
        avg_time = safe_float(time_result.get('avg_time', 0))
        total_time = safe_int(time_result.get('total_time', 0))

        # Module-specific content counts
        if hasattr(obj, 'prefetched_contents'):
            contents = obj.prefetched_contents
        else:
            contents = obj.contents.all()

        pdf_count = safe_int(contents.filter(content_type__name__iexact='pdf').count())
        video_count = safe_int(contents.filter(content_type__name__iexact='video').count())
        qcm_count = safe_int(contents.filter(content_type__name__iexact='qcm').count())
        total_contents_module = safe_int(contents.count())
        return {
            'total_users_enrolled': total_enrolled,
            'total_users_completed': total_completed,
            'total_modules': total_modules,
            'total_contents_course': total_contents_course,
            'completion_rate': completion_rate,
            'average_progress': average_progress,
            'total_contents_module': total_contents_module,
            'pdf_count': pdf_count,
            'video_count': video_count,
            'qcm_count': qcm_count,
            'average_time_spent': avg_time,
            'total_time_tracked': total_time,
        }
class CourseContentSerializer(serializers.ModelSerializer):
    video_content = VideoContentSerializer(read_only=True)
    pdf_content = PDFContentSerializer(read_only=True)
    qcm = QCMSerializer(read_only=True)
    content_type_name = serializers.CharField(source='content_type.name', read_only=True)
    is_completed = serializers.SerializerMethodField()
    can_access = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    
    class Meta:
        model = CourseContent
        fields = [
            'id', 'title', 'caption', 'order', 'status', 'status_display', 
            'content_type_name', 'estimated_duration', 'min_required_time',
            'video_content', 'pdf_content', 'qcm', 'is_completed', 'can_access',
            'views_count', 'completed_count', 'average_rating', 'completion_rate',
            'created_at', 'updated_at'
        ]
    
    def get_status_display(self, obj):
        status_map = {0: 'Brouillon', 1: 'Actif', 2: 'Archivé'}
        return status_map.get(obj.status, 'Non défini')
    
    def get_is_completed(self, obj):
        request = self.context.get('request')
        subscription = self.context.get('subscription')
        
        if not request or not request.user.is_authenticated:
            return False
        
        if subscription:
            if subscription.completed_contents.filter(id=obj.id).exists():
                return True
            
            if obj.content_type.name == 'qcm' and hasattr(obj, 'qcm'):
                return QCMCompletion.objects.filter(
                    subscription=subscription,
                    qcm=obj.qcm,
                    is_passed=True
                ).exists()
        
        return False
    
    def get_can_access(self, obj):
        request = self.context.get('request')
        subscription = self.context.get('subscription')
        
        if not request or not request.user.is_authenticated or not subscription:
            return True
        
        return subscription.can_access_content(obj)

class CourseContentCreateSerializer(serializers.ModelSerializer):
    content_type = serializers.CharField(write_only=True)
    pdf_file = serializers.FileField(required=False, allow_null=True)
    video_file = serializers.FileField(required=False, allow_null=True)
    
    # Multi-question QCM fields
    questions = QCMQuestionCreateSerializer(many=True, required=False, allow_null=True)
    passing_score = serializers.IntegerField(required=False, default=80)
    max_attempts = serializers.IntegerField(required=False, default=3)
    time_limit = serializers.IntegerField(required=False, default=0)

    class Meta:
        model = CourseContent
        fields = [
            'title', 'caption', 'order', 'status', 'content_type',
            'estimated_duration', 'min_required_time',
            'pdf_file', 'video_file', 'questions',
            'passing_score', 'max_attempts', 'time_limit'
        ]

    def validate(self, data):
        content_type_name = data.get('content_type')
        
        if content_type_name == 'pdf' and not data.get('pdf_file'):
            raise serializers.ValidationError("PDF file is required for PDF content")
        
        if content_type_name == 'video' and not data.get('video_file'):
            raise serializers.ValidationError("Video file is required for video content")
        
        if content_type_name == 'qcm':
            questions = data.get('questions', [])
            if not questions:
                raise serializers.ValidationError("At least one question is required for QCM content")
            
            # Validate each question
            for i, question_data in enumerate(questions):
                options = question_data.get('options', [])
                if len(options) < 2:
                    raise serializers.ValidationError(f"Question {i+1}: At least 2 options are required")
                
                correct_options = sum(1 for option in options if option.get('is_correct', False))
                if correct_options == 0:
                    raise serializers.ValidationError(f"Question {i+1}: At least one option must be correct")
                
                # For single choice questions, ensure only one correct option
                question_type = question_data.get('question_type', 'single')
                if question_type == 'single' and correct_options > 1:
                    raise serializers.ValidationError(f"Question {i+1}: Single choice questions can have only one correct option")
        
        # Ensure only one content type is specified
        content_specific_fields = ['pdf_file', 'video_file', 'questions']
        provided_fields = [field for field in content_specific_fields if data.get(field)]
        
        if len(provided_fields) > 1:
            raise serializers.ValidationError("Only one content type can be specified at a time")
        
        return data

    def create(self, validated_data):
        content_type_name = validated_data.pop('content_type')
        content_type = get_object_or_404(ContentType, name=content_type_name)
        
        module = self.context.get('module')
        if not module:
            raise serializers.ValidationError("Module is required to create content")
        
        pdf_file = validated_data.pop('pdf_file', None)
        video_file = validated_data.pop('video_file', None)
        questions_data = validated_data.pop('questions', [])
        passing_score = validated_data.pop('passing_score', 80)
        max_attempts = validated_data.pop('max_attempts', 3)
        time_limit = validated_data.pop('time_limit', 0)

        course_content = CourseContent.objects.create(
            module=module,
            content_type=content_type,
            **validated_data
        )

        if content_type_name == 'pdf' and pdf_file:
            PDFContent.objects.create(course_content=course_content, pdf_file=pdf_file)
        
        elif content_type_name == 'video' and video_file:
            VideoContent.objects.create(course_content=course_content, video_file=video_file)
        
        elif content_type_name == 'qcm' and questions_data:
            # Create QCM
            qcm = QCM.objects.create(
                course_content=course_content,
                passing_score=passing_score,
                max_attempts=max_attempts,
                time_limit=time_limit
            )
            
            # Create questions and options
            for question_data in questions_data:
                options_data = question_data.pop('options')
                
                question = QCMQuestion.objects.create(
                    qcm=qcm,
                    **question_data
                )
                
                for option_data in options_data:
                    QCMOption.objects.create(
                        question=question,  # Link to question
                        **option_data
                    )

        return course_content
# ==================== MODULE SERIALIZERS ====================

class ModuleSerializer(serializers.ModelSerializer):
    contents = serializers.SerializerMethodField()
    content_stats = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    calculated_estimated_duration = serializers.SerializerMethodField()
    calculated_min_required_time = serializers.SerializerMethodField()
    
    class Meta:
        model = Module
        fields = [
            'id', 'title', 'description', 'order', 'status', 'status_display', 
            'estimated_duration', 'min_required_time', 'created_at', 'updated_at',
            'contents', 'content_stats',
            'calculated_estimated_duration', 'calculated_min_required_time'
        ]
    
    def get_status_display(self, obj):
        status_map = {0: 'Brouillon', 1: 'Actif', 2: 'Archivé'}
        return status_map.get(obj.status, 'Non défini')
    
    def get_contents(self, obj):
        contents = obj.contents.all().order_by('order')
        request = self.context.get('request')
        subscription = self.context.get('subscription')
        
        return CourseContentSerializer(
            contents, 
            many=True, 
            context={'request': request, 'subscription': subscription}
        ).data
    
    def get_content_stats(self, obj):
        contents = obj.contents.all()
        return {
            'total_contents': contents.count(),
            'pdf_count': contents.filter(content_type__name='pdf').count(),
            'video_count': contents.filter(content_type__name='video').count(),
            'qcm_count': contents.filter(content_type__name='qcm').count(),
        }
    
    def get_calculated_estimated_duration(self, obj):
        return obj.calculate_estimated_duration()
    
    def get_calculated_min_required_time(self, obj):
        return obj.calculate_min_required_time()


class ModuleCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Module
        fields = ['title', 'description', 'order', 'status', 'estimated_duration', 'min_required_time']
    
    def create(self, validated_data):
        course = self.context.get('course')
        if not course:
            raise serializers.ValidationError("Course is required")
        
        module = Module.objects.create(course=course, **validated_data)
        return module


# ==================== COURSE SERIALIZERS ====================

class CourseSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()
    is_subscribed = serializers.SerializerMethodField()
    module_count = serializers.SerializerMethodField()
    creator_username = serializers.CharField(source='creator.username', read_only=True)
    creator_first_name = serializers.CharField(source='creator.first_name', read_only=True)
    creator_last_name = serializers.CharField(source='creator.last_name', read_only=True)
    status_display = serializers.SerializerMethodField()
    calculated_estimated_duration = serializers.SerializerMethodField()
    calculated_min_required_time = serializers.SerializerMethodField()
    subscriber_count = serializers.SerializerMethodField()
    average_progress = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            'id', 'title_of_course', 'description', 'image_url',
            'status', 'status_display', 'created_at', 'updated_at',
            'estimated_duration', 'min_required_time',
            'progress_percentage', 'is_subscribed', 'module_count',
            'creator_username', 'creator_first_name', 'creator_last_name',
            'subscriber_count', 'average_progress',
            'calculated_estimated_duration', 'calculated_min_required_time'
        ]

    def get_status_display(self, obj):
        status_map = {0: 'Brouillon', 1: 'Actif', 2: 'Archivé'}
        return status_map.get(obj.status, 'Non défini')
    
    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None
    
    def get_calculated_estimated_duration(self, obj):
        return obj.calculate_estimated_duration()
    
    def get_calculated_min_required_time(self, obj):
        return obj.calculate_min_required_time()
    
    def get_subscriber_count(self, obj):
        return obj.course_subscriptions.filter(is_active=True).count()
    
    def get_average_progress(self, obj):
        active_subscriptions = obj.course_subscriptions.filter(is_active=True)
        if not active_subscriptions.exists():
            return 0
        
        total_progress = sum(sub.progress_percentage or 0 for sub in active_subscriptions)
        return round(total_progress / active_subscriptions.count())
    
    def get_progress_percentage(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            subscription = Subscription.objects.filter(
                user=request.user, 
                course=obj, 
                is_active=True
            ).first()
            return subscription.progress_percentage if subscription else 0.0
        return 0.0

    def get_is_subscribed(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return Subscription.objects.filter(
                user=request.user, 
                course=obj, 
                is_active=True
            ).exists()
        return False
    
    def get_module_count(self, obj):
        return obj.modules.count()


class CourseDetailSerializer(CourseSerializer):
    modules = serializers.SerializerMethodField()
    course_statistics = serializers.SerializerMethodField()
    
    class Meta(CourseSerializer.Meta):
        fields = CourseSerializer.Meta.fields + ['modules', 'course_statistics']
    
    def get_modules(self, obj):
        modules = obj.modules.all().order_by('order')
        request = self.context.get('request')
        
        subscription = None
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            subscription = Subscription.objects.filter(
                user=user,
                course=obj,
                is_active=True
            ).first()
        
        return ModuleSerializer(
            modules, 
            many=True, 
            context={'request': request, 'subscription': subscription}
        ).data
    
    def get_course_statistics(self, obj):
        active_subscriptions = obj.course_subscriptions.filter(is_active=True)
        total_subscribers = active_subscriptions.count()
        
        if total_subscribers > 0:
            completed_count = active_subscriptions.filter(is_completed=True).count()
            apprenants_count = active_subscriptions.filter(user__privilege='AP').count()
            
            return {
                'total_subscribers': total_subscribers,
                'apprenants_count': apprenants_count,
                'completed_count': completed_count,
                'completion_rate': round((completed_count / total_subscribers * 100), 2)
            }
        
        return {
            'total_subscribers': 0,
            'apprenants_count': 0,
            'completed_count': 0,
            'completion_rate': 0
        }


class CourseCreateSerializer(serializers.ModelSerializer):
    creator_username = serializers.CharField(source='creator.username', read_only=True)
    
    class Meta:
        model = Course
        fields = [
            'title_of_course', 'description', 'status', 'image',
            'estimated_duration', 'min_required_time', 'creator_username'
        ]
        read_only_fields = ['creator']
    
    def create(self, validated_data):
        request = self.context.get('request')
        
        if request and request.user.is_authenticated:
            validated_data['creator'] = request.user
        else:
            raise serializers.ValidationError("User must be authenticated to create a course")
        
        course = Course.objects.create(**validated_data)
        return course


# ==================== SUBSCRIPTION & PROGRESS SERIALIZERS ====================

class SubscriberSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    privilege_display = serializers.CharField(source='get_privilege_display', read_only=True)
    
    class Meta:
        model = CustomUser
        fields = ['id',  'first_name', 'last_name', 'full_name', 'email', 'privilege', 'privilege_display']


class SubscriptionSerializer(serializers.ModelSerializer):
    user = SubscriberSerializer(read_only=True)
    completed_contents_count = serializers.IntegerField(read_only=True)
    total_contents_count = serializers.IntegerField(read_only=True)
    can_complete_course = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Subscription
        fields = [
            'id', 'user', 'subscribed_at', 'is_active', 'progress_percentage', 
            'total_score', 'completed_contents_count', 'total_contents_count',
            'is_completed', 'completed_at', 'total_time_spent', 
            'average_time_per_session', 'can_complete_course'
        ]


# ==================== CONTENT CREATE SERIALIZERS ====================

class QCMContentCreateSerializer(serializers.ModelSerializer):
    questions = QCMQuestionCreateSerializer(many=True, required=True)
    passing_score = serializers.IntegerField(default=80)
    max_attempts = serializers.IntegerField(default=3)
    time_limit = serializers.IntegerField(default=0)
    title = serializers.CharField(required=True)
    caption = serializers.CharField(required=False, allow_blank=True)
    order = serializers.IntegerField(required=True)

    class Meta:
        model = CourseContent
        fields = [
            'title', 'caption', 'order', 'estimated_duration', 'min_required_time',
            'questions', 'passing_score', 'max_attempts', 'time_limit'
        ]
    
    def create(self, validated_data):
        questions_data = validated_data.pop('questions')
        passing_score = validated_data.pop('passing_score', 80)
        max_attempts = validated_data.pop('max_attempts', 3)
        time_limit = validated_data.pop('time_limit', 0)
        
        module = self.context.get('module')
        content_type = self.context.get('content_type')
        
        course_content = CourseContent.objects.create(
            module=module,
            content_type=content_type,
            **validated_data
        )
        
        qcm = QCM.objects.create(
            course_content=course_content,
            passing_score=passing_score,
            max_attempts=max_attempts,
            time_limit=time_limit
        )
        
        for question_data in questions_data:
            options_data = question_data.pop('options')
            question = QCMQuestion.objects.create(qcm=qcm, **question_data)
            
            for option_data in options_data:
                QCMOption.objects.create(question=question, **option_data)
        
        return course_content


class PDFContentCreateSerializer(serializers.ModelSerializer):
    pdf_file = serializers.FileField(required=True)
    title = serializers.CharField(required=True)
    
    class Meta:
        model = CourseContent
        fields = ['title', 'caption', 'order', 'estimated_duration', 'min_required_time', 'pdf_file']
    
    def create(self, validated_data):
        pdf_file = validated_data.pop('pdf_file')
        module = self.context.get('module')
        content_type = self.context.get('content_type')
        
        course_content = CourseContent.objects.create(
            module=module,
            content_type=content_type,
            **validated_data
        )
        
        PDFContent.objects.create(course_content=course_content, pdf_file=pdf_file)
        return course_content


class VideoContentCreateSerializer(serializers.ModelSerializer):
    video_file = serializers.FileField(required=True)
    title = serializers.CharField(required=True)
    
    class Meta:
        model = CourseContent
        fields = ['title', 'caption', 'order', 'estimated_duration', 'min_required_time', 'video_file']
    
    def create(self, validated_data):
        video_file = validated_data.pop('video_file')
        module = self.context.get('module')
        content_type = self.context.get('content_type')
        
        course_content = CourseContent.objects.create(
            module=module,
            content_type=content_type,
            **validated_data
        )
        
        VideoContent.objects.create(course_content=course_content, video_file=video_file)
        return course_content
    
class FavoriteCourseCreateSerializer(serializers.ModelSerializer):
    """Serializer for adding/removing favorites"""
    class Meta:
        model = FavoriteCourse
        fields = ['course']
    
    def validate_course(self, value):
        # Ensure course is active
        if value.status != 1:
            raise serializers.ValidationError("Can only favorite active courses")
        return value
    
    def create(self, validated_data):
        user = self.context['request'].user
        course = validated_data['course']
        
        # Check if already favorited
        favorite, created = FavoriteCourse.objects.get_or_create(
            user=user,
            course=course
        )
        
        if not created:
            raise serializers.ValidationError("Course is already in favorites")
        
        return favorite
    
from .models import Notification

class NotificationSerializer(serializers.ModelSerializer):
    time_ago = serializers.ReadOnlyField()
    related_course_title = serializers.CharField(source='related_course.title_of_course', read_only=True, allow_null=True)
    related_module_title = serializers.CharField(source='related_module.title', read_only=True, allow_null=True)
    related_content_title = serializers.CharField(source='related_content.title', read_only=True, allow_null=True)
    
    class Meta:
        model = Notification
        fields = [
            'id',
            'notification_type',
            'title',
            'message',
            'is_read',
            'created_at',
            'time_ago',
            'related_course',
            'related_course_title',
            'related_module',
            'related_module_title',
            'related_content',
            'related_content_title'
        ]
        read_only_fields = ['id', 'created_at', 'time_ago']

class NotificationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['is_read']

class FavoriteCourseSerializer(serializers.ModelSerializer):
    """Serializer for displaying favorite courses"""
    course_id = serializers.IntegerField(source='course.id', read_only=True)
    course_title = serializers.CharField(source='course.title_of_course', read_only=True)
    course_description = serializers.CharField(source='course.description', read_only=True)
    course_image = serializers.SerializerMethodField()
    course_department = serializers.CharField(source='course.department', read_only=True)
    course_department_display = serializers.CharField(source='course.get_department_display', read_only=True)
    course_status = serializers.IntegerField(source='course.status', read_only=True)
    course_status_display = serializers.CharField(source='course.get_status_display', read_only=True)
    
    # Creator information
    creator_username = serializers.CharField(source='course.creator.username', read_only=True)
    creator_full_name = serializers.CharField(source='course.creator.full_name', read_only=True)
    creator_first_name = serializers.CharField(source='course.creator.first_name', read_only=True)
    creator_last_name = serializers.CharField(source='course.creator.last_name', read_only=True)
    
    # Additional course info
    estimated_duration = serializers.IntegerField(source='course.estimated_duration', read_only=True)
    min_required_time = serializers.IntegerField(source='course.min_required_time', read_only=True)
    
    # User-specific info
    is_subscribed = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = FavoriteCourse
        fields = [
            'id', 'course_id', 'course_title', 'course_description', 'course_image',
            'course_department', 'course_department_display', 'course_status', 
            'course_status_display', 'creator_username', 'creator_full_name',
            'creator_first_name', 'creator_last_name', 'estimated_duration',
            'min_required_time', 'is_subscribed', 'progress_percentage', 'added_at'
        ]
    
    def get_course_image(self, obj):
        if obj.course.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.course.image.url)
            return obj.course.image.url
        return None
    
    def get_is_subscribed(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return Subscription.objects.filter(
                user=request.user,
                course=obj.course,
                is_active=True
            ).exists()
        return False
    
    def get_progress_percentage(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            subscription = Subscription.objects.filter(
                user=request.user,
                course=obj.course,
                is_active=True
            ).first()
            if subscription:
                return subscription.progress_percentage
        return 0.0
    
# ==================== TAG SERIALIZERS ====================

class TagSerializer(serializers.ModelSerializer):
    course_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Tag
        fields = ['id', 'name', 'description', 'color', 'course_count']
    
    def get_course_count(self, obj):
        return obj.coursetag_set.count()
