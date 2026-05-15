#!/bin/bash
# ══════════════════════════════════════════════════════════════
# Oracle Cloud Always Free VM 초기 배포 스크립트
# 대상 OS : Ubuntu 22.04 (ubuntu 사용자, sudo 권한 필요)
# 프론트엔드 : Vercel 배포 / 백엔드만 이 VM에서 실행
#
# 실행 전 아래 변수를 backend/.env 와 일치하도록 수정하세요
# ══════════════════════════════════════════════════════════════
set -euo pipefail

APP_DIR="/home/ubuntu/expense-auto"   # 서버 내 앱 경로
DB_NAME="expense_auto"
DB_USER="expense_user"
DB_PASS="1234"                        # .env의 DATABASE_URL 비밀번호와 동일하게 설정

# ──────────────────────────────────────────────────────────────
BACKEND_DIR="$APP_DIR/backend"
VENV_DIR="$BACKEND_DIR/venv"
SERVICE_NAME="expense-auto"

# ── 1. 시스템 패키지 ──────────────────────────────────────────
echo ">>> [1/6] 시스템 패키지 설치"
sudo apt-get update -y
sudo apt-get install -y \
    python3 python3-pip python3-venv \
    libmariadb-dev pkg-config \
    libreoffice \
    nginx \
    mariadb-server \
    iptables-persistent

# ── 2. MariaDB ────────────────────────────────────────────────
echo ">>> [2/6] MariaDB 시작 및 DB/사용자 생성"
sudo systemctl enable --now mariadb

sudo mysql <<SQL
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL

# ── 3. Python 가상환경 ────────────────────────────────────────
echo ">>> [3/6] Python 가상환경 생성 및 패키지 설치"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt"

# ── 4. systemd 서비스 ─────────────────────────────────────────
echo ">>> [4/6] systemd 서비스 등록"
sudo cp "$APP_DIR/deploy/expense-auto.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"

# ── 5. Nginx ─────────────────────────────────────────────────
echo ">>> [5/6] Nginx 설정"
sudo cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/"$SERVICE_NAME"
sudo ln -sf \
    /etc/nginx/sites-available/"$SERVICE_NAME" \
    /etc/nginx/sites-enabled/"$SERVICE_NAME"
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl enable --now nginx

# ── 6. Oracle Cloud 방화벽 ───────────────────────────────────
echo ">>> [6/6] iptables 방화벽 오픈 (포트 80 / 443)"
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80  -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save

# ── 완료 메시지 ───────────────────────────────────────────────
PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "확인불가")

cat <<MSG

══════════════════════════════════════════════════════════════
✅ 백엔드 배포 완료
   백엔드 URL : http://${PUBLIC_IP}

유용한 명령어:
  sudo systemctl status  ${SERVICE_NAME}
  sudo journalctl -u ${SERVICE_NAME} -f
  sudo systemctl restart ${SERVICE_NAME}
  sudo nginx -t && sudo systemctl reload nginx

──────────────────────────────────────────────────────────────
Vercel 배포 전 설정 체크리스트:

  1. [OCI Console] Security List → Ingress Rules에 TCP 80/443 추가
  2. [backend/.env] CORS_ORIGINS=https://your-app.vercel.app 추가
                    SOFFICE_PATH=/usr/bin/soffice 로 수정 (Linux 경로)
     수정 후 → sudo systemctl restart ${SERVICE_NAME}

  3. [Vercel] Environment Variables 에 추가:
       VITE_API_URL = http://${PUBLIC_IP}
     (도메인이 있으면 IP 대신 도메인 사용 권장)
══════════════════════════════════════════════════════════════
MSG
