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
import json # 导入 json 模块，用于解析API错误响应
import sys # 导入 sys 模块，用于配置基本日志器的输出流

# --- 错误类型常量 ---
# 定义各种可能的错误类型，用于更细致地记录失败原因

# 永久性错误：这些错误通常指示数据本身的问题，或需要人工干预，在重试模式下会被跳过。
ERROR_TYPE_NO_PANOID_FOUND = "NO_PANOID_FOUND" # 坐标处没有找到PanoId (API返回空字符串)

# 可重试错误：这些错误通常是暂时性的，或者在重试模式下我们希望再次尝试。
ERROR_TYPE_ALL_TILES_MISSING = "ALL_TILES_MISSING_AFTER_RETRIES" # 所有瓦片下载失败（可能因404或持续网络问题）
ERROR_TYPE_API_AUTH_FORBIDDEN = "API_AUTH_FORBIDDEN" # 401/403 权限或配额问题 (通常致命，但根据新策略会重试)
ERROR_TYPE_API_BAD_REQUEST = "API_BAD_REQUEST" # 400 请求参数错误 (通常是客户端问题，但根据新策略会重试)
ERROR_TYPE_INTERNAL_PROCESSING_ERROR = "INTERNAL_PROCESSING_ERROR" # 内部处理错误（如PIL图像处理，文件保存）
ERROR_TYPE_NETWORK_TIMEOUT = "NETWORK_TIMEOUT" # 网络请求超时
ERROR_TYPE_NETWORK_CONNECTION_ERROR = "NETWORK_CONNECTION_ERROR" # 网络连接错误
ERROR_TYPE_API_RATE_LIMIT = "API_RATE_LIMIT" # 429 速率限制 (需要指数退避)
ERROR_TYPE_API_SERVER_ERROR = "API_SERVER_ERROR" # 5xx 服务器端错误
ERROR_TYPE_PANOID_JSON_PARSE_ERROR = "PANOID_JSON_PARSE_ERROR" # PanoId响应JSON解析失败
ERROR_TYPE_UNCLASSIFIED_HTTP_STATUS = "UNCLASSIFIED_HTTP_STATUS" # 遇到未知HTTP状态码
ERROR_TYPE_UNCLASSIFIED_REQUEST_ERROR = "UNCLASSIFIED_REQUEST_ERROR" # 其他requests.exceptions.RequestException
ERROR_TYPE_GENERAL_EXCEPTION = "GENERAL_EXCEPTION" # 捕获到的不符合上述分类的通用异常

# 聚合的永久性错误类型集合，用于控制跳过逻辑。
# 根据你的要求，只有 NO_PANOID_FOUND 会被永久跳过。
PERMANENT_SKIP_ERROR_TYPES = {
    ERROR_TYPE_NO_PANOID_FOUND
}

# ===== 设置详细日志记录函数 =====
def setup_logger(log_file_path, console_output_level=logging.WARNING, file_output_level=logging.DEBUG):
    """
    配置并返回一个日志记录器。
    该日志器会将所有指定级别的日志写入文件，并将指定级别及以上的日志输出到控制台。

    Args:
        log_file_path (str): 日志文件保存的完整路径。
        console_output_level (int): 控制台输出的最低日志级别 (例如 logging.WARNING)。
        file_output_level (int): 文件输出的最低日志级别 (例如 logging.DEBUG)。
    Returns:
        logging.Logger: 配置好的日志器对象。
    """
    logger_obj = logging.getLogger('detailed_downloader') # 获取名为 'detailed_downloader' 的日志器
    logger_obj.setLevel(file_output_level) # 设置日志器捕获的最低级别，通常为文件输出的最低级别

    # 清除现有处理器，防止重复添加（如果函数被多次调用）
    # 迭代一个列表的副本，以便在迭代时修改原始列表
    for handler in logger_obj.handlers[:]:
        logger_obj.removeHandler(handler)

    # 1. 配置文件处理器 (FileHandler)
    file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
    file_handler.setLevel(file_output_level) # 设置文件处理器级别
    # 定义文件日志的格式
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)d - %(message)s')
    file_handler.setFormatter(formatter)
    logger_obj.addHandler(file_handler) # 将文件处理器添加到日志器

    # 2. 配置控制台处理器 (StreamHandler)
    console_handler = logging.StreamHandler(sys.stdout) # 输出到标准输出流 (控制台)
    console_handler.setLevel(console_output_level) # 设置控制台处理器级别
    console_handler.setFormatter(formatter) # 控制台也使用相同的格式
    logger_obj.addHandler(console_handler) # 将控制台处理器添加到日志器

    return logger_obj

# ===== 单个点位处理函数 (用于多线程) =====
def process_single_point(point_data_tuple, pano_id_str, api_key_str, session_token_str, zoom_int, tile_cols_int, tile_rows_int, tile_size_int, sleeptime_float, save_dir_str, logger_obj, thread_local_storage):
    """
    处理单个点位的图像下载和拼接。
    这个函数会在一个独立的线程中运行，负责获取瓦片并将其拼接到全景图中。
    返回一个包含处理结果的字典，包含更详细的错误类型。
    """
    current_point_id_str = str(point_data_tuple.ID) # 从 namedtuple 获取点位 ID

    logger_obj.info(f"线程 {threading.get_ident()}: 开始处理点位 ID: {current_point_id_str}, PanoID: {pano_id_str}")

    # 如果 pano_id_str 为空或 None，直接返回“未找到 PanoID”的失败状态
    # 这通常发生在 PanoIds API 返回空字符串时，表示该坐标没有街景
    if not pano_id_str: 
        logger_obj.warning(f"线程 {threading.get_ident()}: 点位 ID: {current_point_id_str} 未找到 PanoID。")
        return {"status": "failure", "id": current_point_id_str, "reason": "No panoId found for this location", "error_type": ERROR_TYPE_NO_PANOID_FOUND}

    # 创建一个空白图像，用于后续拼接瓦片
    panorama = Image.new('RGB', (tile_size_int * tile_cols_int, tile_size_int * tile_rows_int))
    missing_tiles_count = 0 # 记录缺失瓦片的数量
    total_tiles = tile_cols_int * tile_rows_int # 总瓦片数
    logger_obj.debug(f"线程 {threading.get_ident()}: ID: {current_point_id_str}, PanoID: {pano_id_str} - 创建空白图像，预期总瓦片数: {total_tiles}")

    # 遍历所有瓦片坐标 (x, y)
    # trange 提供进度条，position 用于在多线程环境下分散进度条，避免交错
    for x in trange(tile_cols_int, desc=f"拼接 {current_point_id_str} (线程 {threading.get_ident()})", leave=False, position=threading.get_ident() % 10):
        for y in range(tile_rows_int):
            # 构建瓦片下载的 URL
            tile_url = (
                f"https://tile.googleapis.com/v1/streetview/tiles/{zoom_int}/{x}/{y}"
                f"?session={session_token_str}&key={api_key_str}&panoId={pano_id_str}"
            )
            logger_obj.debug(f"线程 {threading.get_ident()}: ID: {current_point_id_str}, PanoID: {pano_id_str} - 请求瓦片 URL: {tile_url}")

            max_tile_retries = 3 # 每个瓦片的下载尝试次数
            current_tile_retry = 0 # 当前瓦片的重试计数
            tile_download_successful = False # 标记瓦片是否成功下载
            
            current_tile_error_reason = "" # 记录当前瓦片失败的详细原因
            current_tile_error_type = "" # 记录当前瓦片失败的类型

            # 瓦片下载的内部重试循环
            while current_tile_retry < max_tile_retries:
                try:
                    # 发送 GET 请求下载瓦片，设置超时
                    tile_resp = requests.get(tile_url, timeout=10) 
                    if tile_resp.status_code == 200:
                        # 成功下载，打开图像并粘贴到全景图中
                        tile_img = Image.open(BytesIO(tile_resp.content))
                        panorama.paste(tile_img, (x * tile_size_int, y * tile_size_int))
                        tile_download_successful = True
                        logger_obj.debug(f"线程 {threading.get_ident()}: ID: {current_point_id_str}, PanoID: {pano_id_str} - 瓦片 ({x},{y}) 下载成功。")
                        break # 成功，跳出瓦片内部重试循环
                    else:
                        # HTTP 状态码非 200，尝试解析 API 返回的 JSON 错误信息
                        error_detail = ""
                        try:
                            error_json = tile_resp.json()
                            error_detail = error_json.get("error", {}).get("message", "") or error_json.get("message", "")
                        except json.JSONDecodeError:
                            error_detail = tile_resp.text # 如果不是 JSON 响应，则使用原始文本

                        current_tile_error_reason = f"瓦片 ({x},{y}) HTTP {tile_resp.status_code}: {error_detail[:150]}..." # 截断消息以防过长
                        
                        # 根据 HTTP 状态码精细判断错误类型
                        if tile_resp.status_code == 404: # 瓦片不存在
                            current_tile_error_type = ERROR_TYPE_ALL_TILES_MISSING # 标记为瓦片缺失类型
                            break # 对于 404，通常不值得瓦片内部重试，立即结束内部循环
                        elif tile_resp.status_code == 401 or tile_resp.status_code == 403: # 认证失败或权限问题
                            current_tile_error_type = ERROR_TYPE_API_AUTH_FORBIDDEN # 标记为致命错误
                            break # 致命错误不值得瓦片内部重试，立即结束内部循环
                        elif tile_resp.status_code == 429: # 速率限制
                            current_tile_error_type = ERROR_TYPE_API_RATE_LIMIT
                            if current_tile_retry == max_tile_retries - 1: # 如果达到最大重试次数
                                break # 退出瓦片内部重试
                        elif 400 <= tile_resp.status_code < 500: # 其他客户端错误 (如400 Bad Request)
                            current_tile_error_type = ERROR_TYPE_API_BAD_REQUEST # 通常不值得瓦片内部重试
                            break
                        elif 500 <= tile_resp.status_code < 600: # 服务器错误
                            current_tile_error_type = ERROR_TYPE_API_SERVER_ERROR # 值得重试
                            if current_tile_retry == max_tile_retries - 1: # 达到最大重试
                                break
                        else: # 未知 HTTP 状态码
                            current_tile_error_type = ERROR_TYPE_UNCLASSIFIED_HTTP_STATUS
                            if current_tile_retry == max_tile_retries - 1:
                                break
                # 捕获网络请求异常
                except requests.exceptions.Timeout as req_e:
                    current_tile_error_reason = f"瓦片 ({x},{y}) 请求超时: {req_e}"
                    current_tile_error_type = ERROR_TYPE_NETWORK_TIMEOUT
                except requests.exceptions.ConnectionError as req_e:
                    current_tile_error_reason = f"瓦片 ({x},{y}) 连接错误: {req_e}"
                    current_tile_error_type = ERROR_TYPE_NETWORK_CONNECTION_ERROR
                except requests.exceptions.RequestException as req_e: # 捕获其他 requests 异常
                    current_tile_error_reason = f"瓦片 ({x},{y}) 未知请求异常: {req_e}"
                    current_tile_error_type = ERROR_TYPE_UNCLASSIFIED_REQUEST_ERROR
                except Exception as e: # 捕获其他通用异常，如 PIL 图像处理错误
                    current_tile_error_reason = f"处理瓦片 ({x},{y}) 时发生内部错误: {e}"
                    current_tile_error_type = ERROR_TYPE_INTERNAL_PROCESSING_ERROR
                    tile_download_successful = False # 确保标记为失败
                    break # 立即退出瓦片内部重试循环，因为内部错误通常重试无用

                # 如果瓦片下载未成功，且当前错误类型允许内部重试，则记录警告并进入下一次重试
                if not tile_download_successful and current_tile_retry < max_tile_retries:
                    logger_obj.warning(f"线程 {threading.get_ident()}: ID: {current_point_id_str}, PanoID: {pano_id_str} - {current_tile_error_reason}. 类型: {current_tile_error_type}. 重试 {current_tile_retry + 1}/{max_tile_retries}")
                
                current_tile_retry += 1
                # 如果还未达到最大重试次数，进行等待（指数退避）
                if current_tile_retry < max_tile_retries:
                    # 对于 429 错误，等待时间会更长
                    if current_tile_error_type == ERROR_TYPE_API_RATE_LIMIT:
                        sleep_time_retry = min(sleeptime_float * (2 ** current_tile_retry) * 5, 60) 
                    else:
                        sleep_time_retry = min(sleeptime_float * (2 ** current_tile_retry), 30) # 普通指数退避，最大 30 秒
                    sleep(sleep_time_retry)
                else: # 达到最大重试次数，退出循环
                    break
            
            # 如果瓦片在多次内部重试后仍未成功下载
            if not tile_download_successful:
                missing_tiles_count += 1
                logger_obj.error(f"线程 {threading.get_ident()}: ID: {current_point_id_str}, PanoID: {pano_id_str} - 瓦片 ({x},{y}) 最终下载失败。原因: {current_tile_error_reason}, 类型: {current_tile_error_type}")
                
                # 如果遇到被认为是致命的错误类型，立即返回点位失败，不再尝试其他瓦片
                if current_tile_error_type in {
                    ERROR_TYPE_API_AUTH_FORBIDDEN, # 权限/认证问题
                    ERROR_TYPE_API_BAD_REQUEST, # 请求参数错误
                    ERROR_TYPE_INTERNAL_PROCESSING_ERROR, # 内部处理错误
                    ERROR_TYPE_UNCLASSIFIED_HTTP_STATUS, # 未知 HTTP 状态码
                    ERROR_TYPE_UNCLASSIFIED_REQUEST_ERROR # 未知请求异常
                }:
                    return {"status": "failure", "id": current_point_id_str, "reason": current_tile_error_reason, "error_type": current_tile_error_type}


            sleep(sleeptime_float) # 每次瓦片下载后的固定间隔

    # 如果所有瓦片都缺失（并且在瓦片下载循环中没有提前返回致命错误）
    if missing_tiles_count == total_tiles:
        logger_obj.warning(f"线程 {threading.get_ident()}: 点位 ID: {current_point_id_str}, PanoID: {pano_id_str} - 所有瓦片均缺失，跳过保存。")
        # 这通常表示 PanoId 无效（即使不是 None，瓦片本身也返回 404）或者持续的网络/API 问题
        return {"status": "failure", "id": current_point_id_str, "reason": "All tiles missing after repeated attempts", "error_type": ERROR_TYPE_ALL_TILES_MISSING}

    # 成功拼接所有瓦片，尝试保存图像
    filename = f"{current_point_id_str}_{pano_id_str}.jpg"
    filepath = os.path.join(save_dir_str, filename)
    try:
        panorama.save(filepath)
        logger_obj.info(f"线程 {threading.get_ident()}: 点位 ID: {current_point_id_str}, PanoID: {pano_id_str} - 图像成功保存至: {filepath}")
        return {"status": "success", "id": current_point_id_str, "panoId": pano_id_str, "file": filename}
    except Exception as e_save: # 捕获保存图像时可能发生的异常
        logger_obj.error(f"线程 {threading.get_ident()}: 点位 ID: {current_point_id_str}, PanoID: {pano_id_str} - 保存图像失败: {e_save}", exc_info=True)
        return {"status": "failure", "id": current_point_id_str, "reason": f"Save image failed: {e_save}", "error_type": ERROR_TYPE_INTERNAL_PROCESSING_ERROR}


if __name__ == "__main__":
    # --- 阶段1: 程序启动时的基础日志配置 ---
    # 在主程序的最早阶段设置一个临时的、仅输出到控制台的日志器。
    # 这确保了即使在读取配置文件等早期步骤中发生错误，也有日志输出。
    # 它的级别设置为 INFO，以便捕获程序启动时的基本信息和错误。
    temp_console_handler = logging.StreamHandler(sys.stdout)
    temp_console_handler.setLevel(logging.INFO) # 临时日志器输出INFO及以上级别
    temp_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    temp_console_handler.setFormatter(temp_formatter)

    # 获取一个名为 'main_process_logger' 的日志器实例。
    # 它的级别设置为 INFO，确保能捕获到基本信息。
    logger = logging.getLogger('main_process_logger')
    logger.setLevel(logging.INFO)
    # 添加临时控制台处理器。
    logger.addHandler(temp_console_handler)
    # 设置 propagate 为 False，防止日志消息传递给根日志器，避免重复输出到控制台。
    logger.propagate = False 

    # tqdm 全局锁，用于多线程环境下的安全输出
    tqdm.set_lock(threading.RLock())
    thread_local_storage = threading.local() # 用于线程特定的数据，如果需要的话

    try:
        print("程序启动...") # 使用 print 确保这条消息总能被用户看到
        logger.info("程序启动，正在读取配置文件。") # 这条会进入临时日志器

        config = ConfigParser()
        if not os.path.exists('configuration.ini'):
            print("❌ 错误：配置文件 'configuration.ini' 未找到。请创建该文件。")
            logger.error("配置文件 'configuration.ini' 未找到，程序将退出。") # 这条会进入临时日志器
            input("\n按回车键关闭...")
            exit()
        with open('configuration.ini', 'r', encoding='utf-8') as f:
            config.read_file(f)

        # 从配置文件中读取所有路径
        CSV_PATH = config['PATHS']['CSV_PATH']
        API_KEY_PATH = config['PATHS']['API_KEY_PATH']
        SAVE_DIR = config['PATHS']['SAVE_DIR']
        LOG_PATH = config['PATHS']['LOG_PATH']
        FAIL_LOG_PATH = config['PATHS']['FAIL_LOG_PATH']
        DETAILED_LOG_PATH = config['PATHS']['DETAILED_LOG_PATH']

        # --- 阶段2: 配置详细日志器 ---
        # 在读取完所有配置路径后，重新配置日志器到文件，并调整控制台输出级别。
        try:
            # 首先移除之前添加的临时控制台处理器，因为我们将配置一个更精细的日志器
            logger.removeHandler(temp_console_handler)
            # 调用 setup_logger 配置详细日志器，文件输出DEBUG，控制台输出WARNING
            logger = setup_logger(DETAILED_LOG_PATH, 
                                  console_output_level=logging.WARNING, 
                                  file_output_level=logging.DEBUG)
            
            logger.info(f"日志已重定向到文件: {DETAILED_LOG_PATH}") # 这条信息会进入文件 (DEBUG级别)，但不会进入控制台 (INFO < WARNING)
            print(f"日志输出已配置：控制台输出WARNING及以上，所有日志记录在文件: {DETAILED_LOG_PATH}") # 使用 print 确保用户看到配置信息
        except Exception as e_setup_logger:
            # 如果配置详细日志文件失败，则记录错误，并程序将继续使用最初的基础日志器 (输出到控制台)
            # temp_console_handler 仍然有效，因为它没有被关闭，只是从 'logger' 移除了
            # 在这种异常情况下，我们可以重新将 temp_console_handler 添加回 logger，或者简单地让 logger 保持其原始状态
            # 这里，我们让 logger 保持原始状态（即 main_process_logger 仍然输出到控制台），并记录错误
            logger.error(f"配置详细日志文件失败: {e_setup_logger}。日志将继续输出到控制台。", exc_info=True)
            # 注意：此时 logger 已经是 'main_process_logger'，它仍然有其原始的 StreamHandler
            # 所以后面的 logger.info 仍然会打印到控制台，这符合“回退”行为

        logger.info("程序开始运行。") # 这条 INFO 消息将只写入文件，不会显示在控制台
        logger.info(f"配置文件 'configuration.ini' 加载成功。") # 这条 INFO 消息也将只写入文件

        # 读取其他参数配置
        BATCH_SIZE = int(config['PARAMS']['BATCH_SIZE'])
        NUM_BATCHES = int(config['PARAMS']['NUM_BATCHES'])
        RETRY_FAILED_POINTS = config.getboolean('PARAMS', 'RETRY_FAILED_POINTS', fallback=False)
        MAX_POINT_WORKERS = config.getint('PARAMS', 'MAX_POINT_WORKERS', fallback=5)
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


        # 创建保存图像的目录，如果不存在
        os.makedirs(SAVE_DIR, exist_ok=True)
        logger.info(f"保存目录 '{SAVE_DIR}' 已确认/创建。")
        
        # 读取 API Key
        if not os.path.exists(API_KEY_PATH):
            logger.error(f"API Key 文件 '{API_KEY_PATH}' 未找到。")
            print(f"❌ 错误：API Key 文件 '{API_KEY_PATH}' 未找到。")
            input("\n按回车键关闭...")
            exit()
        with open(API_KEY_PATH, 'r') as f:
            API_KEY = f.readline().strip()
        logger.info(f"API Key 从 '{API_KEY_PATH}' 加载成功。")

        # 加载已成功下载的ID，用于跳过已完成的任务
        downloaded_ids = set()
        if os.path.exists(LOG_PATH):
            try:
                log_content_df = pd.read_csv(LOG_PATH)
                if 'ID' in log_content_df.columns:
                    downloaded_ids = set(log_content_df['ID'].dropna().astype(str))
                    logger.info(f"从 '{LOG_PATH}' 加载已成功下载 {len(downloaded_ids)} 个ID。")
                else: logger.warning(f"成功日志 '{LOG_PATH}' 中缺少 'ID' 列。")
            except pd.errors.EmptyDataError: logger.warning(f"成功日志 '{LOG_PATH}' 为空。")
            except Exception as e_log: logger.error(f"读取成功日志 '{LOG_PATH}' 失败: {e_log}", exc_info=True)
        else:
            pd.DataFrame(columns=['ID']).to_csv(LOG_PATH, index=False)
            logger.info(f"'{LOG_PATH}' 不存在，已创建空的成功日志文件。")

        # failed_df_list 用于收集当前运行批次中产生的失败记录
        failed_df_list = []
        
        # 初始时从文件加载历史失败记录，用于构建 ids_to_skip_processing 集合
        initial_failed_ids_from_file = set() # 存储所有历史失败的ID
        permanent_failed_ids_from_file = set() # 存储被判断为永久失败的ID (即重试模式下也要跳过的ID)

        if os.path.exists(FAIL_LOG_PATH):
            try:
                temp_failed_df = pd.read_csv(FAIL_LOG_PATH)
                if not temp_failed_df.empty and 'ID' in temp_failed_df.columns:
                    temp_failed_df['ID'] = temp_failed_df['ID'].astype(str)
                    initial_failed_ids_from_file = set(temp_failed_df['ID'].unique())

                    # 检查失败日志文件是否包含 'error_type' 列（用于兼容旧格式）
                    if 'error_type' in temp_failed_df.columns:
                        # 如果存在 'error_type' 列，则根据该列判断哪些是永久性失败
                        permanent_failed_df = temp_failed_df[temp_failed_df['error_type'].isin(PERMANENT_SKIP_ERROR_TYPES)]
                        permanent_failed_ids_from_file = set(permanent_failed_df['ID'].unique())
                        logger.info(f"从 '{FAIL_LOG_PATH}' 初始加载 {len(permanent_failed_ids_from_file)} 个唯一永久失败ID。")
                    else:
                        # 如果缺少 'error_type' 列，则发出警告，并尝试从 'Reason' 列推断 'NO_PANOID_FOUND'
                        logger.warning(f"失败日志 '{FAIL_LOG_PATH}' 中缺少 'error_type' 列。所有历史失败将被视为可重试（除了明确的NO_PANOID_FOUND）。")
                        no_panoid_from_reason = temp_failed_df[temp_failed_df['Reason'].str.contains("No panoId", na=False)]['ID'].unique()
                        permanent_failed_ids_from_file.update(no_panoid_from_reason)
                        logger.info(f"从旧失败日志的 Reason 推断出 {len(no_panoid_from_reason)} 个 NO_PANOID_FOUND。")

                logger.info(f"从 '{FAIL_LOG_PATH}' 初始加载 {len(initial_failed_ids_from_file)} 个唯一失败ID。")
            except pd.errors.EmptyDataError:
                logger.warning(f"失败日志 '{FAIL_LOG_PATH}' 为空。")
            except Exception as e_fail_log:
                logger.error(f"读取失败日志 '{FAIL_LOG_PATH}' 失败: {e_fail_log}", exc_info=True)
        else:
            # 如果失败日志文件不存在，创建一个新的空文件，并包含所有列
            pd.DataFrame(columns=['ID', 'Reason', 'error_type']).to_csv(FAIL_LOG_PATH, index=False)
            logger.info(f"'{FAIL_LOG_PATH}' 不存在，已创建空的失败日志文件。")

        # 构建最终需要跳过的ID集合
        # 总是跳过已成功下载的ID
        ids_to_skip_processing = set(downloaded_ids)
        if not RETRY_FAILED_POINTS:
            # 如果重试模式关闭，则额外跳过所有之前记录的失败ID
            logger.info("重试模式关闭，将额外跳过所有之前失败记录中的ID。")
            ids_to_skip_processing.update(initial_failed_ids_from_file)
        else:
            # 如果重试模式开启，则只跳过已成功下载的ID 和 明确的永久性失败ID
            logger.info("重试模式开启，将仅跳过已成功下载的ID，以及特定永久失败的ID。")
            ids_to_skip_processing.update(permanent_failed_ids_from_file)

        logger.info(f"总计将明确跳过 {len(ids_to_skip_processing)} 个ID。")

        logger.info("尝试创建街景会话 Token...")
        session_payload = {"mapType": "streetview", "language": "en-US", "region": "US"}
        try:
            # 发送请求创建会话 Token
            session_response = requests.post(f"https://tile.googleapis.com/v1/createSession?key={API_KEY}", headers={"Content-Type": "application/json"}, json=session_payload, timeout=15)
            
            if session_response.status_code == 200:
                # 成功获取 Token
                SESSION_TOKEN = session_response.json().get("session")
                if not SESSION_TOKEN:
                    error_msg = f"无法获取 session token，响应内容：{session_response.text}"
                    logger.error(error_msg)
                    print(f"❌ {error_msg}") # 在控制台显示错误，因为这是一个可能导致程序无法继续的严重错误
                    raise Exception("无法获取 session token")
                logger.info(f"成功获取 Session Token: {SESSION_TOKEN[:10]}...")
            else:
                # Session Token 请求失败（非 200 状态码）
                error_detail = ""
                try:
                    error_json = session_response.json()
                    error_detail = error_json.get("error", {}).get("message", "") or error_json.get("message", "")
                except json.JSONDecodeError:
                    error_detail = session_response.text

                error_reason = f"创建 Session Token 请求失败。状态码: {session_response.status_code}, 消息: {error_detail[:200]}..."
                logger.error(error_reason) # 记录到文件和控制台 (因为是 ERROR 级别)
                print(f"❌ {error_reason}") # 确保在控制台显示给用户

                # 根据状态码判断并抛出特定异常
                if session_response.status_code == 401 or session_response.status_code == 403:
                    raise Exception(f"创建 Session Token 失败: API Key 无效或权限不足 ({error_reason})")
                elif session_response.status_code == 429:
                    raise Exception(f"创建 Session Token 失败: 速率限制，请稍后再试 ({error_reason})")
                elif session_response.status_code >= 500:
                    raise Exception(f"创建 Session Token 失败: 服务器内部错误，可能暂时性 ({error_reason})")
                elif session_response.status_code == 400:
                    raise Exception(f"创建 Session Token 失败: 请求参数错误 ({error_reason})")
                else:
                    raise Exception(f"创建 Session Token 失败: 未知HTTP状态码 ({error_reason})")
        except requests.exceptions.Timeout as req_e:
            logger.error(f"创建 Session Token 请求超时: {req_e}", exc_info=True)
            print(f"❌ 创建 Session Token 请求超时: {req_e}")
            raise Exception(f"创建 Session Token 请求超时: {req_e}")
        except requests.exceptions.ConnectionError as req_e:
            logger.error(f"创建 Session Token 连接错误: {req_e}", exc_info=True)
            print(f"❌ 创建 Session Token 连接错误: {req_e}")
            raise Exception(f"创建 Session Token 连接错误: {req_e}")
        except requests.exceptions.RequestException as req_e:
            logger.error(f"创建 Session Token 请求发生未知异常: {req_e}", exc_info=True)
            print(f"❌ 创建 Session Token 请求发生未知异常: {req_e}")
            raise Exception(f"创建 Session Token 请求发生未知异常: {req_e}")
        except Exception as e_session_general:
            logger.error(f"创建 Session Token 发生意外错误: {e_session_general}", exc_info=True)
            print(f"❌ 创建 Session Token 发生意外错误: {e_session_general}")
            raise Exception(f"创建 Session Token 发生意外错误: {e_session_general}")


        # 检查点位 CSV 文件是否存在
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
        all_df['ID'] = all_df['ID'].astype(str) # 确保 ID 列是字符串类型
        logger.info(f"从 '{CSV_PATH}' 加载 {len(all_df)} 个总点位。")
        
        current_run_log_list = [] # 存储当前运行中成功下载的ID，用于更新成功日志

        # 遍历批次进行处理
        for batch_num in range(NUM_BATCHES):
            logger.info(f"开始处理批次 {batch_num + 1}/{NUM_BATCHES}") # 这条信息会进入文件，不会进入控制台
            
            # 根据已跳过ID集合筛选当前批次要处理的点位
            current_processing_df = all_df[~all_df['ID'].isin(list(ids_to_skip_processing))].head(BATCH_SIZE)
            
            if current_processing_df.empty:
                print("🎉 所有符合条件的点位已处理完毕，无需再运行更多批次。") # 使用 print 确保用户看到
                logger.info("所有符合条件的点位已处理完毕，无需再运行更多批次。") # 这条信息会进入文件
                break # 所有点位都已处理，退出批次循环
            
            print(f"\n🚀 正在处理第 {batch_num + 1}/{NUM_BATCHES} 批，共 {len(current_processing_df)} 个点位...") # 使用 print 确保用户看到
            logger.info(f"批次 {batch_num + 1}：待处理点位数 {len(current_processing_df)}") # 这条信息会进入文件

            # 检查当前批次数据是否包含经纬度列
            if not all(col in current_processing_df.columns for col in ['Lat', 'Lng']):
                logger.error("当前批次点位数据中缺少 'Lat' 或 'Lng' 列。请检查CSV文件。") # 记录到文件和控制台
                print("❌ 错误：当前批次点位数据中缺少 'Lat' 或 'Lng' 列。") # 控制台输出
                continue # 跳过当前批次，进入下一批次

            # 准备请求 PanoIDs 的地理位置列表
            locations = [{"lat": row["Lat"], "lng": row["Lng"]} for _, row in current_processing_df.iterrows()]
            logger.debug(f"批次 {batch_num + 1}：请求 PanoIDs 的地点 (前5个): {locations[:5]}") # 这条信息只进入文件

            # 请求 PanoIDs
            panoid_url = f"https://tile.googleapis.com/v1/streetview/panoIds?session={SESSION_TOKEN}&key={API_KEY}"
            pano_ids_data = [] # 存储 PanoID 响应数据
            try:
                response_pano_ids = requests.post(panoid_url, json={"locations": locations, "radius": 50}, timeout=20)
                if response_pano_ids.status_code == 200:
                    try:
                        pano_ids_data = response_pano_ids.json().get("panoIds", [])
                        logger.info(f"批次 {batch_num + 1}：成功获取 PanoIDs 响应。数量: {len(pano_ids_data)}") # 文件日志
                        logger.debug(f"批次 {batch_num + 1}：获取到的 PanoIDs (部分): {pano_ids_data[:5]}") # 文件日志
                    except json.JSONDecodeError: # JSON 解析失败
                        error_reason = f"获取 PanoIDs 成功，但JSON解析失败。响应文本: {response_pano_ids.text[:200]}..."
                        logger.error(f"批次 {batch_num + 1}：{error_reason}") # 文件和控制台日志
                        # 将本批次所有点位标记为失败，并记录 JSON 解析错误类型
                        for point_row_tuple in current_processing_df.itertuples(index=False):
                            failed_df_list.append({"ID": str(point_row_tuple.ID), "Reason": error_reason, "error_type": ERROR_TYPE_PANOID_JSON_PARSE_ERROR})
                            ids_to_skip_processing.add(str(point_row_tuple.ID)) # 标记为已处理（失败）
                        continue # 跳过当前批次的瓦片下载，进入下一批次
                else:
                    # PanoIDs 请求失败（非 200 状态码）
                    error_detail = ""
                    try:
                        error_json = response_pano_ids.json()
                        error_detail = error_json.get("error", {}).get("message", "") or error_json.get("message", "")
                    except json.JSONDecodeError:
                        error_detail = response_pano_ids.text

                    error_reason = f"获取 PanoIDs 请求失败。状态码: {response_pano_ids.status_code}, 消息: {error_detail[:200]}..."
                    logger.error(f"批次 {batch_num + 1}：{error_reason}") # 文件和控制台日志
                    
                    # 根据状态码判断 PanoID 请求的错误类型
                    current_batch_error_type = ERROR_TYPE_UNCLASSIFIED_HTTP_STATUS # 默认未知HTTP状态码
                    if response_pano_ids.status_code == 400: # Bad Request
                        current_batch_error_type = ERROR_TYPE_API_BAD_REQUEST
                    elif response_pano_ids.status_code == 401 or response_pano_ids.status_code == 403: # Forbidden
                        current_batch_error_type = ERROR_TYPE_API_AUTH_FORBIDDEN
                    elif response_pano_ids.status_code == 429: # Too Many Requests
                        current_batch_error_type = ERROR_TYPE_API_RATE_LIMIT
                    elif 500 <= response_pano_ids.status_code < 600: # Server Error
                        current_batch_error_type = ERROR_TYPE_API_SERVER_ERROR

                    # 将本批次所有点位标记为相应的失败类型
                    for point_row_tuple in current_processing_df.itertuples(index=False):
                        failed_df_list.append({"ID": str(point_row_tuple.ID), "Reason": error_reason, "error_type": current_batch_error_type})
                        ids_to_skip_processing.add(str(point_row_tuple.ID)) # 标记为已处理（失败）
                    continue # 跳过当前批次的瓦片下载，进入下一批次

            except requests.exceptions.Timeout as req_e_pano: # PanoIDs 请求超时
                error_reason = f"获取 PanoIDs 请求超时: {req_e_pano}"
                logger.error(f"批次 {batch_num + 1}：{error_reason}") # 文件和控制台日志
                for point_row_tuple in current_processing_df.itertuples(index=False):
                    failed_df_list.append({"ID": str(point_row_tuple.ID), "Reason": error_reason, "error_type": ERROR_TYPE_NETWORK_TIMEOUT})
                    ids_to_skip_processing.add(str(point_row_tuple.ID))
                continue # 跳过当前批次的瓦片下载
            except requests.exceptions.ConnectionError as req_e_pano: # PanoIDs 连接错误
                error_reason = f"获取 PanoIDs 连接错误: {req_e_pano}"
                logger.error(f"批次 {batch_num + 1}：{error_reason}") # 文件和控制台日志
                for point_row_tuple in current_processing_df.itertuples(index=False):
                    failed_df_list.append({"ID": str(point_row_tuple.ID), "Reason": error_reason, "error_type": ERROR_TYPE_NETWORK_CONNECTION_ERROR})
                    ids_to_skip_processing.add(str(point_row_tuple.ID))
                continue
            except requests.exceptions.RequestException as req_e_pano: # 其他 requests 异常
                error_reason = f"获取 PanoIDs 请求发生未知异常: {req_e_pano}"
                logger.error(f"批次 {batch_num + 1}：{error_reason}") # 文件和控制台日志
                for point_row_tuple in current_processing_df.itertuples(index=False):
                    failed_df_list.append({"ID": str(point_row_tuple.ID), "Reason": error_reason, "error_type": ERROR_TYPE_UNCLASSIFIED_REQUEST_ERROR})
                    ids_to_skip_processing.add(str(point_row_tuple.ID))
                continue
            except Exception as e_pano_general: # 捕获其他通用异常
                error_reason = f"获取 PanoIDs 发生意外错误: {e_pano_general}"
                logger.error(f"批次 {batch_num + 1}：{error_reason}", exc_info=True) # 文件和控制台日志 (含堆栈信息)
                for point_row_tuple in current_processing_df.itertuples(index=False):
                    failed_df_list.append({"ID": str(point_row_tuple.ID), "Reason": error_reason, "error_type": ERROR_TYPE_GENERAL_EXCEPTION}) # 捕获通用异常
                    ids_to_skip_processing.add(str(point_row_tuple.ID))
                continue
            
            print("📍 已获取 panoIds") # 使用 print
            results_this_batch_filenames = [] # 存储当前批次成功下载的文件信息

            # 确保 pano_ids_data 长度与 current_processing_df 匹配
            # Google API 通常会返回与请求 locations 数量相同的 panoIds 列表，
            # 即使某些地点没有 panoId 也会用空字符串 "" 填充。
            # 这里是为了以防万一 API 响应长度不匹配，用 None 补齐。
            if len(pano_ids_data) != len(locations):
                logger.warning(f"批次 {batch_num + 1}: PanoID数量({len(pano_ids_data)})与地点数({len(locations)})不匹配。将尝试按地点数迭代，PanoID不足处会为None。") # 文件和控制台日志
                pano_ids_data.extend([None] * (len(locations) - len(pano_ids_data)))


            # 使用线程池并发处理每个点位
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_POINT_WORKERS) as executor:
                future_to_point = {} # 映射 Future 对象到点位 ID
                for i, point_row_tuple in enumerate(current_processing_df.itertuples(index=False)):
                    current_pano_id = pano_ids_data[i] if i < len(pano_ids_data) else None
                    
                    # 提交处理单个点位的任务到线程池
                    future = executor.submit(process_single_point, 
                                            point_row_tuple, current_pano_id, API_KEY, SESSION_TOKEN, 
                                            ZOOM, TILE_COLS, TILE_ROWS, TILE_SIZE, 
                                            SLEEPTIME, SAVE_DIR, logger, thread_local_storage)
                    future_to_point[future] = str(point_row_tuple.ID) # 使用原始ID作为键

                # 包装 concurrent.futures.as_completed，以便显示总体进度条
                for future in tqdm(concurrent.futures.as_completed(future_to_point), total=len(future_to_point), desc=f"处理批次 {batch_num + 1} 点位"):
                    point_id_processed = future_to_point[future] # 获取已处理点位的 ID
                    try:
                        result = future.result() # 获取线程的返回结果
                        if result['status'] == 'success':
                            # 如果处理成功，记录到成功列表和已跳过ID集合
                            results_this_batch_filenames.append({"ID": result['id'], "panoId": result['panoId'], "file": result['file']})
                            current_run_log_list.append({"ID": result['id']})
                            ids_to_skip_processing.add(result['id']) # 标记为已处理（成功）
                        else: # status == 'failure'
                            # 如果处理失败，记录到失败列表，并标记为已处理
                            reason = result.get('reason', '未知失败')
                            error_type = result.get('error_type', ERROR_TYPE_GENERAL_EXCEPTION) 
                            failed_df_list.append({"ID": result['id'], "Reason": reason, "error_type": error_type})
                            ids_to_skip_processing.add(result['id']) # 标记为已处理（失败）
                    except Exception as exc: # 捕获线程执行过程中未被 process_single_point 捕获的异常
                        logger.error(f"点位ID {point_id_processed} 在线程中执行时产生未捕获异常: {exc}", exc_info=True) # 文件和控制台日志
                        failed_df_list.append({"ID": point_id_processed, "Reason": f"线程中未捕获异常: {exc}", "error_type": ERROR_TYPE_GENERAL_EXCEPTION})
                        ids_to_skip_processing.add(point_id_processed) # 标记为已处理（异常）
            
            # ===== 每批次结束时保存一次本批次产生的失败记录和批次结果 =====
            if failed_df_list: # 如果当前运行的批次中产生了失败记录
                temp_batch_failed_df = pd.DataFrame(failed_df_list)
                # 读取旧的失败日志，合并当前批次产生的失败，去重后保存
                if os.path.exists(FAIL_LOG_PATH):
                    try:
                        old_failed_df = pd.read_csv(FAIL_LOG_PATH)
                        # 如果旧日志没有 'error_type' 列，则添加并填充默认值，确保合并后的DataFrame结构一致
                        if 'error_type' not in old_failed_df.columns:
                            old_failed_df['error_type'] = ERROR_TYPE_GENERAL_EXCEPTION # 默认值
                            logger.warning(f"旧失败日志 '{FAIL_LOG_PATH}' 缺少 'error_type' 列，已添加并填充默认值。") # 文件和控制台日志
                        
                        if not old_failed_df.empty and 'ID' in old_failed_df.columns and 'Reason' in old_failed_df.columns:
                             combined_failed_df = pd.concat([old_failed_df, temp_batch_failed_df], ignore_index=True)
                        else: # 旧日志为空或格式不对
                            combined_failed_df = temp_batch_failed_df
                    except pd.errors.EmptyDataError: # 旧日志文件为空
                        combined_failed_df = temp_batch_failed_df
                    except Exception as e_read_old_fail: # 读取旧日志失败
                        logger.error(f"读取旧失败日志 '{FAIL_LOG_PATH}' 失败: {e_read_old_fail}。将仅保存当前运行的失败记录。", exc_info=True) # 文件和控制台日志
                        # print(f"❌ 读取旧失败日志 '{FAIL_LOG_PATH}' 失败: {e_read_old_fail}。将仅保存当前运行的失败记录。") # 如果希望控制台额外输出
                        combined_failed_df = temp_batch_failed_df
                else: # 旧失败日志不存在
                    combined_failed_df = temp_batch_failed_df
                
                # 检查合并后的DataFrame是否包含所有必要的列，并去重保存
                if 'ID' in combined_failed_df.columns and 'Reason' in combined_failed_df.columns and 'error_type' in combined_failed_df.columns:
                    combined_failed_df['ID'] = combined_failed_df['ID'].astype(str)
                    # 根据 'ID', 'Reason' 和 'error_type' 进行去重，保留最新的记录
                    combined_failed_df.drop_duplicates(subset=['ID', 'Reason', 'error_type'], keep='last').to_csv(FAIL_LOG_PATH, index=False)
                    logger.info(f"失败日志 '{FAIL_LOG_PATH}' 已更新。") # 文件日志
                else:
                    logger.error(f"无法更新失败日志，因为合并后的日志缺少必要的列 (ID, Reason, 或 error_type)。") # 文件和控制台日志
                failed_df_list = [] # 清空当前运行的失败列表，避免重复添加

            # 保存当前批次成功下载的文件列表
            if results_this_batch_filenames:
                pd.DataFrame(results_this_batch_filenames).to_csv(os.path.join(SAVE_DIR, f'results_batch_{batch_num+1}.csv'), index=False)
            logger.info(f"批次 {batch_num + 1} 处理完成。失败日志和批次结果已更新。") # 文件日志

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
                    logger.error(f"读取旧成功日志 '{LOG_PATH}' 失败: {e_read_old_log}。将仅保存当前运行的成功记录。", exc_info=True) # 文件和控制台日志
                    # print(f"❌ 读取旧成功日志 '{LOG_PATH}' 失败: {e_read_old_log}。将仅保存当前运行的成功记录。") # 如果需要控制台额外输出
                    combined_log_df = new_success_df
            else: combined_log_df = new_success_df

            if 'ID' in combined_log_df.columns:
                combined_log_df['ID'] = combined_log_df['ID'].astype(str)
                combined_log_df.drop_duplicates(subset=['ID'], keep='last').to_csv(LOG_PATH, index=False)
                logger.info(f"成功日志 '{LOG_PATH}' 已更新。") # 文件日志
            else: logger.error(f"无法更新成功日志，因为合并后的日志缺少 'ID' 列。") # 文件和控制台日志

        print("\n✅ 所有批次处理完成。") # 始终在控制台显示完成信息
        logger.info("所有批次处理完成。") # 文件日志

    except Exception as e: # 捕获主程序运行时的顶层未处理异常
        print(f"❌ 程序运行出错：{e}") # 始终在控制台显示错误信息
        # 此时 logger 已经确保被初始化，可以直接使用
        if logger: logger.error("程序顶层捕获到未处理异常。", exc_info=True) # 文件和控制台日志 (含堆栈信息)
        else: 
            # 这种情况极少发生，意味着在基础 logger 初始化之前就发生了严重错误
            print("Logger 未初始化，详细错误信息如下：")
            traceback.print_exc() 

        try: # 即使在异常情况下，也尝试保存已收集的失败和成功记录，防止数据丢失
            if 'failed_df_list' in locals() and failed_df_list:
                temp_failed_df_on_exit = pd.DataFrame(failed_df_list)
                if os.path.exists(FAIL_LOG_PATH):
                    try:
                        old_failed_df = pd.read_csv(FAIL_LOG_PATH)
                        if 'error_type' not in old_failed_df.columns:
                            old_failed_df['error_type'] = ERROR_TYPE_GENERAL_EXCEPTION # 默认值
                            # 此时 logger 必定不为 None，可以安全使用
                            if logger: logger.warning(f"旧失败日志 '{FAIL_LOG_PATH}' 缺少 'error_type' 列，已添加并填充默认值。") # 文件和控制台日志
                        
                        if not old_failed_df.empty and 'ID' in old_failed_df.columns and 'Reason' in old_failed_df.columns:
                            combined_failed_df = pd.concat([old_failed_df, temp_failed_df_on_exit], ignore_index=True)
                        else:
                            combined_failed_df = temp_failed_df_on_exit
                    except pd.errors.EmptyDataError:
                        combined_failed_df = temp_failed_df_on_exit
                    except Exception as e_read_old_fail:
                        print(f"读取旧失败日志 '{FAIL_LOG_PATH}' 失败: {e_read_old_fail}。将仅保存当前运行的失败记录。") # 控制台输出
                        if logger: logger.error(f"读取旧失败日志 '{FAIL_LOG_PATH}' 失败: {e_read_old_fail}。将仅保存当前运行的失败记录。", exc_info=True) # 文件和控制台日志
                        combined_failed_df = temp_failed_df_on_exit
                else:
                    combined_failed_df = temp_failed_df_on_exit

                if 'ID' in combined_failed_df.columns and 'Reason' in combined_failed_df.columns and 'error_type' in combined_failed_df.columns:
                    combined_failed_df['ID'] = combined_failed_df['ID'].astype(str)
                    combined_failed_df.drop_duplicates(subset=['ID', 'Reason', 'error_type'], keep='last').to_csv(FAIL_LOG_PATH, index=False)
                    if logger:
                        logger.info("程序异常退出前，尝试保存当前收集的失败记录。") # 文件日志
                else:
                    print(f"❌ 在异常处理中保存失败日志失败：缺少必要的列。") # 控制台输出
                    if logger: logger.error(f"在异常处理中保存失败日志失败：缺少必要的列。", exc_info=True) # 文件和控制台日志

            if 'current_run_log_list' in locals() and current_run_log_list:
                new_success_df = pd.DataFrame(current_run_log_list)
                if os.path.exists(LOG_PATH):
                    try:
                        old_log_df = pd.read_csv(LOG_PATH)
                        if 'ID' not in old_log_df.columns:
                            combined_log_df = new_success_df
                        else:
                            combined_log_df = pd.concat([old_log_df, new_success_df], ignore_index=True)
                    except pd.errors.EmptyDataError:
                        combined_log_df = new_success_df
                    except Exception as e_read_old_log:
                        print(f"读取旧成功日志 '{LOG_PATH}' 失败: {e_read_old_log}。将仅保存当前运行的成功记录。") # 控制台输出
                        if logger: logger.error(f"读取旧成功日志 '{LOG_PATH}' 失败: {e_read_old_log}。将仅保存当前运行的成功记录。", exc_info=True) # 文件和控制台日志
                        combined_log_df = new_success_df
                else:
                    combined_log_df = new_success_df

                if 'ID' in combined_log_df.columns:
                    combined_log_df['ID'] = combined_log_df['ID'].astype(str)
                    combined_log_df.drop_duplicates(subset=['ID'], keep='last').to_csv(LOG_PATH, index=False)
                    if logger:
                        logger.info("程序异常退出前，尝试保存当前收集的成功记录。") # 文件日志
                else:
                    print(f"❌ 在异常处理中保存成功日志失败：缺少必要的列。") # 控制台输出
                    if logger: logger.error(f"在异常处理中保存成功日志失败：缺少必要的列。", exc_info=True) # 文件和控制台日志

        except Exception as log_save_e:
            print(f"❌ 在异常处理中保存日志时也发生错误: {log_save_e}") # 控制台输出
            if logger: logger.error(f"在异常处理中保存日志时也发生错误: {log_save_e}", exc_info=True) # 文件和控制台日志
    finally:
        # 程序结束时，如果 logger 已经初始化，则记录结束信息
        if logger: logger.info("程序结束。\n---------------------------------------\n") # 文件日志
        input("\n按回车键关闭...")