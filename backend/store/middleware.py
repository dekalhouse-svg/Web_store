from django.conf import settings


class CORSMiddleware:
    ALLOWED_HEADERS = "Content-Type, Authorization, X-Comment-Token, X-Visitor-ID, X-Visitor-Token"
    ALLOWED_METHODS = "GET, POST, PUT, PATCH, DELETE, OPTIONS"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.http import HttpResponse
        origin = request.headers.get("Origin", "").rstrip("/")
        allowed = getattr(settings, "CORS_ALLOWED_ORIGINS", set())
        if request.method == "OPTIONS":
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)
        if origin and origin in allowed:
            response["Access-Control-Allow-Origin"] = origin
            response["Vary"] = "Origin"
            response["Access-Control-Allow-Headers"] = self.ALLOWED_HEADERS
            response["Access-Control-Allow-Methods"] = self.ALLOWED_METHODS
            response["Access-Control-Max-Age"] = "86400"
        elif request.method == "OPTIONS":
            return HttpResponse(status=403)
        response["X-Content-Type-Options"] = "nosniff"
        response["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response["X-Frame-Options"] = "DENY"
        return response
