[🇨🇳 中文版](./README.md) | [🇺🇸 English Version](./README_EN.md)

---

# 🏙️ Google 街景图像批量下载工具

本项目包含一个 **配置文件 GUI 编辑器** 和一个 **批量下载街景图像的主程序**，支持从指定点位读取、调用 Google Maps API 拼接图块、保存全景图像，并生成日志与结果表格。

---

## 📁 1 文件结构

```
┌ GUI-RUN.py                 # 配置文件图形化编辑器
├ DOWNLOAD-Multithreads.py  # 多线程街景图像下载脚本
├ process_panorama_images.py # 全景图像黑边检测和处理脚本
├ configuration.ini         # 配置文件（首次运行自动生成）
├ POINTS.csv                # 输入坐标点数据（需包含 ID, Lat, Lng）
├ api_key.txt               # Google API Key 文件
└ output_dir/               # 下载图像及结果保存目录
```

---

## 📦 2 环境配置

本项目基于 **Python 3.7+**，建议使用虚拟环境管理依赖。

### 安装 Python 依赖库

在命令行终端中运行以下命令安装所需依赖：

```bash
pip install -r requirements.txt
```

或手动安装：

```bash
pip install pandas requests pillow tqdm opencv-python
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

功能：
- 自动创建 session 并获取 panoId
- 使用多线程下载并拼接图像
- 实时进度显示（`tqdm`）
- 自动跳过已成功/失败记录（可配置是否重试失败项）
- 输出成功图像、失败记录和批次结果

---

### 4️⃣ 处理全景图像（可选）

如果下载的全景图像存在底部黑边问题，可以使用图像处理脚本进行自动修复：

```bash
python process_panorama_images.py
```

功能特性：
- **智能黑边检测**：专门针对底部黑边进行优化检测
- **自动裁剪修复**：从左上角开始裁剪，保持2:1宽高比
- **多线程处理**：支持批量并行处理，显著提升处理速度
- **进度保存**：支持中断恢复，避免重复处理
- **分类管理**：
  - 正常图像：保持原位置不变
  - 有黑边图像：原图移至 `problematic/` 文件夹，处理后图像保存至 `edit/` 文件夹
- **详细日志**：记录处理过程和统计信息

**配置说明**（在脚本顶部修改）：
- `INPUT_DIR`：输入图片目录（默认：`"panoramas_test"`）
- `OUTPUT_DIR`：处理后图片输出目录（默认：`"edit"`）
- `PROBLEMATIC_DIR`：有问题图片移动目录（默认：`"problematic"`）
- `NUM_WORKERS`：并行处理线程数（默认：15）
- `BLACK_THRESHOLD`：黑边检测阈值（默认：15）

## 🛠️ 4 配置文件结构说明

程序运行依赖 `configuration.ini` 进行参数设定，包含三大部分：路径设置、下载控制、图块拼接设置。以下为字段解释：

### [PATHS] 路径配置
- `csv_path`: 点位输入文件路径
- `api_key_path`: 存储 API Key 的文本路径
- `save_dir`: 图像保存目录
- `log_path`: 成功记录日志
- `fail_log_path`: 失败记录日志
- `detailed_log_path`: 详细日志（包含异常信息）

### [PARAMS] 下载参数
- `retry_failed_points`: 是否重试失败点位（True/False）
- `batch_size`: 每批次最大下载数
- `num_batches`: 总批次数
- `max_point_workers`: 下载线程数（并发点位处理）

### [TILES] 图块参数
- `zoom`: 图像缩放等级（0~5）
- `tile_size`: 每个图块尺寸（px）
- `tile_cols`, `tile_rows`: 拼接图块数（列 × 行）
- `sleeptime`: 每张图块请求间隔（单位秒）

GUI 中支持图块参数预设选择（Zoom 0 - Zoom 5），也可启用自定义（Custom）。

---

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
| `detailed_run.log` | 含异常栈信息的运行日志 |

**使用全景图处理脚本后还会生成：**

| 文件/文件夹 | 说明 |
|-------------|------|
| `edit/*.jpg` | 处理后的图像（去除黑边并修复） |
| `problematic/*.jpg` | 检测到有黑边问题的原始图像 |
| `processing_progress.json` | 处理进度保存文件（支持中断恢复） |
| `panorama_processing_*.log` | 图像处理详细日志 |

---

## ❗ 8 常见问题与提示

| 问题 | 解决方案 |
|------|----------|
| API 报错 403 或无 session | 检查 API Key 是否启用了 *Tile API* |
| 图像为空白 | 图块拼接失败，检查 panoId 是否有效、tile 配置是否正确 |
| 下载失败率高 | 增加 `sleeptime` 间隔，避免被限流 |
| `.exe` 无法写入文件 | 避免将程序放在系统保护目录（如 C:\ 或桌面） |
| 缺少 Tkinter 报错 | 安装 `python3-tk` 或用系统自带 Python 运行 |
| 图像处理脚本无法运行 | 确保已安装 `opencv-python`：`pip install opencv-python` |
| 处理脚本找不到图片 | 检查 `INPUT_DIR` 配置是否正确，确保目录中有图片文件 |
| 处理后图像质量下降 | 可调整 `BLACK_THRESHOLD` 阈值或检查原图质量 |

---

## 📄 9 License

This project is licensed under the [MIT License](./LICENSE).  
Copyright © 2025 Zrim Young.

You are free to use, modify, and distribute this software with proper attribution.




