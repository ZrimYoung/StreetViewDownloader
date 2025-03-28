# 🗺️ StreetViewDownloader

一个基于 Python 的可视化工具，用于**批量下载并拼接 Google 街景图像**，支持通过 CSV 坐标点配置、参数自定义和 EXE 打包运行，特别适合用于城市研究、街景分析、语义分割预处理等应用场景。

> 🔧 项目适配自《MUDP2020 Values of Urban Design》的 Assignment 4 Part II 要求，支持 QGIS 点导入和分段拼接。

---

## ✨ 功能特点

- ✅ **图形化配置界面**（使用 `Tkinter`）便于设置路径、参数
- ✅ **自动下载街景图像**，支持多批次处理 + 图块拼接
- ✅ **兼容打包为 `.exe`**，无需 Python 环境即可运行
- ✅ **日志记录** 成功和失败点，自动避免重复下载
- ✅ 支持配置文件自动生成、路径校验、可视化下载进度

---

## 🗂️ 项目结构

## 🗂️ 项目结构

```
StreetViewDownloader/
├── GUI-RUN.py              # 主程序（推荐入口，带运行按钮）
├── work-ui.py              # 副程序：街景下载逻辑
├── configuration.ini       # 配置文件（可通过 GUI 自动生成）
├── POINTS.csv              # 示例点位文件（含ID,Lat,Lng）
├── api_key.txt             # 存储 Google Maps API Key
├── icon.ico                # 打包使用的图标（可选）
├── README.md               # 项目说明文件
├── requirements.txt        # 项目依赖列表
├── StreetViewDownloader.spec  # PyInstaller 打包配置文件
├── dist/
│   └── StreetViewDownloader/
│       └── StreetViewDownloader.exe  # ✅ 已打包好的可执行文件
└── build/                  # PyInstaller 构建缓存（可忽略）
```

---

## 🚀 快速开始

### 1️⃣ 安装依赖（如使用源码）
```bash
pip install -r requirements.txt
```

### 2️⃣ 启动配置界面
```bash
python GUI3.py
```

- 使用界面设置 `CSV路径`、`API Key`、输出目录等参数
- 点击“保存配置”后再点击“运行下载器”开始下载

### 3️⃣ 准备坐标点文件（CSV）
CSV 文件应包含以下字段：
```csv
ID,Lat,Lng
001,22.302711,114.177216
002,22.284900,114.158917
...
```

---

## 🧰 运行说明

- `GUI3.py`：图形化配置工具，生成 `configuration.ini`
- `work-ui.py`：通过 Google Maps Tile API 下载街景图块并拼接为全景图

拼接结果保存在配置文件中指定的 `save_dir` 目录下，命名格式为：
```
<ID>_<panoId>.jpg
```

---

## 🔧 打包为 EXE（可选）

如果你希望将其部署给非开发者用户，可使用以下命令打包为 `.exe`：

```bash
pyinstaller --noconsole --add-data "work-ui.py;." --name "StreetViewDownloader" GUI3.py
```

打包成功后将在 `dist/StreetViewDownloader/StreetViewDownloader.exe` 中生成可运行程序。

---

## 📊 下载结果

运行后程序会自动生成：

- `download_log.csv`：已成功下载的 ID 记录
- `failed_log.csv`：失败点及原因（无 panoId、拼接失败等）
- `results_batch_*.csv`：每批次下载的详细结果（含文件名）

---

## 📦 依赖库

```txt
pandas
requests
tqdm
Pillow
```

---

## 🧠 TODO / 可拓展功能

- [ ] 多线程加速下载
- [ ] 异常 tile 缓存与重试机制
- [ ] 下载前地图可视化预览
- [ ] 结合 Folium / Leaflet 展示拼接图坐标分布

---

## 📜 License

MIT License © 2025 ZrimYoung

