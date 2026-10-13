# Nginx 双认证代理测试

浏览器使用原生 Basic Auth 登录框，Nginx 将请求转发成：

```http
X-App-Authorization: Basic <浏览器提交的凭据>
Authorization: Bearer <配置的上游 Token>
```

没有 Basic Auth 请求头或格式不符合要求时，Nginx 返回 `401` 和
`WWW-Authenticate`，触发浏览器登录弹窗。Nginx 不维护账号密码；
凭据由已经支持 `X-App-Authorization` 的 ComfyUI 插件校验。
上游网关需要允许这个自定义请求头传到 ComfyUI。

## 启动

需要 Docker 和 Docker Compose。先进入本目录：

```bash
cd deploy/nginx
cp .env.example .env
```

编辑 `.env` 中的 `UPSTREAM_HOST` 和 `UPSTREAM_TOKEN`：

- `UPSTREAM_HOST`：真实上游域名，不带协议、端口或路径。
- `UPSTREAM_SCHEME` / `UPSTREAM_PORT`：默认 `https` / `443`。
- `UPSTREAM_TOKEN`：仅填写 Token，不带 `Bearer ` 前缀。
- `PORT`：浏览器访问端口，默认 `8080`。

然后执行：

```bash
docker compose config --quiet
docker compose run --rm nginx nginx -t
docker compose up -d
```

打开 <http://localhost:8080>，输入 ComfyUI 环境变量中配置的账号密码。
Token 由 Nginx 附加，不需要在浏览器输入。

默认只绑定本机 `127.0.0.1`，适合本地 HTTP 测试。浏览器位于另一台机器时，
可通过 SSH 端口转发访问；对外部署应配置 HTTPS 入口。

如果上游服务运行在宿主机，使用 `UPSTREAM_HOST=host.docker.internal`，
并填写对应协议和端口，不要使用容器内的 `localhost`。
本示例面向独立域名根路径，不包含上游子路径重写。

## 验证与排查

无凭据请求应返回 `401`，且包含 `WWW-Authenticate: Basic`：

```bash
curl -i http://localhost:8080/
```

输入账号后，curl 会提示输入密码；将 `your_username` 替换成真实用户名：

```bash
curl -i --user your_username http://localhost:8080/
```

账号密码和 Token 正确时，应收到 ComfyUI 页面。密码错误时，插件返回 `401`。
Token 错误时，响应由上游网关决定；反复弹出登录框也可能是上游 Token 错误。
浏览器开发者工具中仍会显示 `Authorization: Basic ...`，因为头转换发生在 Nginx。

配置包含 WebSocket Upgrade 转发。当前插件对 `/ws` 跳过账号密码校验，
此代理在该路径也只检查 Basic 请求头格式，因此它不是额外的独立密码验证层。

查看状态和日志：

```bash
docker compose ps
docker compose logs --tail=100 nginx
```

修改 `.env` 或模板后重新创建容器，让环境变量重新写入配置：

```bash
docker compose up -d --force-recreate
```

停止测试：

```bash
docker compose down
```

`.env` 已被本目录的 `.gitignore` 排除。不要分享包含真实 Token 的
`docker compose config` 或 `nginx -T` 输出；检查 Compose 时使用 `--quiet`。

## 配置依据

- [Nginx 官方镜像的环境变量模板](https://hub.docker.com/_/nginx)
- [Nginx 请求头设置](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_set_header)
- [Nginx WebSocket 转发](https://nginx.org/en/docs/http/websocket.html)
