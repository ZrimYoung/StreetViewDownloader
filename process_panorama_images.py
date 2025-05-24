#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
谷歌街景图片黑边检测和处理脚本
专门针对底部黑边进行优化，支持多线程处理、进度保存和中断恢复功能
"""

# ===============================
# 配置参数 - 直接在此处修改
# ===============================

# 基本设置
INPUT_DIR = "panoramas_test"           # 输入图片目录
OUTPUT_DIR = "edit"                    # 处理后图片输出目录  
PROBLEMATIC_DIR = "problematic"        # 有问题图片移动目录

# 处理参数
BLACK_THRESHOLD = 15                   # 黑边检测阈值 (0-255)
MAX_IMAGES = None                      # 最大处理图片数量 (None表示处理所有, 调试时可设为100)
NUM_WORKERS = 15                       # 并行处理线程数 (建议为CPU核心数的1-2倍)

# 日志设置  
LOG_LEVEL = "INFO"                     # 日志级别: DEBUG, INFO, WARNING, ERROR

# 黑边检测优化设置
BOTTOM_BLACK_EDGE_RATIO = 0.05         # 底部黑边检测阈值（占图片高度的比例，5%）
TARGET_ASPECT_RATIO = 2.0              # 目标宽高比 (2:1)

# ===============================

import os
import cv2
import numpy as np
from PIL import Image
import shutil
import json
import logging
from pathlib import Path
from tqdm import tqdm
from datetime import datetime
import time
import concurrent.futures
from threading import Lock

class OptimizedPanoramaProcessor:
    def __init__(self):
        """
        初始化处理器，使用顶部配置的参数
        """
        self.input_dir = Path(INPUT_DIR)
        self.output_dir = Path(OUTPUT_DIR)
        self.problematic_dir = Path(PROBLEMATIC_DIR)
        self.black_threshold = BLACK_THRESHOLD
        self.max_images = MAX_IMAGES
        self.num_workers = NUM_WORKERS
        
        # 创建输出目录
        self.output_dir.mkdir(exist_ok=True)
        self.problematic_dir.mkdir(exist_ok=True)
        
        # 设置日志
        self.setup_logging()
        
        # 进度文件路径
        self.progress_file = Path("processing_progress.json")
        self.lock = Lock()
        
        # 统计信息
        self.stats = {
            'total_images': 0,
            'processed_images': 0,
            'problematic_images': 0,
            'failed_images': 0,
            'skipped_images': 0,
            'start_time': None,
            'end_time': None
        }
        
        # 进度数据
        self.progress_data = {
            'processed_files': set(),
            'problematic_files': set(),
            'failed_files': set(),
            'normal_files': set(),
            'last_update': None,
            'total_files': 0
        }
    
    def setup_logging(self):
        """设置日志配置"""
        log_filename = f"panorama_processing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        logging.basicConfig(
            level=getattr(logging, LOG_LEVEL.upper()),
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_filename, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"日志文件: {log_filename}")
        self.logger.info(f"配置参数: 输入目录={INPUT_DIR}, 输出目录={OUTPUT_DIR}, 线程数={NUM_WORKERS}")
    
    def load_progress(self):
        """加载处理进度"""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 转换列表为集合
                    self.progress_data['processed_files'] = set(data.get('processed_files', []))
                    self.progress_data['problematic_files'] = set(data.get('problematic_files', []))
                    self.progress_data['failed_files'] = set(data.get('failed_files', []))
                    self.progress_data['normal_files'] = set(data.get('normal_files', []))
                    self.progress_data['last_update'] = data.get('last_update')
                    self.progress_data['total_files'] = data.get('total_files', 0)
                
                processed_count = len(self.progress_data['processed_files'])
                self.logger.info(f"从进度文件恢复: 已处理 {processed_count} 张图片")
                return True
            except Exception as e:
                self.logger.error(f"加载进度文件失败: {e}")
                return False
        return False
    
    def save_progress(self):
        """保存处理进度"""
        try:
            with self.lock:
                # 转换集合为列表以便JSON序列化
                data = {
                    'processed_files': list(self.progress_data['processed_files']),
                    'problematic_files': list(self.progress_data['problematic_files']),
                    'failed_files': list(self.progress_data['failed_files']),
                    'normal_files': list(self.progress_data['normal_files']),
                    'last_update': datetime.now().isoformat(),
                    'total_files': self.progress_data['total_files'],
                    'stats': self.stats
                }
                
                with open(self.progress_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存进度文件失败: {e}")
    
    def detect_bottom_black_border(self, image):
        """
        优化版：只检测底部黑边
        
        Args:
            image: numpy数组格式的图片
            
        Returns:
            bool: 是否检测到底部黑边
            int: 有效内容的底部边界（从顶部开始计算）
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        h, w = gray.shape
        
        # 从底部向上检测黑边
        valid_bottom = h
        # 只检查底部的一部分，提高效率
        check_rows = min(h // 2, 200)  # 最多检查200行或图片高度的一半
        
        for i in range(h-1, h-check_rows-1, -1):
            if np.mean(gray[i, :]) > self.black_threshold:
                valid_bottom = i + 1
                break
        
        # 计算底部黑边的高度
        bottom_black_height = h - valid_bottom
        
        # 判断是否有显著的底部黑边
        has_bottom_black_border = bottom_black_height > h * BOTTOM_BLACK_EDGE_RATIO
        
        self.logger.debug(f"底部黑边检测: 图片尺寸={w}x{h}, 底部黑边高度={bottom_black_height}, "
                         f"占比={bottom_black_height/h:.2%}, 检测结果={'有黑边' if has_bottom_black_border else '正常'}")
        
        return has_bottom_black_border, valid_bottom
    
    def crop_from_top_left(self, image, valid_bottom):
        """
        优化版：从左上角开始裁剪，按2:1比例去除底部黑边和右边重复部分
        
        Args:
            image: 原始图片
            valid_bottom: 有效内容的底部边界
            
        Returns:
            numpy.array: 裁剪后的图片
        """
        h, w = image.shape[:2]
        
        # 去除底部黑边后的有效区域
        valid_image = image[:valid_bottom, :]  # 从顶部到有效底部
        valid_h, valid_w = valid_image.shape[:2]
        
        self.logger.debug(f"去除底部黑边后尺寸: {valid_w}x{valid_h}")
        
        # 按2:1比例从左上角开始裁剪
        # 计算在当前高度下，2:1比例的理想宽度
        ideal_width = int(valid_h * TARGET_ASPECT_RATIO)
        
        if ideal_width <= valid_w:
            # 如果理想宽度小于等于当前宽度，直接从左上角裁剪
            cropped_image = valid_image[:, :ideal_width]
            self.logger.debug(f"从左上角裁剪宽度: {ideal_width}")
        else:
            # 如果理想宽度大于当前宽度，说明高度过大，需要裁剪高度
            ideal_height = int(valid_w / TARGET_ASPECT_RATIO)
            cropped_image = valid_image[:ideal_height, :]
            self.logger.debug(f"从左上角裁剪高度: {ideal_height}")
            
        final_h, final_w = cropped_image.shape[:2]
        self.logger.debug(f"最终裁剪尺寸: {final_w}x{final_h}, 比例: {final_w/final_h:.2f}")
        return cropped_image
    
    def resize_to_original(self, processed_image, original_shape):
        """
        将处理后的图片拉伸到原始分辨率
        
        Args:
            processed_image: 处理后的图片
            original_shape: 原始图片的形状 (height, width)
            
        Returns:
            numpy.array: 拉伸后的图片
        """
        original_h, original_w = original_shape[:2]
        resized_image = cv2.resize(processed_image, (original_w, original_h), 
                                 interpolation=cv2.INTER_CUBIC)
        return resized_image
    
    def process_single_image(self, image_path):
        """
        处理单张图片
        
        Args:
            image_path: 图片路径
            
        Returns:
            str: 处理结果状态 ('normal', 'problematic', 'failed', 'skipped')
        """
        try:
            filename = image_path.name
            
            # 检查是否已经处理过
            if filename in self.progress_data['processed_files']:
                return 'skipped'
            
            # 读取图片
            image = cv2.imread(str(image_path))
            if image is None:
                self.logger.warning(f"无法读取图片: {image_path}")
                with self.lock:
                    self.progress_data['failed_files'].add(filename)
                return 'failed'
                
            original_shape = image.shape
            
            # 检测底部黑边
            has_bottom_black_border, valid_bottom = self.detect_bottom_black_border(image)
            
            if has_bottom_black_border:
                # 移动原图到problematic文件夹
                problematic_path = self.problematic_dir / filename
                try:
                    shutil.move(str(image_path), str(problematic_path))
                except Exception as e:
                    self.logger.error(f"移动文件失败 {filename}: {e}")
                    return 'failed'
                
                # 处理图片：从左上角裁剪
                cropped_image = self.crop_from_top_left(image, valid_bottom)
                final_image = self.resize_to_original(cropped_image, original_shape)
                
                # 保存处理后的图片到edit文件夹
                output_path = self.output_dir / filename
                success = cv2.imwrite(str(output_path), final_image)
                if not success:
                    self.logger.error(f"保存处理后图片失败: {output_path}")
                    return 'failed'
                
                with self.lock:
                    self.progress_data['problematic_files'].add(filename)
                    self.progress_data['processed_files'].add(filename)
                
                self.logger.debug(f"处理有底部黑边图片: {filename}")
                return 'problematic'
            else:
                with self.lock:
                    self.progress_data['normal_files'].add(filename)
                    self.progress_data['processed_files'].add(filename)
                
                self.logger.debug(f"正常图片: {filename}")
                return 'normal'
            
        except Exception as e:
            self.logger.error(f"处理图片 {image_path} 时出错: {str(e)}")
            with self.lock:
                self.progress_data['failed_files'].add(filename)
            return 'failed'
    
    def get_image_files(self):
        """获取所有图片文件"""
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']
        image_files = []
        
        for ext in image_extensions:
            image_files.extend(list(self.input_dir.glob(f'*{ext}')))
            image_files.extend(list(self.input_dir.glob(f'*{ext.upper()}')))
        
        # 如果设置了最大处理数量，则限制文件数量
        if self.max_images:
            image_files = image_files[:self.max_images]
            
        return image_files
    
    def process_all_images(self):
        """
        批量处理所有图片
        """
        print(f"🚀 谷歌街景图片黑边处理工具 - 优化版")
        print(f"📂 输入目录: {INPUT_DIR}")
        print(f"📁 输出目录: {OUTPUT_DIR}")
        print(f"⚠️  问题图片目录: {PROBLEMATIC_DIR}")
        print(f"🧵 并行线程数: {NUM_WORKERS}")
        if MAX_IMAGES:
            print(f"🔢 限制处理数量: {MAX_IMAGES} 张")
        print(f"🎯 专门优化: 仅检测底部黑边，从左上角裁剪")
        print("-" * 60)
        
        # 加载之前的进度
        self.load_progress()
        
        # 获取所有图片文件
        image_files = self.get_image_files()
        total_files = len(image_files)
        
        # 过滤已处理的文件
        unprocessed_files = [
            f for f in image_files 
            if f.name not in self.progress_data['processed_files']
        ]
        
        self.stats['total_images'] = total_files
        self.progress_data['total_files'] = total_files
        self.stats['start_time'] = datetime.now().isoformat()
        
        already_processed = total_files - len(unprocessed_files)
        
        self.logger.info(f"总图片数: {total_files}")
        self.logger.info(f"已处理: {already_processed}")
        self.logger.info(f"待处理: {len(unprocessed_files)}")
        
        if len(unprocessed_files) == 0:
            self.logger.info("✅ 所有图片已处理完成！")
            return
        
        # 创建进度条
        progress_bar = tqdm(
            total=len(unprocessed_files),
            desc="🖼️  处理图片",
            unit="张",
            position=0,
            leave=True,
            bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}] {postfix}'
        )
        
        # 初始化计数器
        normal_count = len(self.progress_data['normal_files'])
        problematic_count = len(self.progress_data['problematic_files'])
        failed_count = len(self.progress_data['failed_files'])
        
        def update_progress(result):
            nonlocal normal_count, problematic_count, failed_count
            
            if result == 'normal':
                normal_count += 1
            elif result == 'problematic':
                problematic_count += 1
            elif result == 'failed':
                failed_count += 1
            
            # 更新进度条描述
            progress_bar.set_postfix({
                '✅正常': normal_count,
                '🔧黑边': problematic_count,
                '❌失败': failed_count
            })
            progress_bar.update(1)
            
            # 定期保存进度
            if (normal_count + problematic_count + failed_count) % 100 == 0:
                self.save_progress()
        
        try:
            # 多线程处理
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.num_workers) as executor:
                # 提交所有任务
                future_to_file = {
                    executor.submit(self.process_single_image, image_path): image_path
                    for image_path in unprocessed_files
                }
                
                # 处理完成的任务
                for future in concurrent.futures.as_completed(future_to_file):
                    try:
                        result = future.result()
                        update_progress(result)
                    except Exception as e:
                        self.logger.error(f"处理任务时出错: {e}")
                        update_progress('failed')
        
        except KeyboardInterrupt:
            self.logger.info("收到中断信号，正在保存进度...")
            self.save_progress()
            raise
        
        finally:
            progress_bar.close()
        
        # 更新最终统计
        self.stats['processed_images'] = normal_count
        self.stats['problematic_images'] = problematic_count
        self.stats['failed_images'] = failed_count
        self.stats['end_time'] = datetime.now().isoformat()
        
        # 保存最终进度
        self.save_progress()
        
        # 输出统计信息
        elapsed_time = datetime.fromisoformat(self.stats['end_time']) - datetime.fromisoformat(self.stats['start_time'])
        
        print(f"\n🎉 处理完成!")
        print(f"📊 处理统计:")
        print(f"   • 总图片数: {total_files}")
        print(f"   • ✅ 正常图片: {normal_count}")
        print(f"   • 🔧 有黑边图片: {problematic_count}")
        print(f"   • ❌ 失败图片: {failed_count}")
        print(f"   • ⏱️  处理时间: {elapsed_time}")
        print(f"   • 🚀 平均速度: {len(unprocessed_files)/elapsed_time.total_seconds():.2f} 张/秒")
        print(f"📁 输出目录:")
        print(f"   • 处理后图片: {self.output_dir}")
        print(f"   • 有问题原图: {self.problematic_dir}")
        print(f"   • 进度文件: {self.progress_file}")

def main():
    """
    主函数 - 不再需要外部参数，直接使用顶部配置的变量
    """
    try:
        processor = OptimizedPanoramaProcessor()
        processor.process_all_images()
    except KeyboardInterrupt:
        print("\n⚠️  处理被用户中断")
        print("💾 进度已保存，重新运行脚本即可继续处理")
    except Exception as e:
        print(f"❌ 处理过程中出现错误: {e}")
        logging.error(f"处理过程中出现错误: {e}")

if __name__ == '__main__':
    main() 