# 增加多批次处理和批次进度条支持的 Google 街景图像下载脚本
# ✅ 功能包括：
#   - 从 CSV 文件读取点位信息
#   - 使用 Google Maps API 批量请求街景图像并拼接
#   - 支持配置文件自定义参数
#   - 下载进度可视化（支持批次和单点拼接进度）

import os
import json
import requests
import pandas as pd
from PIL import Image
from io import BytesIO
from time import sleep
from tqdm import tqdm, trange  # tqdm：主进度条；trange：图块拼接进度
from configparser import ConfigParser  # 用于读取 INI 配置文件

# ===== 从 configuration.ini 读取参数 =====
config = ConfigParser()
with open('configuration.ini', 'r', encoding='utf-8') as f:
    config.read_file(f)  # 加载配置文件


# [PATHS] 路径配置：输入/输出/日志等路径
CSV_PATH = config['PATHS']['CSV_PATH']               # 输入的点位CSV文件路径
API_KEY_PATH = config['PATHS']['API_KEY_PATH']       # Google API Key 文件路径
SAVE_DIR = config['PATHS']['SAVE_DIR']               # 拼接图像保存目录
LOG_PATH = config['PATHS']['LOG_PATH']               # 成功下载记录CSV路径
FAIL_LOG_PATH = config['PATHS']['FAIL_LOG_PATH']     # 失败下载记录CSV路径

# [PARAMS] 下载控制参数：批次数、每批数量等
BATCH_SIZE = int(config['PARAMS']['BATCH_SIZE'])     # 每批下载的点位数上限
NUM_BATCHES = int(config['PARAMS']['NUM_BATCHES'])   # 批次数量（循环几轮）

# [TILES] 图块配置参数：拼接视角、尺寸等
ZOOM = int(config['TILES']['ZOOM'])                  # 缩放等级（0~5）
TILE_SIZE = int(config['TILES']['TILE_SIZE'])        # 图块尺寸（像素）
TILE_COLS = int(config['TILES']['TILE_COLS'])        # 横向拼接图块数量
TILE_ROWS = int(config['TILES']['TILE_ROWS'])        # 纵向拼接图块数量
SLEEPTIME = float(config['TILES']['SLEEPTIME'])      # 每张图块之间的请求延迟（秒）

# ===== 输出当前拼接图像参数（便于确认设置） =====
print(f"🔧 当前设置：ZOOM={ZOOM}, TILE_SIZE={TILE_SIZE}, TILE_COLS={TILE_COLS}, TILE_ROWS={TILE_ROWS}")
print(f"🖼️ 预期拼接图像大小：{TILE_COLS * TILE_SIZE} x {TILE_ROWS * TILE_SIZE} 像素")

# ===== 初始化保存目录和 API 密钥 =====
os.makedirs(SAVE_DIR, exist_ok=True)  # 如果保存目录不存在就创建
with open(API_KEY_PATH, 'r') as f:
    API_KEY = f.readline().strip()  # 读取 Google Maps API Key

# ===== 初始化日志记录（避免重复下载） =====
if os.path.exists(LOG_PATH):
    downloaded_ids = set(pd.read_csv(LOG_PATH)['ID'].astype(str))  # 已下载ID集合
else:
    downloaded_ids = set()
    pd.DataFrame(columns=['ID']).to_csv(LOG_PATH, index=False)  # 创建空日志文件

if os.path.exists(FAIL_LOG_PATH):
    failed_df = pd.read_csv(FAIL_LOG_PATH)  # 读取失败记录
else:
    failed_df = pd.DataFrame(columns=['ID', 'Reason'])  # 初始化失败日志

# ===== 创建街景会话 Token，便于后续 API 请求复用 =====
session_payload = {
    "mapType": "streetview",
    "language": "en-US",
    "region": "US"
}
session_response = requests.post(
    f"https://tile.googleapis.com/v1/createSession?key={API_KEY}",
    headers={"Content-Type": "application/json"},
    json=session_payload
)
SESSION_TOKEN = session_response.json().get("session")
if not SESSION_TOKEN:
    print("❌ 无法获取 session token，响应内容：")
    print(session_response.text)
    raise Exception("无法获取 session token，请检查 API Key 或 mapType 设置")

# ===== 读取完整点位表，并加载成功记录表 =====
all_df = pd.read_csv(CSV_PATH)  # 所有点位
log_df = pd.read_csv(LOG_PATH)  # 下载成功记录

# ===== 主循环：控制多批次下载 =====
for batch_num in range(NUM_BATCHES):
    # 过滤出未下载的点位，按批量抓取
    df = all_df[~all_df['ID'].astype(str).isin(downloaded_ids)].head(BATCH_SIZE)
    if df.empty:
        print("🎉 所有点位已处理完毕，无需再运行更多批次。")
        break

    print(f"\n🚀 正在处理第 {batch_num + 1}/{NUM_BATCHES} 批，共 {len(df)} 个点位...")

    # 为当前批次的点位获取对应 panoId
    locations = [{"lat": row["Lat"], "lng": row["Lng"]} for _, row in df.iterrows()]
    panoid_url = f"https://tile.googleapis.com/v1/streetview/panoIds?session={SESSION_TOKEN}&key={API_KEY}"
    response = requests.post(panoid_url, json={"locations": locations, "radius": 50})
    pano_ids = response.json().get("panoIds", [])
    print("📍 已获取 panoIds")

    results = []  # 存储当前批次结果信息

    # ===== 遍历每个点位，处理拼接 =====
    for i, (row, pano_id) in enumerate(tqdm(zip(df.itertuples(index=False), pano_ids), total=len(df), desc=f"批次 {batch_num + 1}"), start=1):
        if not pano_id:
            # 无 panoId 情况，跳过并记录失败
            failed_df = pd.concat([failed_df, pd.DataFrame([{"ID": row.ID, "Reason": "No panoId"}])], ignore_index=True)
            continue

        # 创建一张空白图像用于拼接全景
        panorama = Image.new('RGB', (TILE_SIZE * TILE_COLS, TILE_SIZE * TILE_ROWS))
        missing_tiles = 0  # 缺失图块计数器
        total_tiles = TILE_COLS * TILE_ROWS

        # ===== 下载每个图块，并逐一拼接（带进度条） =====
        for x in trange(TILE_COLS, desc=f"拼接 {row.ID}", leave=False):
            for y in range(TILE_ROWS):
                tile_url = (
                    f"https://tile.googleapis.com/v1/streetview/tiles/{ZOOM}/{x}/{y}"
                    f"?session={SESSION_TOKEN}&key={API_KEY}&panoId={pano_id}"
                )
                tile_resp = requests.get(tile_url)
                if tile_resp.status_code == 200:
                    tile_img = Image.open(BytesIO(tile_resp.content))
                    panorama.paste(tile_img, (x * TILE_SIZE, y * TILE_SIZE))
                else:
                    missing_tiles += 1  # 若 tile 缺失，计数
                sleep(SLEEPTIME)

        # 如果全部图块都缺失，则跳过保存
        if missing_tiles == total_tiles:
            failed_df = pd.concat([failed_df, pd.DataFrame([{"ID": row.ID, "Reason": "All tiles missing"}])], ignore_index=True)
            continue

        # 保存成功拼接的图像
        filename = f"{row.ID}_{pano_id}.jpg"
        filepath = os.path.join(SAVE_DIR, filename)
        try:
            panorama.save(filepath)
            results.append({"ID": row.ID, "panoId": pano_id, "file": filename})
            log_df = pd.concat([log_df, pd.DataFrame([{"ID": row.ID}])], ignore_index=True)
            downloaded_ids.add(str(row.ID))
        except Exception as e:
            # 保存失败情况
            failed_df = pd.concat([failed_df, pd.DataFrame([{"ID": row.ID, "Reason": str(e)}])], ignore_index=True)

    # ===== 保存日志与结果 =====
    log_df.drop_duplicates().to_csv(LOG_PATH, index=False)
    failed_df.drop_duplicates().to_csv(FAIL_LOG_PATH, index=False)
    pd.DataFrame(results).to_csv(os.path.join(SAVE_DIR, f'results_batch_{batch_num+1}.csv'), index=False)

print("\n✅ 所有批次处理完成。")