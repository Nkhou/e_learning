from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    
    if response is not None:
        custom_response = {
            "error": str(response.data.get("detail", "An error occurred")),
            "status_code": response.status_code
        }
        if isinstance(response.data, dict) and "detail" not in response.data:
            custom_response["detail"] = response.data
        response.data = custom_response
    
    return response
