#!/usr/bin/env bash
set -euo pipefail
# Amazon Linux 2023 example bootstrap for the academic deployment host.
dnf update -y
dnf install -y docker git
test -f /usr/lib/systemd/system/docker.service && systemctl enable --now docker
usermod -aG docker ec2-user || true
# Docker Compose plugin availability differs by AMI. Install it from the
# official Docker repository/package for your selected AMI before deployment.
mkdir -p /opt/mediexplain
chown ec2-user:ec2-user /opt/mediexplain
printf '%s\n' 'Host prepared. Upload/extract MediExplain+ to /opt/mediexplain, create .env from .env.example, then run docker compose up -d --build.'
