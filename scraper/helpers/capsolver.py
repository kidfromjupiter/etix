import asyncio
import aiohttp
import json
from typing import Dict, Optional

from utils.logger import setup_logger

class Capsolver:
    """
    Async Capsolver client for solving reCaptcha v2 invisible challenges.
    """

    def __init__(self, api_key: str):
        """
        Initialize the Capsolver client with your API key.

        :param api_key: Your Capsolver API key
        """
        self.api_key = api_key
        self.base_url = "https://api.capsolver.com"
        self.create_task_url = f"{self.base_url}/createTask"
        self.get_result_url = f"{self.base_url}/getTaskResult"
        self.session = None
        self.logger = setup_logger("CAPSOLVER")
        self.logger.propagate = False

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()

    async def create_task(self, website_url: str, website_key: str) -> Optional[str]:
        """
        Create a new reCaptcha v2 invisible task.

        :param website_url: The URL where the captcha is located
        :param website_key: The sitekey of the reCaptcha
        :return: Task ID if successful, None otherwise
        """
        payload = {
            "clientKey": self.api_key,
            "task": {
                "type": "ReCaptchaV2EnterpriseTaskProxyLess",
                "websiteURL": website_url,
                "websiteKey": website_key,
                "isInvisible": True
            }
        }

        try:
            async with self.session.post(self.create_task_url, json=payload) as response:
                data = await response.json()
                if data.get("errorId") == 0:
                    return data.get("taskId")
                else:
                    print(f"Error creating task: {data.get('errorDescription')}")
                    return None
        except Exception as e:
            print(f"Exception in create_task: {str(e)}")
            return None

    async def get_task_result(self, task_id: str, timeout: int = 120, interval: float = 2.0) -> Optional[Dict]:
        """
        Poll for task results until solved or timeout.

        :param task_id: The task ID to check
        :param timeout: Maximum time to wait in seconds
        :param interval: Time between checks in seconds
        :return: Solution dictionary if solved, None otherwise
        """
        payload = {
            "clientKey": self.api_key,
            "taskId": task_id
        }

        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                async with self.session.post(self.get_result_url, json=payload) as response:
                    data = await response.json()

                    if data.get("status") == "ready":
                        return data.get("solution")
                    elif data.get("errorId") != 0:
                        self.logger.error(f"Error in task: {data.get('errorDescription')}")
                        return None

                    await asyncio.sleep(interval)
            except Exception as e:
                self.logger.error(f"Exception in get_task_result: {str(e)}")
                await asyncio.sleep(interval)
                continue

        self.logger.warning("Task timed out")
        return None

    async def solve_recaptcha_v2_invisible(self, website_url: str, website_key: str) -> Optional[str]:
        """
        Solve a reCaptcha v2 invisible challenge.

        :param website_url: The URL where the captcha is located
        :param website_key: The sitekey of the reCaptcha
        :return: gRecaptchaResponse if solved, None otherwise
        """
        task_id = await self.create_task(website_url, website_key)
        if not task_id:
            return None

        result = await self.get_task_result(task_id)
        if result:
            return result.get("gRecaptchaResponse")
        return None

