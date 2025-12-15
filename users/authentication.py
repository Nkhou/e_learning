from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import CSRFCheck
from rest_framework import exceptions
from django.conf import settings

class JWTCookieAuthentication(JWTAuthentication):
    def authenticate(self, request):
        cookie_name = getattr(settings, 'JWT_AUTH_COOKIE', 'access_token')
        raw_token = request.COOKIES.get(cookie_name)
        
        if raw_token is None:
            header = self.get_header(request)
            if header is None:
                return None
            raw_token = self.get_raw_token(header)
        
        if raw_token is None:
            return None
        
        validated_token = self.get_validated_token(raw_token)
        
        if request.COOKIES.get(cookie_name):
            self.enforce_csrf(request)
        
        return self.get_user(validated_token), validated_token
    
    def enforce_csrf(self, request):
        if request.method not in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
            check = CSRFCheck(request)
            reason = check.process_view(request, None, (), {})
            if reason:
                raise exceptions.PermissionDenied('CSRF Failed: %s' % reason)
