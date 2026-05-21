import random
import asyncio
import urllib.parse
from typing import Any

import aiohttp

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")
REQUEST_TIMEOUT = 10


class RandomPicPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        # 读取配置中的触发指令，如果未配置或为空则使用默认值"随机图片"
        trigger = (self.config.get("command_trigger") or "随机图片").strip()
        
        # 仅当纯文本消息内容完全匹配触发词时，才进行处理
        if event.message_str.strip() != trigger:
            return
            
        # 匹配到触发指令后，执行发送随机图片逻辑
        async for r in self._send_random_pic(event):
            yield r
            
    async def _send_random_pic(self, event: AstrMessageEvent):
        api_url = self.config.get("api_url")
        cdn_prefix = self.config.get("cdn_prefix")
        
        # 检查是否配置了 API 和 CDN 前缀
        if not api_url or not cdn_prefix or "YOUR_USER" in api_url:
            yield event.plain_result("错误：请先在 WebUI 配置图床 API 地址和 CDN 前缀！")
            event.stop_event()
            return

        # 确保 CDN 前缀以 '/' 结尾
        if not cdn_prefix.endswith('/'):
            cdn_prefix += '/'

        try:
            # 使用 aiohttp 发起异步请求
            async with aiohttp.ClientSession() as session:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    async with session.get(api_url) as response:
                        if response.status != 200:
                            logger.error(f"[随机图片] 请求 API 失败，状态码: {response.status}")
                            yield event.plain_result(f"获取图片列表失败（状态码 {response.status}），请稍后再试。")
                            event.stop_event()
                            return
                        
                        data = await response.json()
                        
                        # 判断返回的数据是否为数组
                        if not isinstance(data, list):
                            logger.error(f"[随机图片] API 返回的数据格式不正确，期望 JSON 数组。")
                            yield event.plain_result("获取图片列表失败，API 返回格式有误。")
                            event.stop_event()
                            return
                            
                        # 过滤出后缀名为常见图片格式的文件
                        image_files = []
                        for item in data:
                            name = item.get("name", "")
                            if name.lower().endswith(IMAGE_EXTS):
                                image_files.append(name)
                                
                        if not image_files:
                            yield event.plain_result("在指定的目录下没有找到任何支持的图片文件。")
                            event.stop_event()
                            return
                            
                        # 随机抽取一张图片
                        chosen_pic = random.choice(image_files)
                        chosen_pic_encoded = urllib.parse.quote(chosen_pic)
                        pic_url = f"{cdn_prefix}{chosen_pic_encoded}"
                        
                        logger.info(f"[随机图片] 成功抽取并发送图片: {pic_url}")
                        yield event.image_result(pic_url)
                        
                        # 拦截事件，避免被 LLM 等后续流程处理
                        event.stop_event()
                        
        except asyncio.TimeoutError:
            logger.error("[随机图片] 请求图床 API 超时")
            yield event.plain_result("请求图片列表超时，请检查网络或配置。")
            event.stop_event()
        except Exception as e:
            logger.error(f"[随机图片] 发生未捕获的错误: {str(e)}")
            yield event.plain_result("获取图片时发生内部错误。")
            event.stop_event()

    async def terminate(self):
        pass
