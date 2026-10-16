#!/usr/bin/env python3
"""通过 Cloudflare 域名做端到端功能测试。"""
import httpx

PUBLIC = "https://xiaoaiyun.top"
ADMIN = "https://admin.xiaoaiyun.top"
CF_IP = "104.21.39.197"


def client(base, host):
    """强制解析到 Cloudflare（绕过本机 fake-ip 代理）"""
    transport = httpx.HTTPTransport(local_address=None)
    return httpx.Client(
        base_url=base,
        timeout=40,
        follow_redirects=True,
        verify=True,
        headers={"Host": host},
        transport=transport,
    )


def main():
    # 直接把域名映射到 CF IP
    import socket
    real_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host, *args, **kwargs):
        if host in ("xiaoaiyun.top", "www.xiaoaiyun.top", "admin.xiaoaiyun.top"):
            host = CF_IP
        return real_getaddrinfo(host, *args, **kwargs)

    socket.getaddrinfo = fake_getaddrinfo

    print("=== 1. 主站（公开端） ===")
    with httpx.Client(base_url=PUBLIC, timeout=40, follow_redirects=True) as c:
        r = c.get("/")
        print(f"  首页            HTTP {r.status_code}  {len(r.text)} 字节")
        for path in ("/api/health", "/api/system/info", "/api/dorms", "/api/reports/today",
                     "/api/stats/overview", "/api/settings/public"):
            try:
                res = c.get(path)
                print(f"  {path:<26} HTTP {res.status_code}")
            except Exception as exc:
                print(f"  {path:<26} 异常 {type(exc).__name__}")

        print()
        print("  管理接口应该被 404 挡住（公开端口不开管理接口）：")
        for path in ("/api/logs", "/api/accounts", "/api/fund/entries"):
            res = c.get(path)
            flag = "✅ 已挡住" if res.status_code == 404 else f"⚠️ 返回 {res.status_code}"
            print(f"  {path:<26} {flag}")

    print()
    print("=== 2. 管理端 ===")
    with httpx.Client(base_url=ADMIN, timeout=60, follow_redirects=True) as c:
        r = c.post("/api/auth/login", json={"username": "admin", "password": "344940"})
        print(f"  登录            HTTP {r.status_code}")
        data = r.json()
        ok = data.get("ok")
        token = data.get("token", "")
        print(f"  登录结果        ok={ok}")
        if token:
            h = {"X-Session-Token": token}
            print(f"  会话有效期      {data.get('expires_at') or data.get('expire_at') or '-'}")
            for path in ("/api/accounts/me", "/api/dorms", "/api/fund/summary", "/api/qqbot/status",
                         "/api/logs/push?limit=3", "/api/reports/preview"):
                try:
                    res = c.get(path, headers=h)
                    print(f"  {path:<26} HTTP {res.status_code}")
                except Exception as exc:
                    print(f"  {path:<26} 异常 {type(exc).__name__}")

            s = c.get("/api/qqbot/status", headers=h).json()
            print()
            print(f"  QQ 长连接: {s.get('gateway_running')} | 群: {s.get('configured_groups')} 个")

    print()
    print("=== 3. HTTPS 证书 ===")
    with httpx.Client(timeout=20) as c:
        for base in (PUBLIC, ADMIN):
            try:
                r = c.get(base + "/api/health")
                print(f"  {base:<30} HTTP {r.status_code} (TLS 由 Cloudflare 提供)")
            except Exception as exc:
                print(f"  {base:<30} 异常 {exc}")


if __name__ == "__main__":
    main()
