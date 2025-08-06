from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                           QListWidget, QLabel, QLineEdit, QMessageBox, QProgressBar,
                           QWidget, QFileDialog, QProgressDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSettings, QPropertyAnimation, QEasingCurve
from concurrent.futures import ThreadPoolExecutor
import subprocess
import json
import os
from pathlib import Path
from datetime import datetime
import concurrent.futures

class PackageWorker(QThread):
    """包操作工作线程"""
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(int, str)
    package_found = pyqtSignal(str, str, str)  # 包名, 版本, 大小

    def __init__(self, operation, venv_path, **kwargs):
        super().__init__()
        self.operation = operation
        self.venv_path = Path(venv_path)
        self.kwargs = kwargs
        self.is_scanning = False
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        try:
            if self.operation == 'list':
                self.is_scanning = True
                self.is_cancelled = False
                try:
                    python_path = self.venv_path / ('Scripts' if os.name == 'nt' else 'bin') / ('python.exe' if os.name == 'nt' else 'python')
                    
                    # 使用 pip list 获取基本包信息
                    self.progress.emit(0, "正在获取包列表...")
                    result = subprocess.run([str(python_path), '-m', 'pip', 'list', '--format=json'], 
                                         capture_output=True, text=True)
                    
                    if result.returncode != 0:
                        raise Exception(f"获取包列表失败: {result.stderr}")
                    
                    packages = json.loads(result.stdout)
                    total = len(packages)
                    
                    # 创建线程池来并行获取包信息
                    with ThreadPoolExecutor(max_workers=4) as executor:
                        futures = []
                        for pkg in packages:
                            if self.is_cancelled:
                                break
                            # 提交获取包详细信息的任务
                            future = executor.submit(self.get_package_info, str(python_path), pkg['name'], pkg['version'])
                            futures.append((pkg['name'], pkg['version'], future))
                        
                        # 处理完成的任务
                        for i, (name, version, future) in enumerate(futures):
                            if self.is_cancelled:
                                break
                            try:
                                size = future.result()
                                self.package_found.emit(name, version, size)
                                progress = int((i + 1) / total * 100)
                                self.progress.emit(progress, f"正在获取包信息... ({i + 1}/{total})")
                            except Exception as e:
                                print(f"获取包 {name} 信息失败: {e}")
                                self.package_found.emit(name, version, "0 B")
                    
                    if self.is_cancelled:
                        self.progress.emit(0, "扫描已取消")
                        self.finished.emit(False, "扫描已取消")
                    else:
                        self.progress.emit(100, "扫描完成")
                        self.finished.emit(True, "扫描完成")
                        
                except Exception as e:
                    self.progress.emit(0, f"扫描出错: {str(e)}")
                    self.finished.emit(False, str(e))
                finally:
                    self.is_scanning = False
                    
            elif self.operation == 'batch_install':
                # 批量安装包
                requirements = self.kwargs.get('requirements', [])
                total = len(requirements)
                max_workers = min(32, total)  # 最大并发数
                completed = 0
                results = []
                
                def install_package(pkg):
                    """安装单个包的函数"""
                    try:
                        result = subprocess.run(
                            [str(self.kwargs['python_path']), '-m', 'pip', 'install', pkg],
                            capture_output=True,
                            text=True
                        )
                        return pkg, result.returncode == 0, result.stderr if result.returncode != 0 else None
                    except Exception as e:
                        return pkg, False, str(e)
                
                # 使用线程池并行安装
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # 提交所有安装任务
                    future_to_pkg = {
                        executor.submit(install_package, pkg): pkg 
                        for pkg in requirements
                    }
                    
                    # 处理完成的任务
                    for future in concurrent.futures.as_completed(future_to_pkg):
                        completed += 1
                        pkg, success, error = future.result()
                        results.append((pkg, success, error))
                        
                        # 更新进度
                        progress = int(completed * 100 / total)
                        self.progress.emit(
                            progress,
                            f"正在安装 ({completed}/{total}): {pkg}"
                        )
                
                # 统计结果
                success_count = sum(1 for _, success, _ in results if success)
                failed_packages = [(pkg, err) for pkg, success, err in results if not success]
                
                # 生成结果消息
                if failed_packages:
                    error_msg = "\n\n失败的包:\n" + "\n".join(
                        f"{pkg}: {err}" for pkg, err in failed_packages
                    )
                    self.finished.emit(
                        False,
                        f"安装完成，成功: {success_count}/{total}\n{error_msg}"
                    )
                else:
                    self.finished.emit(
                        True,
                        f"所有包安装成功 ({total}/{total})"
                    )
            elif self.operation in ['install', 'uninstall', 'upgrade']:
                package = self.kwargs.get('package')
                python_path = self.venv_path / ('Scripts' if os.name == 'nt' else 'bin') / ('python.exe' if os.name == 'nt' else 'python')
                
                cmd = [str(python_path), '-m', 'pip']
                if self.operation == 'install':
                    cmd.extend(['install', package])
                elif self.operation == 'uninstall':
                    cmd.extend(['uninstall', '-y', package])
                else:  # upgrade
                    cmd.extend(['install', '--upgrade', package])
                
                self.progress.emit(10, f"正在{self.operation} {package}...")
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    self.progress.emit(100, "操作完成")
                    self.finished.emit(True, f"{package} {self.operation}成功")
                else:
                    raise Exception(result.stderr)
                    
        except Exception as e:
            self.progress.emit(0, f"错误: {str(e)}")
            self.finished.emit(False, str(e))

    def get_package_info(self, python_path, package_name, version):
        """获取包的详细信息"""
        try:
            # 使用 pip show 获取包信息
            result = subprocess.run([python_path, '-m', 'pip', 'show', package_name], 
                                 capture_output=True, text=True)
            
            if result.returncode != 0:
                return "0 B"
            
            # 解析包信息
            info = {}
            for line in result.stdout.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    info[key.strip()] = value.strip()
            
            # 获取包的实际位置
            if 'Location' not in info:
                return "0 B"
                
            package_path = Path(info['Location']) / package_name.lower()
            if not package_path.exists():
                # 尝试查找类似名称的目录
                parent = Path(info['Location'])
                for item in parent.iterdir():
                    if item.is_dir() and item.name.lower().startswith(package_name.lower()):
                        package_path = item
                        break
                else:
                    return "0 B"
            
            # 计算包大小
            total_size = 0
            for path in package_path.rglob('*'):
                if path.is_file():
                    total_size += path.stat().st_size
            
            # 转换大小
            units = ['B', 'KB', 'MB', 'GB']
            size = float(total_size)
            unit_index = 0
            
            while size >= 1024 and unit_index < len(units) - 1:
                size /= 1024
                unit_index += 1
            
            return f"{size:.1f} {units[unit_index]}"
            
        except Exception as e:
            print(f"获取包 {package_name} 大小失败: {e}")
            return "0 B"

class PackageManagerDialog(QDialog):
    def __init__(self, venv_path, parent=None):
        super().__init__(parent)
        self.venv_path = venv_path
        self.settings = QSettings('VenvManager', 'Settings')
        # 移除帮助按钮
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.worker = None
        self.init_ui()
        self.refresh_packages()

    def init_ui(self):
        self.setWindowTitle(f'包管理器 - {self.venv_path}')
        self.setGeometry(300, 300, 600, 400)
        
        layout = QVBoxLayout(self)
        
        # 包列表
        self.package_list = QListWidget()
        self.package_list.setAlternatingRowColors(True)
        layout.addWidget(QLabel('已安装的包:'))
        layout.addWidget(self.package_list)
        
        # 安装包区域
        install_layout = QHBoxLayout()
        self.package_input = QLineEdit()
        self.package_input.setPlaceholderText('输入包名')
        install_layout.addWidget(self.package_input)
        
        install_btn = QPushButton('安装')
        install_btn.clicked.connect(self.install_package)
        install_layout.addWidget(install_btn)
        
        layout.addLayout(install_layout)
        
        # 操作按钮
        button_layout = QHBoxLayout()
        upgrade_btn = QPushButton('升级选中包')
        uninstall_btn = QPushButton('卸载选中包')
        refresh_btn = QPushButton('刷新列表')
        export_btn = QPushButton('导出包列表')
        import_btn = QPushButton('导入安装')  # 新增导入按钮

        upgrade_btn.clicked.connect(self.upgrade_package)
        uninstall_btn.clicked.connect(self.uninstall_package)
        refresh_btn.clicked.connect(self.refresh_packages)
        export_btn.clicked.connect(self.export_packages)
        import_btn.clicked.connect(self.import_packages)  # 连接导入功能

        button_layout.addWidget(upgrade_btn)
        button_layout.addWidget(uninstall_btn)
        button_layout.addWidget(refresh_btn)
        button_layout.addWidget(export_btn)
        button_layout.addWidget(import_btn)  # 添加导入按钮
        
        layout.addLayout(button_layout)

    def _create_worker(self, operation, **kwargs):
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
        if self.worker:
            self.worker.deleteLater()
            
        self.worker = PackageWorker(operation, self.venv_path, **kwargs)
        if operation == 'list':
            self.package_list.clear()
            self.worker.package_found.connect(lambda name, version, size: 
                self.add_package_to_list(name, version, size))
        return self.worker

    def get_package_size(self, package_name):
        """获取包大小"""
        try:
            # 获取python解释器路径
            python_path = self.venv_path / ('Scripts' if os.name == 'nt' else 'bin') / ('python.exe' if os.name == 'nt' else 'python')
            
            # 使用pip show命令获取包信息
            result = subprocess.run([str(python_path), '-m', 'pip', 'show', package_name], 
                                 capture_output=True, text=True)
            
            if result.returncode != 0:
                return "未知大小"
            
            # 获取包的位置
            location = None
            for line in result.stdout.split('\n'):
                if line.startswith('Location:'):
                    location = line.split(':', 1)[1].strip()
                    break
            
            if not location:
                return "未知大小"
            
            # 计算包目录大小
            package_path = Path(location) / package_name
            if not package_path.exists():
                return "未知大小"
            
            total_size = 0
            for path in package_path.rglob('*'):
                if path.is_file():
                    total_size += path.stat().st_size
            
            # 转换为合适的单位
            units = ['B', 'KB', 'MB', 'GB']
            size = float(total_size)
            unit_index = 0
            
            while size >= 1024 and unit_index < len(units) - 1:
                size /= 1024
                unit_index += 1
            
            return f"{size:.1f} {units[unit_index]}"
            
        except Exception as e:
            print(f"获取包大小失败: {e}")
            return "未知大小"

    def add_package_to_list(self, name, version, size=None):
        """添加包到列表"""
        if self.settings.value('show_pkg_size', False, type=bool) and size:
            self.package_list.addItem(f"{name} ({version}) - {size}")
        else:
            self.package_list.addItem(f"{name} ({version})")
        # 按字母顺序排序
        self.package_list.sortItems()

    def update_progress(self, value, message):
        self.progress_widget.show()
        # 创建动画效果
        animation = QPropertyAnimation(self.progress_bar, b"value")
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.setDuration(300)
        animation.setStartValue(self.progress_bar.value())
        animation.setEndValue(value)
        animation.start()
        self.status_label.setText(message)

    def refresh_packages(self):
        if self.worker and self.worker.is_scanning:
            self.worker.cancel()
            return
            
        worker = self._create_worker('list')
        worker.finished.connect(self._handle_refresh_result)
        worker.start()

    def _handle_refresh_result(self, success, msg):
        if not success and msg != "扫描已取消":
            QMessageBox.critical(self, '错误', f'刷新列表失败: {msg}')
        if msg == "扫描已取消":
            QTimer.singleShot(100, self.refresh_packages)

    def install_package(self):
        package = self.package_input.text().strip()
        if not package:
            QMessageBox.warning(self, '警告', '请输入包名')
            return
            
        worker = self._create_worker('install', package=package)
        worker.finished.connect(self._handle_operation_result)
        worker.start()

    def upgrade_package(self):
        selected = self.package_list.currentItem()
        if not selected:
            QMessageBox.warning(self, '警告', '请选择要升级的包')
            return
            
        package = selected.text().split()[0]  # 获取包名（不含版本号）
        worker = self._create_worker('upgrade', package=package)
        worker.finished.connect(self._handle_operation_result)
        worker.start()

    def uninstall_package(self):
        selected = self.package_list.currentItem()
        if not selected:
            QMessageBox.warning(self, '警告', '请选择要卸载的包')
            return
            
        package = selected.text().split()[0]
        reply = QMessageBox.question(self, '确认卸载',
                                   f'确定要卸载包 {package} 吗？',
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            worker = self._create_worker('uninstall', package=package)
            worker.finished.connect(self._handle_operation_result)
            worker.start()

    def _handle_operation_result(self, success, msg):
        if success:
            self.package_input.clear()
            self.refresh_packages()
            QMessageBox.information(self, '成功', msg)
        else:
            QMessageBox.critical(self, '错误', f'操作失败: {msg}')

    def export_packages(self):
        """导出包列表到文件"""
        # 获取环境名称
        venv_name = self.venv_path.name
        # 生成时间戳
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # 生成默认文件名
        default_name = f"requirements_{venv_name}_{timestamp}.txt"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出包列表",
            str(Path.home() / default_name),
            "Text Files (*.txt);;All Files (*.*)"
        )
        
        if file_path:
            try:
                # 获取Python路径
                python_path = self.venv_path / ('Scripts' if os.name == 'nt' else 'bin') / ('python.exe' if os.name == 'nt' else 'python')
                
                # 获取Python版本
                version_result = subprocess.run(
                    [str(python_path), '--version'],
                    capture_output=True, text=True, check=True
                )
                python_version = version_result.stdout.strip()
                
                # 导出包列表
                result = subprocess.run(
                    [str(python_path), '-m', 'pip', 'freeze'],
                    capture_output=True, text=True, check=True
                )
                
                # 写入文件
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"# 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"# 虚拟环境: {self.venv_path}\n")
                    f.write(f"# {python_version}\n\n")
                    f.write(result.stdout)
                    
                QMessageBox.information(self, "成功", "包列表导出成功！")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败: {str(e)}")

    def _get_python_version(self):
        """获取Python版本"""
        try:
            python_path = self.venv_path / ('Scripts' if os.name == 'nt' else 'bin') / ('python.exe' if os.name == 'nt' else 'python')
            result = subprocess.run([str(python_path), '--version'], capture_output=True, text=True)
            return result.stdout.strip()
        except:
            return "未知" 

    def import_packages(self):
        """从requirements.txt导入并安装包"""
        try:
            # 获取文件路径
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                '选择requirements文件',
                str(Path.home()),
                'Text Files (*.txt);;All Files (*)'
            )
            
            if not file_path:
                return
            
            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                requirements = []
                for line in f:
                    line = line.strip()
                    # 跳过注释和空行
                    if line and not line.startswith('#'):
                        requirements.append(line)
            
            if not requirements:
                QMessageBox.warning(self, '警告', '文件中没有找到有效的包信息')
                return
            
            # 确认安装
            reply = QMessageBox.question(
                self,
                '确认安装',
                f'将安装以下{len(requirements)}个包：\n\n' + '\n'.join(requirements[:10]) +
                ('\n...' if len(requirements) > 10 else ''),
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                python_path = self.venv_path / ('Scripts' if os.name == 'nt' else 'bin') / ('python.exe' if os.name == 'nt' else 'python')
                
                # 创建工作线程
                worker = self._create_worker(
                    'batch_install',
                    python_path=python_path,
                    requirements=requirements
                )
                
                # 创建进度对话框
                progress_dialog = QProgressDialog(
                    "正在安装包...", 
                    "取消", 
                    0, 
                    100, 
                    self
                )
                progress_dialog.setWindowTitle("安装进度")
                progress_dialog.setWindowModality(Qt.WindowModal)
                progress_dialog.setAutoClose(False)
                progress_dialog.setAutoReset(False)
                # 移除帮助按钮
                progress_dialog.setWindowFlags(progress_dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
                
                # 连接信号
                worker.progress.connect(
                    lambda v, m: progress_dialog.setLabelText(m) or progress_dialog.setValue(v)
                )
                worker.finished.connect(progress_dialog.close)
                worker.finished.connect(self._handle_operation_result)
                
                # 启动工作线程
                worker.start()
                progress_dialog.exec_()
                
        except Exception as e:
            QMessageBox.critical(self, '错误', f'导入失败: {str(e)}')