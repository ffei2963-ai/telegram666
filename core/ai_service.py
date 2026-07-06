from openai import OpenAI
from utils.logger import setup_logger

logger = setup_logger(__name__)


class AIService:
    def __init__(self, api_key: str, model: str = "deepseek-chat",
                 base_url: str = "https://api.deepseek.com"):
        self.client = OpenAI(api_key=api_key, base_url=base_url) if api_key else None
        self.model = model
        self.available = api_key != ""

    def chat(self, messages: list[dict], temperature: float = 0.7,
             max_tokens: int = 1024) -> str:
        if not self.client:
            return "[AI服务未配置API Key]"
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.error("DeepSeek API调用失败: %s", e)
            return f"[AI服务错误: {e}]"

    def summarize_messages(self, messages: list[str]) -> str:
        prompt = (
            "请总结以下Telegram消息的关键信息，提取核心内容，用简洁中文回复：\n\n"
            + "\n".join(messages[:20])
        )
        return self.chat([{"role": "user", "content": prompt}], max_tokens=512)

    def parse_command(self, text: str) -> dict:
        prompt = (
            "你是一个Telegram管理助手。请从用户输入中解析操作意图。\n"
            "支持的操作类型: import_accounts(导入账号), list_accounts(查看账号), "
            "create_group(创建分组), assign_group(分配分组), "
            "bulk_dm(群发私信), join_group(进群), change_2fa(修改2FA), "
            "change_avatar(修改头像), change_name(修改名字), "
            "search_group(搜索群组), scrape_members(提取成员), "
            "register_account(注册账号)。\n\n"
            f"用户输入: {text}\n\n"
            '请返回JSON格式: {"action": "操作类型", "params": {...}}'
        )
        resp = self.chat([{"role": "user", "content": prompt}], temperature=0.3, max_tokens=256)
        try:
            import json
            return json.loads(resp)
        except Exception:
            return {"action": "unknown", "raw": resp}

    def is_available(self) -> bool:
        return self.available
