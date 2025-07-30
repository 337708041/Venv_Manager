import os
import venv
import shutil
import subprocess
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime
import threading
from queue import Queue

class VenvManager:
    def __init__(self):
        # 设置日志
        self.setup_logging()
        
        # 默认路径为用户目录下的.virtualenvs
        self.base_path = Path.home() / '.virtualenvs'
        self.base_path.mkdir(exist_ok=True)
        self.logger.info(f"虚拟环境基础路径: {self.base_path}")

    def setup_logging(self):
        self.logger = logging.getLogger('VenvManager')
        self.logger.setLevel(logging.INFO)
        
        # 确保日志目录存在
        log_dir = os.path.expanduser('~/.virtualenvs')
        os.makedirs(log_dir, exist_ok=True)
        
        # 设置日志文件路径
        log_path = os.path.join(log_dir, 'venv_manager.log')
        
        # 创建日志滚动处理器 (5MB/文件，保留3个备份)
        fh = logging.handlers.RotatingFileHandler(
            log_path, 
            maxBytes=512*1024, 
            backupCount=3,
            encoding='utf-8'
        )
        fh.setLevel(logging.INFO)
        
        # 设置日志格式
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

    def set_base_path(self, path):
        """设置虚拟环境基础路径"""
        new_path = Path(path)
        new_path.mkdir(exist_ok=True)
        self.base_path = new_path
        self.logger.info(f"更新虚拟环境基础路径为: {self.base_path}")

    def create_venv(self, name, python_path=None):
        """创建虚拟环境
        
        Args:
            name: 虚拟环境名称
            python_path: 可选，指定Python解释器路径
        """
        venv_path = self.base_path / name
        if venv_path.exists():
            raise Exception(f"虚拟环境 {name} 已存在")
        
        try:
            self.logger.info(f"开始创建虚拟环境: {name}")
            
            if python_path:
                # 使用指定的Python解释器创建虚拟环境
                try:
                    subprocess.run([
                        python_path,
                        '-m',
                        'venv',
                        str(venv_path)
                    ], check=True, capture_output=True, text=True)
                except subprocess.CalledProcessError as e:
                    raise Exception(f"创建虚拟环境失败: {e.stderr}")
            else:
                # 使用当前Python解释器
                venv.create(venv_path, with_pip=True)
            
            # 获取python和pip路径
            if os.name == 'nt':
                python_path = venv_path / 'Scripts' / 'python.exe'
                pip_path = venv_path / 'Scripts' / 'pip.exe'
            else:
                python_path = venv_path / 'bin' / 'python'
                pip_path = venv_path / 'bin' / 'pip'
                
            # 确保pip已安装并可用
            try:
                subprocess.run([str(python_path), '-m', 'ensurepip', '--upgrade'],
                             check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError:
                pass  # 忽略错误，继续执行
            
            self.logger.info(f"虚拟环境 {name} 创建成功")
        except Exception as e:
            self.logger.error(f"创建虚拟环境失败: {str(e)}")
            raise

    def delete_venv(self, venv_path):
        """删除虚拟环境"""
        full_path = self.base_path / venv_path
        if not full_path.exists():
            raise Exception(f"虚拟环境 {venv_path} 不存在")
            
        try:
            self.logger.info(f"开始删除虚拟环境: {venv_path}")
            shutil.rmtree(full_path)
            self.logger.info(f"虚拟环境 {venv_path} 删除成功")
        except Exception as e:
            self.logger.error(f"删除虚拟环境失败: {str(e)}")
            raise

    def activate_venv(self, venv_path):
        """激活虚拟环境"""
        full_path = self.base_path / venv_path
        if not full_path.exists():
            raise Exception(f"虚拟环境 {venv_path} 不存在")
        
        # 创建并启动工作线程
        worker = ActivateWorker(venv_path, full_path, self.logger)
        worker.start()
        return worker

    def get_venv_info(self, venv_path):
        """获取虚拟环境信息"""
        # 将相对路径转换为完整路径
        full_path = self.base_path / venv_path
        if not full_path.exists():
            return None
            
        info = {
            'name': full_path.name,
            'path': str(full_path),
            'relative_path': venv_path,
            'created_time': datetime.fromtimestamp(full_path.stat().st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
            'python_version': self._get_python_version(full_path)
        }
        return info

    def _get_python_version(self, venv_path):
        """获取虚拟环境的Python版本"""
        try:
            if os.name == 'nt':
                python_path = venv_path / 'Scripts' / 'python.exe'
            else:
                python_path = venv_path / 'bin' / 'python'
                
            result = subprocess.run([str(python_path), '--version'], 
                                  capture_output=True, text=True)
            return result.stdout.strip()
        except:
            return "未知"

    def list_venvs(self):
        """列出所有虚拟环境（包括子文件夹）"""
        try:
            venvs = []
            self._scan_venvs(self.base_path, venvs)
            return sorted(venvs)
        except Exception as e:
            self.logger.error(f"获取虚拟环境列表失败: {str(e)}")
            return []

    def _scan_venvs(self, path, venvs, depth=0, max_depth=5):
        """递归扫描虚拟环境
        
        Args:
            path: 要扫描的路径
            venvs: 存储结果的列表
            depth: 当前递归深度
            max_depth: 最大递归深度，防止无限递归
        """
        if depth > max_depth:
            return

        try:
            for item in path.iterdir():
                if item.is_dir():
                    # 检查当前目录是否为虚拟环境
                    if self._is_valid_venv(item):
                        # 使用相对路径
                        rel_path = str(item.relative_to(self.base_path))
                        venvs.append(rel_path)
                    # 递归扫描子目录
                    self._scan_venvs(item, venvs, depth + 1, max_depth)
        except Exception as e:
            # 添加异常处理
            self.logger.error(f"扫描目录 {path} 时出错: {str(e)}")
            # 继续扫描其他目录,不中断整个扫描过程
            pass

    def _is_valid_venv(self, path):
        """检查是否为有效的虚拟环境"""
        if os.name == 'nt':
            return (path / 'Scripts' / 'python.exe').exists()
        return (path / 'bin' / 'python').exists()

class ActivateWorker(threading.Thread):
    """虚拟环境激活工作线程"""
    def __init__(self, venv_path, full_path, logger):
        super().__init__()
        self.venv_path = venv_path
        self.full_path = full_path
        self.logger = logger
        self.result_queue = Queue()

    def run(self):
        try:
            self.logger.info(f"正在激活虚拟环境: {self.venv_path}")
            if os.name == 'nt':
                activate_script = self.full_path / 'Scripts' / 'activate.bat'
                cmd = f'cd /d "{str(self.full_path.parent)}" && call "{str(activate_script)}"'
                subprocess.Popen(f'start cmd.exe /K "{cmd}"', shell=True)
            else:
                activate_script = self.full_path / 'bin' / 'activate'
                subprocess.Popen(['gnome-terminal', '--', 'bash', '-c', 
                                f'cd "{str(self.full_path)}" && source "{str(activate_script)}"; exec bash'], 
                                shell=False)
            self.logger.info(f"虚拟环境 {self.venv_path} 激活成功")
            self.result_queue.put((True, "激活成功"))
        except Exception as e:
            error_msg = f"激活虚拟环境失败: {str(e)}"
            self.logger.error(error_msg)
            self.result_queue.put((False, error_msg)) 