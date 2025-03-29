
# 🏙️ Google 街景图像批量下载工具

本项目包含一个 **配置文件 GUI 编辑器** 和一个 **批量下载街景图像的主程序**，支持从指定点位读取、调用 Google Maps API 拼接图块、保存全景图像，并生成日志与结果表格。

---

## 📁 文件结构

```
├── config_gui.py           # GUI 配置编辑器（可打包为 exe）
├── DOWNLOAD.py             # 主下载脚本，支持多批次处理与图块拼接
├── configuration.ini       # 配置文件（首次运行自动生成）
├── POINTS.csv              # 输入点位文件（需包含 ID, Lat, Lng）
├── api_key.txt             # Google API Key 文件
└── output_dir/             # 下载图像和结果输出目录
```

---

## 📦 环境配置

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

## 🛠️ 项目使用流程

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

---

## 🔧 配置文件结构说明

`configuration.ini` 是程序的核心参数文件，示例如下：

```ini
[PATHS]
csv_path = POINTS.csv
api_key_path = api_key.txt
save_dir = output_dir
log_path = download_log.csv
fail_log_path = failed_log.csv

[PARAMS]
batch_size = 10
num_batches = 3

[TILES]
zoom = 1
tile_size = 512
tile_cols = 2
tile_rows = 1
sleeptime = 0.02
```

---


## 📁 输出说明

成功运行后，会生成以下内容：

| 文件 | 说明 |
|------|------|
| `output_dir/*.jpg` | 拼接成功的街景图像 |
| `download_log.csv` | 成功下载的 ID 记录 |
| `failed_log.csv` | 下载失败 ID 与原因 |
| `results_batch_*.csv` | 每批次的下载结果汇总 |

---

## ❗ 常见问题与提示

| 问题 | 解决方案 |
|------|----------|
| API 报错 403 或无 session | 检查 API Key 是否启用了 *Street View Static API* 和 *Tile API* |
| 图像为空白 | 图块拼接失败，检查 panoId 是否有效、tile 配置是否正确 |
| 下载失败率高 | 增加 `sleeptime` 间隔，避免被限流 |
| `.exe` 无法写入文件 | 避免将程序放在系统保护目录（如 C:\ 或桌面） |
| 缺少 Tkinter 报错 | 安装 `python3-tk` 或用系统自带 Python 运行 |

---





