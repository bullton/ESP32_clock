# 部署文档 - 墨水屏时钟服务器

## 服务器信息
- **IP**: 192.168.50.180
- **SSH**: `ssh -i ~/.ssh/id_rsa_bullton_180_nopass bullton@192.168.50.180`

## SSH 配置

### 问题
原来的密钥 `~/.ssh/id_rsa_bullton_180` 有密码保护，导致 SSH 免密登录失败。

### 解决
生成了新的无密码密钥 `~/.ssh/id_rsa_bullton_180_nopass`，并添加到服务器的 `~/.ssh/authorized_keys`。

### 新密钥登录
```bash
ssh -i ~/.ssh/id_rsa_bullton_180_nopass bullton@192.168.50.180
```

### 以后新增密钥
1. 生成密钥对（无密码）：
   ```python
   from paramiko import RSAKey
   key = RSAKey.generate(4096)
   key.write_private_key_file("path/to/key")
   ```
2. 获取公钥：
   ```bash
   cat path/to/key.pub
   ```
3. 添加到远程服务器：
   ```python
   import paramiko
   client = paramiko.SSHClient()
   client.connect('192.168.50.180', username='bullton', password='密码')
   client.exec_command('echo "公钥内容" >> ~/.ssh/authorized_keys')
   ```

## 服务管理

### 启动服务
```bash
ssh -i ~/.ssh/id_rsa_bullton_180_nopass bullton@192.168.50.180
cd /home/bullton/clock_server
python3 app.py &
```

### 查看日志
```bash
ssh -i ~/.ssh/id_rsa_bullton_180_nopass bullton@192.168.50.180 "tail -50 /home/bullton/clock_server/server.log"
```

### 重启服务
```bash
ssh -i ~/.ssh/id_rsa_bullton_180_nopass bullton@192.168.50.180 "pkill -f 'python3 app.py'; sleep 1; cd /home/bullton/clock_server && python3 app.py > server.log 2>&1 &"
```

### 验证运行
```bash
curl http://192.168.50.180:5000/api/health
curl http://192.168.50.180:5000/api/screen_2x -o /dev/null -w "%{http_code}"
```

## 文件位置
- **服务端代码**: `/home/bullton/clock_server/`
  - `app.py` - Flask 入口
  - `data.py` - 数据层（天气 API）
  - `renderer.py` - 渲染核心
  - `weathericons-regular-webfont.ttf` - 天气图标字体
- **日志**: `/home/bullton/clock_server/server.log`

## ESP32 端配置
```python
SERVER_URL = "http://192.168.50.180:5000/api/screen_2x"
```

## API 端点
| 端点 | 说明 |
|------|------|
| `/api/screen_2x` | 15000 字节 raw binary（ESP32 用）|
| `/api/screen_2x.png` | 2x PNG 预览 |
| `/api/info` | JSON 当前数据 |
| `/api/health` | 健康检查 |