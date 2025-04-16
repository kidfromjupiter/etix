import threading
import subprocess
import sys
import os
import time
import traceback
import queue
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

from logger import setup_logger

@dataclass
class RunnerConfig:
    """Configuration for a Runner instance"""
    id: str
    script_path: str
    args: List[str] = None
    env_vars: Dict[str, str] = None


class Runner(threading.Thread):
    """Runner class that manages a Puppeteer instance in a separate process"""

    def __init__(self, config: RunnerConfig, result_queue: queue.Queue):
        super().__init__(daemon=True)
        self.id = config.id
        self.script_path = config.script_path
        self.args = config.args or []
        self.env_vars = config.env_vars or {}
        self.process = None
        self.result_queue = result_queue
        self.is_running = False
        self.exit_code = None
        self.error = None
        self.logger = setup_logger(f'Runner-{self.id}')

    def run(self):
        """Main thread execution method"""
        self.logger.info(f"Starting Runner {self.id}")
        try:
            self.is_running = True

            # Create environment with base environment plus custom vars
            env = dict(os.environ)
            env.update(self.env_vars)

            # Start the Puppeteer process
            cmd = [sys.executable, self.script_path] + self.args
            self.logger.info(f"Executing command: {' '.join(cmd)}")

            self.process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Monitor the process
            stdout, stderr = self.process.communicate()
            self.exit_code = self.process.returncode

            if self.exit_code != 0:
                self.error = stderr
                self.logger.error(f"Runner {self.id} failed with exit code {self.exit_code}")
                self.logger.error(f"Error: {stderr}")
                self.result_queue.put((self.id, False, self.error))
            else:
                self.logger.info(f"Runner {self.id} completed successfully")
                self.result_queue.put((self.id, True, stdout))

        except Exception as e:
            self.error = str(e)
            self.logger.error(f"Exception in Runner {self.id}: {e}")
            self.logger.error(traceback.format_exc())
            self.result_queue.put((self.id, False, self.error))
        finally:
            self.is_running = False

    def terminate(self):
        """Terminate the runner process"""
        if self.process and self.is_running:
            self.logger.info(f"Terminating Runner {self.id}")
            try:
                self.process.terminate()
                # Give it a moment to terminate gracefully
                time.sleep(1)
                # Force kill if still running
                if self.process.poll() is None:
                    self.process.kill()
            except Exception as e:
                self.logger.error(f"Error terminating Runner {self.id}: {e}")