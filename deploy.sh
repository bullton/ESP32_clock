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
cp -f server/app.py server/data.py server/renderer.py server/symbols.py server/auth.py server/styles.py .
cp -f server/requirements.txt .
cp -f server/*.ttf server/*.otf . 2>/dev/null || true

mkdir -p templates icon static fonts
cp -rf server/templates/. templates/
cp -rf server/icon/. icon/
cp -rf server/static/. static/
cp -rf server/fonts/. fonts/

# 重启服务
# 注意：本机 clock_server 由 PM2 托管（pm2 list 中 name=clock_server），
# 不要用 pkill —— 进程被杀了 PM2 会立刻拉起，和手动启动的实例抢 5000 端口。
rm -rf __pycache__

PM2_BIN="$(command -v pm2 || echo /home/bullton/.npm-global/bin/pm2)"
if "$PM2_BIN" describe clock_server >/dev/null 2>&1; then
  "$PM2_BIN" restart clock_server --update-env >/dev/null
  WHO="PM2 clock_server"
else
  nohup python3 app.py >> server.log 2>&1 &
  WHO="nohup python3 app.py"
fi

sleep 3
if curl -fsS --max-time 5 http://127.0.0.1:5000/api/health >/dev/null; then
  echo "Deployed at $(date) —— $WHO 已重启，/api/health 正常"
else
  echo "启动失败，最近日志："
  "$PM2_BIN" logs clock_server --lines 20 --nostream 2>/dev/null || tail -n 20 server.log
  exit 1
fi
