# ComfyUI Basic Auth

A simple authentication middleware for ComfyUI that adds basic HTTP authentication to protect your ComfyUI instance.

## Features

- Basic HTTP Authentication protection for ComfyUI
- Optional Bearer token authentication via `COMFYUI_TOKEN` and `COMFYUI_TOKEN2` for rotation, usable alongside Basic Auth
- Supports up to 3 username/password pairs for credential rotation
- Lightweight and easy to set up
- Compatible with all ComfyUI versions

## Installation

1. Navigate to your ComfyUI custom nodes folder:
```bash
cd ComfyUI/custom_nodes/
```

2. Clone this repository:
```bash
git clone https://github.com/fofr/comfyui-basic-auth
```

## Configuration

To use token authentication, set a non-empty `COMFYUI_TOKEN` or `COMFYUI_TOKEN2`:

```bash
export COMFYUI_TOKEN=your_token
export COMFYUI_TOKEN2=your_next_token
```

Either configured token is accepted, and either variable can be used on its own.
Empty values are ignored. Basic Auth and Bearer authentication can be configured
at the same time. The request header's scheme selects the validation method:
`Bearer <token>` is checked against the configured tokens, while
`Basic <base64(username:password)>` is checked against the configured
username/password pairs. Scheme names are case-insensitive; token values are
case-sensitive. When authentication is enabled, missing or invalid credentials,
unsupported schemes, and schemes without configured credentials return HTTP 401.
Failed validation does not fall back to the other method.

To rotate tokens, add the new token in the other variable and restart ComfyUI.
Once clients have switched to the new token, remove the old token and restart
again. Both tokens are accepted during the transition.

Set environment variables for your username and password:

```bash
export COMFYUI_USERNAME=your_username
export COMFYUI_PASSWORD=your_password
```

You can configure up to 3 username/password pairs. Any configured pair will be accepted:

```bash
export COMFYUI_USERNAME=primary_username
export COMFYUI_PASSWORD=primary_password

export COMFYUI_USERNAME_2=backup_username
export COMFYUI_PASSWORD_2=backup_password

export COMFYUI_USERNAME_3=rotation_username
export COMFYUI_PASSWORD_3=rotation_password
```

Only complete pairs are used. For example, `COMFYUI_USERNAME_2` is ignored unless
`COMFYUI_PASSWORD_2` is also set.

Restart ComfyUI for the changes to take effect.

## Usage

The authentication will automatically be active once the node is installed and configured.
With token authentication enabled, send `Authorization: Bearer <token>`:

```bash
curl -H "Authorization: Bearer $COMFYUI_TOKEN" http://localhost:8188/
```

You can also use `X-App-Authorization: Bearer <token>`. For both authentication
modes, `X-App-Authorization` takes priority; `Authorization` is used only when
`X-App-Authorization` is absent.

With Basic Auth enabled, your browser will prompt for a configured username and
password. You can also send Basic Auth explicitly, even when tokens are configured:

```bash
curl -u "$COMFYUI_USERNAME:$COMFYUI_PASSWORD" http://localhost:8188/
```

If neither a non-empty token nor a complete username/password pair is
configured, authentication is disabled. The existing `/ws` authentication bypass
applies in both modes.

## Security Note

Basic authentication sends credentials encoded (not encrypted) in the HTTP header. While this provides a basic level of protection, it's recommended to:

- Use strong passwords
- Access ComfyUI through HTTPS if exposed to the internet
- Consider additional security measures for production environments
