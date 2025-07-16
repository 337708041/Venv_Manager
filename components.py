from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                           QLabel, QLineEdit, QProgressBar, QSizePolicy, QComboBox, QFileDialog, QMessageBox)
from PyQt5.QtCore import Qt
import sys
import os
from pathlib import Path
import subprocess

class PathSelector(QWidget):
    """路径选择组件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.path_label = QLabel('当前路径:')
        self.path_display = QLineEdit()
        self.path_display.setReadOnly(True)
        self.change_path_btn = QPushButton('更改路径')
        
        layout.addWidget(self.path_label)
        layout.addWidget(self.path_display)
        layout.addWidget(self.change_path_btn)

class ProgressWidget(QWidget):
    """进度显示组件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.status_label.setMinimumWidth(150)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        
        # 设置进度条的大小策略，使其占用75%的宽度
        self.progress_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        # 创建一个包装器widget来控制进度条的宽度
        self.progress_wrapper = QWidget()
        progress_layout = QHBoxLayout(self.progress_wrapper)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.addWidget(self.progress_bar)
        
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_wrapper)
        layout.addStretch()
        
        self.hide()

    def showEvent(self, event):
        """组件显示时更新宽度"""
        super().showEvent(event)
        self.update_progress_width()
        
        # 设置父窗口的resize事件
        if self.parent() and not hasattr(self.parent(), '_original_resize_event'):
            self.parent()._original_resize_event = self.parent().resizeEvent
            self.parent().resizeEvent = self._handle_parent_resize

    def _handle_parent_resize(self, event):
        """处理父窗口大小变化"""
        if hasattr(self.parent(), '_original_resize_event'):
            self.parent()._original_resize_event(event)
        self.update_progress_width()

    def update_progress_width(self):
        """更新进度条宽度"""
        if self.parent():
            width = int(self.parent().width() * 0.75)
            self.progress_wrapper.setFixedWidth(width)

    def update_progress(self, value, message):
        """更新进度"""
        self.show()
        self.progress_bar.setValue(value)
        self.status_label.setText(message)

class InputWithButton(QWidget):
    """输入框和按钮组合组件"""
    def __init__(self, placeholder='', button_text='', parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.input = QLineEdit()
        self.input.setPlaceholderText(placeholder)
        self.button = QPushButton(button_text)
        
        layout.addWidget(self.input)
        layout.addWidget(self.button)

class ButtonGroup(QWidget):
    """按钮组组件"""
    def __init__(self, buttons=None, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.buttons = {}
        if buttons:
            for text in buttons:
                btn = QPushButton(text)
                self.buttons[text] = btn
                layout.addWidget(btn)

class PythonSelector(QWidget):
    """Python解释器选择组件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.python_label = QLabel('Python解释器:')
        self.python_combo = QComboBox()
        self.python_combo.setMinimumWidth(200)
        self.refresh_btn = QPushButton('刷新')
        
        layout.addWidget(self.python_label)
        layout.addWidget(self.python_combo)
        layout.addWidget(self.refresh_btn)
        
        # 连接信号
        self.refresh_btn.clicked.connect(self.scan_python_interpreters)
        self.python_combo.activated.connect(self._handle_combo_activated)
        
        # 初始扫描
        self.scan_python_interpreters()
    
    def scan_python_interpreters(self):
        """扫描系统中的Python解释器"""
        self.python_combo.clear()
        
        # 获取当前Python信息
        try:
            current_python = sys.executable
            result = subprocess.run(
                [current_python, '--version'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                self.python_combo.addItem(f"{version} (当前环境)", None)
            else:
                self.python_combo.addItem('使用当前Python', None)
        except:
            self.python_combo.addItem('使用当前Python', None)
            
        self.python_combo.addItem('手动选择...', 'manual')
        self.python_combo.insertSeparator(2)  # 添加分隔线
        
        # 扫描常见Python安装路径
        paths = self._get_search_paths()
        for path in paths:
            self._scan_directory(path)
    
    def _handle_combo_activated(self, index):
        """处理下拉框选择事件"""
        if self.python_combo.itemData(index) == 'manual':
            python_path, _ = QFileDialog.getOpenFileName(
                self,
                '选择Python解释器',
                str(Path.home()),
                'Python (python.exe);;All Files (*)' if sys.platform == 'win32' else 'Python (python);;All Files (*)'
            )
            
            if python_path:
                try:
                    # 验证选择的是否为有效的Python解释器
                    result = subprocess.run(
                        [python_path, '--version'],
                        capture_output=True,
                        text=True
                    )
                    if result.returncode == 0:
                        version = result.stdout.strip()
                        # 首先检查是否已存在于列表中
                        for i in range(self.python_combo.count()):
                            item_text = self.python_combo.itemText(i)
                            item_data = self.python_combo.itemData(i)
                            # 检查路径是否匹配
                            if item_data and str(Path(item_data)) == str(Path(python_path)):
                                self.python_combo.setCurrentIndex(i)
                                return
                            # 检查版本字符串是否匹配
                            if f"{version} ({python_path})" == item_text:
                                self.python_combo.setCurrentIndex(i)
                                return
                        
                        # 如果不存在，则添加到列表并选中
                        self.python_combo.addItem(f"{version} ({python_path})", str(python_path))
                        self.python_combo.setCurrentIndex(self.python_combo.count() - 1)
                    else:
                        raise Exception("无效的Python解释器")
                except Exception as e:
                    QMessageBox.critical(self, '错误', f'选择的Python解释器无效: {str(e)}')
                    self.python_combo.setCurrentIndex(0)  # 重置为默认选项
            else:
                self.python_combo.setCurrentIndex(0)  # 如果用户取消选择，重置为默认选项
    
    def _scan_directory(self, path_pattern):
        """扫描目录查找Python解释器"""
        try:
            if isinstance(path_pattern, str):
                path_pattern = Path(path_pattern)
                
            paths = []  # 初始化paths列表
            
            try:
                if '*' in str(path_pattern):
                    # 处理通配符路径
                    parent = path_pattern.parent
                    pattern = path_pattern.name
                    if parent.exists() and os.access(parent, os.R_OK):  # 检查读取权限
                        paths = list(parent.glob(pattern))
                else:
                    # 处理确切路径
                    if path_pattern.exists() and os.access(path_pattern, os.R_OK):  # 检查读取权限
                        paths = [path_pattern]
                    
                for path in paths:
                    if os.access(path, os.R_OK):  # 确保有读取权限
                        self._add_python_from_path(path)
            except PermissionError:
                # 忽略权限错误，继续扫描其他路径
                pass
                
        except Exception as e:
            # 只打印非权限相关的错误
            if not isinstance(e, PermissionError):
                print(f"扫描路径 {path_pattern} 时出错: {str(e)}")
    
    def _get_search_paths(self):
        """获取需要扫描的路径列表"""
        paths = []
        if sys.platform == 'win32':
            # Windows路径
            # 获取当前用户的 AppData 路径
            appdata_local = os.getenv('LOCALAPPDATA')
            program_files = os.getenv('ProgramFiles')
            program_files_x86 = os.getenv('ProgramFiles(x86)')
            
            # 添加常见的Python安装路径
            if appdata_local:
                paths.append(Path(appdata_local) / 'Programs' / 'Python*')
            
            if program_files:
                paths.append(Path(program_files) / 'Python*')
                
            if program_files_x86:
                paths.append(Path(program_files_x86) / 'Python*')
                
            # 检查系统PATH中的Python
            system_paths = os.getenv('PATH', '').split(os.pathsep)
            for sys_path in system_paths:
                if 'python' in sys_path.lower():
                    paths.append(Path(sys_path))
        else:
            # Unix-like系统路径
            paths.extend([
                Path('/usr/bin'),
                Path('/usr/local/bin'),
                Path(os.path.expanduser('~/.local/bin'))
            ])
        return paths
    
    def _add_python_from_path(self, path):
        """添加找到的Python解释器到下拉框"""
        try:
            if path.is_dir():
                # 目录情况
                python_exec = 'python.exe' if sys.platform == 'win32' else 'python'
                python_path = path / python_exec
                if not python_path.exists() and sys.platform == 'win32':
                    python_path = path / 'python.exe'
            else:
                # 文件情况
                python_path = path
            
            if python_path.exists() and os.access(python_path, os.X_OK):  # 检查执行权限
                try:
                    # 获取版本信息
                    result = os.popen(f'"{python_path}" --version 2>&1').read().strip()
                    if result and 'python' in result.lower():
                        # 检查是否已经添加过相同的解释器
                        version_str = f"{result} ({python_path})"
                        for i in range(self.python_combo.count()):
                            if self.python_combo.itemText(i) == version_str:
                                return
                        self.python_combo.addItem(version_str, str(python_path))
                except:
                    pass
                    
        except Exception as e:
            # 忽略权限错误
            if not isinstance(e, PermissionError):
                print(f"处理Python路径 {path} 时出错: {str(e)}")
    
    def get_selected_python(self):
        """获取选中的Python解释器路径"""
        return self.python_combo.currentData() 