"""OpenAPI description of the JWT header/cookie authentication."""
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class JWTHeaderOrCookieScheme(OpenApiAuthenticationExtension):
    target_class = "apps.core.authentication.JWTHeaderOrCookieAuthentication"
    name = ["jwtBearer", "jwtCookie"]

    def get_security_definition(self, auto_schema):
        return [
            {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
            {"type": "apiKey", "in": "cookie", "name": "ws_access"},
        ]
