import asyncio
import base64
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from aiohttp import web
from multidict import CIMultiDict

from basic_auth import BasicAuthMiddleware


def basic_header(username, password):
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


async def ok_handler(request):
    return web.Response(status=200)


def run_auth(middleware, username, password):
    request = SimpleNamespace(
        path="/",
        headers={"Authorization": basic_header(username, password)},
    )
    return asyncio.run(middleware.handle(request, ok_handler))


class BasicAuthMiddlewareTest(unittest.TestCase):
    def test_authorization_header_selection(self):
        env = {
            "COMFYUI_USERNAME": "primary",
            "COMFYUI_PASSWORD": "primary-pass",
        }
        valid = basic_header("primary", "primary-pass")
        invalid = basic_header("primary", "wrong-pass")
        cases = [
            ("standard header", {"Authorization": valid}, 200),
            ("app header", {"X-App-Authorization": valid}, 200),
            ("app header wins", {"X-App-Authorization": valid, "Authorization": invalid}, 200),
            ("invalid app credentials", {"X-App-Authorization": invalid, "Authorization": valid}, 401),
            ("malformed app header", {"X-App-Authorization": "invalid", "Authorization": valid}, 401),
            ("empty app header", {"X-App-Authorization": "", "Authorization": valid}, 401),
            ("case insensitive", {"x-app-authorization": valid}, 200),
            ("missing headers", {}, 401),
        ]

        with patch.dict(os.environ, env, clear=True):
            middleware = BasicAuthMiddleware()

        for name, headers, expected_status in cases:
            with self.subTest(name=name):
                request = SimpleNamespace(path="/", headers=CIMultiDict(headers))
                response = asyncio.run(middleware.handle(request, ok_handler))
                self.assertEqual(response.status, expected_status)
                if expected_status == 401:
                    self.assertEqual(
                        response.headers["WWW-Authenticate"],
                        'Basic realm="ComfyUI Server"',
                    )

    def test_accepts_any_configured_credential_pair(self):
        env = {
            "COMFYUI_USERNAME": "primary",
            "COMFYUI_PASSWORD": "primary-pass",
            "COMFYUI_USERNAME_2": "backup",
            "COMFYUI_PASSWORD_2": "backup-pass",
            "COMFYUI_USERNAME_3": "rotate",
            "COMFYUI_PASSWORD_3": "rotate-pass",
        }

        with patch.dict(os.environ, env, clear=True):
            middleware = BasicAuthMiddleware()

        self.assertEqual(run_auth(middleware, "primary", "primary-pass").status, 200)
        self.assertEqual(run_auth(middleware, "backup", "backup-pass").status, 200)
        self.assertEqual(run_auth(middleware, "rotate", "rotate-pass").status, 200)

    def test_ignores_incomplete_credential_pairs(self):
        env = {
            "COMFYUI_USERNAME_2": "backup",
            "COMFYUI_USERNAME_3": "rotate",
            "COMFYUI_PASSWORD_3": "rotate-pass",
        }

        with patch.dict(os.environ, env, clear=True):
            middleware = BasicAuthMiddleware()

        self.assertEqual(run_auth(middleware, "backup", "").status, 401)
        self.assertEqual(run_auth(middleware, "rotate", "rotate-pass").status, 200)


if __name__ == "__main__":
    unittest.main()
