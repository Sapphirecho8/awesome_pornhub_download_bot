# awesome_pornhub_download_bot

一个基于 Python 的 Telegram 机器人：当收到 Pornhub 视频链接时，使用 yt-dlp 下载，然后通过本地 Bot API 发送视频。发送完成后自动删除本地文件，并写入日志。

- 上传大小限制为 2GB
- 白名单模式：仅允许指定的 TGID 使用
- 频道发布模式：推送到频道，私聊提示进度；或直接回发到私聊
- 完整日志（Rolling file）保存在 `logs/bot.log`

欢迎直接使用机器人：https://t.me/awesome_pornhub_download_bot

欢迎关注频道 Pornhub 精选：https://t.me/awesome_pornhub

## 快速开始（Docker Compose）

1. 创建一个docker-compose.yml文件
需要修改的内容：
- `BOT_TOKEN`：从 BotFather 获得
- `TELEGRAM_API_ID`、`TELEGRAM_API_HASH`：从 https://my.telegram.org/apps 获得
- `ADMIN_IDS`：逗号分隔的用户 ID 列表，如 `123,456`
- `CHANNEL_ID`：数字频道 ID，如 `-100xxxxxxxxxx`

```bash
services:
  botapi:
    image: aiogram/telegram-bot-api:latest
    container_name: botapi
    restart: unless-stopped
    environment:
      - TELEGRAM_API_ID=123123
      - TELEGRAM_API_HASH=314354dd3245
      - TELEGRAM_LOCAL=1
    volumes:
      - botapi-data:/var/lib/telegram-bot-api
    # no ports exposed publicly; bot talks via service name

  bot:
    image: sapphirecho8/awesome_pornhub_download_bot:latest
    container_name: awesome_pornhub_download_bot
    depends_on:
      - botapi
    restart: unless-stopped
    environment:
      - BOT_TOKEN=xxx
      - ADMIN_IDS=123,456
      - CHANNEL_ID=-100xxxxxxxx
      - SEND_TO_CHANNEL=true
      - BOT_API_BASE_URL=http://botapi:8081/bot
      - BOT_API_FILE_URL=http://botapi:8081/file/bot
    volumes:
      - botapi-data:/var/lib/telegram-bot-api

volumes:
  botapi-data:
```

2. 启动服务

```bash
docker compose up -d
```


## 从源代码运行

1. 下载源码
```bash
git clone https://github.com/Sapphirecho8/awesome_pornhub_download_bot.git 
```

2. 进入源码目录
```bash
cd awesome_pornhub_download_bot/ 
```

3. 创建文件储存目录

```bash
mkdir -p /var/lib/telegram-bot-api/uploads
```

4. 启动本地 Bot API Server

在 8081 端口运行本地 Bot API，分享数据目录供机器人容器/进程使用

注意替换 TELEGRAM_API_ID/HASH

```bash
docker run -d --name botapi \
  -e TELEGRAM_LOCAL=1 \
  -e TELEGRAM_API_ID=YOUR_ID \
  -e TELEGRAM_API_HASH=YOUR_HASH \
  -v /var/lib/telegram-bot-api:/var/lib/telegram-bot-api \
  -p 8081:8081 \
  aiogram/telegram-bot-api:latest
```

5. 安装依赖（示例在 Ubuntu/Debian 下安装）

```bash
sudo apt-get update && sudo apt-get install ffmpeg python3.11-venv -y
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

6. 设置环境变量
注意替换 BOT_TOKEN/ADMIN_IDS/CHANNEL_ID
在有多个管理员的时候，请将管理员ID使用  `,`  分割

```bash
export BOT_TOKEN=xxx
export ADMIN_IDS=123,456
export CHANNEL_ID=-100xxxxxxxxxx
# 可选：
export SEND_TO_CHANNEL=true
export BOT_API_BASE_URL=http://127.0.0.1:8081/bot
export BOT_API_FILE_URL=http://127.0.0.1:8081/file/bot
```

7. 测试能否运行成功
```bash
python -u bot_phdl.py
```

7. 测试成功后可以使用nohup在后台运行

```bash
nohup .venv/bin/python -u bot_phdl.py >/dev/null 2>&1 </dev/null &
```



## 指令

- `/sendtochannel on|off`
  - 开启/关闭频道模式
  - 开启后：接到链接时私聊提示“开始下载，请稍候…”，视频直接发布到 `CHANNEL_ID` 指定的频道，随后私聊提示“下载完成，已发送。”
  - 关闭后：视频直接回发到私聊，并在发送成功后自动删除“开始下载，请稍候…”提示
- 管理员白名单：
  - 仅 `ADMIN_IDS` 指定的用户可用。其他人会收到：
    - `抱歉，这不是你的机器人，请向管理员申请权限或者自行部署机器人，Github地址：https://github.com/Sapphirecho8/awesome_pornhub_download_bot`


## 目录结构

- `bot_phdl.py`：机器人主程序
- `requirements.txt`：Python 依赖
- `Dockerfile`：构建机器人镜像
- `docker-compose.yml`：示例
- `.gitignore`：忽略缓存、日志、环境文件等
- `logs/bot.log`：运行日志
