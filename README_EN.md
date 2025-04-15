[🇨🇳 中文版](./README.md) | [🇺🇸 English Version](./README_EN.md)

---

# 🎙️ Google Street View Batch Downloader Tool

This project includes a **GUI configuration editor** and a **main program for batch downloading Google Street View images**. It supports reading from specified coordinates, calling the Google Maps Tile API to download tiles, stitching them into panoramas, saving images, and generating logs and summary tables.

---

## 📁 1 File Structure

```
├── config_gui.py           # GUI configuration editor (can be packaged into .exe)
├── DOWNLOAD.py             # Main download script; supports batch processing and tile stitching
├── configuration.ini       # Config file (auto-generated on first run)
├── POINTS.csv              # Input points file (should include ID, Lat, Lng)
├── api_key.txt             # Google API Key file
└── output_dir/             # Directory for downloaded and stitched images
```

---

## 🛆 2 Environment Setup

This project requires **Python 3.7+**. It's recommended to use a virtual environment.

### Install Python Dependencies

Run the following command in terminal to install required packages:

```bash
pip install -r requirements.txt
```

Or install manually:

```bash
pip install pandas requests pillow tqdm
```

To run the GUI, ensure Tkinter is installed (pre-installed on most systems):

- Windows: Already included
- macOS: Use the system Python
- Linux (e.g. Ubuntu):

```bash
sudo apt install python3-tk
```

---

## 🛠️ 3 How to Use

### 1️⃣ Prepare Input Data

- `POINTS.csv`: Contains `ID`, `Lat`, and `Lng` columns
- `api_key.txt`: Your Google API Key

---

### 2️⃣ Edit Config with GUI (Recommended)

Run the GUI config editor:

```bash
python GUI-RUN.py
```

Or run the packaged executable:

```bash
SVIDownloaderConfiguration.exe
```

Editable parameters include:
- File paths
- Number of batches
- Tile dimensions
- Request intervals, etc.

The config file `configuration.ini` and log template are auto-generated on first run.

---

### 3️⃣ Start Download Script

Run the main download script:

```bash
python DOWNLOAD.py # (Single-threaded)
```
Or

```bash
python DOWNLOAD-Multithreads.py # (Multi-threaded)
```

Features include:
- Automatically requesting panoId
- Downloading and stitching tiles
- Saving images and results
- Logging success and failure records

---

## 🛠️ 4 Config File Structure

The program relies on `configuration.ini` to set parameters. It consists of three parts: paths, download settings, and tile settings. Explanation below:

### `[PATHS]`

| Parameter | Type | Example | Description |
|----------|------|---------|-------------|
| `csv_path` | file path | `POINTS.csv` | Input point file with ID, Lat, Lng |
| `api_key_path` | file path | `api_key.txt` | Google API key file |
| `save_dir` | directory path | `output_dir` | Save directory for stitched images |
| `log_path` | file path | `download_log.csv` | Log for successful downloads |
| `fail_log_path` | file path | `failed_log.csv` | Log for failed downloads |

### `[PARAMS]`

| Parameter | Type | Example | Description |
|----------|------|---------|-------------|
| `batch_size` | integer | `10` | Max images per batch |
| `num_batches` | integer | `3` | Total number of batches (loops) |

### `[TILES]`

| Parameter | Type | Example | Description |
|----------|------|---------|-------------|
| `zoom` | integer (0~5) | `1` | Zoom level (higher = clearer, more tiles) |
| `tile_size` | integer | `512` | Tile side length in pixels |
| `tile_cols` | integer | `2` | Number of columns of tiles |
| `tile_rows` | integer | `1` | Number of rows of tiles |
| `sleeptime` | float | `0.02` | Delay between tile requests (in seconds) |

---

## 📀 5 Tile Parameters

According to the [Google Maps Tile API](https://developers.google.com/maps/documentation/tile/streetview?hl=en#zoom-levels), different `zoom` levels affect resolution and number of tiles. Reference:

| `zoom` | Image Size (pixels) | Suggested tile_cols × tile_rows |
|--------|---------------------|----------------------------------|
| 0      | 512 × 256           | 1 × 1                            |
| 1      | 1024 × 512          | 2 × 1                            |
| 2      | 2048 × 1024         | 4 × 2                            |
| 3      | 4096 × 2048         | 8 × 4                            |
| 4      | 6656 × 3328         | 13 × 7                           |
| 5      | 13312 × 6656        | 26 × 13                          |

You may adjust settings depending on your need:

- ✅ For quick testing: `zoom=1`, `tile_cols=2`, `tile_rows=1`
- 📸 For high resolution: `zoom=5`, `tile_cols=26`, `tile_rows=13`

Image output size = `tile_size × tile_cols` width × `tile_size × tile_rows` height  
Example:

```ini
zoom = 2
tile_size = 512
tile_cols = 4
tile_rows = 2
```

✅ Use `GUI-RUN.py` or `SVIDownloaderConfiguration.exe` for easy editing. Files are auto-generated on first run.

---

## 🌐 6 Google Maps Tile API

This project uses [Google Maps Tile API](https://developers.google.com/maps/documentation/tile/streetview?hl=en) to download Street View imagery.

### 🔑 API Key Setup

1. Visit [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable:
   - Maps Tile API
   - Street View Static API (optional backup)
3. Generate and save your API key in `api_key.txt`

### 🗺️ Download Process Overview

1. **Create Street View Session**  
   - POST to `https://tile.googleapis.com/v1/createSession` with `"mapType": "streetview"`  
   - Receive a session token

2. **Get panoId**
   - POST coordinates to `panoIds` API to get panorama ID

3. **Download Tiles**
   - Use this URL template to download tiles:

     ```
     https://tile.googleapis.com/v1/streetview/tiles/{zoom}/{x}/{y}?session=...&key=...&panoId=...
     ```

4. **Stitch Results**
   - All tiles are merged into one panorama and saved in `save_dir`

---

## 📁 7 Output Explanation

After running successfully, the following files will be generated:

| File | Description |
|------|-------------|
| `output_dir/*.jpg` | Stitched Street View images |
| `download_log.csv` | Log of successful downloads |
| `failed_log.csv` | Log of failures and reasons |
| `results_batch_*.csv` | Summary per batch |

---

## ❗ 8 Common Issues & Tips

| Issue | Solution |
|-------|----------|
| 403 or no session | Ensure *Street View Static API* and *Tile API* are enabled |
| Blank image | Check panoId validity and tile settings |
| High failure rate | Increase `sleeptime` to reduce throttling |
| `.exe` can't write files | Avoid running in protected directories (like `C:\` or desktop) |
| Tkinter missing | Install `python3-tk` or use system Python |

---

## 📄 9 License

This project is licensed under the [MIT License](./LICENSE).  
© 2025 Zrim Young.

You are free to use, modify, and distribute this software with proper attribution.

