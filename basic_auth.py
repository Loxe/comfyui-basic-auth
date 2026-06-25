import os
import base64
import hmac
from aiohttp import web

class BasicAuthMiddleware:
    def __init__(self):
        self.credentials = self._load_credentials()
        self.enabled = bool(self.credentials)

    def _load_credentials(self):
        credential_keys = [
            ('COMFYUI_USERNAME', 'COMFYUI_PASSWORD'),
            ('COMFYUI_USERNAME_2', 'COMFYUI_PASSWORD_2'),
            ('COMFYUI_USERNAME_3', 'COMFYUI_PASSWORD_3'),
        ]
        credentials = []

        for username_key, password_key in credential_keys:
            username = os.getenv(username_key, '')
            password = os.getenv(password_key, '')
            if username and password:
                credentials.append((username, password))

        return credentials

    def _credentials_match(self, username, password):
        return any(
            hmac.compare_digest(username, valid_username)
            and hmac.compare_digest(password, valid_password)
            for valid_username, valid_password in self.credentials
        )

    @web.middleware
    async def handle(self, request, handler):
        if not self.enabled:
            return await handler(request)

        # Skip auth for WebSocket connections
        if request.path == '/ws':
            return await handler(request)

        # Get Authorization header
        auth_header = request.headers.get('Authorization')

        if not auth_header:
            return web.Response(
                status=401,
                headers={'WWW-Authenticate': 'Basic realm="ComfyUI Server"'}
            )

        try:
            auth_type, auth_string = auth_header.split(' ', 1)
            if auth_type.lower() != 'basic':
                raise ValueError('Invalid auth type')

            decoded = base64.b64decode(auth_string).decode('utf-8')
            provided_username, provided_password = decoded.split(':', 1)

            if self._credentials_match(provided_username, provided_password):
                return await handler(request)

        except Exception:
            pass

        return web.Response(
            status=401,
            headers={'WWW-Authenticate': 'Basic realm="ComfyUI Server"'}
        )

class BasicAuthSetup:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "enabled": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("BASIC_AUTH",)
    FUNCTION = "setup_auth"
    CATEGORY = "utils"
    OUTPUT_NODE = True

    def setup_auth(self, enabled):
        return ({"enabled": enabled},)

NODE_CLASS_MAPPINGS = {
    "BasicAuthSetup": BasicAuthSetup
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "BasicAuthSetup": "Basic Auth Setup"
}

# Register the middleware
try:
    import server
except ModuleNotFoundError as e:
    if e.name != 'server':
        print(f"Failed to register basic auth middleware: {e}")
else:
    try:
        app = server.PromptServer.instance.app
        middleware = BasicAuthMiddleware()
        app.middlewares.insert(0, middleware.handle)
    except Exception as e:
        print(f"Failed to register basic auth middleware: {e}")
