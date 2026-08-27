import os

def get_optimal_gemini_model(prompt_text: str, task_complexity: str = "simple") -> str:
    """
    Dynamically routes to the most efficient Gemini model based on task complexity
    and approximate input length, minimizing token cost while maintaining quality.
    
    Args:
        prompt_text (str): The prompt being sent to the model (to estimate token weight).
        task_complexity (str): 'simple' (classification, extraction) or 'complex' (reasoning).
    """
    # Rough estimation: 4 chars ~ 1 token
    estimated_tokens = len(prompt_text) // 4
    
    # Defaults targeting cost-efficiency as per Hackathon strategy
    base_flash = os.environ.get("CINESPINE_GEMINI_FLASH_MODEL", "gemini-3.7-flash")
    base_pro = os.environ.get("CINESPINE_GEMINI_PRO_MODEL", "gemini-3.7-pro")
    
    # If it's a massive context (> 100k tokens), we default to Flash as it handles 
    # massive context extremely cheaply without degrading much.
    if estimated_tokens > 100000:
        return base_flash
        
    if task_complexity == "complex":
        return base_pro
        
    return base_flash
