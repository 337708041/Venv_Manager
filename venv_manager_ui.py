import logging
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                           QPushButton, QLineEdit, QLabel, QListWidget, QListWidgetItem,
                           QMessageBox, QFileDialog, QProgressBar, QDialog,
                           QInputDialog, QStyledItemDelegate, QStyle)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSettings, QRect
from PyQt5.QtGui import QPainter, QFontMetrics
from venv_manager import VenvManager
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Value, Lock
from package_manager_ui import PackageManagerDialog
from settings_dialog import SettingsDialog
from config_manager import ConfigManager
from components import PathSelector, ProgressWidget, InputWithButton, ButtonGroup, PythonSelector
import os
import subprocess

class VenvItemDelegate(QStyledItemDelegate):
    """自定义列表项代理,用于在最右侧显示Python版本"""
    
    def paint(self, painter, option, index):
        # 获取项目数据
        venv_path = index.data()
        python_version = index.data(Qt.UserRole + 1)
        
        # 如果没有Python版本信息，使用默认绘制
        if not python_version:
            super().paint(painter, option, index)
            return
            
        # 保存画笔状态
        painter.save()
        
        # 绘制选中状态背景
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
            painter.setPen(option.palette.highlightedText().color())
        else:
            painter.setPen(option.palette.text().color())
            
        # 计算文本区域
        text_rect = QRect(option.rect)
        text_rect.setWidth(text_rect.width() - 5)  # 右边留出一点空间
        
        # 获取版本文本的宽度
        version_text = f"[{python_version}]"
        font_metrics = QFontMetrics(option.font)
        version_width = font_metrics.horizontalAdvance(version_text)
        
        # 绘制路径文本（左对齐）
        path_rect = QRect(text_rect)
        path_rect.setRight(text_rect.right() - version_width - 10)  # 为版本文本留出空间
        painter.drawText(path_rect, Qt.AlignLeft | Qt.AlignVCenter, venv_path)
        
        # 绘制版本文本（右对齐）
        version_rect = QRect(text_rect)
        version_rect.setLeft(text_rect.right() - version_width)
        painter.drawText(version_rect, Qt.AlignRight | Qt.AlignVCenter, version_text)
        
        # 恢复画笔状态
        painter.restore()

class VenvWorker(QThread):
    """工作线程类，用于处理耗时的虚拟环境操作"""
    finished = pyqtSignal(bool, str)  # 操作完成信号
    progress = pyqtSignal(int, str)   # 进度信号
    venv_found = pyqtSignal(str, str)  # 发现虚拟环境信号 (路径, Python版本)

    def __init__(self, operation, venv_manager, config=None, **kwargs):
        super().__init__()
        self.operation = operation
        self.venv_manager = venv_manager
        self.config = config  # 添加配置对象
        self.kwargs = kwargs
        self.is_scanning = False
        self.is_cancelled = False

    def cancel(self):
        """取消扫描"""
        self.is_cancelled = True

    def run(self):
        try:
            if self.operation == 'copy':
                source_name = self.kwargs['source']
                target_name = self.kwargs['target']
                
                self.progress.emit(10, "正在复制虚拟环境...")
                source_path = self.venv_manager.base_path / source_name
                target_path = self.venv_manager.base_path / target_name
                
                # 创建新环境
                self.progress.emit(30, "创建目标环境...")
                self.venv_manager.create_venv(target_name)
                
                # 获取源环境的包列表
                self.progress.emit(50, "获取包列表...")
                python_path = source_path / ('Scripts' if os.name == 'nt' else 'bin') / ('python.exe' if os.name == 'nt' else 'python')
                result = subprocess.run([str(python_path), '-m', 'pip', 'freeze'], 
                                    capture_output=True, text=True, check=True)
                requirements = result.stdout.splitlines()
                
                if requirements:
                    # 安装包到新环境
                    self.progress.emit(70, "安装包...")
                    target_python = target_path / ('Scripts' if os.name == 'nt' else 'bin') / ('python.exe' if os.name == 'nt' else 'python')
                    for req in requirements:
                        if req.strip() and not req.startswith('#'):
                            try:
                                subprocess.run([str(target_python), '-m', 'pip', 'install', req.strip()],
                                            check=True, capture_output=True, text=True)
                            except subprocess.CalledProcessError as e:
                                logging.error(f"安装包失败: {req}, 错误: {e.stderr}")
                                print(f"Warning: Failed to install {req}: {e.stderr}")
                
                self.progress.emit(100, "完成")
                self.finished.emit(True, f"虚拟环境 {source_name} 已复制到 {target_name}")
                
            elif self.operation == 'create':
                # 创建环境的进度步骤
                self.progress.emit(10, "正在创建虚拟环境...")
                python_path = self.kwargs.get('python_path')
                self.venv_manager.create_venv(
                    self.kwargs['name'],
                    python_path=python_path
                )
                
                # 使用新创建环境的Python解释器
                if self.config.get('auto_upgrade_pip', True):
                    self.progress.emit(50, "正在升级pip...")
                    venv_path = self.venv_manager.base_path / self.kwargs['name']
                    python_path = venv_path / ('Scripts' if os.name == 'nt' else 'bin') / ('python.exe' if os.name == 'nt' else 'python')
                    
                    try:
                        # 首先确保pip已安装
                        subprocess.run([str(python_path), '-m', 'ensurepip', '--upgrade'],
                                    check=True, capture_output=True, text=True)
                        
                        # 升级pip
                        subprocess.run([str(python_path), '-m', 'pip', 'install', '--upgrade', 'pip'],
                                    check=True, capture_output=True, text=True)
                        
                        # 安装基本包
                        subprocess.run([str(python_path), '-m', 'pip', 'install', 'setuptools', 'wheel'],
                                    check=True, capture_output=True, text=True)
                        
                    except subprocess.CalledProcessError as e:
                        print(f"Warning: Failed to upgrade pip: {e.stderr}")
                        # 继续执行，不中断创建过程
                
                self.progress.emit(100, "完成")
                self.finished.emit(True, f"虚拟环境 {self.kwargs['name']} 创建成功")
            elif self.operation == 'delete':
                self.progress.emit(30, "正在删除虚拟环境...")
                self.venv_manager.delete_venv(self.kwargs['name'])
                self.progress.emit(100, "完成")
                self.finished.emit(True, f"虚拟环境 {self.kwargs['name']} 删除成功")
            elif self.operation == 'activate':
                self.venv_manager.activate_venv(self.kwargs['name'])
                self.finished.emit(True, f"虚拟环境 {self.kwargs['name']} 已激活")
            elif self.operation == 'list':
                self.is_scanning = True
                self.is_cancelled = False
                try:
                    root_dirs = [d for d in self.venv_manager.base_path.iterdir() if d.is_dir()]
                    total_items = len(root_dirs)
                    self.progress.emit(0, "开始扫描...")
                    
                    if total_items == 0:
                        self.progress.emit(100, "扫描完成")
                        self.finished.emit(True, str([]))
                        return
                        
                    venvs = []
                    venvs_lock = Lock()
                    scanned_count = Value('i', 0)
                    
                    def scan_dir(root_dir):
                        if self.is_cancelled:
                            return
                        try:
                            def scan_single_dir(path, depth=0, max_depth=None):
                                if self.is_cancelled:
                                    return []
                                if max_depth is not None and depth > max_depth:
                                    return []
                                    
                                results = []
                                try:
                                    if self.venv_manager._is_valid_venv(path):
                                        rel_path = str(path.relative_to(self.venv_manager.base_path))
                                        # 获取Python版本
                                        python_version = ""
                                        if self.config.get('show_python_version'):
                                            python_version = self.venv_manager.get_python_version(path)
                                        self.venv_found.emit(rel_path, python_version)
                                        results.append(rel_path)
                                    
                                    for item in path.iterdir():
                                        if self.is_cancelled:
                                            return results
                                        if item.is_dir():
                                            results.extend(scan_single_dir(item, depth + 1, max_depth))
                                except Exception:
                                    pass
                                return results
                            
                            # 从配置获取扫描深度
                            max_depth = self.config.get('scan_depth', 100)  # 默认值改为100
                            dir_results = scan_single_dir(root_dir, 0, max_depth)
                            
                            with venvs_lock:
                                venvs.extend(dir_results)
                                with scanned_count.get_lock():
                                    scanned_count.value += 1
                                    progress = int((scanned_count.value / total_items) * 100)
                                self.progress.emit(progress, "正在扫描...")
                                
                        except Exception as e:
                            logging.error(f"扫描目录失败: {root_dir}, 错误: {str(e)}")
                            print(f"Error scanning directory {root_dir}: {e}")
                    
                    # 使用配置的线程数
                    max_threads = self.config.get('max_threads', 32)
                    
                    with ThreadPoolExecutor(max_workers=min(max_threads, total_items)) as executor:
                        if not self.is_cancelled:
                            executor.map(scan_dir, root_dirs)
                    
                    if self.is_cancelled:
                        self.progress.emit(0, "扫描已取消")
                        self.finished.emit(False, "扫描已取消")
                    else:
                        self.progress.emit(100, "扫描完成")
                        self.finished.emit(True, str(sorted(venvs)))
                    
                except Exception as e:
                    self.progress.emit(0, f"扫描出错: {str(e)}")
                    self.finished.emit(False, str(e))
                finally:
                    self.is_scanning = False
            elif self.operation == 'batch_delete':
                venv_names = self.kwargs['names']
                total = len(venv_names)
                
                for i, name in enumerate(venv_names, 1):
                    try:
                        progress = int((i - 1) / total * 100)
                        self.progress.emit(progress, f"正在删除 {name}...")
                        self.venv_manager.delete_venv(name)
                    except Exception as e:
                        logging.error(f"删除虚拟环境失败: {name}, 错误: {str(e)}")
                        print(f"Warning: Failed to delete {name}: {str(e)}")
                
                self.progress.emit(100, "完成")
                if total == 1:
                    self.finished.emit(True, f"虚拟环境 {venv_names[0]} 删除成功")
                else:
                    self.finished.emit(True, f"{total} 个虚拟环境删除成功")
        except FileNotFoundError as e:
            logging.exception(f"操作失败: {self.operation}, 未找到文件: {str(e)}")
            self.progress.emit(0, f"错误: 未找到指定的文件，请检查Python路径是否正确")
            self.finished.emit(False, "未找到指定的文件")
        except Exception as e:
            logging.exception(f"操作失败: {self.operation}")
            self.progress.emit(0, f"错误: {str(e)}")
            self.finished.emit(False, str(e))

class VenvManagerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # 移除帮助按钮
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.config = ConfigManager()
        self.venv_manager = VenvManager()
        self.worker = None
        self.is_scanning = False  # 添加扫描状态标志
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self.check_worker)
        self.cleanup_timer.start(100)
        
        # 从配置加载基础路径
        base_path = self.config.get('base_path')
        self.venv_manager.set_base_path(base_path)
        
        self.init_ui()
        # 恢复窗口位置
        self.config.restore_window_geometry(self)

    def closeEvent(self, event):
        """窗口关闭事件"""
        # 保存窗口位置
        self.config.save_window_geometry(self)
        # 保存当前路径
        self.config.set('base_path', str(self.venv_manager.base_path))
        
        if self.worker:
            if self.worker.is_scanning:
                self.worker.cancel()
            if self.worker.isRunning():
                self.worker.quit()
                self.worker.wait()
        event.accept()
        
    def check_worker(self):
        """检查工作线程状态"""
        if self.worker and not self.worker.isRunning():
            self.worker.deleteLater()
            self.worker = None
            
    def _create_worker(self, operation, **kwargs):
        """创建新的工作线程"""
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
        if self.worker:
            self.worker.deleteLater()
            
        self.worker = VenvWorker(
            operation=operation, 
            venv_manager=self.venv_manager,
            config=self.config,  # 传递配置对象
            **kwargs
        )
        self.worker.progress.connect(self.update_progress)
        if operation == 'list':
            self.venv_list.clear()
            self.worker.venv_found.connect(self.add_venv_to_list)
        return self.worker

    def add_venv_to_list(self, venv_path, python_version=""):
        """添加发现的虚拟环境到列表"""
        # 检查是否已存在
        items = self.venv_list.findItems(venv_path, Qt.MatchExactly)
        if not items:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, venv_path)  # 存储原始路径
            
            if python_version and self.config.get('show_python_version'):
                # 创建自定义显示，确保版本信息在最右边
                item.setText(venv_path)
                item.setData(Qt.UserRole + 1, python_version)  # 存储Python版本
            else:
                item.setText(venv_path)
                
            self.venv_list.addItem(item)
            # 按字母顺序排序
            self.venv_list.sortItems()

    def get_venv_path_from_text(self, item_or_text):
        """从列表项或文本中提取虚拟环境路径"""
        # 如果是QListWidgetItem对象
        if isinstance(item_or_text, QListWidgetItem):
            # 优先使用存储的原始路径
            stored_path = item_or_text.data(Qt.UserRole)
            if stored_path:
                return stored_path
            return item_or_text.text()
        
        # 如果是文本字符串（兼容旧代码）
        text = item_or_text
        if '[' in text and ']' in text:
            # 处理制表符分隔的格式
            if '\t' in text:
                return text.split('\t')[0].strip()
            # 兼容旧格式
            return text.split('[')[0].strip()
        return text
        
    def init_ui(self):
        self.setWindowTitle('Python虚拟环境管理器')
        self.setGeometry(300, 300, 600, 400)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 路径选择器
        self.path_selector = PathSelector()
        self.path_selector.path_display.setText(str(self.venv_manager.base_path))
        self.path_selector.change_path_btn.clicked.connect(self.change_base_path)
        layout.addWidget(self.path_selector)
        
        # 虚拟环境列表
        self.venv_list = QListWidget()
        self.venv_list.setAlternatingRowColors(True)
        self.venv_list.setSelectionMode(QListWidget.ExtendedSelection)
        # 设置自定义代理，确保Python版本显示在最右边
        self.venv_list.setItemDelegate(VenvItemDelegate())
        layout.addWidget(QLabel('已存在的虚拟环境:'))
        layout.addWidget(self.venv_list)
        
        # 添加Python选择器
        self.python_selector = PythonSelector()
        layout.addWidget(self.python_selector)
        
        # 创建环境输入区域
        create_layout = QHBoxLayout()
        
        # 环境名称输入
        self.create_input = QLineEdit()
        self.create_input.setPlaceholderText('输入虚拟环境名称')
        create_layout.addWidget(self.create_input)
        
        # 创建按钮
        create_btn = QPushButton('创建虚拟环境')
        create_btn.clicked.connect(self.create_venv)
        create_layout.addWidget(create_btn)
        
        layout.addLayout(create_layout)
        
        # 进度显示
        self.progress_widget = ProgressWidget()
        layout.addWidget(self.progress_widget)
        
        # 操作按钮组
        self.button_group = ButtonGroup([
            '激活环境', '复制环境', '删除环境', '刷新列表', '设置'
        ])
        self.button_group.buttons['激活环境'].clicked.connect(self.activate_venv)
        self.button_group.buttons['复制环境'].clicked.connect(self.copy_venv)
        self.button_group.buttons['删除环境'].clicked.connect(self.delete_venv)
        self.button_group.buttons['刷新列表'].clicked.connect(self.refresh_venv_list)
        self.button_group.buttons['设置'].clicked.connect(self.show_settings)
        layout.addWidget(self.button_group)
        
        # 列表设置
        self.venv_list.itemDoubleClicked.connect(self.show_venv_info)
        
        # 初始化列表
        self.refresh_venv_list()
        
    def create_venv(self):
        """创建虚拟环境"""
        name = self.create_input.text().strip()
        if not name:
            QMessageBox.warning(self, '警告', '请输入虚拟环境名称')
            return
            
        name_path = Path(name)
        if name_path.parts:
            parent_dir = self.venv_manager.base_path / name_path.parent
            parent_dir.mkdir(parents=True, exist_ok=True)
        
        # 获取选中的Python解释器路径
        python_path = self.python_selector.get_selected_python()
        
        # 使用工作线程创建环境
        self.progress_widget.progress_bar.setValue(0)
        worker = self._create_worker(
            'create',
            name=name,
            python_path=python_path
        )
        worker.finished.connect(self._handle_create_result)
        worker.start()

    def _handle_create_result(self, success, msg):
        """处理创建结果"""
        if success:
            if self.config.get('auto_refresh'):
                self.refresh_venv_list()
            self.create_input.clear()
            QMessageBox.information(self, '成功', msg)
        else:
            QMessageBox.critical(self, '错误', f'创建虚拟环境失败: {msg}')

    def activate_venv(self):
        selected = self.venv_list.currentItem()
        if not selected:
            QMessageBox.warning(self, '警告', '请选择要激活的虚拟环境')
            return
            
        venv_name = self.get_venv_path_from_text(selected)
        try:
            # 启动激活线程
            worker = self.venv_manager.activate_venv(venv_name)
            # 等待结果
            worker.join()
            success, msg = worker.result_queue.get()
            
            if not success:
                QMessageBox.critical(self, '错误', f'激活虚拟环境失败: {msg}')
            
        except Exception as e:
            QMessageBox.critical(self, '错误', f'激活虚拟环境失败: {str(e)}')

    def delete_venv(self):
        """删除虚拟环境(支持批量删除)"""
        selected_items = self.venv_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, '警告', '请选择要删除的虚拟环境')
            return
        
        # 获取所有选中的环境名称
        venv_names = [item.text() for item in selected_items]
        count = len(venv_names)
        
        # 构建确认消息
        if count == 1:
            message = f'确定要删除虚拟环境 {venv_names[0]} 吗？'
        else:
            message = f'确定要删除以下 {count} 个虚拟环境吗？\n\n' + '\n'.join(venv_names)
        
        reply = QMessageBox.question(
            self, '确认删除', message,
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.progress_widget.progress_bar.setValue(0)
            worker = self._create_worker('batch_delete', names=venv_names)
            worker.finished.connect(self._handle_delete_result)
            worker.start()

    def _handle_delete_result(self, success, msg):
        if success:
            self.refresh_venv_list()
            QMessageBox.information(self, '成功', msg)
        else:
            QMessageBox.critical(self, '错误', f'删除虚拟环境失败: {msg}')

    def refresh_venv_list(self):
        # 如果正在扫描，先取消当前扫描
        if self.worker and self.worker.is_scanning:
            self.worker.cancel()
            self.progress_widget.status_label.setText("正在取消扫描...")
            return
            
        self.progress_widget.progress_bar.setValue(0)
        worker = self._create_worker('list')
        worker.finished.connect(self._handle_refresh_result)
        worker.start()

    def _handle_refresh_result(self, success, msg):
        """扫描完成的处理"""
        if not success and msg != "扫描已取消":  # 不显示取消的错误消息
            QMessageBox.critical(self, '错误', f'刷新列表失败: {msg}')
        
        # 如果是取消的扫描，自动开始新的扫描
        if msg == "扫描已取消":
            QTimer.singleShot(100, self.refresh_venv_list)

    def change_base_path(self):
        """更改虚拟环境基础路径"""
        new_path = QFileDialog.getExistingDirectory(
            self, 
            '选择虚拟环境存储路径',
            str(self.venv_manager.base_path)
        )
        if new_path:
            try:
                self.venv_manager.set_base_path(new_path)
                self.path_selector.path_display.setText(new_path)
                self.config.add_recent_path(new_path)
                self.refresh_venv_list()
            except Exception as e:
                logging.error(f"更改路径失败: {new_path}, 错误: {str(e)}")
                QMessageBox.critical(self, '错误', f'更改路径失败: {str(e)}')
    
    def show_venv_info(self, item):
        """显示包管理器"""
        venv_path_text = self.get_venv_path_from_text(item.text())
        venv_path = self.venv_manager.base_path / venv_path_text
        dialog = PackageManagerDialog(venv_path, self)
        dialog.exec_()

    def update_progress(self, value, message):
        """更新进度条和状态信息"""
        self.progress_widget.update_progress(value, message)
        
    def hide_progress(self):
        """隐藏进度条和状态标签"""
        self.progress_widget.hide()

    def show_settings(self):
        """显示设置对话框"""
        dialog = SettingsDialog(self.config, self)  # 传递 self.config 而不是 self
        if dialog.exec_() == QDialog.Accepted:
            # 应用新设置
            self.apply_settings()

    def apply_settings(self):
        """应用新的设置"""
        # 直接从 config 获取设置
        self.max_scan_depth = self.config.get('scan_depth')
        self.max_threads = self.config.get('max_threads')
        # 如果设置改变了，刷新列表
        # 当显示Python版本设置改变时，始终刷新列表
        if self.config.get('auto_refresh') or self.config.get('show_python_version'):
            self.refresh_venv_list() 

    def copy_venv(self):
        """复制虚拟环境"""
        selected = self.venv_list.currentItem()
        if not selected:
            QMessageBox.warning(self, '警告', '请选择要复制的虚拟环境')
            return
        
        source_name = self.get_venv_path_from_text(selected)
        target_name, ok = QInputDialog.getText(
            self, '复制虚拟环境',
            '请输入新环境名称:',
            QLineEdit.Normal
        )
        
        if ok and target_name.strip():
            target_name = target_name.strip()
            if target_name == source_name:
                QMessageBox.warning(self, '警告', '新环境名称不能与源环境相同')
                return
            
            target_path = Path(target_name)
            if target_path.parts:
                parent_dir = self.venv_manager.base_path / target_path.parent
                parent_dir.mkdir(parents=True, exist_ok=True)
            
            self.progress_widget.progress_bar.setValue(0)
            worker = self._create_worker('copy', source=source_name, target=target_name)
            worker.finished.connect(self._handle_copy_result)
            worker.start()

    def _handle_copy_result(self, success, msg):
        """处理复制结果"""
        if success:
            self.refresh_venv_list()
            QMessageBox.information(self, '成功', msg)
        else:
            QMessageBox.critical(self, '错误', f'复制虚拟环境失败: {msg}') 