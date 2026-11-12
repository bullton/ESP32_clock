#!/bin/bash
# 部署脚本 —— 在服务器上运行（/home/bullton/clock_server）
# 用法：bash deploy.sh
set -e
cd /home/bullton/clock_server

# 备份数据文件（下面 git pull / 复制不会碰它们，但保险起见）
cp bottom_content.txt /tmp/bottom_content.txt.bak 2>/dev/null || true
cp alarm.json /tmp/alarm.json.bak 2>/dev/null || true

# 拉取最新代码（只允许快进，避免在服务器上产生意外合并）
git pull --ff-only origin master

# 恢复数据文件
cp /tmp/bottom_content.txt.bak bottom_content.txt 2>/dev/null || true
cp /tmp/alarm.json.bak alarm.json 2>/dev/null || true

# 把 server/ 子目录的内容复制到运行目录（覆盖根目录里旧的散装文件）
cp -f server/app.py server/data.py server/renderer.py server/symbols.py server/auth.py .
cp -f server/requirements.txt .
cp -f server/*.ttf server/*.otf . 2>/dev/null || true

mkdir -p templates icon static fonts
cp -rf server/templates/. templates/
cp -rf server/icon/. icon/
cp -rf server/static/. static/
cp -rf server/fonts/. fonts/

# 重启服务：先按 5000 端口找占用进程，再用锚定模式兜底
port_pid() { ss -lptnH 'sport = :5000' 2>/dev/null | grep -o 'pid=[0-9]*' | head -n1 | cut -d= -f2; }
PID="$(port_pid)"
if [ -n "$PID" ]; then
  kill "$PID" 2>/dev/null || true
  for _ in $(seq 1 10); do
    [ -z "$(port_pid)" ] && break
    sleep 1
  done
  [ -n "$(port_pid)" ] && kill -9 "$PID" 2>/dev/null || true
fi
pkill -f '^/usr/bin/python3 app\.py$' 2>/dev/null || true
sleep 1
rm -rf __pycache__
nohup python3 app.py >> server.log 2>&1 &

sleep 3
if [ -n "$(port_pid)" ]; then
  echo "Deployed at $(date) —— 服务已监听 5000 (pid $(port_pid))"
else
  echo "启动失败，最近日志："
  tail -n 20 server.log
  exit 1
fi
