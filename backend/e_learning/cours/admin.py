from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    Course,
    Enrollment,
    ContentType,
    Module,
    CourseContent,
    ContentProgress,
    QCMQuestion,
    QCM,
    QCMOption,
    VideoContent,
    PDFContent,
    Subscription,
    QCMCompletion,
    QCMAttempt,
    Tag,
    CourseTag,
    DetailedTimeTracking,
    TimeTracking,
    FavoriteCourse,
    Notification,
)


# ==================== INLINE ADMINS ====================

class ModuleInline(admin.TabularInline):
    model = Module
    extra = 0
    fields = ('title', 'status', 'order', 'estimated_duration', 'min_required_time')
    readonly_fields = ('estimated_duration', 'min_required_time')
    ordering = ['order']


class CourseContentInline(admin.TabularInline):
    model = CourseContent
    extra = 0
    fields = ('title', 'content_type', 'status', 'order', 'estimated_duration', 'min_required_time')
    readonly_fields = ('views_count', 'completed_count')
    ordering = ['order']


class QCMQuestionInline(admin.TabularInline):
    model = QCMQuestion
    extra = 1
    fields = ('question', 'question_type', 'points', 'order')
    ordering = ['order']


class QCMOptionInline(admin.TabularInline):
    model = QCMOption
    extra = 2
    fields = ('text', 'is_correct', 'order')
    ordering = ['order']


class CourseTagInline(admin.TabularInline):
    model = CourseTag
    extra = 1
    fields = ('tag', 'weight')


# ==================== MAIN ADMIN CLASSES ====================

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = (
        'title_of_course', 'creator', 'status', 'get_subscriber_count',
        'get_active_module_count', 'estimated_duration_display', 'created_at'
    )
    list_filter = ('status', 'created_at', 'creator')
    search_fields = ('title_of_course', 'description', 'creator__username', 'creator__email')
    readonly_fields = (
        'created_at', 'updated_at', 'estimated_duration', 'min_required_time',
        'get_subscriber_count', 'get_active_module_count'
    )
    inlines = [CourseTagInline, ModuleInline]
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Informations de base', {
            'fields': ('title_of_course', 'description', 'image', 'creator', 'status')
        }),
        ('Statistiques', {
            'fields': ('get_subscriber_count', 'get_active_module_count'),
            'classes': ('collapse',)
        }),
        ('Durées', {
            'fields': ('estimated_duration', 'min_required_time'),
            'classes': ('collapse',)
        }),
        ('Dates', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def estimated_duration_display(self, obj):
        hours = obj.get_total_time_required_hours()
        return f"{hours}h" if hours > 0 else "Non défini"
    estimated_duration_display.short_description = 'Durée estimée'
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Recalculate durations after save
        obj.estimated_duration = obj.calculate_estimated_duration()
        obj.min_required_time = obj.calculate_min_required_time()
        obj.save()


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'course', 'status', 'order', 
        'estimated_duration', 'min_required_time', 'created_at'
    )
    list_filter = ('status', 'course', 'created_at')
    search_fields = ('title', 'description', 'course__title_of_course')
    readonly_fields = ('created_at', 'updated_at', 'estimated_duration', 'min_required_time')
    inlines = [CourseContentInline]
    ordering = ['course', 'order']
    
    fieldsets = (
        ('Informations de base', {
            'fields': ('course', 'title', 'description', 'status', 'order')
        }),
        ('Durées calculées', {
            'fields': ('estimated_duration', 'min_required_time'),
            'classes': ('collapse',)
        }),
        ('Dates', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(CourseContent)
class CourseContentAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'content_type', 'module', 'status', 'order',
        'views_count', 'completed_count', 'completion_rate_display'
    )
    list_filter = ('status', 'content_type', 'module__course', 'created_at')
    search_fields = ('title', 'caption', 'module__title', 'module__course__title_of_course')
    readonly_fields = (
        'created_at', 'updated_at', 'views_count', 'completed_count',
        'average_rating', 'completion_rate'
    )
    ordering = ['module', 'order']
    
    fieldsets = (
        ('Informations de base', {
            'fields': ('module', 'content_type', 'title', 'caption', 'status', 'order')
        }),
        ('Durées', {
            'fields': ('estimated_duration', 'min_required_time')
        }),
        ('Statistiques', {
            'fields': ('views_count', 'completed_count', 'average_rating', 'completion_rate'),
            'classes': ('collapse',)
        }),
        ('Dates', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def completion_rate_display(self, obj):
        return f"{obj.completion_rate:.1f}%"
    completion_rate_display.short_description = 'Taux de complétion'


@admin.register(ContentType)
class ContentTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'display_name')
    search_fields = ('name', 'display_name')


@admin.register(QCM)
class QCMAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'course_content', 'passing_score', 
        'questions_count', 'total_points', 'max_attempts', 'time_limit'
    )
    list_filter = ('passing_score', 'max_attempts')
    search_fields = ('title', 'course_content__title')
    readonly_fields = ('questions_count', 'total_points')
    inlines = [QCMQuestionInline]
    
    fieldsets = (
        ('Informations de base', {
            'fields': ('course_content', 'title')
        }),
        ('Paramètres', {
            'fields': ('passing_score', 'max_attempts', 'time_limit')
        }),
        ('Statistiques', {
            'fields': ('questions_count', 'total_points'),
            'classes': ('collapse',)
        }),
    )


@admin.register(QCMQuestion)
class QCMQuestionAdmin(admin.ModelAdmin):
    list_display = ('question_short', 'qcm', 'question_type', 'points', 'order')
    list_filter = ('question_type', 'qcm')
    search_fields = ('question', 'qcm__title')
    inlines = [QCMOptionInline]
    ordering = ['qcm', 'order']
    
    def question_short(self, obj):
        return obj.question[:50] + '...' if len(obj.question) > 50 else obj.question
    question_short.short_description = 'Question'


@admin.register(QCMOption)
class QCMOptionAdmin(admin.ModelAdmin):
    list_display = ('text', 'question', 'is_correct', 'order')
    list_filter = ('is_correct', 'question__qcm')
    search_fields = ('text', 'question__question')
    ordering = ['question', 'order']


@admin.register(VideoContent)
class VideoContentAdmin(admin.ModelAdmin):
    list_display = ('course_content', 'duration_display', 'video_file')
    search_fields = ('course_content__title',)
    readonly_fields = ('duration',)
    
    def duration_display(self, obj):
        minutes = obj.duration // 60
        seconds = obj.duration % 60
        return f"{minutes}:{seconds:02d}"
    duration_display.short_description = 'Durée'


@admin.register(PDFContent)
class PDFContentAdmin(admin.ModelAdmin):
    list_display = ('course_content', 'page_count', 'estimated_reading_time', 'pdf_file')
    search_fields = ('course_content__title',)
    readonly_fields = ('estimated_reading_time',)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'course', 'is_active', 'progress_percentage',
        'completed_contents_count', 'is_completed', 'subscribed_at'
    )
    list_filter = ('is_active', 'is_completed', 'subscribed_at')
    search_fields = ('user__username', 'user__email', 'course__title_of_course')
    readonly_fields = (
        'subscribed_at', 'completed_at', 'progress_percentage',
        'total_time_spent', 'completed_contents_count', 'total_contents_count'
    )
    filter_horizontal = ('completed_contents', 'locked_contents')
    date_hierarchy = 'subscribed_at'
    
    fieldsets = (
        ('Informations de base', {
            'fields': ('user', 'course', 'is_active', 'subscribed_at')
        }),
        ('Progression', {
            'fields': (
                'progress_percentage', 'completed_contents_count', 
                'total_contents_count', 'is_completed', 'completed_at'
            )
        }),
        ('Temps', {
            'fields': ('total_time_spent', 'average_time_per_session'),
            'classes': ('collapse',)
        }),
        ('Contenus', {
            'fields': ('completed_contents', 'locked_contents'),
            'classes': ('collapse',)
        }),
    )


@admin.register(QCMCompletion)
class QCMCompletionAdmin(admin.ModelAdmin):
    list_display = (
        'subscription', 'qcm', 'best_score', 'points_earned',
        'is_passed', 'attempts_count', 'last_attempt'
    )
    list_filter = ('is_passed', 'last_attempt')
    search_fields = (
        'subscription__user__username', 'qcm__title',
        'qcm__course_content__title'
    )
    readonly_fields = ('last_attempt',)
    date_hierarchy = 'last_attempt'


@admin.register(QCMAttempt)
class QCMAttemptAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'qcm', 'attempt_number', 'score',
        'is_passed', 'time_taken_display', 'started_at'
    )
    list_filter = ('is_passed', 'started_at', 'qcm')
    search_fields = ('user__username', 'qcm__title')
    readonly_fields = ('started_at', 'completed_at', 'score', 'points_earned', 'is_passed')
    filter_horizontal = ('selected_options',)
    date_hierarchy = 'started_at'
    
    def time_taken_display(self, obj):
        minutes = obj.time_taken // 60
        seconds = obj.time_taken % 60
        return f"{minutes}:{seconds:02d}"
    time_taken_display.short_description = 'Temps pris'


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'progress', 'completed', 'enrolled_at')
    list_filter = ('completed', 'enrolled_at')
    search_fields = ('user__username', 'course__title_of_course')
    readonly_fields = ('enrolled_at',)
    date_hierarchy = 'enrolled_at'


@admin.register(ContentProgress)
class ContentProgressAdmin(admin.ModelAdmin):
    list_display = ('enrollment', 'content', 'completed', 'time_spent_display', 'viewed_at')
    list_filter = ('completed', 'viewed_at')
    search_fields = (
        'enrollment__user__username', 'content__title',
        'enrollment__course__title_of_course'
    )
    readonly_fields = ('viewed_at',)
    date_hierarchy = 'viewed_at'
    
    def time_spent_display(self, obj):
        minutes = obj.time_spent // 60
        seconds = obj.time_spent % 60
        return f"{minutes}:{seconds:02d}"
    time_spent_display.short_description = 'Temps passé'


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'color_preview', 'description')
    search_fields = ('name', 'description')
    
    def color_preview(self, obj):
        return format_html(
            '<span style="background-color: {}; padding: 5px 10px; border-radius: 3px; color: white;">{}</span>',
            obj.color,
            obj.color
        )
    color_preview.short_description = 'Couleur'


@admin.register(CourseTag)
class CourseTagAdmin(admin.ModelAdmin):
    list_display = ('course', 'tag', 'weight')
    list_filter = ('tag', 'course')
    search_fields = ('course__title_of_course', 'tag__name')


@admin.register(TimeTracking)
class TimeTrackingAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'course', 'module', 'content',
        'session_type', 'duration_display', 'start_time'
    )
    list_filter = ('session_type', 'start_time', 'course')
    search_fields = ('user__username', 'course__title_of_course')
    readonly_fields = ('created_at', 'updated_at', 'start_time', 'end_time')
    date_hierarchy = 'start_time'
    
    def duration_display(self, obj):
        minutes = obj.duration // 60
        seconds = obj.duration % 60
        return f"{minutes}:{seconds:02d}"
    duration_display.short_description = 'Durée'


@admin.register(DetailedTimeTracking)
class DetailedTimeTrackingAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'content', 'session_type', 'duration_display',
        'progress_before', 'progress_after', 'start_time'
    )
    list_filter = ('session_type', 'start_time', 'content__module__course')
    search_fields = ('user__username', 'content__title')
    readonly_fields = ('created_at', 'start_time', 'end_time')
    date_hierarchy = 'start_time'
    
    def duration_display(self, obj):
        minutes = obj.duration // 60
        seconds = obj.duration % 60
        return f"{minutes}:{seconds:02d}"
    duration_display.short_description = 'Durée'


@admin.register(FavoriteCourse)
class FavoriteCourseAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'added_at')
    list_filter = ('added_at',)
    search_fields = ('user__username', 'course__title_of_course')
    readonly_fields = ('added_at',)
    date_hierarchy = 'added_at'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'notification_type', 'title', 'is_read',
        'time_ago', 'created_at'
    )
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('user__username', 'title', 'message')
    readonly_fields = ('created_at', 'time_ago')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Informations de base', {
            'fields': ('user', 'notification_type', 'title', 'message', 'is_read')
        }),
        ('Liens', {
            'fields': ('related_course', 'related_module', 'related_content'),
            'classes': ('collapse',)
        }),
        ('Dates', {
            'fields': ('created_at', 'time_ago'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['mark_as_read', 'mark_as_unread']
    
    def mark_as_read(self, request, queryset):
        updated = queryset.update(is_read=True)
        self.message_user(request, f'{updated} notification(s) marquée(s) comme lue(s).')
    mark_as_read.short_description = 'Marquer comme lu'
    
    def mark_as_unread(self, request, queryset):
        updated = queryset.update(is_read=False)
        self.message_user(request, f'{updated} notification(s) marquée(s) comme non lue(s).')
    mark_as_unread.short_description = 'Marquer comme non lu'