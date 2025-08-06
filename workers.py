import logging
import os
import subprocess
from PyQt5.QtCore import QThread, pyqtSignal
from multiprocessing import Value, Lock
from concurrent.futures import ThreadPoolExecutor

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