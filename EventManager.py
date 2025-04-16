import threading
import time
import queue
import traceback
import httpx
from typing import Dict, List, Any, Callable, Optional

from logger import setup_logger
from runner import Runner, RunnerConfig

class EventManager:
    """
    EventManager class responsible for spawning and managing Runner instances.
    Handles restarting failed Runners up to a retry threshold and
    sends data to the FastAPI backend.
    """

    def __init__(
            self,
            max_retries: int = 3,
            max_concurrent_runners: int = 5,
            runner_script_path: str = None,
            api_endpoint: str = "http://localhost:8000/api/scrape-data",
            on_runner_complete: Callable[[str, bool, Any], None] = None,
            on_all_complete: Callable[[], None] = None
    ):
        """
        Initialize the EventManager
        
        Args:
            max_retries: Maximum number of retries per Runner before giving up
            max_concurrent_runners: Maximum number of concurrent Runners
            runner_script_path: Default script path for Runners
            api_endpoint: URL for the FastAPI backend
            on_runner_complete: Callback when a runner completes
            on_all_complete: Callback when all runners complete
        """
        self.max_retries = max_retries
        self.max_concurrent_runners = max_concurrent_runners
        self.default_runner_script_path = runner_script_path
        self.api_endpoint = api_endpoint
        self.on_runner_complete = on_runner_complete
        self.on_all_complete = on_all_complete

        # Track runners and their retry counts
        self.runners: Dict[str, Runner] = {}
        self.retry_counts: Dict[str, int] = {}
        self.pending_configs: List[RunnerConfig] = []
        self.completed_runners: Dict[str, bool] = {}  # runner_id -> success

        # Data collection
        self.collected_data: Dict[str, List[Dict[str, Any]]] = {}
        self.data_lock = threading.Lock()

        # Thread synchronization
        self.lock = threading.Lock()
        self.result_queue = queue.Queue()
        self.data_queue = queue.Queue()
        self.monitor_thread = None
        self.api_thread = None
        self.is_running = False

        self.logger = setup_logger('EventManager')

    def add_runner(self, config: RunnerConfig) -> str:
        """
        Add a runner configuration to be executed
        
        Args:
            config: Runner configuration
            
        Returns:
            Runner ID
        """
        # Set up data callback
        config.data_callback = self._handle_runner_data

        with self.lock:
            self.pending_configs.append(config)
            self.retry_counts[config.id] = 0
            self.collected_data[config.id] = []
            return config.id

    def start(self):
        """Start the EventManager and begin processing runners"""
        if self.is_running:
            return

        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.logger.info("EventManager monitor thread started")

        # Start the result processing thread
        result_thread = threading.Thread(target=self._process_results, daemon=True)
        result_thread.start()
        self.logger.info("EventManager result thread started")

        # Start the API communication thread
        self.api_thread = threading.Thread(target=self._api_communication_loop, daemon=True)
        self.api_thread.start()
        self.logger.info("EventManager API thread started")

        self.logger.info("EventManager fully started")

    def stop(self):
        """Stop the EventManager and terminate all runners"""
        if not self.is_running:
            return

        self.logger.info("Stopping EventManager")
        self.is_running = False

        # Terminate all active runners
        with self.lock:
            for runner_id, runner in self.runners.items():
                try:
                    runner.terminate()
                except Exception as e:
                    self.logger.error(f"Error stopping runner {runner_id}: {e}")

        # Wait for monitor thread to end
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)

        # Wait for API thread to end
        if self.api_thread and self.api_thread.is_alive():
            self.api_thread.join(timeout=5)

        self.logger.info("EventManager stopped")

    def _handle_runner_data(self, runner_id: str, data: Dict[str, Any]):
        """
        Handle data received from a runner
        
        Args:
            runner_id: ID of the runner that produced the data
            data: Data from the runner
        """
        # Store data locally
        with self.data_lock:
            if runner_id not in self.collected_data:
                self.collected_data[runner_id] = []
            self.collected_data[runner_id].append(data)

        # Queue data for API submission
        self.data_queue.put((runner_id, data))

        self.logger.info(f"Received data from runner {runner_id}")

    def _api_communication_loop(self):
        """Send data to the FastAPI backend"""
        while self.is_running:
            try:
                # Get data from queue with timeout to allow checking is_running
                try:
                    runner_id, data = self.data_queue.get(timeout=1)
                except queue.Empty:
                    continue

                # Submit data to API
                try:
                    # Create payload with metadata
                    payload = {
                        "runner_id": runner_id,
                        "url": data.get("url", "unknown"),
                        "data": data,
                        "status": "success",
                        "timestamp": data.get("scrape_time") or time.strftime("%Y-%m-%dT%H:%M:%SZ")
                    }

                    # Error data?
                    if "error" in data:
                        payload["status"] = "error"
                        payload["error_message"] = data["error"]

                    # Make API request
                    with httpx.Client(timeout=30.0) as client:
                        response = client.post(self.api_endpoint, json=payload)
                        response.raise_for_status()
                        self.logger.info(f"Data for runner {runner_id} sent to API successfully")

                except Exception as e:
                    self.logger.error(f"Failed to send data to API: {str(e)}")

                # Mark queue task as done
                self.data_queue.task_done()

            except Exception as e:
                self.logger.error(f"Error in API communication loop: {str(e)}")
                self.logger.error(traceback.format_exc())
                time.sleep(1)

    def _monitor_loop(self):
        """Main monitoring loop that manages runner execution"""
        while self.is_running:
            try:
                with self.lock:
                    # Start new runners if we have capacity
                    available_slots = self.max_concurrent_runners - len(self.runners)
                    if available_slots > 0 and self.pending_configs:
                        for _ in range(min(available_slots, len(self.pending_configs))):
                            if not self.pending_configs:
                                break

                            config = self.pending_configs.pop(0)
                            self._start_runner(config)

                # Check if we're done
                with self.lock:
                    if (not self.runners and not self.pending_configs and
                            self.is_running and self.on_all_complete):
                        self.logger.info("All runners completed")
                        self.on_all_complete()

                # Small sleep to prevent CPU spinning
                time.sleep(0.1)

            except Exception as e:
                self.logger.error(f"Error in monitor loop: {str(e)}")
                self.logger.error(traceback.format_exc())
                time.sleep(1)  # Prevent tight loop on errors

    def _process_results(self):
        """Process runner results from the queue"""
        while self.is_running:
            try:
                # Block for a short while, but allow checking if manager is still running
                try:
                    runner_id, success, result = self.result_queue.get(timeout=1)
                except queue.Empty:
                    continue

                self.logger.info(f"Runner {runner_id} completed with success={success}")

                with self.lock:
                    # Remove runner from active runners
                    if runner_id in self.runners:
                        del self.runners[runner_id]

                    # Handle retry logic if failed
                    if not success:
                        retry_count = self.retry_counts.get(runner_id, 0)
                        if retry_count < self.max_retries:
                            # Find the original config for this runner
                            found_config = None
                            for config in self.pending_configs:
                                if config.id == runner_id:
                                    found_config = config
                                    break

                            if not found_config:
                                self.logger.error(f"Could not find config for failed runner {runner_id}")
                                continue

                            # Increment retry count and re-queue
                            self.retry_counts[runner_id] = retry_count + 1
                            self.logger.info(f"Retrying runner {runner_id} (attempt {retry_count + 1}/{self.max_retries})")
                            self.pending_configs.append(found_config)
                        else:
                            self.logger.warning(f"Runner {runner_id} failed after {self.max_retries} attempts")
                            self.completed_runners[runner_id] = False
                    else:
                        self.completed_runners[runner_id] = True

                # Notify via callback if provided
                if self.on_runner_complete:
                    try:
                        self.on_runner_complete(runner_id, success, result)
                    except Exception as e:
                        self.logger.error(f"Error in runner complete callback: {e}")

            except Exception as e:
                self.logger.error(f"Error processing runner results: {str(e)}")
                self.logger.error(traceback.format_exc())
                time.sleep(1)  # Prevent tight loop on errors

    def _start_runner(self, config: RunnerConfig):
        """Start a new runner thread"""
        try:
            # Use default script path if not provided
            if not config.script_path and self.default_runner_script_path:
                config.script_path = self.default_runner_script_path

            if not config.script_path:
                raise ValueError(f"No script path provided for runner {config.id}")

            runner = Runner(config, self.result_queue)
            self.runners[config.id] = runner
            runner.start()
            self.logger.info(f"Started runner {config.id}")

        except Exception as e:
            self.logger.error(f"Failed to start runner {config.id}: {str(e)}")
            self.logger.error(traceback.format_exc())
            self.result_queue.put((config.id, False, str(e)))
