# 修改后的配置文件 GUI 编辑器
# - 自动创建默认 configuration.ini（若不存在）
# - 支持文件/文件夹选择器，限制格式，检查路径/格式/日志等
# - section 中文名称显示、分割线、固定窗口尺寸、微软雅黑字体
# - ✅ 添加 "运行下载器" 按钮，弹出终端运行 work-ui.py
# - ✅ 支持打包路径识别，确保 .exe 中可以调用副程序

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from configparser import ConfigParser
import os
import subprocess
import sys

# 配置文件名称
INI_FILE = 'configuration.ini'

# 默认配置内容（按三个 section 分类）
DEFAULT_CONFIG = {
    'PATHS': {
        'csv_path': 'POINTS.csv',  # 点位CSV路径
        'api_key_path': 'api_key.txt',  # API密钥路径
        'save_dir': 'output_dir',  # 保存图像目录
        'log_path': 'download_log.csv',  # 成功日志
        'fail_log_path': 'failed_log.csv'  # 失败日志
    },
    'PARAMS': {
        'batch_size': '10',  # 每批下载点数
        'num_batches': '3'  # 批次数量
    },
    'TILES': {
        'zoom': '1',  # 缩放等级
        'tile_size': '512',  # 图块尺寸
        'tile_cols': '2',  # 横向图块数
        'tile_rows': '1',  # 纵向图块数
        'sleeptime': '0.02'  # 请求间隔
    }
}

# section 显示的中文名
SECTION_NAME_MAP = {
    'PATHS': '路径配置',
    'PARAMS': '下载参数',
    'TILES': '图块参数',
}

# 每个参数的中文标签
LABEL_MAP = {
    'csv_path': '点位CSV文件',
    'api_key_path': 'API密钥文件',
    'save_dir': '图像保存目录',
    'log_path': '成功日志文件',
    'fail_log_path': '失败日志文件',
    'batch_size': '每批下载数量',
    'num_batches': '总批次数',
    'zoom': '缩放等级',
    'tile_size': '图块尺寸',
    'tile_cols': '横向图块数',
    'tile_rows': '纵向图块数',
    'sleeptime': '请求间隔时间（秒）',
}

# 特殊路径字段及其选择器类型（文件/目录）
PATH_KEYS = {
    'csv_path': ('file', [('CSV 文件', '*.csv')]),
    'api_key_path': ('file', [('文本文件', '*.txt'), ('所有文件', '*.*')]),
    'save_dir': ('dir', None),
    'log_path': ('file', [('CSV 文件', '*.csv')]),
    'fail_log_path': ('file', [('CSV 文件', '*.csv')]),
}

# 如果配置文件不存在，创建默认配置文件
if not os.path.exists(INI_FILE):
    config = ConfigParser()
    for section, items in DEFAULT_CONFIG.items():
        config[section] = items
    with open(INI_FILE, 'w', encoding='utf-8') as f:
        config.write(f)

# 主类：配置编辑器 GUI
class ConfigEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("配置文件编辑器 (configuration.ini)")
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        self.root.minsize(width, height)
        self.root.resizable(False, False)
        self.default_font = ("微软雅黑", 10)
        self.section_font = ("微软雅黑", 12, "bold")

        self.config = ConfigParser()
        self.config.read(INI_FILE, encoding='utf-8')

        self.entries = {}  # 存储所有 Entry 控件
        self.check_and_initialize_logs()  # 初始化日志文件
        self.build_form()  # 构建 GUI 表单

    # 自动创建日志文件（若不存在）
    def check_and_initialize_logs(self):
        for section in self.config.sections():
            for key in self.config[section]:
                if key.lower() in ('log_path', 'fail_log_path'):
                    path = self.config[section][key]
                    if not os.path.exists(path):
                        try:
                            with open(path, 'w', encoding='utf-8') as f:
                                if 'fail' in key.lower():
                                    f.write('ID,Reason\n')
                                else:
                                    f.write('ID\n')
                        except Exception as e:
                            print(f"⚠️ 无法创建日志文件 {path}：{e}")

    # 构建窗口控件（表单布局）
    def build_form(self):
        row = 0
        for section in self.config.sections():
            section_name = SECTION_NAME_MAP.get(section, section)
            frame = ttk.Separator(self.root, orient='horizontal')
            frame.grid(row=row, column=0, columnspan=3, sticky='ew', pady=(10, 2))
            row += 1
            label = ttk.Label(self.root, text=section_name, font=self.section_font)
            label.grid(row=row, column=0, columnspan=3, sticky='w', padx=10)
            row += 1

            for key, value in self.config[section].items():
                cn_label = LABEL_MAP.get(key.lower(), '')
                display_name = f"{cn_label}（{key}）" if cn_label else key
                ttk.Label(self.root, text=display_name, font=self.default_font).grid(row=row, column=0, sticky='e', padx=10)

                entry = ttk.Entry(self.root, width=40, font=self.default_font)
                entry.insert(0, value)
                entry.grid(row=row, column=1, padx=10, pady=2)
                self.entries[(section, key)] = entry

                if key.lower() in PATH_KEYS:
                    btn = ttk.Button(self.root, text="选择", command=lambda k=(section, key): self.select_path(k))
                    btn.grid(row=row, column=2, padx=5)

                row += 1

        # 保存按钮
        save_btn = ttk.Button(self.root, text="保存配置", command=self.save_config)
        save_btn.grid(row=row, column=0, columnspan=3, pady=10)

        # 运行下载器按钮（调用 work-ui.py）
        run_btn = ttk.Button(self.root, text="运行下载器", command=self.run_downloader)
        run_btn.grid(row=row+1, column=0, columnspan=3, pady=(0, 10))

    # 文件/文件夹选择器
    def select_path(self, key_tuple):
        section, key = key_tuple
        path_type, filetypes = PATH_KEYS.get(key.lower(), ('file', None))
        if path_type == 'dir':
            path = filedialog.askdirectory()
        else:
            path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            self.entries[(section, key)].delete(0, tk.END)
            self.entries[(section, key)].insert(0, path)

    # 保存配置到 INI 文件
    def save_config(self):
        for (section, key), entry in self.entries.items():
            value = entry.get()
            if key.lower() in PATH_KEYS:
                if not os.path.exists(value):
                    messagebox.showerror("路径不存在", f"[{section}] {key} 路径不存在：{value}")
                    return
            elif key.lower() in {'batch_size', 'num_batches', 'zoom', 'tile_size', 'tile_cols', 'tile_rows'}:
                if not value.isdigit():
                    messagebox.showerror("输入格式错误", f"[{section}] {key} 必须是整数")
                    return
            elif key.lower() == 'sleeptime':
                try:
                    float(value)
                except ValueError:
                    messagebox.showerror("输入格式错误", f"[{section}] sleeptime 必须是浮点数")
                    return
            self.config[section][key] = value

        with open(INI_FILE, 'w', encoding='utf-8') as f:
            self.config.write(f)

        messagebox.showinfo("保存成功", f"配置文件已保存到 {INI_FILE}")

    # 运行下载器脚本：在新命令行窗口中运行 work-ui.py，兼容打包路径
    def run_downloader(self):
        try:
            # 判断是否在 PyInstaller 打包环境中
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.dirname(os.path.abspath(__file__))

            script_path = os.path.join(base_path, 'work-ui.py')
            subprocess.Popen(['python', script_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as e:
            messagebox.showerror("运行失败", f"无法运行下载器脚本：{e}")

# 启动主程序
if __name__ == '__main__':
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)  # 高分辨率支持
    except:
        pass

    root = tk.Tk()
    app = ConfigEditor(root)
    root.mainloop()
