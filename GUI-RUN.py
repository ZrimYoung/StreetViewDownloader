import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from configparser import ConfigParser
import os

# 配置文件名
INI_FILE = 'configuration.ini'

# 配置文件的默认内容
DEFAULT_CONFIG = {
    'PATHS': {
        'csv_path': 'POINTS.csv',
        'api_key_path': 'api_key.txt',
        'save_dir': 'output_dir',
        'log_path': 'download_log.csv',
        'fail_log_path': 'failed_log.csv',
        'detailed_log_path': 'detailed_run.log'
    },
    'PARAMS': {
        'retry_failed_points': 'False', # Moved to top for default order
        'batch_size': '150',
        'num_batches': '10',
        'max_point_workers': '5'
    },
    'TILES': { # Default matches "Zoom 1(快速测试 , 2x1 瓦片)"
        'zoom': '1',
        'tile_size': '512',
        'tile_cols': '2',
        'tile_rows': '1',
        'sleeptime': '0.01'
    }
}

# 各配置部分的中文标题 (英文名将自动从section key获取)
SECTION_NAME_MAP = {
    'PATHS': '路径配置',
    'PARAMS': '下载参数',
    'TILES': '图块参数',
}

# 每个参数字段的中文标签 (英文名将自动从item key获取)
LABEL_MAP = {
    'csv_path': '点位CSV文件',
    'api_key_path': 'API密钥文件',
    'save_dir': '图像保存目录',
    'log_path': '成功日志文件',
    'fail_log_path': '失败日志文件',
    'detailed_log_path': '详细运行时日志文件',
    'batch_size': '每批下载数量',
    'num_batches': '总批次数',
    'retry_failed_points': '重试已失败点位',
    'max_point_workers': '点位处理并发数',
    'zoom': '缩放等级', # Zoom, Tile Size etc. will have key appended
    'tile_size': '图块尺寸',
    'tile_cols': '横向图块数',
    'tile_rows': '纵向图块数',
    'sleeptime': '请求间隔时间', # （秒） will be part of the key display
}

# 路径选择字段配置
PATH_KEYS = {
    'csv_path': ('file', [('CSV 文件', '*.csv'), ('所有文件', '*.*')]),
    'api_key_path': ('file', [('文本文件', '*.txt'), ('所有文件', '*.*')]),
    'save_dir': ('dir', None),
    'log_path': ('file', [('CSV 文件', '*.csv')]),
    'fail_log_path': ('file', [('CSV 文件', '*.csv')]),
    'detailed_log_path': ('file', [('日志文件', '*.log'), ('所有文件', '*.*')]),
}

# 图块参数预设定义 (使用您提供的新列表)
TILE_PRESET_CUSTOM_NAME = "自定义 (Custom)"
TILE_PRESETS = {
    "Zoom 0 (基础全景, 1x1 瓦片)": {'zoom': '0', 'tile_size': '512', 'tile_cols': '1', 'tile_rows': '1'},
    "Zoom 1 (快速测试, 2x1 瓦片)": {'zoom': '1', 'tile_size': '512', 'tile_cols': '2', 'tile_rows': '1'}, # Adjusted name slightly for consistency
    "Zoom 2 (中等清晰度, 4x2 瓦片)": {'zoom': '2', 'tile_size': '512', 'tile_cols': '4', 'tile_rows': '2'},
    "Zoom 3 (较高清晰度, 8x4 瓦片)": {'zoom': '3', 'tile_size': '512', 'tile_cols': '8', 'tile_rows': '4'},
    "Zoom 4 (高清晰度, 13x7 瓦片)": {'zoom': '4', 'tile_size': '512', 'tile_cols': '13', 'tile_rows': '7'},
    "Zoom 5 (高清图像, 26x13 瓦片)": {'zoom': '5', 'tile_size': '512', 'tile_cols': '26', 'tile_rows': '13'},
}
# 这些是受预设控制的图块参数键名 (小写)
PRESET_CONTROLLED_TILE_KEYS = ['zoom', 'tile_size', 'tile_cols', 'tile_rows']


if not os.path.exists(INI_FILE):
    config = ConfigParser()
    # Ensure sections are added in a specific order if desired for a new file
    ordered_sections = ['PATHS', 'PARAMS', 'TILES']
    for section_name in ordered_sections:
        if section_name in DEFAULT_CONFIG:
            config[section_name] = DEFAULT_CONFIG[section_name]
    # Add any other sections from DEFAULT_CONFIG not in ordered_sections (if any)
    for section_name, items in DEFAULT_CONFIG.items():
        if not config.has_section(section_name):
             config[section_name] = items

    with open(INI_FILE, 'w', encoding='utf-8') as f:
        config.write(f)
    print(f"提示：配置文件 {INI_FILE} 未找到，已根据默认设置创建。")

class ConfigEditor:
    def __init__(self, root_window):
        self.root = root_window
        self.root.title("谷歌街景下载器配置编辑器 (Google Street View Downloader Config Editor)")
        
        self.style = ttk.Style()
        self.style.theme_use('clam') 
        self.default_font = ("微软雅黑", 10)
        self.section_font = ("微软雅黑", 12, "bold")
        self.root.option_add("*Font", self.default_font)

        self.config = ConfigParser()
        # ConfigParser by default converts keys to lowercase. To preserve case from file:
        self.config.optionxform = str 
        self.config.read(INI_FILE, encoding='utf-8')
        self.ensure_config_completeness()

        self.entries = {}
        self.boolean_vars = {}
        self.tile_preset_var = tk.StringVar() 
        self.tile_param_entries = {} 

        self.check_and_initialize_logs()
        self.build_form()
        self.load_initial_tile_preset_state() 

        self.root.update_idletasks()
        self.root.resizable(True, True)

    def ensure_config_completeness(self):
        dirty = False
        # Preserve original case for sections and keys if they exist
        # If not, use DEFAULT_CONFIG's case
        for section_key_default, default_items in DEFAULT_CONFIG.items():
            # Find if section exists, possibly with different case
            actual_section_key = None
            for s_key in self.config.sections():
                if s_key.lower() == section_key_default.lower():
                    actual_section_key = s_key
                    break
            
            if not actual_section_key:
                self.config.add_section(section_key_default) # Add with default case
                actual_section_key = section_key_default
                dirty = True

            for key_default, default_value in default_items.items():
                actual_item_key = None
                if self.config.has_section(actual_section_key):
                    for item_k in self.config.options(actual_section_key):
                        if item_k.lower() == key_default.lower():
                            actual_item_key = item_k
                            break
                
                if not actual_item_key:
                    self.config.set(actual_section_key, key_default, default_value) # Add with default case
                    dirty = True
        if dirty:
            try:
                with open(INI_FILE, 'w', encoding='utf-8') as configfile:
                    self.config.write(configfile)
                print(f"提示：配置文件 {INI_FILE} 已更新，补充了缺失的默认项。")
                # Re-read to ensure consistency if we modified it
                self.config.read(INI_FILE, encoding='utf-8')
            except Exception as e:
                print(f"⚠️ 无法写入更新后的配置文件 {INI_FILE}: {e}")


    def check_and_initialize_logs(self):
        # Iterate through config using actual (possibly cased) section names
        for section_key_actual in self.config.sections():
            if section_key_actual.lower() == 'paths': # Target 'PATHS' section, case-insensitively
                for key_actual, path in self.config.items(section_key_actual):
                    if key_actual.lower() in ('log_path', 'fail_log_path', 'detailed_log_path'):
                        if not os.path.exists(path):
                            try:
                                parent_dir = os.path.dirname(path)
                                if parent_dir and not os.path.exists(parent_dir):
                                    os.makedirs(parent_dir, exist_ok=True)
                                with open(path, 'w', encoding='utf-8') as f:
                                    if key_actual.lower() == 'fail_log_path': f.write('ID,Reason\n')
                                    elif key_actual.lower() == 'log_path': f.write('ID\n')
                                print(f"提示：日志文件 {path} 未找到，已创建。")
                            except Exception as e:
                                print(f"⚠️ 无法创建日志文件 {path}：{e}")

    def on_tile_preset_change(self, event=None):
        selected_preset_name = self.tile_preset_var.get()
        
        if selected_preset_name == TILE_PRESET_CUSTOM_NAME:
            for key_lower in PRESET_CONTROLLED_TILE_KEYS:
                if key_lower in self.tile_param_entries:
                    self.tile_param_entries[key_lower].config(state='normal')
        elif selected_preset_name in TILE_PRESETS:
            preset_values = TILE_PRESETS[selected_preset_name]
            for key_lower, entry_widget in self.tile_param_entries.items(): # key_lower is already lowercase
                if key_lower in preset_values: # preset_values keys are also lowercase
                    entry_widget.config(state='normal') 
                    entry_widget.delete(0, tk.END)
                    entry_widget.insert(0, preset_values[key_lower])
                    entry_widget.config(state='readonly')
                elif key_lower in PRESET_CONTROLLED_TILE_KEYS: 
                    entry_widget.config(state='normal')
                    entry_widget.delete(0, tk.END)
                    entry_widget.config(state='readonly')

    def handle_tile_entry_focus(self, event):
        if self.tile_preset_var.get() != TILE_PRESET_CUSTOM_NAME:
            self.tile_preset_var.set(TILE_PRESET_CUSTOM_NAME)
            self.on_tile_preset_change() 
            if event.widget.cget('state') == 'readonly': 
                 event.widget.config(state='normal')
            event.widget.focus_set()


    def load_initial_tile_preset_state(self):
        current_tile_config = {}
        # Find the 'TILES' section, case-insensitively
        tiles_section_actual_key = None
        for s_key in self.config.sections():
            if s_key.lower() == 'tiles':
                tiles_section_actual_key = s_key
                break

        if tiles_section_actual_key:
            for key_lower_controlled in PRESET_CONTROLLED_TILE_KEYS:
                # Find the option, case-insensitively
                actual_option_key = None
                for opt_key in self.config.options(tiles_section_actual_key):
                    if opt_key.lower() == key_lower_controlled:
                        actual_option_key = opt_key
                        break
                if actual_option_key:
                    current_tile_config[key_lower_controlled] = self.config.get(tiles_section_actual_key, actual_option_key)
        
        matched_preset = None
        if current_tile_config: 
            for preset_name, preset_values in TILE_PRESETS.items():
                is_match = True
                # preset_values keys are lowercase, current_tile_config keys are also lowercase here
                if not all(current_tile_config.get(key_l) == value for key_l, value in preset_values.items()):
                    is_match = False
                # Ensure current_tile_config doesn't have extra controlled keys not in this preset
                if is_match and not all(key_l in preset_values for key_l in current_tile_config if key_l in PRESET_CONTROLLED_TILE_KEYS):
                     is_match = False
                if is_match and len(current_tile_config) == len(preset_values): # Ensure same number of keys
                    matched_preset = preset_name
                    break
        
        if matched_preset:
            self.tile_preset_var.set(matched_preset)
        else:
            self.tile_preset_var.set(TILE_PRESET_CUSTOM_NAME)
        
        self.on_tile_preset_change() 

    def build_form(self):
        main_frame = ttk.Frame(self.root, padding="10 10 10 10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        row_idx = 0
        # Define preferred section order for display
        section_order_display = ['PATHS', 'PARAMS', 'TILES']
        
        # Get actual section keys from config to maintain casing
        actual_section_keys_map = {s.upper(): s for s in self.config.sections()}
        
        processed_sections_upper = set()

        for section_key_upper_ordered in section_order_display:
            section_orig_case = actual_section_keys_map.get(section_key_upper_ordered)
            if not section_orig_case: # Should not happen if ensure_config_completeness worked
                continue 
            
            processed_sections_upper.add(section_key_upper_ordered)

            english_section_name = section_orig_case 
            chinese_section_name = SECTION_NAME_MAP.get(section_key_upper_ordered, section_orig_case) # Use upper for map key
            section_display_name = f"{chinese_section_name} ({english_section_name})"
            
            if row_idx > 0:
                 ttk.Separator(main_frame, orient='horizontal').grid(row=row_idx, column=0, columnspan=3, sticky='ew', pady=(15, 5))
                 row_idx += 1
            
            section_label_widget = ttk.Label(main_frame, text=section_display_name, font=self.section_font)
            section_label_widget.grid(row=row_idx, column=0, columnspan=3, sticky='w', padx=5, pady=(0,5))
            row_idx += 1

            # Define item order for PARAMS section
            items_to_process_in_section = []
            if section_key_upper_ordered == 'PARAMS':
                param_order_lower = ['retry_failed_points', 'batch_size', 'num_batches', 'max_point_workers']
                actual_options_map = {o.lower(): o for o in self.config.options(section_orig_case)}
                for key_l_ordered in param_order_lower:
                    if key_l_ordered in actual_options_map:
                        orig_opt_key = actual_options_map[key_l_ordered]
                        items_to_process_in_section.append((orig_opt_key, self.config.get(section_orig_case, orig_opt_key)))
                # Add any other params not in defined order (for robustness if INI has more)
                for opt_l, orig_opt_key in actual_options_map.items():
                    if opt_l not in param_order_lower:
                        items_to_process_in_section.append((orig_opt_key, self.config.get(section_orig_case, orig_opt_key)))
            else: # For PATHS and TILES (or other sections)
                items_to_process_in_section = list(self.config.items(section_orig_case))


            if section_key_upper_ordered == 'TILES':
                ttk.Label(main_frame, text=f"图块预设 (Tile Presets):").grid(row=row_idx, column=0, sticky='e', padx=(5,2), pady=2)
                preset_options = [TILE_PRESET_CUSTOM_NAME] + list(TILE_PRESETS.keys())
                preset_combo = ttk.Combobox(main_frame, textvariable=self.tile_preset_var, values=preset_options, state="readonly", width=42) # Adjusted width
                preset_combo.grid(row=row_idx, column=1, padx=(0,10), pady=2, sticky='ew')
                preset_combo.bind("<<ComboboxSelected>>", self.on_tile_preset_change)
                row_idx += 1

            for key_original_case, value in items_to_process_in_section:
                key_l = key_original_case.lower()
                cn_label_text = LABEL_MAP.get(key_l, key_l.replace('_', ' ').title())
                widget_display_text = f"{cn_label_text} ({key_original_case})" # Use original case for key in display

                if key_l == 'retry_failed_points':
                    bool_var = tk.BooleanVar(value=(value.lower() == 'true'))
                    self.boolean_vars[(section_orig_case, key_original_case)] = bool_var
                    # Checkbutton uses the full display text
                    chk = ttk.Checkbutton(main_frame, text=widget_display_text, variable=bool_var) 
                    chk.grid(row=row_idx, column=0, columnspan=2, sticky='w', padx=5, pady=2)
                else:
                    # General Label for other items
                    label_widget = ttk.Label(main_frame, text=widget_display_text)
                    label_widget.grid(row=row_idx, column=0, sticky='e', padx=(5,2), pady=2)
                    
                    # Entry widgets
                    entry = ttk.Entry(main_frame, width=45)
                    entry.insert(0, value)
                    entry.grid(row=row_idx, column=1, padx=(0,10), pady=2, sticky='ew')
                    self.entries[(section_orig_case, key_original_case)] = entry

                    if section_key_upper_ordered == 'TILES' and key_l in PRESET_CONTROLLED_TILE_KEYS:
                        self.tile_param_entries[key_l] = entry 
                        entry.bind("<FocusIn>", self.handle_tile_entry_focus)
                    
                    if key_l in PATH_KEYS:
                        btn = ttk.Button(main_frame, text="选择", command=lambda k_tuple=(section_orig_case, key_original_case): self.select_path(k_tuple))
                        btn.grid(row=row_idx, column=2, padx=5, pady=2)
                
                main_frame.columnconfigure(1, weight=1)
                row_idx += 1
        
        # Process any sections not in section_order_display (if any, for robustness)
        for section_orig_case in self.config.sections():
            if section_orig_case.upper() not in processed_sections_upper:
                # ... (similar logic to display these sections and their items) ...
                # This part can be omitted if section_order_display is exhaustive for display
                pass

        save_btn = ttk.Button(main_frame, text="保存配置 (Save Config)", command=self.save_config, style="Accent.TButton")
        save_btn.grid(row=row_idx, column=0, columnspan=3, pady=20)
        
        try:
            self.style.configure("Accent.TButton", font=(self.default_font[0], self.default_font[1], "bold"))
        except tk.TclError:
            print("提示：当前主题可能不支持 Accent.TButton 样式。")


    def select_path(self, key_tuple):
        section, key = key_tuple # key is original case
        key_lower = key.lower()
        path_type, filetypes = PATH_KEYS.get(key_lower, ('file', None))
        
        entry_widget = self.entries.get((section, key))
        if not entry_widget: return

        current_path = entry_widget.get()
        initial_dir = os.path.dirname(current_path) if current_path and os.path.exists(os.path.dirname(current_path)) else '.'
        
        cn_label_text = LABEL_MAP.get(key_lower, key_lower.replace('_', ' ').title())
        dialog_title = f"选择 {cn_label_text} ({key})"


        path = ""
        if path_type == 'dir':
            path = filedialog.askdirectory(initialdir=initial_dir, title=dialog_title)
        else:
            path = filedialog.askopenfilename(initialdir=initial_dir, filetypes=filetypes, title=dialog_title)

        if path:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, path)

    def save_config(self):
        temp_config = ConfigParser()
        temp_config.optionxform = str # Preserve case when writing

        for section_orig_case_read in self.config.sections(): # Iterate based on current config's sections
            temp_config.add_section(section_orig_case_read)
            for key_orig_case_read in self.config.options(section_orig_case_read):
                key_l = key_orig_case_read.lower()
                value_str = ""

                if key_l == 'retry_failed_points':
                    # Find the actual (section, key) tuple used for boolean_vars, which should match original case
                    actual_tuple = None
                    for s_k_tuple in self.boolean_vars:
                        if s_k_tuple[0].lower() == section_orig_case_read.lower() and s_k_tuple[1].lower() == key_l:
                            actual_tuple = s_k_tuple
                            break
                    bool_var = self.boolean_vars.get(actual_tuple)
                    value_str = str(bool_var.get()) if bool_var else self.config.get(section_orig_case_read, key_orig_case_read) # fallback
                
                elif section_orig_case_read.lower() == 'tiles' and key_l in PRESET_CONTROLLED_TILE_KEYS:
                    selected_preset_name = self.tile_preset_var.get()
                    if selected_preset_name != TILE_PRESET_CUSTOM_NAME and selected_preset_name in TILE_PRESETS:
                        value_str = TILE_PRESETS[selected_preset_name].get(key_l, self.config.get(section_orig_case_read, key_orig_case_read)) 
                    else: 
                        entry = self.tile_param_entries.get(key_l) # tile_param_entries uses lowercase keys
                        value_str = entry.get() if entry else self.config.get(section_orig_case_read, key_orig_case_read)
                else: 
                    entry = self.entries.get((section_orig_case_read, key_orig_case_read))
                    value_str = entry.get() if entry else self.config.get(section_orig_case_read, key_orig_case_read)

                # Path creation and validation logic (remains largely the same)
                if key_l in PATH_KEYS:
                    try:
                        if PATH_KEYS[key_l][0] == 'dir':
                            if value_str and not os.path.exists(value_str): os.makedirs(value_str, exist_ok=True)
                        else:
                            parent_dir = os.path.dirname(value_str)
                            if parent_dir and not os.path.exists(parent_dir): os.makedirs(parent_dir, exist_ok=True)
                            if value_str and not os.path.exists(value_str):
                                with open(value_str, 'w', encoding='utf-8') as f:
                                    if key_l == 'fail_log_path': f.write('ID,Reason\n')
                                    elif key_l == 'log_path': f.write('ID\n')
                    except Exception as e:
                        messagebox.showerror("路径创建失败", f"为 [{section_orig_case_read}] {key_orig_case_read} ({value_str}) 创建路径时出错: {e}")
                        return
                
                if key_l in {'batch_size', 'num_batches', 'zoom', 'tile_size', 'tile_cols', 'tile_rows', 'max_point_workers'}:
                    if not value_str.isdigit() or int(value_str) < 0:
                        cn_text = LABEL_MAP.get(key_l, key_l)
                        messagebox.showerror("输入格式错误", f"[{section_orig_case_read}] {cn_text} ({key_orig_case_read}) 必须是一个非负整数。")
                        return
                elif key_l == 'sleeptime':
                    try:
                        if float(value_str) < 0:
                             cn_text = LABEL_MAP.get(key_l, key_l)
                             messagebox.showerror("输入格式错误", f"[{section_orig_case_read}] {cn_text} ({key_orig_case_read}) 必须是一个非负浮点数。")
                             return
                        float(value_str) 
                    except ValueError:
                        cn_text = LABEL_MAP.get(key_l, key_l)
                        messagebox.showerror("输入格式错误", f"[{section_orig_case_read}] {cn_text} ({key_orig_case_read}) 必须是浮点数。")
                        return
                
                temp_config.set(section_orig_case_read, key_orig_case_read, value_str)
        
        try:
            with open(INI_FILE, 'w', encoding='utf-8') as configfile:
                temp_config.write(configfile)
            # Update self.config with the new, potentially case-preserved config
            self.config = ConfigParser()
            self.config.optionxform = str 
            self.config.read(INI_FILE, encoding='utf-8')
            messagebox.showinfo("保存成功", f"配置文件已保存到 {INI_FILE}")
        except Exception as e:
            messagebox.showerror("保存失败", f"无法写入配置文件 {INI_FILE}: {e}")

if __name__ == '__main__':
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception: 
        print("提示: 未能设置 DPI awareness (可能是非 Windows 系统或环境不支持)。")

    root = tk.Tk()
    app = ConfigEditor(root)
    root.mainloop()
