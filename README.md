
# 🏙️ Google 街景图像批量下载工具

本项目包含一个 **配置文件 GUI 编辑器** 和一个 **批量下载街景图像的主程序**，支持从指定点位读取、调用 Google Maps API 拼接图块、保存全景图像，并生成日志与结果表格。

---

## 📁 1 文件结构

```
├── config_gui.py           # GUI 配置编辑器（可打包为 exe）
├── DOWNLOAD.py             # 主下载脚本，支持多批次处理与图块拼接
├── configuration.ini       # 配置文件（首次运行自动生成）
├── POINTS.csv              # 输入点位文件（需包含 ID, Lat, Lng）
├── api_key.txt             # Google API Key 文件
└── output_dir/             # 下载图像和结果输出目录
```

---

## 📦 2 环境配置

本项目基于 **Python 3.7+**，建议使用虚拟环境管理依赖。

### ✅ 1. 安装 Python 依赖库

在命令行终端中运行以下命令安装所需依赖：

```bash
pip install -r requirements.txt
```

或手动安装：

```bash
pip install pandas requests pillow tqdm
```

如需运行 GUI 编辑器，还需安装 Tkinter（大多数系统默认自带）：
- Windows：已内置
- macOS：建议使用系统 Python
- Linux（如 Ubuntu）：

```bash
sudo apt install python3-tk
```

---

## 🛠️ 3 项目使用流程

### 1️⃣ 准备数据

- `POINTS.csv`：包含 `ID`, `Lat`, `Lng` 的点位信息
- `api_key.txt`：你的 Google API Key

---

### 2️⃣ 使用 GUI 编辑配置文件（推荐方式）

运行配置编辑器：

```bash
python GUI-RUN.py
```

或者运行打包后的可执行文件：

```bash
SVIDownloaderConfiguration.exe
```

配置参数包括：
- 数据路径
- 下载批次数
- 图像拼接大小
- 请求间隔时间等

首次运行将自动生成 `configuration.ini` 配置文件和日志模板。

---

### 3️⃣ 启动图像下载程序

运行主下载脚本：

```bash
python DOWNLOAD.py #（单线程）
```
或者

```bash
python DOWNLOAD-Multithreads.py #（多线程）
```


功能包括：
- 自动请求 panoId
- 下载并拼接图块
- 保存图像与批次结果
- 记录成功与失败日志



## 🛠️ 4 配置文件结构说明

程序运行依赖 `configuration.ini` 进行参数设定，包含三大部分：路径设置、下载控制、图块拼接设置。以下为字段解释：

### `[PATHS]` 路径设置

| 参数 | 类型 | 示例值 | 说明 |
|------|------|--------|------|
| `csv_path` | 文件路径 | `POINTS.csv` | 包含 `ID`, `Lat`, `Lng` 的点位输入文件 |
| `api_key_path` | 文件路径 | `api_key.txt` | 存储 Google API 密钥的文件 |
| `save_dir` | 文件夹路径 | `output_dir` | 下载并保存拼接图像的目录 |
| `log_path` | 文件路径 | `download_log.csv` | 成功下载记录的日志文件 |
| `fail_log_path` | 文件路径 | `failed_log.csv` | 下载失败记录及原因 |

### `[PARAMS]` 下载参数设置

| 参数 | 类型 | 示例值 | 说明 |
|------|------|--------|------|
| `batch_size` | 整数 | `10` | 每批次下载的最大图像数量 |
| `num_batches` | 整数 | `3` | 下载总批次数（循环次数）|

### `[TILES]` 图块拼接设置

| 参数 | 类型 | 示例值 | 说明 |
|------|------|--------|------|
| `zoom` | 整数（0~5） | `1` | 缩放等级，数值越大图像越清晰，图块数量越多 |
| `tile_size` | 整数 | `512` | 单个图块像素边长，建议为 512 |
| `tile_cols` | 整数 | `2` | 横向图块数量 |
| `tile_rows` | 整数 | `1` | 纵向图块数量 |
| `sleeptime` | 浮点数 | `0.02` | 每张图块下载请求间隔时间（秒），可减少限流风险 |

## 📐 5 图块(Tiles)参数说明

根据 [Google Maps Tile API](https://developers.google.com/maps/documentation/tile/streetview?hl=zh-cn#zoom-levels) 文档，不同 `zoom` 级别会影响图像分辨率和所需拼接图块数量，如下所示：

| `zoom` | 图像尺寸（像素）     | 推荐 tile_cols × tile_rows |
|--------|-----------------------|-----------------------------|
| 0      | 512 × 256             | 1 × 1                       |
| 1      | 1024 × 512            | 2 × 1                       |
| 2      | 2048 × 1024           | 4 × 2                       | 
| 3      | 4096 × 2048           | 8 × 4                       |
| 4      | 6656 × 3328           | 13 × 7                      |
| 5      | 13312 × 6656          | 26 × 13                     |

你可以根据实际需求进行设置：

- ✅ 若希望快速测试，使用 `zoom=1`, `tile_cols=2`, `tile_rows=1`
- 📸 若需高清图像输出，使用 `zoom=5`, `tile_cols=26`, `tile_rows=13`

图像输出尺寸 = `tile_size × tile_cols` 宽 × `tile_size × tile_rows` 高  
例如：

```ini
zoom = 2
tile_size = 512
tile_cols = 4
tile_rows = 2
```

✅ 可通过 `GUI-RUN.py`或 `SVIDownloaderConfiguration.exe` 图形界面轻松编辑所有参数。首次运行将自动生成该配置文件和日志模板。




## 🌐 6 Google Maps Tile API

本项目使用 [Google Maps Tile API](https://developers.google.com/maps/documentation/tile/streetview?hl=zh-cn) 获取街景图像，具体流程如下：

### 🔑 API Key 获取

1. 登录 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建项目 → 启用以下服务：
   - Maps Tile API
   - Street View Static API（用于备用或验证）
3. 生成 API 密钥，并保存为 `api_key.txt`

### 🗺️ 图像下载流程简述

1. **创建街景会话**
   - 向 `https://tile.googleapis.com/v1/createSession` 发送 POST 请求，设置参数 `"mapType": "streetview"`。
   - 获取 `session token`，用于后续请求复用。

2. **获取街景 panoId**
   - 通过经纬度坐标向 `panoIds` 接口提交 POST 请求，获取对应位置的 panoId。

3. **下载街景图块**
   - 使用以下 URL 模板，拼接多个图块获取完整图像：

     ```
     https://tile.googleapis.com/v1/streetview/tiles/{zoom}/{x}/{y}?session=...&key=...&panoId=...
     ```

4. **拼接结果**
   - 所有图块被组合为一张完整的全景街景图，保存在配置中指定的 `save_dir` 路径下。
---






## 📁 7 输出说明

成功运行后，会生成以下内容：

| 文件 | 说明 |
|------|------|
| `output_dir/*.jpg` | 拼接成功的街景图像 |
| `download_log.csv` | 成功下载的 ID 记录 |
| `failed_log.csv` | 下载失败 ID 与原因 |
| `results_batch_*.csv` | 每批次的下载结果汇总 |

---

## ❗ 8 常见问题与提示

| 问题 | 解决方案 |
|------|----------|
| API 报错 403 或无 session | 检查 API Key 是否启用了 *Street View Static API* 和 *Tile API* |
| 图像为空白 | 图块拼接失败，检查 panoId 是否有效、tile 配置是否正确 |
| 下载失败率高 | 增加 `sleeptime` 间隔，避免被限流 |
| `.exe` 无法写入文件 | 避免将程序放在系统保护目录（如 C:\ 或桌面） |
| 缺少 Tkinter 报错 | 安装 `python3-tk` 或用系统自带 Python 运行 |

---

## 📄 9 License

This project is licensed under the [MIT License](./LICENSE).  
Copyright © 2025 Zrim Young.

You are free to use, modify, and distribute this software with proper attribution.




