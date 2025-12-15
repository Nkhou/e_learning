from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from datetime import timedelta

# ==================== USER MODEL ====================

PRIVILEGE_CHOICES = [
    ('A', 'Admin'),
    ('AP', 'Apprenant'),
    ('F', 'Formateur'),
    ('O', 'Organisation'),
]

USER_STATUS_CHOICES = [
    (1, 'Actif'),
    (2, 'Suspendu'),
]

APPROVAL_STATUS_CHOICES = [
    ('pending', 'En attente'),
    ('approved', 'Approuvé'),
    ('rejected', 'Rejeté'),
]

class CustomUser(AbstractUser):
    privilege = models.CharField(max_length=10, choices=PRIVILEGE_CHOICES, default='AP')
    status = models.IntegerField(choices=USER_STATUS_CHOICES, default=1)
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspension_reason = models.TextField(blank=True, null=True)
    accept_conditions = models.BooleanField(default=False)
    approval_status = models.CharField(
        max_length=20, 
        choices=APPROVAL_STATUS_CHOICES, 
        default='approved',
        help_text="Statut d'approbation pour formateurs et organisations"
    )
    approval_requested_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL,
        null=True, 
        blank=True,
        related_name='approved_users',
        help_text="Admin qui a approuvé cet utilisateur"
    )
    rejection_reason = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.username

    def full_name(self):
        """Return full name for React component compatibility"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username
    
    def get_consecutive_reading_days(self, days_to_check=30):
        """Calculer les jours consécutifs de lecture"""
        try:
            from django.db.models import Count
            from cours.models import DetailedTimeTracking
            
            today = timezone.now().date()
            start_date = today - timedelta(days=days_to_check)
            
            # Récupérer les jours avec activité de lecture
            active_days = DetailedTimeTracking.objects.filter(
                user=self,
                start_time__date__gte=start_date
            ).values('start_time__date').annotate(
                count=Count('id')
            ).order_by('start_time__date')
            
            if not active_days:
                return 0
            
            # Convertir en dates et trier
            dates = [item['start_time__date'] for item in active_days]
            dates.sort()
            
            # Vérifier la séquence consécutive en partant d'aujourd'hui
            consecutive = 0
            current_date = today
            
            # Vérifier si aujourd'hui a de l'activité
            if today in dates:
                consecutive += 1
                current_date = today - timedelta(days=1)
                
                # Continuer à vérifier les jours précédents
                while current_date in dates:
                    consecutive += 1
                    current_date = current_date - timedelta(days=1)
            
            return consecutive
        except ImportError:
            return 0
    
    def update_strength_levels(self):
        """Mettre à jour les niveaux de force par thème"""
        try:
            from django.db.models import OuterRef
            from cours.models import Subscription, CourseTag, QCMCompletion, CourseContent, DetailedTimeTracking
            
            # Récupérer tous les tags des cours suivis
            user_subscriptions = Subscription.objects.filter(
                user=self, 
                is_active=True
            ).values_list('course_id', flat=True)
            
            course_tags = CourseTag.objects.filter(
                course_id__in=user_subscriptions
            ).select_related('tag')
            
            for course_tag in course_tags:
                tag = course_tag.tag
                
                # Calculer les statistiques pour ce tag
                contents_with_tag = CourseContent.objects.filter(
                    module__course__tags__tag=tag,
                    module__course__course_subscriptions__user=self
                ).distinct()
                
                # Calculer le temps passé
                time_spent = DetailedTimeTracking.objects.filter(
                    user=self,
                    content__in=contents_with_tag
                ).aggregate(total=models.Sum('duration'))['total'] or 0
                
                # Calculer le score moyen
                qcm_scores = QCMCompletion.objects.filter(
                    subscription__user=self,
                    qcm__course_content__in=contents_with_tag
                ).aggregate(avg_score=models.Avg('best_score'))['avg_score'] or 0
                
                # Calculer le nombre de contenus complétés
                completed = contents_with_tag.filter(
                    subscription__user=self,
                    subscription__completed_contents=OuterRef('pk')
                ).count()
                
                # Déterminer le niveau de force
                strength = 'faible'
                if completed > 0:
                    completion_rate = (completed / contents_with_tag.count()) * 100
                    if completion_rate >= 80 and qcm_scores >= 80:
                        strength = 'fort'
                    elif completion_rate >= 50 and qcm_scores >= 60:
                        strength = 'moyen'
                
                # Mettre à jour ou créer UserThemeStats
                UserThemeStats.objects.update_or_create(
                    user=self,
                    tag=tag,
                    defaults={
                        'total_time_spent': time_spent,
                        'average_score': qcm_scores,
                        'completed_contents': completed,
                        'total_contents': contents_with_tag.count(),
                        'strength_level': strength
                    }
                )
        except ImportError:
            pass  # Les modèles ne sont pas encore disponibles

    @property
    def is_active_user(self):
        return self.status == 1

    @property
    def can_access_platform(self):
        """Check if user can access the platform based on privilege and approval"""
        if self.privilege == 'AP':  # Apprenants have direct access
            return self.status == 1
        elif self.privilege in ['F', 'O']:  # Formateurs and Organisations need approval
            return self.status == 1 and self.approval_status == 'approved'
        elif self.privilege == 'A':  # Admins always have access if active
            return self.status == 1
        return False

    @property
    def needs_approval(self):
        """Check if user needs approval"""
        return self.privilege in ['F', 'O'] and self.approval_status == 'pending'

    def request_approval(self):
        """Request approval for formateur or organisation"""
        if self.privilege in ['F', 'O']:
            self.approval_status = 'pending'
            self.approval_requested_at = timezone.now()
            self.save()

    def approve(self, approved_by_user):
        """Approve user access"""
        self.approval_status = 'approved'
        self.approved_at = timezone.now()
        self.approved_by = approved_by_user
        self.save()

    def reject(self, reason=""):
        """Reject user access"""
        self.approval_status = 'rejected'
        self.rejection_reason = reason
        self.save()

    def suspend_user(self, reason=""):
        self.status = 2
        self.suspended_at = timezone.now()
        self.suspension_reason = reason
        self.save()

    def activate_user(self):
        self.status = 1
        self.suspended_at = None
        self.suspension_reason = None
        self.save()

    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'


# ==================== AUTHENTICATION & VERIFICATION ====================

VERIFICATION_TYPE_CHOICES = [
    ('email', 'Email Verification'),
    ('password_reset', 'Password Reset'),
    ('2fa', 'Two Factor Authentication'),
    ('approval_confirmation', 'Approval Confirmation'),
]

class VerificationCode(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='verification_codes')
    code = models.CharField(max_length=10)
    type = models.CharField(max_length=50, choices=VERIFICATION_TYPE_CHOICES)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.type} - {self.code}"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_used(self):
        return self.used_at is not None

    def mark_as_used(self):
        self.used_at = timezone.now()
        self.save()

    class Meta:
        db_table = 'verification_codes'
        ordering = ['-created_at']


# ==================== ORGANIZATION MODELS EXTENSIONS ====================

class Organization(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='owned_organizations')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    organization_type = models.CharField(max_length=100, blank=True, null=True, help_text="Type d'organisation (école, entreprise, etc.)")
    contact_email = models.EmailField(blank=True, null=True)
    contact_phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Nouveaux champs pour les statistiques
    total_members = models.IntegerField(default=0)
    total_groups = models.IntegerField(default=0)
    total_formations = models.IntegerField(default=0)
    
    def __str__(self):
        return self.name

    class Meta:
        db_table = 'organizations'
        ordering = ['-created_at']
    
    def update_statistics(self):
        """Met à jour les statistiques de l'organisation"""
        self.total_members = self.get_total_members()
        self.total_groups = self.groups.count()
        self.total_formations = self.get_total_formations()
        self.save()
    
    def get_total_members(self):
        """Retourne le nombre total de membres uniques dans l'organisation"""
        from django.db.models import Count
        return Member.objects.filter(
            group__org=self
        ).values('user').annotate(total=Count('user')).count()
    
    def get_total_formations(self):
        """Retourne le nombre total de formations liées à l'organisation"""
        try:
            from cours.models import Course
            return Course.objects.filter(status=1).count()
        except ImportError:
            return 0
    
    def get_active_members_count(self):
        """Nombre de membres actifs (connectés dans les 4 derniers jours)"""
        four_days_ago = timezone.now() - timedelta(days=4)
        user_ids = Member.objects.filter(
            group__org=self
        ).values_list('user_id', flat=True).distinct()
        
        return CustomUser.objects.filter(
            id__in=user_ids,
            last_login__gte=four_days_ago
        ).count()
    
    def get_completion_rate(self):
        """Taux d'achèvement moyen des formations par les membres"""
        try:
            from cours.models import Subscription
            from django.db.models import Avg
            
            user_ids = Member.objects.filter(
                group__org=self
            ).values_list('user_id', flat=True).distinct()
            
            avg_progress = Subscription.objects.filter(
                user_id__in=user_ids,
                is_active=True
            ).aggregate(avg=Avg('progress_percentage'))['avg'] or 0
            
            return round(avg_progress, 2)
        except ImportError:
            return 0.0

class Group(models.Model):
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='groups')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Nouveaux champs
    status = models.CharField(max_length=20, choices=[
        ('active', 'Actif'),
        ('inactive', 'Inactif'),
        ('archived', 'Archivé')
    ], default='active')
    
    def __str__(self):
        return f"{self.org.name} - {self.name}"

    @property
    def member_count(self):
        return self.members.count()
    
    @property
    def active_member_count(self):
        """Nombre de membres actifs dans le groupe"""
        four_days_ago = timezone.now() - timedelta(days=4)
        user_ids = self.members.values_list('user_id', flat=True)
        
        return CustomUser.objects.filter(
            id__in=user_ids,
            last_login__gte=four_days_ago
        ).count()
    
    @property
    def is_active_group(self):
        """Détermine si le groupe est actif (au moins un membre actif)"""
        return self.active_member_count > 0
    
    @property
    def formation_count(self):
        """Nombre de formations associées au groupe"""
        try:
            from cours.models import GroupFormation
            return GroupFormation.objects.filter(group=self).count()
        except ImportError:
            return 0

    class Meta:
        db_table = 'groups'
        ordering = ['-created_at']


class Member(models.Model):
    MEMBER_ROLE_CHOICES = [
        ('member', 'Membre'),
        ('moderator', 'Modérateur'),
        ('admin', 'Administrateur'),
    ]
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='memberships')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='members')
    role = models.CharField(max_length=50, choices=MEMBER_ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)
    
    # Nouveaux champs
    status = models.CharField(max_length=20, choices=[
        ('active', 'Actif'),
        ('inactive', 'Inactif'),
        ('suspended', 'Suspendu'),
        ('pending', 'En attente')
    ], default='active')
    
    last_active_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.group.name}"
    
    def is_active(self):
        """Vérifie si le membre est actif"""
        if not self.last_active_at:
            return False
        days_inactive = (timezone.now() - self.last_active_at).days
        return days_inactive <= 4 and self.status == 'active'
    
    def update_last_active(self):
        """Met à jour la dernière activité"""
        self.last_active_at = timezone.now()
        self.save(update_fields=['last_active_at'])

    class Meta:
        db_table = 'members'
        unique_together = ['user', 'group']
        ordering = ['-joined_at']

# ==================== NEW MODELS FOR STATISTICS ====================

class UserThemeStats(models.Model):
    """Statistiques de l'utilisateur par thème/tag"""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='theme_stats')
    tag = models.ForeignKey('cours.Tag', on_delete=models.CASCADE)
    total_time_spent = models.IntegerField(default=0)  # en secondes
    average_score = models.FloatField(default=0)
    completed_contents = models.IntegerField(default=0)
    total_contents = models.IntegerField(default=0)
    strength_level = models.CharField(max_length=20, choices=[
        ('faible', 'Faible'),
        ('moyen', 'Moyen'),
        ('fort', 'Fort'),
    ], default='faible')
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_theme_stats'
        unique_together = ['user', 'tag']
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.tag.name}"

class OrganizationDailyStats(models.Model):
    """Statistiques journalières pour les organisations"""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='daily_stats')
    date = models.DateField()
    active_members = models.IntegerField(default=0)
    inactive_members = models.IntegerField(default=0)
    total_learning_time = models.IntegerField(default=0)  # en secondes
    courses_started = models.IntegerField(default=0)
    courses_completed = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'organization_daily_stats'
        unique_together = ['organization', 'date']
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.organization.name} - {self.date}"