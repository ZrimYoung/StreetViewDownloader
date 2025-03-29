# 原版本配置文件 GUI 编辑器代码 使用打包exe唤起脚本

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
        self.root.title("谷歌街景下载器")
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
            # ✅ 若用户选择了输出目录，但目录不存在，则自动创建
            if path and not os.path.exists(path):
                try:
                    os.makedirs(path, exist_ok=True)
                except Exception as e:
                    messagebox.showerror("目录创建失败", f"无法创建目录：{path}\n{e}")
                    return
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
                # ✅ 自动创建目录或文件（如不存在）
                try:
                    if key.lower() == 'save_dir':
                        os.makedirs(value, exist_ok=True)
                    elif key.lower().endswith('_log_path') or key.lower().endswith('_path'):
                        parent_dir = os.path.dirname(value)
                        if parent_dir and not os.path.exists(parent_dir):
                            os.makedirs(parent_dir, exist_ok=True)
                        if not os.path.exists(value):
                            with open(value, 'w', encoding='utf-8') as f:
                                if 'fail' in key.lower():
                                    f.write('ID,Reason\n')
                                elif 'log' in key.lower():
                                    f.write('ID\n')
                    elif not os.path.exists(value):
                        os.makedirs(os.path.dirname(value), exist_ok=True)
                        with open(value, 'w', encoding='utf-8') as f:
                            pass
                except Exception as e:
                    messagebox.showerror("创建失败", f"[{section}] {key} 自动创建失败：{e}")
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

    def run_downloader(self):
        try:
            # 判断是否在 PyInstaller 打包环境中
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.dirname(os.path.abspath(__file__))

            exe_path = os.path.join(base_path, 'work-ui.exe')

            if not os.path.exists(exe_path):
                raise FileNotFoundError(f"找不到打包的副程序 work-ui.exe：{exe_path}")

            subprocess.Popen([exe_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as e:
            messagebox.showerror("运行失败", f"无法启动下载器：{e}")

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
