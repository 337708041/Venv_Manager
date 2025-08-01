from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                           QLabel, QCheckBox, QSpinBox, QGroupBox, QFormLayout)
from PyQt5.QtCore import Qt, QSettings

class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        self.setWindowTitle('设置')
        self.setFixedWidth(400)
        layout = QVBoxLayout(self)

        # 常规设置组
        general_group = QGroupBox('常规设置')
        general_layout = QFormLayout()

        # 自动刷新设置
        self.auto_refresh = QCheckBox()
        self.auto_refresh.setToolTip('创建或删除虚拟环境后自动刷新列表')
        general_layout.addRow('自动刷新列表:', self.auto_refresh)

        # 扫描深度设置
        self.scan_depth = QSpinBox()
        self.scan_depth.setRange(1, 100)
        self.scan_depth.setToolTip('扫描子文件夹的最大深度（设置较大的值可以扫描更深的目录）')
        general_layout.addRow('扫描深度:', self.scan_depth)

        # 最大线程数设置
        self.max_threads = QSpinBox()
        self.max_threads.setRange(1, 64)
        self.max_threads.setToolTip('扫描时使用的最大线程数')
        general_layout.addRow('最大线程数:', self.max_threads)

        general_group.setLayout(general_layout)
        layout.addWidget(general_group)

        # 包管理设置组
        pkg_group = QGroupBox('包管理设置')
        pkg_layout = QVBoxLayout()

        # 第一行：自动升级pip和显示包大小
        first_row_layout = QHBoxLayout()
        
        # 自动升级pip
        self.auto_upgrade_pip = QCheckBox('自动升级pip')
        self.auto_upgrade_pip.setToolTip('创建新环境时自动升级pip')
        first_row_layout.addWidget(self.auto_upgrade_pip)
        
        # 显示包大小
        self.show_pkg_size = QCheckBox('显示包大小')
        self.show_pkg_size.setToolTip('在包列表中显示包大小')
        first_row_layout.addWidget(self.show_pkg_size)
        
        pkg_layout.addLayout(first_row_layout)
        
        # 第二行：显示Python版本
        second_row_layout = QHBoxLayout()
        second_row_layout.setAlignment(Qt.AlignLeft)  # 强制左对齐
        
        # 显示Python版本
        self.show_python_version = QCheckBox('显示Python版本')
        self.show_python_version.setToolTip('在虚拟环境列表中显示Python版本')
        second_row_layout.addWidget(self.show_python_version)
        
        pkg_layout.addLayout(second_row_layout)
        
        pkg_group.setLayout(pkg_layout)
        layout.addWidget(pkg_group)

        # 按钮
        btn_layout = QHBoxLayout()
        save_btn = QPushButton('保存')
        cancel_btn = QPushButton('取消')
        reset_btn = QPushButton('重置')

        save_btn.clicked.connect(self.save_settings)
        cancel_btn.clicked.connect(self.reject)
        reset_btn.clicked.connect(self.reset_settings)

        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(reset_btn)
        layout.addLayout(btn_layout)

    def load_settings(self):
        """加载设置"""
        self.auto_refresh.setChecked(self.config.get('auto_refresh'))
        self.scan_depth.setValue(self.config.get('scan_depth'))
        self.max_threads.setValue(self.config.get('max_threads'))
        self.auto_upgrade_pip.setChecked(self.config.get('auto_upgrade_pip'))
        self.show_pkg_size.setChecked(self.config.get('show_pkg_size'))
        self.show_python_version.setChecked(self.config.get('show_python_version'))

    def save_settings(self):
        """保存设置到配置"""
        self.config.set('auto_refresh', self.auto_refresh.isChecked())
        self.config.set('scan_depth', self.scan_depth.value())
        self.config.set('max_threads', self.max_threads.value())
        self.config.set('auto_upgrade_pip', self.auto_upgrade_pip.isChecked())
        self.config.set('show_pkg_size', self.show_pkg_size.isChecked())
        self.config.set('show_python_version', self.show_python_version.isChecked())
        self.accept()

    def reset_settings(self):
        """重置为默认设置"""
        self.config.clear()
        self.config.load_defaults()
        self.load_settings()

    def accept(self):
        """保存设置并关闭对话框"""
        self.config.set('auto_refresh', self.auto_refresh.isChecked())
        self.config.set('scan_depth', self.scan_depth.value())
        self.config.set('max_threads', self.max_threads.value())
        self.config.set('auto_upgrade_pip', self.auto_upgrade_pip.isChecked())
        self.config.set('show_pkg_size', self.show_pkg_size.isChecked())
        self.config.set('show_python_version', self.show_python_version.isChecked())
        
        super().accept() 