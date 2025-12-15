#!/bin/bash

echo "=========================================="
echo "Fixing Circular Import Issue"
echo "=========================================="

# Fix the authentication.py file to remove circular import
echo -e "\n[1/2] Fixing users/authentication.py..."

cat > users/authentication.py << 'EOFPYTHON'
"""
Custom authentication classes for JWT tokens
"""
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import CSRFCheck
from rest_framework import exceptions
from django.conf import settings


class JWTCookieAuthentication(JWTAuthentication):
    """
    Custom JWT authentication class that reads the token from cookies
    instead of the Authorization header.
    """
    
    def authenticate(self, request):
        # First try to get token from cookie
        cookie_name = getattr(settings, 'JWT_AUTH_COOKIE', 'access_token')
        raw_token = request.COOKIES.get(cookie_name)
        
        # If no token in cookie, try the Authorization header (fallback)
        if raw_token is None:
            header = self.get_header(request)
            if header is None:
                return None
            raw_token = self.get_raw_token(header)
        
        if raw_token is None:
            return None
        
        # Validate the token
        validated_token = self.get_validated_token(raw_token)
        
        # Enforce CSRF check for cookie-based authentication
        if request.COOKIES.get(cookie_name):
            self.enforce_csrf(request)
        
        return self.get_user(validated_token), validated_token
    
    def enforce_csrf(self, request):
        """Enforce CSRF validation for cookie-based authentication"""
        # Only check CSRF for state-changing methods
        if request.method not in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
            check = CSRFCheck(request)
            reason = check.process_view(request, None, (), {})
            if reason:
                raise exceptions.PermissionDenied('CSRF Failed: %s' % reason)


class JWTRefreshCookieAuthentication(JWTAuthentication):
    """Authentication class for refresh tokens stored in cookies"""
    
    def authenticate(self, request):
        cookie_name = getattr(settings, 'JWT_REFRESH_COOKIE', 'refresh_token')
        raw_token = request.COOKIES.get(cookie_name)
        
        if raw_token is None:
            return None
        
        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token
EOFPYTHON

echo "✓ users/authentication.py fixed (removed circular import)"

# Copy to container if running
echo -e "\n[2/2] Updating Docker container..."

if docker-compose ps | grep -q "backend"; then
    # Copy the fixed file to container
    docker cp users/authentication.py $(docker-compose ps -q backend):/app/e_learning/users/authentication.py
    
    # Restart to reload
    echo "Restarting backend container..."
    docker-compose restart backend
    
    echo "✓ Container updated and restarted"
    
    # Show logs
    echo -e "\nWaiting for restart..."
    sleep 5
    echo -e "\nRecent logs:"
    docker-compose logs --tail=20 backend
else
    echo "⚠ Container not running. Start with: docker-compose up -d"
fi

echo -e "\n=========================================="
echo "✓ Fix Complete!"
echo "=========================================="