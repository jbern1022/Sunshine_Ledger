#!/usr/bin/env bash
# One-time setup of the Sunshine Ledger pilot-light standby (Ubuntu 24.04 on
# AWS EC2). Run as root by the instance's first-boot user data, which clones
# the public GitHub mirror to /opt/sunshine-ledger first. Safe to re-run.
set -euo pipefail

REPO=/opt/sunshine-ledger

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -yq ca-certificates curl git python3 unzip

# Docker Engine + compose plugin from Docker's own apt repository.
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

# AWS CLI v2 (SSM, S3, SNS from the boot script; credentials come from the
# instance role, never from stored keys).
if ! command -v aws >/dev/null; then
  tmp=$(mktemp -d)
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip" -o "$tmp/awscliv2.zip"
  unzip -q "$tmp/awscliv2.zip" -d "$tmp"
  "$tmp/aws/install"
  rm -rf "$tmp"
fi

# 4 GB of RAM is tight for Postgres + the Next.js production build at once.
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

install -m 0644 "$REPO/scripts/standby/sunshine-standby.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable sunshine-standby.service
echo "standby install complete"
