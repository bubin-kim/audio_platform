"""Google Drive OAuth 1회 설정 헬퍼 (docs/09 §2 절차 4~5).

실행: cd backend && uv run python scripts/setup_drive_auth.py
사전 준비: GCP에서 Drive API 활성화 + OAuth 동의화면 '프로덕션' 게시 +
          데스크톱 앱 클라이언트 생성 (docs/09 §2 절차 1~3).

하는 일:
  1. 브라우저 동의(loopback 리다이렉트) → refresh token 발급
  2. 백업 루트 폴더 'AudioPlatform 백업' 생성 (drive.file 스코프는 앱이 만든
     폴더만 접근 가능하므로 반드시 이 스크립트로 생성해야 한다 — 09 §8 함정)
  3. backend/.env 에 넣을 값 출력

표준 라이브러리 + httpx만 사용 (추가 의존성 0).
"""

import http.server
import json
import secrets
import threading
import urllib.parse
import webbrowser

import httpx

SCOPE = "https://www.googleapis.com/auth/drive.file"
REDIRECT_PORT = 8765
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
ROOT_FOLDER_NAME = "AudioPlatform 백업"


def _receive_auth_code(expected_state: str) -> str:
    """loopback 서버로 Google 리다이렉트의 인증 코드를 1회 수신한다."""
    result: dict[str, str] = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (표준 라이브러리 규약)
            query = urllib.parse.urlparse(self.path).query
            params = dict(urllib.parse.parse_qsl(query))
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            if params.get("state") != expected_state:
                self.wfile.write("state 불일치 — 다시 시도하세요.".encode())
                return
            if "code" in params:
                result["code"] = params["code"]
                self.wfile.write(
                    "✅ 인증 완료. 이 창을 닫고 터미널로 돌아가세요.".encode()
                )
            else:
                self.wfile.write(f"오류: {params.get('error', '?')}".encode())
            done.set()

        def log_message(self, *args: object) -> None:  # 콘솔 소음 제거
            pass

    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    done.wait(timeout=300)  # 5분 안에 동의 안 하면 포기
    server.shutdown()
    if "code" not in result:
        raise SystemExit("인증 코드를 받지 못했습니다. 다시 실행해 주세요.")
    return result["code"]


def main() -> None:
    print("=== Google Drive OAuth 설정 (docs/09 §2) ===")
    client_id = input("OAuth 클라이언트 ID: ").strip()
    client_secret = input("OAuth 클라이언트 Secret: ").strip()
    if not client_id or not client_secret:
        raise SystemExit("클라이언트 ID/Secret이 필요합니다.")

    # 1) 브라우저 동의 → 인증 코드
    state = secrets.token_urlsafe(16)
    auth_url = AUTH_URL + "?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",  # refresh token 요청
            "prompt": "consent",  # 재실행 시에도 refresh token 재발급
            "state": state,
        }
    )
    print("\n브라우저에서 Google 동의 화면을 엽니다...")
    print(f"(자동으로 안 열리면 직접 열기: {auth_url})\n")
    webbrowser.open(auth_url)
    code = _receive_auth_code(state)

    # 2) 코드 → refresh token 교환
    res = httpx.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=30.0,
    )
    res.raise_for_status()
    tokens = res.json()
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise SystemExit(
            "refresh_token이 없습니다. GCP 동의 화면이 '프로덕션'으로 게시됐는지, "
            "prompt=consent로 재동의했는지 확인하세요 (docs/09 §8)."
        )

    # 3) 백업 루트 폴더 생성 (앱 소유 — drive.file 스코프로 접근 가능)
    res = httpx.post(
        DRIVE_FILES_URL,
        params={"supportsAllDrives": "true"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={
            "name": ROOT_FOLDER_NAME,
            "mimeType": "application/vnd.google-apps.folder",
        },
        timeout=30.0,
    )
    res.raise_for_status()
    folder = res.json()

    print("\n=== 완료! backend/.env 에 아래 값을 추가하세요 ===\n")
    print(f"GOOGLE_OAUTH_CLIENT_ID={client_id}")
    print(f"GOOGLE_OAUTH_CLIENT_SECRET={client_secret}")
    print(f"GOOGLE_OAUTH_REFRESH_TOKEN={refresh_token}")
    print(f"DRIVE_ROOT_FOLDER_ID={folder['id']}")
    print(f"\nDrive 폴더: https://drive.google.com/drive/folders/{folder['id']}")
    print("(서버 재기동 후 CSV export 시 이 폴더에 자동 미러링됩니다)")


if __name__ == "__main__":
    main()
