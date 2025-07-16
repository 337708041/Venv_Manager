from PyQt5.QtCore import QSettings
import json
from pathlib import Path

class ConfigManager:
    """配置管理类"""
    def __init__(self):
        self.settings = QSettings('VenvManager', 'Settings')
        self.load_defaults()

    def load_defaults(self):
        """加载默认配置"""
        self.defaults = {
            'base_path': str(Path.home() / 'venvs'),  # 默认虚拟环境存储路径
            'auto_refresh': True,                      # 自动刷新列表
            'scan_depth': 5,                          # 扫描深度
            'max_threads': 32,                        # 最大线程数
            'auto_upgrade_pip': True,                 # 自动升级pip
            'show_pkg_size': False,                   # 显示包大小
            'window_geometry': None,                  # 窗口位置和大小
            'last_used_paths': [],                    # 最近使用的路径
        }

    def get(self, key, default=None):
        """获取配置值"""
        if default is None:
            default = self.defaults.get(key)
        
        value = self.settings.value(key, default)
        
        # 类型转换
        if isinstance(default, bool):
            # 确保布尔值正确转换
            if isinstance(value, str):
                return value.lower() == 'true'
            return bool(value)
        elif isinstance(default, int):
            return int(value)
        elif isinstance(default, list):
            try:
                return json.loads(value) if value else default
            except:
                return default
        return value

    def set(self, key, value):
        """设置配置值"""
        if isinstance(value, (list, dict)):
            value = json.dumps(value)
        elif isinstance(value, bool):
            # 确保布尔值被正确存储
            value = 'true' if value else 'false'
        self.settings.setValue(key, value)
        self.settings.sync()

    def save_window_geometry(self, window):
        """保存窗口位置和大小"""
        self.set('window_geometry', window.saveGeometry().toBase64().data().decode())

    def restore_window_geometry(self, window):
        """恢复窗口位置和大小"""
        geometry = self.get('window_geometry')
        if geometry:
            try:
                window.restoreGeometry(bytes(geometry, 'ascii'))
            except:
                pass

    def add_recent_path(self, path):
        """添加最近使用的路径"""
        paths = self.get('last_used_paths', [])
        if path in paths:
            paths.remove(path)
        paths.insert(0, path)
        paths = paths[:10]  # 只保留最近10个
        self.set('last_used_paths', paths)

    def clear(self):
        """清除所有设置"""
        self.settings.clear()
        self.settings.sync() 