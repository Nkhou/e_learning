# cours/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'favorites', views.FavoriteCourseViewSet, basename='favorite')

urlpatterns = [
    # Authentication
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('check-auth/', views.CheckAuthentificationView.as_view(), name='check-auth'),
    
    # Course Management
    path('', views.CourseList.as_view(), name='course-list'),
    path('my-courses/', views.MyCourses.as_view(), name='my-courses'),
    path('<int:pk>/', views.CourseDetail.as_view(), name='course-detail'),
    path('all/', views.AllCoursesView.as_view(), name='all-courses'),
    path('filters/', views.CourseFiltersView.as_view(), name='course-filters'),
    path('conditional-display/', views.ConditionalCoursesDisplayView.as_view(), name='conditional-display'),
    path('create_qcm/', views.CreateQCMContentView.as_view(), name='create_qcm'),
    path('create_pdf/', views.CreatePDFContentView.as_view(), name='create_pdf'),
    path('create_video/', views.CreateVideoContentView.as_view(), name='create-video'),
    
    # Subscriptions
    path('<int:pk>/subscribe/', views.SubscribeToCourse.as_view(), name='subscribe'),
    path('<int:pk>/unsubscribe/', views.UnsubscribeFromCourse.as_view(), name='unsubscribe'),
    path('<int:pk>/check-subscription/', views.CheckSubscription.as_view(), name='check-subscription'),
    path('my-subscriptions/', views.MySubscriptions.as_view(), name='my-subscriptions'),
    
    # Content Completion
    path('contents/<int:content_id>/mark-completed/', views.MarkContentCompletedView.as_view(), name='mark-content-completed'),
    path('<int:course_id>/mark-video-completed/', views.MarkVideoCompletedView.as_view(), name='mark-video-completed'),
    path('<int:course_id>/mark-pdf-completed/', views.MarkPDFCompletedView.as_view(), name='mark-pdf-completed'),
    path('contents/<int:content_id>/check-completion/', views.CheckContentCompletionView.as_view(), name='check-completion'),
    path('<int:course_id>/completed-contents/', views.GetCompletedContentsView.as_view(), name='completed-contents'),
    
    # QCM
    path('<int:pk>/submit-qcm/', views.SubmitQCM.as_view(), name='submit-qcm'),
    
    # Time Tracking
    path('<int:pk>/record-time/', views.TimeTrackingRecordView.as_view(), name='record-time'),
    
    # Notifications
    path('notifications/', views.NotificationListView.as_view(), name='notification-list'),
    path('notifications/<int:notification_id>/mark-read/', views.NotificationMarkAsReadView.as_view(), name='mark-notification-read'),
    path('notifications/mark-all-read/', views.NotificationMarkAllAsReadView.as_view(), name='mark-all-notifications-read'),
    path('notifications/unread-count/', views.NotificationUnreadCountView.as_view(), name='unread-notification-count'),
    
    # Router URLs
    path('', include(router.urls)),
]