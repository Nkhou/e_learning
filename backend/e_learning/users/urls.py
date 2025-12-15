# users/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('health/', views.HealthCheckView.as_view(), name='health-check'),
    path('simple-health/', views.simple_health_check, name='simple-health-check'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('request-login-code/', views.RequestLoginCodeView.as_view(), name='request-login-code'),
    path('verify-login-code/', views.VerifyLoginCodeView.as_view(), name='verify-login-code'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('resend-login-code/', views.ResendLoginCodeView.as_view(), name='resend-login-code'),
    
    # User Management
    path('approve/', views.ApprovedView.as_view(), name='approve-user'),
    path('update/', views.UpdateUserView.as_view(), name='update-user'),
    path('search/', views.SearchUserView.as_view(), name='search-user'),
    path('delete-rejected/', views.DeleteRejectedUserView.as_view(), name='delete-rejected'),
    path('pending-approvals/', views.PendingApprovalsView.as_view(), name='pending-approvals'),
    path('toggle-status/', views.ToggleUserStatusView.as_view(), name='toggle-user-status'),
    path('create-admin/', views.CreateAdminView.as_view(), name='create-admin'),
    
    # Organization Views
    path('organization/dashboard/', views.OrganizationDashboardView.as_view(), name='org-dashboard'),
    path('organization/groups/', views.OrganizationGroupsView.as_view(), name='org-groups'),
    path('organization/groups/<int:group_id>/', views.OrganizationGroupDetailView.as_view(), name='org-group-detail'),
    path('organization/members/', views.OrganizationMembersView.as_view(), name='org-members'),
    path('organization/members/add-by-email/', views.AddMemberByEmailView.as_view(), name='add-member-by-email'),
    path('organization/members/<int:member_id>/', views.OrganizationMemberDetailView.as_view(), name='org-member-detail'),
    path('organization/formations/', views.OrganizationFormationsView.as_view(), name='org-formations'),
]