[🇨🇳 Chinese Version](./README.md) | [🇺🇸 English Version](./README_EN.md)

---

# 🏙️ Google Street View Bulk Image Downloader

This project includes a **GUI-based configuration editor** and a **multi-threaded main download program** that supports reading coordinates, calling the Google Maps API to stitch tiles, saving panorama images, and generating logs and result tables.

---

## 📁 1. File Structure

```
┌ GUI-RUN.py                 # GUI configuration editor
├ DOWNLOAD-Multithreads.py  # Multi-threaded Street View image downloader
├ process_panorama_images.py # Panoramic image black border detection and processing script
├ configuration.ini         # Configuration file (auto-generated on first run)
├ POINTS.csv                # Input coordinates file (must include ID, Lat, Lng)
├ api_key.txt               # Google API Key file
└ output_dir/               # Output directory for downloaded images and logs
```

---

## 📦 2. Environment Setup

The project is built with **Python 3.7+**. A virtual environment is recommended.

### Install Python Dependencies

Run the following command to install required libraries:

```bash
pip install -r requirements.txt
```

Or manually:

```bash
pip install pandas requests pillow tqdm opencv-python
```

To run the GUI editor, Tkinter is also needed (included by default on most systems):
- Windows: pre-installed
- macOS: use system Python
- Linux (e.g., Ubuntu):

```bash
sudo apt install python3-tk
```

---

## 🛠️ 3. How to Use the Project

### 1️⃣ Prepare Your Data

- `POINTS.csv`: contains point info with `ID`, `Lat`, `Lng`
- `api_key.txt`: contains your Google API Key

---

### 2️⃣ Edit Configuration with GUI (Recommended)

Run the configuration editor:

```bash
python GUI-RUN.py
```

Or run the packaged executable:

```bash
SVIDownloaderConfiguration.exe
```

Configurable parameters include:
- File paths
- Batch count
- Image tile stitching size
- Sleep time between requests

First run will automatically generate `configuration.ini` and log templates.

---

### 3️⃣ Start the Download Program

Run the main script:

```bash
python DOWNLOAD.py # (Single-threaded)
```
or
```bash
python DOWNLOAD-Multithreads.py # (Multi-threaded)
```

Features:
- Automatically create session and get panoId
- Download and stitch tiles concurrently
- Live progress display (`tqdm`)
- Skip completed/failed records (configurable retry)
- Output images, failure logs, and batch results

---

### 4️⃣ Process Panoramic Images (Optional)

If your downloaded panoramic images have bottom black border issues, you can use the image processing script for automatic repair:

```bash
python process_panorama_images.py
```

Key Features:
- **Smart Black Border Detection**: Optimized specifically for bottom black border detection
- **Automatic Crop & Repair**: Crops from top-left corner, maintains 2:1 aspect ratio
- **Multi-threaded Processing**: Supports batch parallel processing for significant speed improvement
- **Progress Saving**: Supports interruption recovery to avoid reprocessing
- **Categorized Management**:
  - Normal images: Keep in original location
  - Images with black borders: Original moved to `problematic/` folder, processed images saved to `edit/` folder
- **Detailed Logging**: Records processing progress and statistics

**Configuration** (modify at the top of the script):
- `INPUT_DIR`: Input image directory (default: `"panoramas_test"`)
- `OUTPUT_DIR`: Processed image output directory (default: `"edit"`)
- `PROBLEMATIC_DIR`: Problematic image directory (default: `"problematic"`)
- `NUM_WORKERS`: Number of parallel processing threads (default: 15)
- `BLACK_THRESHOLD`: Black border detection threshold (default: 15)

---

## 🛠️ 4. Configuration File Structure

The program uses `configuration.ini` for all parameters. It contains three main sections:

### [PATHS] Path Settings
- `csv_path`: input CSV with coordinates
- `api_key_path`: file with your API key
- `save_dir`: output folder for images
- `log_path`: file to log successful downloads
- `fail_log_path`: file to record failed attempts
- `detailed_log_path`: file for detailed runtime logs

### [PARAMS] Download Parameters
- `retry_failed_points`: whether to retry failed points (True/False)
- `batch_size`: max number of images per batch
- `num_batches`: total batch cycles
- `max_point_workers`: number of concurrent threads

### [TILES] Tile Parameters
- `zoom`: zoom level (0–5)
- `tile_size`: pixel size of each tile
- `tile_cols`, `tile_rows`: number of tiles per row/column
- `sleeptime`: interval between requests (seconds)

GUI provides presets (Zoom 0–5) or allows custom tile settings.

---

## 📐 5. Tile Parameters Overview

Based on [Google Maps Tile API](https://developers.google.com/maps/documentation/tile/streetview?hl=en), different `zoom` levels affect image resolution and tile count:

| `zoom` | Image Size (px)      | Suggested tile_cols × tile_rows |
|--------|-----------------------|-------------------------------|
| 0      | 512 × 256             | 1 × 1                         |
| 1      | 1024 × 512            | 2 × 1                         |
| 2      | 2048 × 1024           | 4 × 2                         |
| 3      | 4096 × 2048           | 8 × 4                         |
| 4      | 6656 × 3328           | 13 × 7                        |
| 5      | 13312 × 6656          | 26 × 13                       |

Example:
```ini
zoom = 2
tile_size = 512
tile_cols = 4
tile_rows = 2
```

✅ Easily configured via `GUI-RUN.py` or executable. Auto-generates config and logs on first use.

---

## 🌐 6. Google Maps Tile API Overview

The project uses the [Google Maps Tile API](https://developers.google.com/maps/documentation/tile/streetview?hl=en) to retrieve images.

### 🔑 Get an API Key

1. Visit [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable:
   - Maps Tile API
3. Generate an API key and save it to `api_key.txt`

### 🗺️ Image Download Workflow

1. **Create a session**
   - POST to `https://tile.googleapis.com/v1/createSession` with `"mapType": "streetview"`
   - Receive `session token`

2. **Get panoId**
   - POST coordinates to the `panoIds` endpoint

3. **Download tiles**
   - Use this format:

     ```
     https://tile.googleapis.com/v1/streetview/tiles/{zoom}/{x}/{y}?session=...&key=...&panoId=...
     ```

4. **Stitch the image**
   - Combine tiles into one panorama and save to `save_dir`

---

## 📁 7. Output Description

After successful runs, the following files will be generated:

| File | Description |
|------|-------------|
| `output_dir/*.jpg` | Final stitched panorama images |
| `download_log.csv` | Log of successful downloads |
| `failed_log.csv` | Failed points and reasons |
| `results_batch_*.csv` | Per-batch result summaries |
| `detailed_run.log` | Full log including exceptions |

**After using the panoramic image processing script:**

| File/Folder | Description |
|-------------|-------------|
| `edit/*.jpg` | Processed images (black borders removed and repaired) |
| `problematic/*.jpg` | Original images with detected black border issues |
| `processing_progress.json` | Processing progress save file (supports interruption recovery) |
| `panorama_processing_*.log` | Detailed image processing logs |

---

## ❗ 8. Common Issues & Tips

| Issue | Solution |
|-------|----------|
| 403 or no session | Check if API has Tile API enabled |
| Blank image | Possibly invalid panoId or tile config error |
| High failure rate | Increase `sleeptime` to avoid rate limits |
| `.exe` can't write files | Avoid protected directories like `C:\` or desktop |
| Missing Tkinter | Install `python3-tk` or use system Python |
| Image processing script won't run | Make sure `opencv-python` is installed: `pip install opencv-python` |
| Processing script can't find images | Check if `INPUT_DIR` configuration is correct and images exist in directory |
| Processed image quality degraded | Adjust `BLACK_THRESHOLD` value or check original image quality |

---

## 📄 9. License

This project is licensed under the [MIT License](./LICENSE).  
Copyright © 2025 Zrim Young.

You are free to use, modify, and distribute this software with proper attribution.
