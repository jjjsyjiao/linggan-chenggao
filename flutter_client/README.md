# 灵感成稿 · Flutter 客户端上手指南

这个 App 把相册图片和你的创作要求发给 Python 服务，生成可编辑的小红书标题、正文和话题，再携图打开分享。它支持 Android 和 iOS；首次体验建议先跑 Android。

**需要同时运行两个程序：电脑上的 Python 服务，以及手机/模拟器上的 Flutter App。** 下面按“先跑通演示，再切换真实 AI”的顺序操作。演示不需要模型密钥，不会产生模型调用费用。

## 1. 在电脑启动 Python 服务

先在编辑器中打开整个项目，并打开终端 A。当前目录应能看到 `pyproject.toml`、`src/` 和 `flutter_client/`，这里称为“项目根目录”。这一节所有命令都在根目录执行。

### 安装 uv 和 Python 依赖

`uv` 用来准备 Python 和项目依赖。已安装则先运行 `uv --version`；未安装可按 [uv 官方安装说明](https://docs.astral.sh/uv/getting-started/installation/)操作，常用命令如下。

Windows PowerShell：

```powershell
winget install --id astral-sh.uv -e
```

macOS / Linux 终端：

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

安装后重新打开终端，并确认仍在项目根目录。以下命令两种系统都能运行：

```sh
uv --version
uv python install 3.13
uv sync --frozen --extra dev --python 3.13
```

本项目使用 Python 3.11～3.13；当前 CrewAI 依赖不支持 Python 3.14 及以上，这里统一选用已验证的 3.13。成功后根目录会出现 `.venv/`。不需要额外激活虚拟环境，也不需要为了笔记生成接口安装 MySQL 或 Redis。

### 创建配置，先用演示模式

仅第一次创建 `.env`，已有文件请保留：

Windows PowerShell：

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

macOS / Linux：

```sh
if [ ! -f .env ]; then cp .env.example .env; fi
```

用文本编辑器打开根目录的 `.env`，找到并修改以下项；同名配置只保留一条：

```dotenv
APP_ENV=development
APP_XHS_DEMO_MODE=true
APP_LLM_API_KEY=
APP_API_KEYS=
APP_DATABASE_URL=sqlite+aiosqlite:///./app.db
```

保留 `.env.example` 中已有的 `CREWAI_TELEMETRY_DISABLED=true`、`OTEL_SDK_DISABLED=true` 等设置。此时不用申请或填写任何模型密钥。

### 启动并检查服务

在项目根目录执行，Windows PowerShell、macOS 和 Linux 使用同一条命令，无需激活虚拟环境：

```sh
uv run --frozen python -m uvicorn app.main:app --app-dir src --host 0.0.0.0 --port 8072
```

使用这条单进程命令，不加 `--reload` 或 `--workers`。Windows 的 reload/多 worker 配置可能选择不支持生成子进程的事件循环，导致图片生成失败；修改配置或代码后手动停止并重新启动即可。

看到 `Uvicorn running on http://0.0.0.0:8072` 和 `Application startup complete` 表示已启动。**保持终端 A 开着**，电脑浏览器访问：

- [健康检查](http://127.0.0.1:8072/health/live)：应显示 `{"status":"ok"}`。
- [接口文档](http://127.0.0.1:8072/docs)：应能看到接口列表。

健康检查只证明服务进程能访问，不会调用模型。`0.0.0.0` 表示接受其他设备连接，不能作为 App 的服务地址。启动命令已明确指定端口 `8072`；后续地址中的端口需与它一致。

## 2. 安装 Flutter 和 Android 开发环境

新开终端 B，后续用来运行 App，保留终端 A 中的服务。

1. 按 [Flutter 官方安装指南](https://docs.flutter.dev/install)安装 Flutter SDK，并把 SDK 的 `bin` 目录加入 PATH。只安装 Android Studio 的 Flutter 插件还不能使用 `flutter` 命令。
2. 安装 [Android Studio](https://developer.android.com/studio)，完成首次启动向导。打开 **Tools → SDK Manager**，安装 Android SDK Platform、Build-Tools、Command-line Tools、Platform-Tools；使用模拟器还需安装 Android Emulator 和系统镜像。构建所需具体 SDK/NDK 版本以 Flutter 提示为准，使用 Android Studio 自带的 JDK。
3. 关闭后重新打开终端 B，运行以下检查，并按提示处理 Android toolchain 项的问题。详细步骤见 [Flutter Android 环境配置](https://docs.flutter.dev/platform-integration/android/setup)。

```sh
flutter --version
flutter doctor --android-licenses
flutter doctor -v
```

成功标志：`flutter --version` 能输出版本，Android 许可已接受，`flutter doctor` 的 **Android toolchain** 可用。仅运行 Android 时，未安装 Xcode 或其他桌面开发工具不影响这一条路径。本项目的 `pubspec.yaml` 要求 Dart `>=3.9.0 <4.0.0`，请使用满足它的 Flutter stable SDK。

本机验证使用 Flutter 3.47.8 / Dart 3.13.7，对应 Android SDK Platform 36，最低运行设备为 Android 7.0（API 24）。工程的编译 SDK、最低 SDK 和 NDK 跟随所用 Flutter SDK，升级 Flutter 后以构建提示为准。

如果提示找不到 `flutter`，先修复 PATH。临时设置举例（把路径换成你实际解压的位置）：

```powershell
# Windows PowerShell，仅当前终端生效
$env:Path = "C:\src\flutter\bin;$env:Path"
```

```sh
# macOS / Linux，仅当前终端生效
export PATH="$HOME/development/flutter/bin:$PATH"
```

项目目录里的 `.tooling/flutter` 是这台开发电脑准备的可选 SDK，通常不随源码分发；新电脑无需有这个目录。本机已存在时，可以在 `flutter_client/` 中用 `../.tooling/flutter/bin/flutter` 代替 `flutter`。Windows SDK 的入口是 `flutter.bat`。

## 3. 选择 Android 模拟器或真机

### 方案 A：Android 官方模拟器

在 Android Studio 打开 **Tools → Device Manager**，创建并启动一台 Android 虚拟设备，再运行：

```sh
flutter devices
```

列表中出现平台为 `android` 的设备即成功，例如设备 ID 为 `emulator-5554`。App 服务地址使用 **`http://10.0.2.2:8072`**，这是 Android 官方模拟器访问电脑的地址，也是本 App 的 Android 默认值。

### 方案 B：Android 真机，推荐先用同一 Wi-Fi

1. 手机开启“开发者选项 → USB 调试”，用可传数据的 USB 线连接电脑；手机弹出授权时允许调试。部分手机还需允许 USB 安装。Windows 若不识别设备，检查对应厂商 USB 驱动。
2. 运行 `flutter devices`，确认能看到手机的 Android 设备 ID。未授权时先解锁手机完成授权。
3. 手机和电脑接入同一 Wi-Fi，查电脑当前的局域网 IPv4：Windows 用 `ipconfig`，macOS 在“系统设置 → Wi-Fi → 当前网络详细信息”查看，Linux 用 `ip -4 addr`。选用正在联网的网卡，避免 VPN/虚拟网卡地址。
4. 假设电脑 IP 为 `192.168.1.8`，在手机浏览器访问 `http://192.168.1.8:8072/health/live`。出现 `{"status":"ok"}` 后，App 也填 `http://192.168.1.8:8072`。

这里的 `192.168.1.8` 只是例子，必须替换成你电脑的 IP。手机的 `127.0.0.1` / `localhost` 指手机自身；直接填它通常连不到电脑。手机浏览器也无法访问时，先检查服务是否还开着、监听是否为 `0.0.0.0`、电脑防火墙是否允许本地 8072 端口，以及 Wi-Fi 是否隔离设备。电脑 IP 变化后需更新 App 设置。

### 可选：Android 真机通过 USB 连接服务

如果不走 Wi-Fi，可使用 Android SDK 的 `adb reverse`。把 SDK 的 `platform-tools` 目录加入 PATH；Windows 中若当前就在该目录，使用 `./adb.exe`。将下面的 `DEVICE_ID` 替换为实际 Android 设备 ID：

```sh
adb -s DEVICE_ID reverse tcp:8072 tcp:8072
adb -s DEVICE_ID reverse --list
```

看到 `tcp:8072 tcp:8072` 后，App 改填 **`http://127.0.0.1:8072`**。USB 模式需保持连接；重连、设备重启或 ADB 服务重建后，转发可能丢失，需要重新执行上面的命令。它与 Wi-Fi 地址是两种连接方式，选择当前实际使用的一种。

## 4. 安装并启动 App

在终端 B 从项目根目录进入客户端目录：

```sh
cd flutter_client
flutter pub get
flutter devices
```

`flutter pub get` 成功时会显示依赖已获取。将设备列表里的 ID 填入运行命令，例如：

```sh
# Android 模拟器示例；若你的 ID 不同请替换
flutter run -d emulator-5554
```

真机运行时，可以在启动命令中指定你的服务地址：

```sh
# DEVICE_ID 和 IP 均需替换；此单行命令同样适用于 PowerShell
flutter run -d DEVICE_ID --dart-define=API_BASE_URL=http://192.168.1.8:8072
```

成功标志：目标设备上出现 **“灵感成稿”** 首页，终端提示 App 正在运行。首次构建需要下载 Gradle 和 Android 依赖，可能较慢。请选择 Android 设备，不要选 Chrome 或 macOS 桌面条目；本客户端当前按 Android/iOS 配置。

App 右上角 **“服务设置”** 可以随时修改连接；点击“保存连接设置”后生效：

| 场景 | App 服务地址 |
| --- | --- |
| Android 官方模拟器 | `http://10.0.2.2:8072` |
| Android 真机，同一 Wi-Fi | `http://电脑局域网IP:8072` |
| Android 真机，已配置 USB reverse | `http://127.0.0.1:8072` |
| iOS 模拟器，服务也在同一台 Mac | `http://127.0.0.1:8072` |
| iPhone 真机，同一 Wi-Fi | `http://电脑局域网IP:8072` |
| 部署到公网的服务 | 你的 HTTPS 服务根地址 |

服务地址只填根地址，**不要追加 `/api`、`/generate` 或 `/docs`**。Android debug 构建允许本地 HTTP；release 默认使用 HTTPS。服务地址设置和服务 API Key 保存在本次 App 运行中，完全退出后需要重新填写，或用 `--dart-define=API_BASE_URL=...` 指定默认地址。

## 5. 选图、生成和分享

1. 点击“从相册挑选图片”，选择单张或多张图片，可调整顺序。只选择图片，不包含视频。首次体验先用 1–2 张 JPEG/PNG。
2. 输入具体创作要求，例如：“给这张菊花照片写一篇温柔的观花随笔，正文两段，不写地点、花期和养护建议。”
3. 点击生成。演示模式会显示 **“演示结果：未调用 AI 模型”**，标题固定、正文套用演示模板并回显部分创作要求与图片数量，不会按提示词真实创作。
4. 在预览页编辑标题、正文和话题。真实生成仍需核对图片细节和事实；出现 **“有待核对的草稿”** 时，逐项查看提示。警示不会被复制进正文，无警示也不代表事实已核验。
5. 点击“复制文案并分享图片”。Android 优先尝试携图打开已安装的小红书，无法接收时转到系统分享面板；iOS 使用系统分享面板。在小红书中手动粘贴标题和正文，再自行确认发布。

创作要求为 1–2000 字。图片最多 20 张，单张不超过 10 MiB，总计不超过 50 MiB；服务端会校验实际格式和像素。发布目标为标题 20 字符、正文连话题 1000 字符，超长稿件可继续编辑，不会静默截断。分享传递的是本地图片，能否进入发布器及携带多少张，取决于小红书版本和设备；本 App 不会自动公开发布笔记。相册及小红书发布器最终效果需用真机确认。

## 6. 切换真实 AI 生成

演示流程跑通后，到阿里云百炼准备可用的通义千问模型 API Key，在**项目根目录 `.env`** 中修改：

```dotenv
APP_XHS_DEMO_MODE=false
APP_LLM_API_KEY=这里填写你自己的模型密钥
APP_LLM_IMAGE_MODEL=qwen3-vl-plus
APP_LLM_REGION=cn
```

密钥与服务地域需匹配；如果使用其他地域或自定义兼容接口，先核对后端配置说明。**按 Ctrl+C 停止终端 A 的服务，再用第 1 节的统一命令重新启动**。修改 `.env` 不会让已启动的进程自动刷新；若终端中手动设置过同名环境变量，它优先于 `.env`，也需一并修改或清除。

`.env` 中一律填写 `APP_LLM_API_KEY`。备用 `QWEN_API_KEY` 只读取已导出的系统环境变量，写进 `.env` 不会作为备用密钥生效。

两种 Key 的用途不同：

| 配置 | 填在哪里 | 用途 |
| --- | --- | --- |
| `APP_LLM_API_KEY` | 电脑根目录 `.env` | Python 向模型服务发请求；不要填入手机 App |
| `APP_API_KEYS` | 电脑根目录 `.env`，可逗号分隔 | 你自己设置的 Python 接口访问密钥，本地开发可留空 |
| App 中“API Key（可选）” | App 的“服务设置” | 仅在后端 `APP_API_KEYS` 非空时填写其中一个值 |

真实模式每次生成会发送所选图片和完整创作要求，一次视觉模型调用同时返回逐图观察和自由稿件，不使用固定模板覆盖结果，也不自动重试模型请求。会产生供应商费用；模型质量、耗时与额度需通过真实生成确认，健康检查和演示无法代替。取消等待或断网不保证供应商计费立即停止，避免连续重复提交。

## 7. 常见问题

| 现象 | 先检查什么 |
| --- | --- |
| 找不到 `uv` / `flutter` / `adb` | 工具是否安装、对应目录是否在 PATH；更改后重新打开终端 |
| `flutter devices` 没有手机 | 数据线、USB 调试授权、Windows 厂商驱动；模拟器需先启动 |
| App 无法连接服务 | 先用手机浏览器检查 `/health/live`；真机 Wi-Fi 用电脑 IP，USB 模式检查 reverse，模拟器用 `10.0.2.2` |
| 端口被占用 / `Address already in use` | 已有程序占用 8072；确认是否已有本项目服务，或换端口并同步修改 App 地址 |
| 鉴权失败，HTTP 401/403 | App 服务 API Key 是否匹配 `APP_API_KEYS`，不要填成模型 Key |
| 不同提示词仍总是固定示例 | 看页面是否标注演示；将 `APP_XHS_DEMO_MODE` 改为 `false` 并重启后端 |
| HTTP 502/503 或模型密钥未配置 | 检查后端 `.env` 的模型 Key、地域和可用模型；结合 App 请求 ID 查终端 A 或根目录 `logs/` |
| HTTP 429 | 服务繁忙或模型限流，等当前任务结束后再试 |
| 选图上传失败 | 先试一张小 JPEG/PNG，检查单图/总大小；HEIC 在真实 iPhone 验证 |
| 分享面板没有小红书 | 检查是否安装并更新小红书；分享扩展是否提供由目标应用决定，也可手动选图并粘贴文案 |

## 8. iOS、检查和打包

iOS 构建需要 **macOS + Xcode**，Windows/Linux 无法本地编译 iOS。当前工程部署目标为 iOS 15.0；iOS 模拟器启动后可通过 `flutter devices` 查看 ID，再用 `flutter run -d DEVICE_ID` 运行。iPhone 真机还需在 Xcode 设置开发者 Team 和唯一 Bundle ID，首次连接本地服务时允许局域网权限。参考 [Flutter iOS 环境配置](https://docs.flutter.dev/platform-integration/ios/setup)。

在 `flutter_client/` 中执行：

```sh
flutter test
flutter analyze
flutter build apk --debug
```

debug APK 位于 `build/app/outputs/flutter-apk/app-debug.apk`。Android 正式分发前需配置自己的签名及 HTTPS 服务；当前 Android 应用 ID 为 `com.linggan.linggan_chenggao`，iOS Bundle ID 为 `com.linggan.lingganChenggao`，发布前换成自己的标识。仅在 Mac 的 Xcode 环境准备完成后，可运行 `flutter build ios --simulator --debug` 检查模拟器构建。

开发者如需跑已有模拟器联调测试，先开启第 1 节的演示服务，再在 `flutter_client/` 中执行以下单行命令（替换设备 ID；iOS 模拟器把地址改成 `http://127.0.0.1:8072`）：

```sh
flutter drive --no-pub -d DEVICE_ID --driver=test_driver/integration_test.dart --target=integration_test/demo_flow_test.dart --dart-define=API_BASE_URL=http://10.0.2.2:8072
```

该测试替换相册返回的测试图片，实际经过上传、HTTP、解码、预览和编辑；截图写到根目录 `artifacts/mobile/`。它不能代替真实模型或小红书发布器验收。接口为 `POST /api/v1/xhs/notes/generate`，使用 multipart 的 `idea_text`、重复 `images` 字段及可选 `X-API-Key`，完整接口可查看 Python 的 `/docs`；原 `/report` 是完整多 Agent 报告接口，客户端不调用。实现与验证细节见[生成速度优化](../doc/生成速度优化.md)和[客户端接口与服务验证](../doc/客户端接口与服务验证.md)。
