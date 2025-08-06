import logging
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                           QPushButton, QLineEdit, QLabel, QListWidget, QListWidgetItem,
                           QMessageBox, QFileDialog, QProgressBar, QDialog,
                           QInputDialog, QMenuBar, QMenu, QAction)
from PyQt5.QtCore import Qt, QTimer, QSettings
from venv_manager import VenvManager
from pathlib import Path
from package_manager_ui import PackageManagerDialog
from settings_dialog import SettingsDialog
from config_manager import ConfigManager
from components import PathSelector, ProgressWidget, InputWithButton, PythonSelector, VenvItemDelegate
from workers import VenvWorker
import os

# 应用版本信息
APP_NAME = "Python虚拟环境管理器"
APP_VERSION = "1.5.0"
APP_AUTHOR = "MAO-NIANG"


class VenvManagerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # 移除帮助按钮
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.config = ConfigManager()
        self.venv_manager = VenvManager()
        self.worker = None
        self.is_scanning = False  # 添加扫描状态标志
        self.current_search_text = ""  # 添加当前搜索文本变量
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
            
            # 如果有搜索条件，应用过滤
            if hasattr(self, 'current_search_text') and self.current_search_text:
                # 检查是否匹配搜索条件
                if (self.current_search_text in venv_path.lower() or 
                    (python_version and self.current_search_text in python_version.lower())):
                    item.setHidden(False)
                else:
                    item.setHidden(True)
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
        self.setWindowTitle(f'{APP_NAME} v{APP_VERSION}')
        self.setGeometry(300, 300, 600, 400)
        
        # 创建菜单栏
        self.create_menu_bar()
        
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
        
        # 启用右键菜单
        self.venv_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.venv_list.customContextMenuRequested.connect(self.show_context_menu)
        
        # 添加搜索框
        search_layout = QHBoxLayout()
        search_label = QLabel('搜索:')
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('按名称或版本过滤')
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.filter_venv_list)
        
        # 添加清除按钮
        clear_btn = QPushButton('清除')
        clear_btn.setToolTip('清除搜索条件')
        clear_btn.clicked.connect(self.clear_search)
        
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(clear_btn)
        

        layout.addLayout(search_layout)
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
        create_btn = QPushButton('创建环境')
        create_btn.setToolTip('创建新的虚拟环境')
        create_btn.clicked.connect(self.create_venv)
        create_layout.addWidget(create_btn)
        
        layout.addLayout(create_layout)
        
        # 进度显示
        self.progress_widget = ProgressWidget()
        layout.addWidget(self.progress_widget)
        
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
        self.progress_widget.update_progress(0, self.progress_widget.status_label.text())
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
            self.progress_widget.update_progress(0, self.progress_widget.status_label.text())
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
            
        self.progress_widget.update_progress(0, self.progress_widget.status_label.text())
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
        elif success:
            # 如果搜索框有内容，应用过滤
            if hasattr(self, 'search_input') and self.search_input.text():
                self.filter_venv_list(self.search_input.text())

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
            except KeyboardInterrupt:
                logging.warning("用户中断了路径更改操作")
                QMessageBox.information(self, '提示', '操作已取消')
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
        
        # 更新菜单项的选中状态
        if hasattr(self, 'auto_refresh_action'):
            self.auto_refresh_action.setChecked(self.config.get('auto_refresh'))
        if hasattr(self, 'show_python_version_action'):
            self.show_python_version_action.setChecked(self.config.get('show_python_version'))
        if hasattr(self, 'auto_upgrade_pip_action'):
            self.auto_upgrade_pip_action.setChecked(self.config.get('auto_upgrade_pip'))
        if hasattr(self, 'show_pkg_size_action'):
            self.show_pkg_size_action.setChecked(self.config.get('show_pkg_size'))
            
        # 如果设置改变了，刷新列表
        # 当显示Python版本设置改变时，始终刷新列表
        if self.config.get('auto_refresh') or self.config.get('show_python_version'):
            self.refresh_venv_list() 
            
    def create_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu('文件')
        
        # 设置菜单 - 作为顶层菜单
        settings_menu = menubar.addMenu('设置')
        
        # 常规设置
        general_settings_action = QAction('设置页面', self)
        general_settings_action.triggered.connect(self.show_settings)
        settings_menu.addAction(general_settings_action)

        # 自动刷新设置
        self.auto_refresh_action = QAction('自动刷新列表', self)
        self.auto_refresh_action.setCheckable(True)
        self.auto_refresh_action.setChecked(self.config.get('auto_refresh'))
        self.auto_refresh_action.triggered.connect(self.toggle_auto_refresh)
        settings_menu.addAction(self.auto_refresh_action)
        
        # 显示Python版本设置
        self.show_python_version_action = QAction('显示Python版本', self)
        self.show_python_version_action.setCheckable(True)
        self.show_python_version_action.setChecked(self.config.get('show_python_version'))
        self.show_python_version_action.triggered.connect(self.toggle_show_python_version)
        settings_menu.addAction(self.show_python_version_action)
        
        # 自动升级pip设置
        self.auto_upgrade_pip_action = QAction('自动升级pip', self)
        self.auto_upgrade_pip_action.setCheckable(True)
        self.auto_upgrade_pip_action.setChecked(self.config.get('auto_upgrade_pip'))
        self.auto_upgrade_pip_action.triggered.connect(self.toggle_auto_upgrade_pip)
        settings_menu.addAction(self.auto_upgrade_pip_action)
        
        # 显示包大小设置
        self.show_pkg_size_action = QAction('显示包大小', self)
        self.show_pkg_size_action.setCheckable(True)
        self.show_pkg_size_action.setChecked(self.config.get('show_pkg_size'))
        self.show_pkg_size_action.triggered.connect(self.toggle_show_pkg_size)
        settings_menu.addAction(self.show_pkg_size_action)
        
        # 添加分隔线
        settings_menu.addSeparator()
        
        # 重置设置
        reset_settings_action = QAction('重置所有设置', self)
        reset_settings_action.triggered.connect(self.reset_all_settings)
        settings_menu.addAction(reset_settings_action)
        
        # 添加分隔线
        file_menu.addSeparator()
        
        # 退出动作
        exit_action = QAction('退出', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu('帮助')
        
        # 关于动作
        about_action = QAction('关于', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

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
            
            self.progress_widget.update_progress(0, self.progress_widget.status_label.text())
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
            
    def toggle_auto_refresh(self):
        """切换自动刷新设置"""
        value = self.auto_refresh_action.isChecked()
        self.config.set('auto_refresh', value)
        
    def toggle_show_python_version(self):
        """切换显示Python版本设置"""
        value = self.show_python_version_action.isChecked()
        self.config.set('show_python_version', value)
        # 刷新列表以应用新设置
        self.refresh_venv_list()
        
    def toggle_auto_upgrade_pip(self):
        """切换自动升级pip设置"""
        value = self.auto_upgrade_pip_action.isChecked()
        self.config.set('auto_upgrade_pip', value)
        
    def toggle_show_pkg_size(self):
        """切换显示包大小设置"""
        value = self.show_pkg_size_action.isChecked()
        self.config.set('show_pkg_size', value)
    
    def filter_venv_list(self, text):
        """根据搜索文本过滤虚拟环境列表"""
        # 保存当前搜索文本，以便在扫描过程中添加新项目时使用
        self.current_search_text = text.lower()
        
        # 如果搜索文本为空，显示所有项
        if not self.current_search_text:
            for i in range(self.venv_list.count()):
                self.venv_list.item(i).setHidden(False)
            return
            
        # 遍历所有项，根据名称和版本过滤
        for i in range(self.venv_list.count()):
            item = self.venv_list.item(i)
            venv_path = item.text().lower()
            python_version = item.data(Qt.UserRole + 1)
            
            # 检查路径或版本是否包含搜索文本
            if self.current_search_text in venv_path or (python_version and self.current_search_text in python_version.lower()):
                item.setHidden(False)
            else:
                item.setHidden(True)
                
    def clear_search(self):
        """清除搜索框并显示所有项"""
        self.search_input.clear()
        self.current_search_text = ""
        # 显示所有项
        for i in range(self.venv_list.count()):
            self.venv_list.item(i).setHidden(False)
        
    def set_scan_depth(self):
        """设置扫描深度"""
        current_depth = self.config.get('scan_depth')
        depth, ok = QInputDialog.getInt(
            self, '设置扫描深度', 
            '请输入扫描子文件夹的最大深度（1-100）：',
            current_depth, 1, 100
        )
        
        if ok:
            self.config.set('scan_depth', depth)
            self.max_scan_depth = depth
            # 如果启用了自动刷新，则刷新列表
            if self.config.get('auto_refresh'):
                self.refresh_venv_list()
                
    def set_max_threads(self):
        """设置最大线程数"""
        current_threads = self.config.get('max_threads')
        threads, ok = QInputDialog.getInt(
            self, '设置最大线程数', 
            '请输入扫描时使用的最大线程数（1-64）：',
            current_threads, 1, 64
        )
        
        if ok:
            self.config.set('max_threads', threads)
            self.max_threads = threads
        
    def reset_all_settings(self):
        """重置所有设置"""
        reply = QMessageBox.question(
            self, '确认重置', '确定要将所有设置重置为默认值吗？',
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.config.clear()
            self.config.load_defaults()
            # 更新菜单项的选中状态
            self.auto_refresh_action.setChecked(self.config.get('auto_refresh'))
            self.show_python_version_action.setChecked(self.config.get('show_python_version'))
            self.auto_upgrade_pip_action.setChecked(self.config.get('auto_upgrade_pip'))
            self.show_pkg_size_action.setChecked(self.config.get('show_pkg_size'))
            # 应用新设置
            self.apply_settings()
            QMessageBox.information(self, '成功', '所有设置已重置为默认值')
    
    def show_context_menu(self, position):
        """显示右键菜单"""
        menu = QMenu()
        
        # 获取当前选中项
        selected_items = self.venv_list.selectedItems()
        
        # 只有在有选中项时才显示激活、复制和删除选项
        if selected_items:
            # 添加菜单项
            activate_action = QAction('激活环境', self)
            activate_action.triggered.connect(self.activate_venv)
            menu.addAction(activate_action)
            
            copy_action = QAction('复制环境', self)
            copy_action.triggered.connect(self.copy_venv)
            menu.addAction(copy_action)
            
            delete_action = QAction('删除环境', self)
            delete_action.triggered.connect(self.delete_venv)
            menu.addAction(delete_action)
            
            # 添加分隔线
            menu.addSeparator()
        
        # 刷新列表选项始终显示
        refresh_action = QAction('刷新列表', self)
        refresh_action.triggered.connect(self.refresh_venv_list)
        menu.addAction(refresh_action)
        
        # 显示菜单
        menu.exec_(self.venv_list.viewport().mapToGlobal(position))
        
    def show_about(self):
        """显示关于对话框"""
        QMessageBox.about(self, 
                         f'{APP_NAME}',
                         f'{APP_NAME} v{APP_VERSION}\n'
                         f'By {APP_AUTHOR}')