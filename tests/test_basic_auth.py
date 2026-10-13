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
    def test_token_rotation_accepts_only_currently_configured_tokens(self):
        configurations = [
            {"COMFYUI_TOKEN": "old-token", "COMFYUI_TOKEN2": "new-token"},
            {"COMFYUI_TOKEN2": "new-token"},
            {"COMFYUI_TOKEN": "", "COMFYUI_TOKEN2": "new-token"},
            {"COMFYUI_TOKEN": "old-token", "COMFYUI_TOKEN2": ""},
        ]
        for config in configurations:
            for with_basic_auth in (False, True):
                env = dict(config)
                if with_basic_auth:
                    env.update(COMFYUI_USERNAME="primary", COMFYUI_PASSWORD="primary-pass")
                with patch.dict(os.environ, env, clear=True):
                    middleware = BasicAuthMiddleware()
                cases = [
                    ("Bearer old-token", 200 if config.get("COMFYUI_TOKEN") else 401),
                    ("Bearer new-token", 200 if config.get("COMFYUI_TOKEN2") else 401),
                    ("Bearer wrong-token", 401),
                    ("Bearer ", 401),
                    (basic_header("primary", "primary-pass"), 401),
                    (None, 401),
                ]
                for header_name in ("Authorization", "X-App-Authorization"):
                    for header, expected_status in cases:
                        with self.subTest(config=config, basic=with_basic_auth,
                                          header_name=header_name, header=header):
                            headers = {} if header is None else {header_name: header}
                            request = SimpleNamespace(path="/", headers=CIMultiDict(headers))
                            response = asyncio.run(middleware.handle(request, ok_handler))
                            self.assertEqual(response.status, expected_status)
                            if expected_status == 401:
                                self.assertEqual(
                                    response.headers["WWW-Authenticate"],
                                    'Bearer realm="ComfyUI Server"',
                                )

    def test_token_auth_takes_precedence_over_basic_auth(self):
        env = {
            "COMFYUI_TOKEN": "test-token",
            "COMFYUI_USERNAME": "primary",
            "COMFYUI_PASSWORD": "primary-pass",
        }
        cases = [
            ("valid token", "Bearer test-token", 200),
            ("case insensitive scheme", "bearer test-token", 200),
            ("wrong token", "Bearer wrong-token", 401),
            ("case sensitive token", "Bearer TEST-TOKEN", 401),
            ("empty token", "Bearer ", 401),
            ("malformed header", "Bearer", 401),
            ("wrong scheme", "Token test-token", 401),
            ("basic credentials", basic_header("primary", "primary-pass"), 401),
            ("missing header", None, 401),
        ]
        with patch.dict(os.environ, env, clear=True):
            middleware = BasicAuthMiddleware()

        for name, header, expected_status in cases:
            with self.subTest(name=name):
                headers = {} if header is None else {"Authorization": header}
                request = SimpleNamespace(path="/", headers=CIMultiDict(headers))
                response = asyncio.run(middleware.handle(request, ok_handler))
                self.assertEqual(response.status, expected_status)
                if expected_status == 401:
                    self.assertEqual(
                        response.headers["WWW-Authenticate"],
                        'Bearer realm="ComfyUI Server"',
                    )

    def test_token_alone_enables_auth_and_preserves_header_priority(self):
        valid = "Bearer test-token"
        invalid = "Bearer wrong-token"
        cases = [
            ("standard header", {"Authorization": valid}, 200),
            ("app header", {"X-App-Authorization": valid}, 200),
            ("app header wins", {"X-App-Authorization": valid, "Authorization": invalid}, 200),
            ("invalid app token", {"X-App-Authorization": invalid, "Authorization": valid}, 401),
            ("empty app header", {"X-App-Authorization": "", "Authorization": valid}, 401),
            ("case insensitive header", {"x-app-authorization": valid}, 200),
            ("missing headers", {}, 401),
        ]
        with patch.dict(os.environ, {"COMFYUI_TOKEN": "test-token"}, clear=True):
            middleware = BasicAuthMiddleware()

        for name, headers, expected_status in cases:
            with self.subTest(name=name):
                request = SimpleNamespace(path="/", headers=CIMultiDict(headers))
                response = asyncio.run(middleware.handle(request, ok_handler))
                self.assertEqual(response.status, expected_status)

    def test_empty_token_falls_back_to_basic_auth(self):
        env = {
            "COMFYUI_TOKEN": "",
            "COMFYUI_TOKEN2": "",
            "COMFYUI_USERNAME": "primary",
            "COMFYUI_PASSWORD": "primary-pass",
        }
        with patch.dict(os.environ, env, clear=True):
            middleware = BasicAuthMiddleware()

        self.assertEqual(run_auth(middleware, "primary", "primary-pass").status, 200)
        self.assertEqual(run_auth(middleware, "primary", "wrong-pass").status, 401)

    def test_no_credentials_keeps_auth_disabled(self):
        for env in ({}, {"COMFYUI_TOKEN": "", "COMFYUI_TOKEN2": ""}):
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True):
                middleware = BasicAuthMiddleware()
                request = SimpleNamespace(path="/", headers={})
                response = asyncio.run(middleware.handle(request, ok_handler))
                self.assertEqual(response.status, 200)

    def test_token_auth_preserves_websocket_bypass(self):
        with patch.dict(os.environ, {"COMFYUI_TOKEN": "test-token"}, clear=True):
            middleware = BasicAuthMiddleware()
        request = SimpleNamespace(path="/ws", headers={})
        response = asyncio.run(middleware.handle(request, ok_handler))
        self.assertEqual(response.status, 200)

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
