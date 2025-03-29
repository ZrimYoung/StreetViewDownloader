# 配置文件编辑器代码

import tkinter as tk  # tkinter 是 Python 的标准 GUI 库
from tkinter import ttk, messagebox, filedialog  # ttk 提供更美观的控件，messagebox 和 filedialog 用于对话框
from configparser import ConfigParser  # 用于读取和写入 INI 配置文件
import os  # 操作文件系统用

# 配置文件名
INI_FILE = 'configuration.ini'

# 配置文件的默认内容（包含路径设置、下载参数、图块拼接参数）
DEFAULT_CONFIG = {
    'PATHS': {
        'csv_path': 'POINTS.csv',
        'api_key_path': 'api_key.txt',
        'save_dir': 'output_dir',
        'log_path': 'download_log.csv',
        'fail_log_path': 'failed_log.csv'
    },
    'PARAMS': {
        'batch_size': '10',
        'num_batches': '3'
    },
    'TILES': {
        'zoom': '1',
        'tile_size': '512',
        'tile_cols': '2',
        'tile_rows': '1',
        'sleeptime': '0.02'
    }
}

# 各配置部分的中文标题
SECTION_NAME_MAP = {
    'PATHS': '路径配置',
    'PARAMS': '下载参数',
    'TILES': '图块参数',
}

# 每个参数字段的中文标签
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

# 指定哪些字段需要使用文件/文件夹选择器，以及对应的文件类型过滤
PATH_KEYS = {
    'csv_path': ('file', [('CSV 文件', '*.csv')]),
    'api_key_path': ('file', [('文本文件', '*.txt'), ('所有文件', '*.*')]),
    'save_dir': ('dir', None),
    'log_path': ('file', [('CSV 文件', '*.csv')]),
    'fail_log_path': ('file', [('CSV 文件', '*.csv')]),
}

# 如果配置文件不存在，自动生成默认配置文件
if not os.path.exists(INI_FILE):
    config = ConfigParser()
    for section, items in DEFAULT_CONFIG.items():
        config[section] = items
    with open(INI_FILE, 'w', encoding='utf-8') as f:
        config.write(f)

# GUI 主类
class ConfigEditor:
    def __init__(self, root):
        # 初始化窗口属性
        self.root = root
        self.root.title("谷歌街景下载器配置编辑器")
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        self.root.minsize(width, height)
        self.root.resizable(False, False)

        # 设置字体
        self.default_font = ("微软雅黑", 10)
        self.section_font = ("微软雅黑", 12, "bold")

        # 加载配置文件
        self.config = ConfigParser()
        self.config.read(INI_FILE, encoding='utf-8')

        self.entries = {}  # 存储输入框控件
        self.check_and_initialize_logs()  # 自动初始化日志文件
        self.build_form()  # 构建界面表单

    # 初始化日志文件（如果文件不存在则创建）
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

    # 构建图形界面表单
    def build_form(self):
        row = 0
        for section in self.config.sections():
            # 添加分隔线和 Section 中文标题
            section_name = SECTION_NAME_MAP.get(section, section)
            frame = ttk.Separator(self.root, orient='horizontal')
            frame.grid(row=row, column=0, columnspan=3, sticky='ew', pady=(10, 2))
            row += 1
            label = ttk.Label(self.root, text=section_name, font=self.section_font)
            label.grid(row=row, column=0, columnspan=3, sticky='w', padx=10)
            row += 1

            # 遍历该 section 的每个参数字段
            for key, value in self.config[section].items():
                cn_label = LABEL_MAP.get(key.lower(), '')
                display_name = f"{cn_label}（{key}）" if cn_label else key
                ttk.Label(self.root, text=display_name, font=self.default_font).grid(row=row, column=0, sticky='e', padx=10)

                # 创建输入框
                entry = ttk.Entry(self.root, width=40, font=self.default_font)
                entry.insert(0, value)
                entry.grid(row=row, column=1, padx=10, pady=2)
                self.entries[(section, key)] = entry

                # 如果是路径字段，添加“选择”按钮
                if key.lower() in PATH_KEYS:
                    btn = ttk.Button(self.root, text="选择", command=lambda k=(section, key): self.select_path(k))
                    btn.grid(row=row, column=2, padx=5)

                row += 1

        # 保存按钮
        save_btn = ttk.Button(self.root, text="保存配置", command=self.save_config)
        save_btn.grid(row=row, column=0, columnspan=3, pady=10)

    # 文件或文件夹路径选择器
    def select_path(self, key_tuple):
        section, key = key_tuple
        path_type, filetypes = PATH_KEYS.get(key.lower(), ('file', None))
        if path_type == 'dir':
            path = filedialog.askdirectory()
            # 如果目录不存在，自动创建
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

    # 保存配置并校验输入格式
    def save_config(self):
        for (section, key), entry in self.entries.items():
            value = entry.get()

            # 如果是路径字段，尝试自动创建必要目录/文件
            if key.lower() in PATH_KEYS:
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

            # 校验整数字段
            elif key.lower() in {'batch_size', 'num_batches', 'zoom', 'tile_size', 'tile_cols', 'tile_rows'}:
                if not value.isdigit():
                    messagebox.showerror("输入格式错误", f"[{section}] {key} 必须是整数")
                    return

            # 校验浮点字段
            elif key.lower() == 'sleeptime':
                try:
                    float(value)
                except ValueError:
                    messagebox.showerror("输入格式错误", f"[{section}] sleeptime 必须是浮点数")
                    return

            # 赋值到配置中
            self.config[section][key] = value

        # 写入 INI 配置文件
        with open(INI_FILE, 'w', encoding='utf-8') as f:
            self.config.write(f)

        messagebox.showinfo("保存成功", f"配置文件已保存到 {INI_FILE}")

# 主程序入口
if __name__ == '__main__':
    try:
        # 兼容 Windows 高分屏显示
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass

    # 启动 GUI 窗口
    root = tk.Tk()
    app = ConfigEditor(root)
    root.mainloop()
