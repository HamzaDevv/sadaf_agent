from config import AI_PROVIDER

class ProxyFactory:
    @staticmethod
    def get_proxy():
        if AI_PROVIDER == "gemini":
            from .fallback_proxy import FallbackProxy
            return FallbackProxy()
        elif AI_PROVIDER == "deepseek":
            from .deepseek_impl import DeepSeekProxyImpl
            return DeepSeekProxyImpl()
        elif AI_PROVIDER == "openrouter":
            from .openrouter_impl import OpenRouterProxyImpl
            return OpenRouterProxyImpl()
        else:
            from .groq_impl import GroqProxyImpl
            return GroqProxyImpl()

# Singleton proxy instance
llm_proxy = ProxyFactory.get_proxy()
