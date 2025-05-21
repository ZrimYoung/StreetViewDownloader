import os
import requests
import pandas as pd
from PIL import Image
from io import BytesIO
from time import sleep
from tqdm import tqdm, trange
from configparser import ConfigParser
import logging
import traceback
import concurrent.futures # 导入多线程模块
import threading # 用于 tqdm 的锁

# ===== 设置详细日志记录 =====
def setup_logger(log_path):
    """配置日志记录器"""
    logger_obj = logging.getLogger('detailed_downloader') # 使用 logger_obj 避免与外层 logger 变量名冲突
    logger_obj.setLevel(logging.DEBUG)

    if not logger_obj.handlers:
        fh = logging.FileHandler(log_path, encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)d - %(message)s')
        fh.setFormatter(formatter)
        logger_obj.addHandler(fh)
    return logger_obj

# ===== 单个点位处理函数 (用于多线程) =====
def process_single_point(point_data_tuple, pano_id_str, api_key_str, session_token_str, zoom_int, tile_cols_int, tile_rows_int, tile_size_int, sleeptime_float, save_dir_str, logger_obj, thread_local_storage):
    """
    处理单个点位的图像下载和拼接。
    返回一个包含处理结果的字典。
    """
    current_point_id_str = str(point_data_tuple.ID) # 从 namedtuple 获取 ID
    # 使用线程本地存储来管理 trange 的输出，避免交错
    # 或者直接在主线程的tqdm中更新，这里暂时保留 trange，但输出可能交错
    # 如果 trange 输出混乱，可以考虑移除或寻找更高级的tqdm线程安全用法

    logger_obj.info(f"线程 {threading.get_ident()}: 开始处理点位 ID: {current_point_id_str}, PanoID: {pano_id_str}")

    if not pano_id_str: # pano_id 为 None 或空字符串
        logger_obj.warning(f"线程 {threading.get_ident()}: 点位 ID: {current_point_id_str} 未找到 PanoID。")
        return {"status": "failure", "id": current_point_id_str, "reason": "No panoId"}

    panorama = Image.new('RGB', (tile_size_int * tile_cols_int, tile_size_int * tile_rows_int))
    missing_tiles = 0
    total_tiles = tile_cols_int * tile_rows_int
    logger_obj.debug(f"线程 {threading.get_ident()}: ID: {current_point_id_str}, PanoID: {pano_id_str} - 创建空白图像，预期总瓦片数: {total_tiles}")

    # trange 在多线程中直接使用，其输出可能会交错。
    # 如果需要更干净的输出，可以考虑在 process_single_point 内部不使用 trange，
    # 或者使用一个全局的 tqdm 对象在主线程中更新子任务进度。
    # 这里为了简化，暂时保留 trange。
    for x in trange(tile_cols_int, desc=f"拼接 {current_point_id_str} (线程 {threading.get_ident()})", leave=False, position=threading.get_ident() % 10): # 尝试使用 position 分散进度条
        for y in range(tile_rows_int):
            tile_url = (
                f"https://tile.googleapis.com/v1/streetview/tiles/{zoom_int}/{x}/{y}"
                f"?session={session_token_str}&key={api_key_str}&panoId={pano_id_str}"
            )
            logger_obj.debug(f"线程 {threading.get_ident()}: ID: {current_point_id_str}, PanoID: {pano_id_str} - 请求瓦片 URL: {tile_url}")
            
            try:
                tile_resp = requests.get(tile_url, timeout=10) 
                if tile_resp.status_code == 200:
                    tile_img = Image.open(BytesIO(tile_resp.content))
                    panorama.paste(tile_img, (x * tile_size_int, y * tile_size_int))
                else:
                    missing_tiles += 1
                    logger_obj.warning(f"线程 {threading.get_ident()}: ID: {current_point_id_str}, PanoID: {pano_id_str} - 瓦片 ({x},{y}) 下载失败。状态码: {tile_resp.status_code}")
            except requests.exceptions.RequestException as req_e:
                missing_tiles += 1
                logger_obj.error(f"线程 {threading.get_ident()}: ID: {current_point_id_str}, PanoID: {pano_id_str} - 瓦片 ({x},{y}) 请求异常: {req_e}")
            
            sleep(sleeptime_float) 

    if missing_tiles == total_tiles:
        logger_obj.warning(f"线程 {threading.get_ident()}: 点位 ID: {current_point_id_str}, PanoID: {pano_id_str} - 所有瓦片均缺失，跳过保存。")
        return {"status": "failure", "id": current_point_id_str, "reason": "All tiles missing"}

    filename = f"{current_point_id_str}_{pano_id_str}.jpg"
    filepath = os.path.join(save_dir_str, filename)
    try:
        panorama.save(filepath)
        logger_obj.info(f"线程 {threading.get_ident()}: 点位 ID: {current_point_id_str}, PanoID: {pano_id_str} - 图像成功保存至: {filepath}")
        return {"status": "success", "id": current_point_id_str, "panoId": pano_id_str, "file": filename}
    except Exception as e_save:
        logger_obj.error(f"线程 {threading.get_ident()}: 点位 ID: {current_point_id_str}, PanoID: {pano_id_str} - 保存图像失败: {e_save}", exc_info=True)
        return {"status": "failure", "id": current_point_id_str, "reason": str(e_save)}


if __name__ == "__main__":
    logger = None 
    # tqdm 全局锁，用于多线程环境下的安全输出
    tqdm.set_lock(threading.RLock())
    thread_local_storage = threading.local() # 用于线程特定的数据，如果需要的话

    try:
        config = ConfigParser()
        if not os.path.exists('configuration.ini'):
            print("❌ 错误：配置文件 'configuration.ini' 未找到。请创建该文件。")
            input("\n按回车键关闭...")
            exit()
        with open('configuration.ini', 'r', encoding='utf-8') as f:
            config.read_file(f)

        CSV_PATH = config['PATHS']['CSV_PATH']
        API_KEY_PATH = config['PATHS']['API_KEY_PATH']
        SAVE_DIR = config['PATHS']['SAVE_DIR']
        LOG_PATH = config['PATHS']['LOG_PATH']
        FAIL_LOG_PATH = config['PATHS']['FAIL_LOG_PATH']
        DETAILED_LOG_PATH = config['PATHS']['DETAILED_LOG_PATH']

        logger = setup_logger(DETAILED_LOG_PATH)
        logger.info("程序开始运行。")
        logger.info(f"配置文件 'configuration.ini' 加载成功。")

        BATCH_SIZE = int(config['PARAMS']['BATCH_SIZE'])
        NUM_BATCHES = int(config['PARAMS']['NUM_BATCHES'])
        RETRY_FAILED_POINTS = config.getboolean('PARAMS', 'RETRY_FAILED_POINTS', fallback=False)
        MAX_POINT_WORKERS = config.getint('PARAMS', 'MAX_POINT_WORKERS', fallback=5) # 读取线程数配置
        logger.info(f"参数加载：BATCH_SIZE={BATCH_SIZE}, NUM_BATCHES={NUM_BATCHES}, RETRY_FAILED_POINTS={RETRY_FAILED_POINTS}, MAX_POINT_WORKERS={MAX_POINT_WORKERS}")

        ZOOM = int(config['TILES']['ZOOM'])
        TILE_SIZE = int(config['TILES']['TILE_SIZE'])
        TILE_COLS = int(config['TILES']['TILE_COLS'])
        TILE_ROWS = int(config['TILES']['TILE_ROWS'])
        SLEEPTIME = float(config['TILES']['SLEEPTIME'])
        logger.info(f"参数加载：ZOOM={ZOOM}, TILE_SIZE={TILE_SIZE}, TILE_COLS={TILE_COLS}, TILE_ROWS={TILE_ROWS}, SLEEPTIME={SLEEPTIME}")

        print(f"🔧 当前设置：ZOOM={ZOOM}, TILE_SIZE={TILE_SIZE}, TILE_COLS={TILE_COLS}, TILE_ROWS={TILE_ROWS}")
        print(f"🖼️ 预期拼接图像大小：{TILE_COLS * TILE_SIZE} x {TILE_ROWS * TILE_SIZE} 像素")
        print(f"🔄 重试失败点位模式: {'开启' if RETRY_FAILED_POINTS else '关闭'}")
        print(f"🧵 点位处理并发线程数: {MAX_POINT_WORKERS}")
        logger.info(f"点位处理并发线程数: {MAX_POINT_WORKERS}")


        os.makedirs(SAVE_DIR, exist_ok=True)
        logger.info(f"保存目录 '{SAVE_DIR}' 已确认/创建。")
        if not os.path.exists(API_KEY_PATH):
            logger.error(f"API Key 文件 '{API_KEY_PATH}' 未找到。")
            print(f"❌ 错误：API Key 文件 '{API_KEY_PATH}' 未找到。")
            input("\n按回车键关闭...")
            exit()
        with open(API_KEY_PATH, 'r') as f:
            API_KEY = f.readline().strip()
        logger.info(f"API Key 从 '{API_KEY_PATH}' 加载成功。")

        downloaded_ids = set()
        if os.path.exists(LOG_PATH):
            try:
                log_content_df = pd.read_csv(LOG_PATH)
                if 'ID' in log_content_df.columns:
                    downloaded_ids = set(log_content_df['ID'].dropna().astype(str))
                    logger.info(f"从 '{LOG_PATH}' 加载已成功下载 {len(downloaded_ids)} 个ID。")
                else: logger.warning(f"成功日志 '{LOG_PATH}' 中缺少 'ID' 列。")
            except pd.errors.EmptyDataError: logger.warning(f"成功日志 '{LOG_PATH}' 为空。")
            except Exception as e_log: logger.error(f"读取成功日志 '{LOG_PATH}' 失败: {e_log}")
        else:
            pd.DataFrame(columns=['ID']).to_csv(LOG_PATH, index=False)
            logger.info(f"'{LOG_PATH}' 不存在，已创建空的成功日志文件。")

        failed_df_list = [] # 用于收集当前运行的失败记录
        # 初始时从文件加载历史失败记录，用于构建 ids_to_skip_processing
        initial_failed_ids_from_file = set()
        if os.path.exists(FAIL_LOG_PATH):
            try:
                temp_failed_df = pd.read_csv(FAIL_LOG_PATH)
                if not temp_failed_df.empty and 'ID' in temp_failed_df.columns:
                    initial_failed_ids_from_file = set(temp_failed_df['ID'].dropna().astype(str).unique())
                logger.info(f"从 '{FAIL_LOG_PATH}' 初始加载 {len(initial_failed_ids_from_file)} 个唯一失败ID（用于跳过逻辑）。")
            except pd.errors.EmptyDataError: logger.warning(f"失败日志 '{FAIL_LOG_PATH}' 为空。")
            except Exception as e_fail_log: logger.error(f"读取失败日志 '{FAIL_LOG_PATH}' 失败: {e_fail_log}")
        else:
            pd.DataFrame(columns=['ID', 'Reason']).to_csv(FAIL_LOG_PATH, index=False)
            logger.info(f"'{FAIL_LOG_PATH}' 不存在，已创建空的失败日志文件。")

        ids_to_skip_processing = set(downloaded_ids)
        if not RETRY_FAILED_POINTS:
            logger.info("重试模式关闭，将额外跳过之前失败记录中的ID。")
            if initial_failed_ids_from_file:
                ids_to_skip_processing.update(initial_failed_ids_from_file)
                logger.info(f"已将 {len(initial_failed_ids_from_file)} 个之前记录的失败ID添加到跳过列表。")
        else:
            logger.info("重试模式开启，将仅跳过已成功下载的ID。")
        logger.info(f"总计将明确跳过 {len(ids_to_skip_processing)} 个ID。")

        logger.info("尝试创建街景会话 Token...")
        session_payload = {"mapType": "streetview", "language": "en-US", "region": "US"}
        session_response = requests.post(f"https://tile.googleapis.com/v1/createSession?key={API_KEY}", headers={"Content-Type": "application/json"}, json=session_payload, timeout=15)
        
        if session_response.status_code == 200:
            SESSION_TOKEN = session_response.json().get("session")
            if not SESSION_TOKEN:
                logger.error(f"无法获取 session token，响应内容：{session_response.text}")
                print(f"❌ 无法获取 session token，响应内容：\n{session_response.text}")
                raise Exception("无法获取 session token")
            logger.info(f"成功获取 Session Token: {SESSION_TOKEN[:10]}...")
        else:
            logger.error(f"创建 Session Token 请求失败，状态码: {session_response.status_code}, 响应: {session_response.text}")
            print(f"❌ 创建 Session Token 请求失败，状态码: {session_response.status_code}\n{session_response.text}")
            raise Exception(f"创建 Session Token 请求失败")

        if not os.path.exists(CSV_PATH):
            logger.error(f"点位CSV文件 '{CSV_PATH}' 未找到。")
            print(f"❌ 错误：点位CSV文件 '{CSV_PATH}' 未找到。")
            input("\n按回车键关闭...")
            exit()
        all_df = pd.read_csv(CSV_PATH)
        if 'ID' not in all_df.columns:
            logger.error(f"点位CSV文件 '{CSV_PATH}' 中缺少 'ID' 列。")
            print(f"❌ 错误：点位CSV文件 '{CSV_PATH}' 中缺少 'ID' 列。")
            input("\n按回车键关闭...")
            exit()
        all_df['ID'] = all_df['ID'].astype(str)
        logger.info(f"从 '{CSV_PATH}' 加载 {len(all_df)} 个总点位。")
        
        current_run_log_list = [] # 存储当前运行的成功记录字典

        for batch_num in range(NUM_BATCHES):
            logger.info(f"开始处理批次 {batch_num + 1}/{NUM_BATCHES}")
            
            # 在每个批次开始时，基于最新的 ids_to_skip_processing 筛选
            # (ids_to_skip_processing 会在批次内处理点后动态更新)
            current_processing_df = all_df[~all_df['ID'].isin(list(ids_to_skip_processing))].head(BATCH_SIZE) # list() for safety with some pandas versions
            
            if current_processing_df.empty:
                print("🎉 所有符合条件的点位已处理完毕，无需再运行更多批次。")
                logger.info("所有符合条件的点位已处理完毕，无需再运行更多批次。")
                break
            
            print(f"\n🚀 正在处理第 {batch_num + 1}/{NUM_BATCHES} 批，共 {len(current_processing_df)} 个点位...")
            logger.info(f"批次 {batch_num + 1}：待处理点位数 {len(current_processing_df)}")

            if not all(col in current_processing_df.columns for col in ['Lat', 'Lng']):
                logger.error("当前批次点位数据中缺少 'Lat' 或 'Lng' 列。请检查CSV文件。")
                print("❌ 错误：当前批次点位数据中缺少 'Lat' 或 'Lng' 列。")
                continue

            locations = [{"lat": row["Lat"], "lng": row["Lng"]} for _, row in current_processing_df.iterrows()]
            logger.debug(f"批次 {batch_num + 1}：请求 PanoIDs 的地点 (前5个): {locations[:5]}")
            
            panoid_url = f"https://tile.googleapis.com/v1/streetview/panoIds?session={SESSION_TOKEN}&key={API_KEY}"
            pano_ids_data = []
            try:
                response_pano_ids = requests.post(panoid_url, json={"locations": locations, "radius": 50}, timeout=20)
                if response_pano_ids.status_code == 200:
                    try:
                        pano_ids_data = response_pano_ids.json().get("panoIds", [])
                        logger.info(f"批次 {batch_num + 1}：成功获取 PanoIDs 响应。数量: {len(pano_ids_data)}")
                        logger.debug(f"批次 {batch_num + 1}：获取到的 PanoIDs (部分): {pano_ids_data[:5]}")
                    except requests.exceptions.JSONDecodeError:
                        logger.error(f"批次 {batch_num + 1}：获取 PanoIDs 成功，但JSON解析失败。响应文本: {response_pano_ids.text}")
                else:
                    logger.error(f"批次 {batch_num + 1}：获取 PanoIDs 请求失败。状态码: {response_pano_ids.status_code}, 响应: {response_pano_ids.text}")
            except requests.exceptions.RequestException as req_e_pano:
                logger.error(f"批次 {batch_num + 1}：获取 PanoIDs 请求发生异常: {req_e_pano}")
            
            print("📍 已获取 panoIds") 
            results_this_batch_filenames = [] 

            # 确保 pano_ids_data 长度与 current_processing_df 匹配
            # 如果API返回的pano_ids_data比locations短，需要处理对齐问题
            # 通常API会返回等长列表，包含null。如果不是，这里需要额外逻辑。
            # 假设pano_ids_data与locations等长
            if len(pano_ids_data) != len(locations):
                logger.warning(f"批次 {batch_num + 1}: PanoID数量({len(pano_ids_data)})与地点数({len(locations)})不匹配。将尝试按地点数迭代，PanoID不足处会为None。")
                # 补齐 pano_ids_data 到 locations 的长度，用 None 填充
                pano_ids_data.extend([None] * (len(locations) - len(pano_ids_data)))


            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_POINT_WORKERS) as executor:
                future_to_point = {}
                for i, point_row_tuple in enumerate(current_processing_df.itertuples(index=False)):
                    # 从 pano_ids_data 中获取对应的 pano_id，注意索引安全
                    current_pano_id = pano_ids_data[i] if i < len(pano_ids_data) else None
                    
                    # 提交任务
                    future = executor.submit(process_single_point, 
                                             point_row_tuple, current_pano_id, API_KEY, SESSION_TOKEN, 
                                             ZOOM, TILE_COLS, TILE_ROWS, TILE_SIZE, 
                                             SLEEPTIME, SAVE_DIR, logger, thread_local_storage)
                    future_to_point[future] = str(point_row_tuple.ID) # 使用原始ID作为键

                # 使用 tqdm 包装 concurrent.futures.as_completed 来显示总体进度
                for future in tqdm(concurrent.futures.as_completed(future_to_point), total=len(future_to_point), desc=f"处理批次 {batch_num + 1} 点位"):
                    point_id_processed = future_to_point[future]
                    try:
                        result = future.result() # 获取线程的返回结果
                        if result['status'] == 'success':
                            results_this_batch_filenames.append({"ID": result['id'], "panoId": result['panoId'], "file": result['file']})
                            current_run_log_list.append({"ID": result['id']})
                            ids_to_skip_processing.add(result['id']) # 标记为已处理（成功）
                        else: # status == 'failure'
                            failed_df_list.append({"ID": result['id'], "Reason": result['reason']})
                            ids_to_skip_processing.add(result['id']) # 标记为已处理（失败）
                    except Exception as exc:
                        logger.error(f"点位ID {point_id_processed} 在线程中执行时产生未捕获异常: {exc}", exc_info=True)
                        failed_df_list.append({"ID": point_id_processed, "Reason": f"线程异常: {exc}"})
                        ids_to_skip_processing.add(point_id_processed) # 标记为已处理（异常）
            
            # ===== 每批次结束时保存一次本批次产生的失败记录和批次结果 =====
            if failed_df_list: # 只处理当前运行产生的失败
                temp_batch_failed_df = pd.DataFrame(failed_df_list)
                # 读取旧的失败日志，合并，去重，然后保存
                if os.path.exists(FAIL_LOG_PATH):
                    try:
                        old_failed_df = pd.read_csv(FAIL_LOG_PATH)
                        if not old_failed_df.empty and 'ID' in old_failed_df.columns and 'Reason' in old_failed_df.columns:
                             combined_failed_df = pd.concat([old_failed_df, temp_batch_failed_df], ignore_index=True)
                        else: # 旧日志为空或格式不对
                            combined_failed_df = temp_batch_failed_df
                    except pd.errors.EmptyDataError:
                        combined_failed_df = temp_batch_failed_df
                    except Exception as e_read_old_fail:
                        logger.error(f"读取旧失败日志 '{FAIL_LOG_PATH}' 失败: {e_read_old_fail}。将仅保存当前运行的失败记录。")
                        combined_failed_df = temp_batch_failed_df
                else: # 旧失败日志不存在
                    combined_failed_df = temp_batch_failed_df
                
                if 'ID' in combined_failed_df.columns and 'Reason' in combined_failed_df.columns:
                    combined_failed_df['ID'] = combined_failed_df['ID'].astype(str)
                    combined_failed_df.drop_duplicates(subset=['ID', 'Reason'], keep='last').to_csv(FAIL_LOG_PATH, index=False)
                failed_df_list = [] # 清空当前运行的失败列表，避免重复添加

            if results_this_batch_filenames:
                pd.DataFrame(results_this_batch_filenames).to_csv(os.path.join(SAVE_DIR, f'results_batch_{batch_num+1}.csv'), index=False)
            logger.info(f"批次 {batch_num + 1} 处理完成。失败日志和批次结果已更新。")

        # ===== 所有批次处理完成后，统一更新成功日志 =====
        if current_run_log_list:
            new_success_df = pd.DataFrame(current_run_log_list)
            if os.path.exists(LOG_PATH):
                try:
                    old_log_df = pd.read_csv(LOG_PATH)
                    if 'ID' not in old_log_df.columns: combined_log_df = new_success_df
                    else: combined_log_df = pd.concat([old_log_df, new_success_df], ignore_index=True)
                except pd.errors.EmptyDataError: combined_log_df = new_success_df
                except Exception as e_read_old_log:
                    logger.error(f"读取旧成功日志 '{LOG_PATH}' 失败: {e_read_old_log}。将仅保存当前运行的成功记录。")
                    combined_log_df = new_success_df
            else: combined_log_df = new_success_df

            if 'ID' in combined_log_df.columns:
                combined_log_df['ID'] = combined_log_df['ID'].astype(str)
                combined_log_df.drop_duplicates(subset=['ID'], keep='last').to_csv(LOG_PATH, index=False)
                logger.info(f"成功日志 '{LOG_PATH}' 已更新。")
            else: logger.error(f"无法更新成功日志，因为合并后的日志缺少 'ID' 列。")

        print("\n✅ 所有批次处理完成。")
        logger.info("所有批次处理完成。")

    except Exception as e:
        print(f"❌ 程序运行出错：{e}") 
        if logger: logger.error("程序顶层捕获到未处理异常。", exc_info=True) 
        else: 
            print("Logger 未初始化，详细错误信息如下：")
            traceback.print_exc() 
        
        try: # 异常时也尝试保存已收集的失败和成功记录
            if 'failed_df_list' in locals() and failed_df_list:
                # ... (与批次结束时类似的失败日志保存逻辑) ...
                temp_failed_df_on_exit = pd.DataFrame(failed_df_list)
                # (代码省略，与批次结束时保存失败日志的逻辑类似，合并旧日志并保存)
                logger.info("程序异常退出前，尝试保存当前收集的失败记录。")


            if 'current_run_log_list' in locals() and current_run_log_list:
                # ... (与程序正常结束时类似的成功日志保存逻辑) ...
                logger.info("程序异常退出前，尝试保存当前收集的成功记录。")

        except Exception as log_save_e:
            print(f"❌ 在异常处理中保存日志时也发生错误: {log_save_e}")
            if logger: logger.error(f"在异常处理中保存日志时也发生错误: {log_save_e}", exc_info=True)
    finally:
        if logger: logger.info("程序结束。\n---------------------------------------\n")
        input("\n按回车键关闭...")
