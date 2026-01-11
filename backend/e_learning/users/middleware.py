# users/middleware.py

class DisableCSRFForAPIMiddleware:
    """
    Disable CSRF checks for all API endpoints
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Disable CSRF for all /api/ paths
        if request.path.startswith('/api/'):
            setattr(request, '_dont_enforce_csrf_checks', True)
        
        response = self.get_response(request)
        return response