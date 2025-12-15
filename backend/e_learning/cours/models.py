import math
import os
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from users.models import CustomUser, UserThemeStats

COURSE_STATUS_CHOICES = [
    (0, 'Brouillon'),
    (1, 'Actif'),
    (2, 'Archivé'),
]

QUESTION_TYPE_CHOICES = [
    ('single', 'Single Choice'),
    ('multiple', 'Multiple Choice'),
]


class Course(models.Model):

    title_of_course = models.CharField(max_length=100, blank=False, null=False)
    description = models.TextField(blank=True, null=True)
    # department = models.CharField(max_length=20, choices=DEPARTMENT_CHOICES, default='F')
    image = models.ImageField(
        upload_to='course_images/',
        null=True, 
        blank=True,
        max_length=100  
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_courses'
    )    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.IntegerField(choices=COURSE_STATUS_CHOICES, default=0)
    subscribers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        through='Subscription', 
        related_name='subscribed_courses',
        blank=True
    )
    # NEW FIELDS - Added for time tracking
    estimated_duration = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Total course duration in minutes"
    )
    min_required_time = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Minimum time required to complete in minutes"
    )

    def __str__(self):
        creator_name = self.creator.get_full_name() or self.creator.username
        return f"{self.title_of_course} by {creator_name}"

    # NEW METHODS FOR MODULE COUNT, TIME, AND SUBSCRIBERS
    def get_active_module_count(self):
        """Get count of active modules in this course"""
        return self.modules.filter(status=1).count()

    def get_total_time_required_hours(self):
        """Get total time required in hours"""
        minutes = self.get_total_time_required_minutes()
        return round(minutes / 60, 1) if minutes > 0 else 0

    def get_subscriber_count(self):
        """Get count of active subscribers for this course"""
        return self.course_subscriptions.filter(is_active=True).count()



    def calculate_estimated_duration(self):
        """Calculate total duration from ACTIVE modules and contents only"""
        total_duration = 0
        
        # Filter only active modules (status = 1)
        active_modules = self.modules.filter(status=1)
        
        for module in active_modules:
            # Use the module's calculate_estimated_duration method
            total_duration += module.calculate_estimated_duration()
        
        return total_duration

    def calculate_min_required_time(self):
        """Calculate minimum required time from ACTIVE modules and contents only"""
        total_min_time = 0
        
        # Filter only active modules (status = 1)
        active_modules = self.modules.filter(status=1)
        
        for module in active_modules:
            # Filter only active contents within the module
            active_contents = module.contents.filter(status=1)
            
            for content in active_contents:
                if content.min_required_time:
                    total_min_time += content.min_required_time
                else:
                    # Fallback to estimated_duration if min_required_time not set
                    if content.estimated_duration:
                        total_min_time += content.estimated_duration
                    else:
                        # Default fallback based on content type
                        content_type_name = content.content_type.name.lower()
                        if content_type_name == 'video':
                            total_min_time += 10  # Default 10 minutes for video
                        elif content_type_name == 'pdf':
                            total_min_time += 15  # Default 15 minutes for PDF
                        elif content_type_name == 'qcm':
                            total_min_time += 5   # Default 5 minutes for QCM
        
        return total_min_time
    
class Enrollment(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)
    progress = models.IntegerField(default=0)  # 0-100 percentage
    
    class Meta:
        unique_together = ['user', 'course']
    
    def __str__(self):
        return f"{self.user.username} - {self.course.title_of_course}"

class ContentType(models.Model):
    name = models.CharField(max_length=50)  # 'video', 'qcm', or 'pdf'
    # NEW FIELD - Added for better display names
    display_name = models.CharField(max_length=50, blank=True)
    
    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = self.name
        super().save(*args, **kwargs)

class Module(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules')
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    status = models.IntegerField(choices=COURSE_STATUS_CHOICES, default=0)
    order = models.PositiveIntegerField(default=0)
    # NEW FIELDS - Added for time tracking
    estimated_duration = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Module total duration in minutes"
    )
    min_required_time = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Minimum time required for module in minutes"
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.course.title_of_course} - {self.title}"

    # NEW PROPERTY - Added for React compatibility
    @property
    def status_display(self):
        return dict(COURSE_STATUS_CHOICES).get(self.status, 'Unknown')

    def calculate_estimated_duration(self):
        """Calculate total duration from ACTIVE contents only"""
        # Safety check: can't calculate for unsaved instances
        if not self.pk:
            return 0
            
        total_duration = 0
        
        # Filter only active contents (status = 1)
        active_contents = self.contents.filter(status=1)
        
        for content in active_contents:
            if content.estimated_duration:
                total_duration += content.estimated_duration
            else:
                # Fallback to default estimates based on content type
                content_type_name = content.content_type.name.lower()
                if content_type_name == 'video':
                    # Check if video has duration, otherwise default to 10 min
                    if hasattr(content, 'video_content') and content.video_content and content.video_content.duration:
                        total_duration += math.ceil(content.video_content.duration / 60)  # Convert seconds to minutes
                    else:
                        total_duration += 10
                elif content_type_name == 'pdf':
                    total_duration += 15
                elif content_type_name == 'qcm':
                    total_duration += 5
                else:
                    total_duration += 10  # Default for other content types
        
        return total_duration

    def calculate_min_required_time(self):
        """Calculate minimum required time from ACTIVE contents only"""
        # Safety check: can't calculate for unsaved instances
        if not self.pk:
            return 0
            
        total_min_time = 0
        
        # Filter only active contents (status = 1)
        active_contents = self.contents.filter(status=1)
        
        for content in active_contents:
            if content.min_required_time:
                total_min_time += content.min_required_time
            else:
                # Fallback to estimated_duration if min_required_time not set
                if content.estimated_duration:
                    total_min_time += content.estimated_duration
                else:
                    # Default fallback
                    content_type_name = content.content_type.name.lower()
                    if content_type_name == 'video':
                        total_min_time += 10
                    elif content_type_name == 'pdf':
                        total_min_time += 15
                    elif content_type_name == 'qcm':
                        total_min_time += 5
        
        return total_min_time

    def save(self, *args, **kwargs):
        # Only calculate durations if the module already exists (has an ID)
        if self.pk is not None:
            # Auto-calculate durations only for existing modules
            if not self.estimated_duration:
                self.estimated_duration = self.calculate_estimated_duration()
            if not self.min_required_time:
                self.min_required_time = self.calculate_min_required_time()
        else:
            # For new modules, set default values
            if not self.estimated_duration:
                self.estimated_duration = 0
            if not self.min_required_time:
                self.min_required_time = 0
        
        super().save(*args, **kwargs)

class CourseContent(models.Model):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='contents', null=True, blank=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    caption = models.CharField(max_length=200, blank=True)
    status = models.IntegerField(choices=COURSE_STATUS_CHOICES, default=1)
    order = models.PositiveIntegerField(default=0)
    
    # NEW FIELDS - Added for time tracking
    estimated_duration = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Content duration in minutes"
    )
    min_required_time = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Minimum time required for content in minutes"
    )
    
    # NEW FIELDS - Added for statistics
    views_count = models.PositiveIntegerField(default=0, verbose_name="Nombre de vues")
    completed_count = models.PositiveIntegerField(default=0, verbose_name="Nombre de complétions")
    average_rating = models.FloatField(default=0, verbose_name="Note moyenne")
    completion_rate = models.FloatField(default=0, verbose_name="Taux de complétion")
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.content_type}: {self.title}"

    # NEW PROPERTIES - Added for React compatibility
    @property
    def content_type_name(self):
        return self.content_type.display_name or self.content_type.name

    @property
    def status_display(self):
        return dict(COURSE_STATUS_CHOICES).get(self.status, 'Unknown')

    def update_completion_rate(self):
        """Update completion rate based on subscriptions"""
        total_subscriptions = Subscription.objects.filter(
            course=self.module.course,
            is_active=True
        ).count()
        
        if total_subscriptions > 0:
            completed_count = self.completed_by_users.filter(
                subscription__is_active=True
            ).count()
            self.completion_rate = (completed_count / total_subscriptions) * 100
            self.save()

class ContentProgress(models.Model):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='content_progress')
    content = models.ForeignKey(CourseContent, on_delete=models.CASCADE)
    completed = models.BooleanField(default=False)
    viewed_at = models.DateTimeField(auto_now_add=True)
    time_spent = models.IntegerField(default=0)  # in seconds
    
    class Meta:
        unique_together = ['enrollment', 'content']
    
    def __str__(self):
        return f"{self.enrollment.user.username} - {self.content.title}"

class QCMQuestion(models.Model):
    """Model for multiple questions in a QCM"""
    qcm = models.ForeignKey('QCM', on_delete=models.CASCADE, related_name='questions')
    question = models.TextField()
    question_type = models.CharField(max_length=10, choices=QUESTION_TYPE_CHOICES, default='single')
    points = models.IntegerField(default=1)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.qcm.course_content.title} - Q{self.order}: {self.question[:50]}"

# Modifiez le modèle QCM existant
class QCM(models.Model):
    course_content = models.OneToOneField(CourseContent, on_delete=models.CASCADE, related_name='qcm')
    title = models.CharField(max_length=200, blank=True)  # Add this field
    passing_score = models.IntegerField(default=80) 
    max_attempts = models.IntegerField(default=3)  
    time_limit = models.IntegerField(default=0)  # in minutes

    def __str__(self):
        return f"QCM: {self.course_content.title}"
    
    def save(self, *args, **kwargs):
        # Auto-populate title from course_content if not provided
        if not self.title and self.course_content:
            self.title = self.course_content.title
        super().save(*args, **kwargs)
    
    @property
    def total_points(self):
        """Calculate total points from all questions"""
        return sum(question.points for question in self.questions.all())
    
    @property
    def questions_count(self):
        """Get number of questions"""
        return self.questions.count()
class QCMOption(models.Model):
    # Link to question (not directly to QCM)
    question = models.ForeignKey(QCMQuestion, on_delete=models.CASCADE, related_name='options')
    
    text = models.CharField(max_length=200)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.text} ({'Correct' if self.is_correct else 'Incorrect'})"
class VideoContent(models.Model):
    course_content = models.OneToOneField(CourseContent, on_delete=models.CASCADE, related_name='video_content')
    video_file = models.FileField(upload_to='videos/%y')
    # NEW FIELD - Added for video duration
    duration = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Video duration in seconds"
    )
    
    def __str__(self):
        return self.course_content.title

class PDFContent(models.Model):
    course_content = models.OneToOneField(CourseContent, on_delete=models.CASCADE, related_name='pdf_content')
    pdf_file = models.FileField(upload_to='pdfs/')
    # NEW FIELDS - Added for PDF metadata
    page_count = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Number of pages in PDF"
    )
    estimated_reading_time = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Estimated reading time in minutes"
    )
    
    def __str__(self):
        return self.course_content.title

    def calculate_reading_time(self):
        """Calculate reading time based on page count (2 minutes per page)"""
        return self.page_count * 2

    def save(self, *args, **kwargs):
        # Auto-calculate reading time if not set
        if not self.estimated_reading_time and self.page_count > 0:
            self.estimated_reading_time = self.calculate_reading_time()
        super().save(*args, **kwargs)

class Subscription(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='course_subscriptions')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='course_subscriptions')
    subscribed_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    total_score = models.IntegerField(default=0) 
    completed_contents = models.ManyToManyField('CourseContent', blank=True, related_name='completed_by_users') 
    completed_qcms = models.ManyToManyField(QCM, through='QCMCompletion', blank=True)
    locked_contents = models.ManyToManyField('CourseContent', blank=True, related_name='locked_for_users')
    
    progress_percentage = models.FloatField(default=0.0)
    # NEW FIELDS - Added for time tracking and completion
    total_time_spent = models.IntegerField(default=0, help_text="Total time spent on course in seconds")
    average_time_per_session = models.IntegerField(default=0, help_text="Average session time in seconds")
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['user', 'course']

    def __str__(self):
        return f"{self.user.username} - {self.course.title_of_course}"

    # NEW PROPERTIES - Added for React compatibility
    @property
    def completed_contents_count(self):
        """Count only active completed contents (status=1)"""
        return self.completed_contents.filter(status=1).count()

    @property
    def total_contents_count(self):
        """Count only active course contents (status=1)"""
        return CourseContent.objects.filter(
            module__course=self.course, 
            status=1
        ).count()

    @property
    def can_complete_course(self):
        """Check if user meets time requirements to complete course"""
        if not self.course.min_required_time:
            return True
        return (self.total_time_spent / 60) >= self.course.min_required_time

    @property
    def completion_requirements(self):
        """Get completion requirements status"""
        required_time = (self.course.min_required_time or 0) * 60  # Convert to seconds
        return {
            'time_met': self.total_time_spent >= required_time,
            'required_time': required_time,
            'actual_time': self.total_time_spent,
            'progress_percentage': self.progress_percentage
        }

    def update_total_score(self):
        """Update total score from completed QCMs"""
        completed_qcms = QCMCompletion.objects.filter(subscription=self, is_passed=True)
        self.total_score = sum(completion.points_earned for completion in completed_qcms)
        self.save()
        return self.total_score

    def update_progress(self):
        """Update progress percentage considering only active content"""
        total_contents = self.total_contents_count
        if total_contents > 0:
            self.progress_percentage = (self.completed_contents_count / total_contents) * 100
            self.save()

    def can_access_content(self, content):
        """Check if user can access specific content based on prerequisites"""
        # If content is not active (status != 1), user cannot access it
        if content.status != 1:
            return False
            
        module_contents = CourseContent.objects.filter(
            module=content.module, 
            status=1
        ).order_by('order')
        
        content_position = None
        for i, module_content in enumerate(module_contents):
            if module_content.id == content.id:
                content_position = i
                break
        
        # If content not found in active contents or is first content
        if content_position is None:
            return False
        if content_position == 0:
            return True
        
        # Check previous content completion
        previous_content = module_contents[content_position - 1]
        
        if hasattr(previous_content, 'qcm') and previous_content.qcm:
            qcm = previous_content.qcm
            completion = QCMCompletion.objects.filter(
                subscription=self, 
                qcm=qcm, 
                is_passed=True
            ).exists()
            return completion
        
        return self.completed_contents.filter(id=previous_content.id).exists()

    # In your models.py, add these methods to Subscription model
    
    def calculate_progress_percentage(self):
        """Calculate progress based on completed vs total active contents"""
        try:
            course = self.course
            
            # Get active modules and contents
            active_modules = Module.objects.filter(course=course, status=1)
            active_contents = CourseContent.objects.filter(
                module__in=active_modules,
                status=1
            )
            
            # Get completed active contents
            completed_active_contents = self.completed_contents.filter(
                id__in=active_contents.values_list('id', flat=True)
            )
            
            total_active_contents = active_contents.count()
            completed_count = completed_active_contents.count()
            
            if total_active_contents > 0:
                progress = (completed_count / total_active_contents) * 100
                # Update the field
                self.progress_percentage = round(progress, 2)
                self.save(update_fields=['progress_percentage'])
                return self.progress_percentage
            
            self.progress_percentage = 0.0
            self.save(update_fields=['progress_percentage'])
            return 0.0
            
        except Exception as e:
            print(f"Error calculating progress: {str(e)}")
            return 0.0
    
    def update_completion_status(self):
        """Update the is_completed field based on progress and time requirements"""
        try:
            # Calculate progress first
            self.calculate_progress_percentage()
            
            # Check if all content is completed and time requirements are met
            course = self.course
            
            # Get active modules and contents
            active_modules = Module.objects.filter(course=course, status=1)
            active_contents = CourseContent.objects.filter(
                module__in=active_modules,
                status=1
            )
            
            # Get completed active contents
            completed_active_contents = self.completed_contents.filter(
                id__in=active_contents.values_list('id', flat=True)
            )
            
            # Check completion criteria
            all_content_completed = completed_active_contents.count() >= active_contents.count()
            
            # For now, set completion based on content only
            # You can add time requirements later
            self.is_completed = all_content_completed and self.progress_percentage >= 100
            self.save(update_fields=['is_completed'])
            
        except Exception as e:
            print(f"Error updating completion status: {str(e)}")
    
    def check_time_requirements(self):
        """Check if user meets time requirements for course completion"""
        if not self.course.min_required_time:
            return True  # No time requirement
        
        # Convert required time to seconds and check
        required_seconds = self.course.min_required_time * 60
        return self.total_time_spent >= required_seconds
    
    def mark_content_completed(self, content):
        """Mark a content as completed and update progress (only if content is active)"""
        if content.status != 1:
            return False
            
        if not self.completed_contents.filter(id=content.id).exists():
            self.completed_contents.add(content)
            self.update_completion_status()
            return True
        return False
    
    def mark_content_incomplete(self, content):
        """Mark a content as incomplete and update progress"""
        if self.completed_contents.filter(id=content.id).exists():
            self.completed_contents.remove(content)
            self.update_completion_status()
            return True
        return False
    
    def get_completion_requirements(self):
        """Get detailed completion requirements status considering only active content"""
        total_contents = CourseContent.objects.filter(
            module__course=self.course, 
            status=1
        ).count()
        completed_contents = self.completed_contents.filter(status=1).count()
        
        required_time_seconds = (self.course.min_required_time or 0) * 60
        
        return {
            'contents_met': completed_contents >= total_contents,
            'time_met': self.total_time_spent >= required_time_seconds,
            'required_contents': total_contents,
            'completed_contents': completed_contents,
            'required_time_seconds': required_time_seconds,
            'actual_time_seconds': self.total_time_spent,
            'progress_percentage': self.progress_percentage,
            'can_complete': completed_contents >= total_contents and self.total_time_spent >= required_time_seconds
        }
    
    def get_active_completed_contents(self):
        """Get only active completed contents (status=1)"""
        return self.completed_contents.filter(status=1)
    
    def get_active_locked_contents(self):
        """Get only active locked contents (status=1)"""
        return self.locked_contents.filter(status=1)

class QCMCompletion(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE)
    qcm = models.ForeignKey(QCM, on_delete=models.CASCADE)
    best_score = models.FloatField(default=0)
    points_earned = models.IntegerField(default=0)
    is_passed = models.BooleanField(default=False)
    attempts_count = models.IntegerField(default=0)
    last_attempt = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['subscription', 'qcm']

class QCMAttempt(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='qcm_attempts')
    qcm = models.ForeignKey(QCM, on_delete=models.CASCADE, related_name='attempts')
    selected_options = models.ManyToManyField(QCMOption)
    score = models.FloatField(default=0)  # Percentage score
    points_earned = models.IntegerField(default=0)  # Actual points earned
    is_passed = models.BooleanField(default=False)
    attempt_number = models.IntegerField(default=1)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    time_taken = models.IntegerField(default=0)  # Time taken in seconds

    class Meta:
        unique_together = ['user', 'qcm', 'attempt_number']
    
    def calculate_score(self):
        correct_options = self.qcm.options.filter(is_correct=True)
        selected_correct = self.selected_options.filter(is_correct=True).count()
        total_correct = correct_options.count()
        
        if total_correct > 0:
            self.score = (selected_correct / total_correct) * 100
            self.is_passed = self.score >= self.qcm.passing_score
            self.points_earned = self.qcm.points if self.is_passed else 0
        else:
            self.score = 0
            self.is_passed = False
            self.points_earned = 0
        
        self.save()
        return self.score


# Ajoutez ces modèles à votre fichier models.py

class Tag(models.Model):
    """Tags/Thèmes pour les formations"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    color = models.CharField(max_length=7, default='#3498db')  # Code couleur hex
    
    def __str__(self):
        return self.name

class CourseTag(models.Model):
    """Relation Many-to-Many entre cours et tags"""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='tags')
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)
    weight = models.FloatField(default=1.0)  # Poids du tag pour ce cours
    
    class Meta:
        unique_together = ('course', 'tag')

class DetailedTimeTracking(models.Model):
    """Tracking détaillé du temps par contenu"""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    content = models.ForeignKey(CourseContent, on_delete=models.CASCADE)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    duration_seconds = models.IntegerField()  # Durée en secondes
    progress_percentage = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'content']),
            models.Index(fields=['start_time']),
        ]



class TimeTracking(models.Model):
    """Suivi du temps global par cours"""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='time_tracking')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='time_tracking')
    module = models.ForeignKey(Module, on_delete=models.SET_NULL, null=True, blank=True)
    content = models.ForeignKey(CourseContent, on_delete=models.SET_NULL, null=True, blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    duration = models.IntegerField(default=0, help_text="Durée en secondes")
    session_type = models.CharField(max_length=50, choices=[
        ('content', 'Contenu'),
        ('quiz', 'Quiz'),
        ('reading', 'Lecture'),
        ('video', 'Vidéo'),
        ('practice', 'Pratique')
    ], default='content')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.course.title_of_course} - {self.duration}s"

    class Meta:
        db_table = 'time_tracking'
        ordering = ['-start_time']

class DetailedTimeTracking(models.Model):
    """Suivi détaillé du temps par contenu"""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='detailed_time_tracking')
    content = models.ForeignKey(CourseContent, on_delete=models.CASCADE, related_name='detailed_time_tracking')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    duration = models.IntegerField(default=0, help_text="Durée en secondes")
    progress_before = models.FloatField(default=0, help_text="Progression avant la session")
    progress_after = models.FloatField(default=0, help_text="Progression après la session")
    session_type = models.CharField(max_length=50, choices=[
        ('view', 'Visualisation'),
        ('read', 'Lecture'),
        ('practice', 'Pratique'),
        ('review', 'Révision')
    ], default='view')
    device_info = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.content.title} - {self.duration}s"

    class Meta:
        db_table = 'detailed_time_tracking'
        ordering = ['-start_time']
class FavoriteCourse(models.Model):
    """Model for users to mark courses as favorites"""
    user = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE, 
        related_name='favorite_courses'
    )
    course = models.ForeignKey(
        Course, 
        on_delete=models.CASCADE, 
        related_name='favorited_by'
    )
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'course']
        ordering = ['-added_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.course.title_of_course}"
    
class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('course_activated', 'Course Activated'),
        ('module_activated', 'Module Activated'),
        ('content_activated', 'Content Activated'),
        ('qcm_result', 'QCM Result'),
        ('system', 'System Announcement'),
        ('message', 'New Message'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    related_course = models.ForeignKey(Course, on_delete=models.CASCADE, null=True, blank=True)
    related_module = models.ForeignKey(Module, on_delete=models.CASCADE, null=True, blank=True)
    related_content = models.ForeignKey(CourseContent, on_delete=models.CASCADE, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.title}"

    @property
    def time_ago(self):
        """Get human-readable time difference"""
        now = timezone.now()
        diff = now - self.created_at
        
        if diff.days > 0:
            return f"Il y a {diff.days} jour{'s' if diff.days > 1 else ''}"
        elif diff.seconds >= 3600:
            hours = diff.seconds // 3600
            return f"Il y a {hours} heure{'s' if hours > 1 else ''}"
        elif diff.seconds >= 60:
            minutes = diff.seconds // 60
            return f"Il y a {minutes} minute{'s' if minutes > 1 else ''}"
        else:
            return "À l'instant"