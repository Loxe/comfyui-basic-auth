import os
import base64
import hmac
import logging
import time
import uuid
from aiohttp import web

logger = logging.getLogger(__name__)

class BasicAuthMiddleware:
    def __init__(self):
        self.tokens = [
            token for token in (
                os.getenv('COMFYUI_TOKEN', ''),
                os.getenv('COMFYUI_TOKEN2', ''),
            ) if token
        ]
        self.credentials = self._load_credentials()
        self.enabled = bool(self.tokens or self.credentials)

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
        request_id = uuid.uuid4().hex
        started = time.perf_counter()

        def log(message, *args):
            logger.info('[basic-auth request_id=%s] ' + message, request_id, *args)

        async def call_handler():
            log('handler=enter')
            try:
                response = await handler(request)
            except Exception as error:
                # Exception messages can contain credentials or request data.
                log('handler=error error=%s elapsed_ms=%.2f',
                    type(error).__name__, (time.perf_counter() - started) * 1000)
                raise
            log('handler=exit status=%s elapsed_ms=%.2f',
                response.status, (time.perf_counter() - started) * 1000)
            return response

        # Use path only: query parameters may contain tokens. %r escapes newlines.
        log('request=enter method=%s path=%r', getattr(request, 'method', '?'), request.path)
        if not self.enabled:
            log('auth=bypass reason=disabled')
            return await call_handler()

        # Skip auth for WebSocket connections
        if request.path == '/ws':
            log('auth=bypass reason=websocket')
            return await call_handler()

        challenge = ', '.join(
            f'{scheme} realm="ComfyUI Server"'
            for scheme, configured in (('Basic', self.credentials), ('Bearer', self.tokens))
            if configured
        )

        # Prefer the app-specific header; fall back only when it is absent.
        auth_header = request.headers.get('X-App-Authorization')
        header_source = 'X-App-Authorization'
        if auth_header is None:
            auth_header = request.headers.get('Authorization')
            header_source = 'Authorization' if auth_header is not None else 'none'
        log('auth=select_header header=%s', header_source)

        if not auth_header:
            log('auth=denied reason=missing_header status=401')
            return web.Response(
                status=401,
                headers={'WWW-Authenticate': challenge}
            )

        reason = 'malformed_header'
        try:
            auth_type, auth_string = auth_header.split(' ', 1)
            auth_type = auth_type.lower()

            if auth_type == 'bearer':
                log('auth=validate scheme=bearer')
                authenticated = any(
                    hmac.compare_digest(auth_string.encode('utf-8'), token.encode('utf-8'))
                    for token in self.tokens
                )
            elif auth_type == 'basic':
                log('auth=validate scheme=basic')
                decoded = base64.b64decode(auth_string).decode('utf-8')
                provided_username, provided_password = decoded.split(':', 1)
                authenticated = self._credentials_match(provided_username, provided_password)
            else:
                reason = 'unsupported_scheme'
                raise ValueError('Invalid auth type')

            reason = 'invalid_credentials'
            if authenticated:
                log('auth=accepted')
                reason = 'handler_error'
                return await call_handler()

        except Exception as error:
            log('auth=error reason=%s error=%s', reason, type(error).__name__)

        log('auth=denied reason=%s status=401', reason)
        return web.Response(
            status=401,
            headers={'WWW-Authenticate': challenge}
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
        logger.info('[basic-auth] middleware=registered position=0 enabled=%s '
                    'bearer_tokens=%d basic_accounts=%d',
                    middleware.enabled, len(middleware.tokens), len(middleware.credentials))
    except Exception as e:
        print(f"Failed to register basic auth middleware: {e}")
