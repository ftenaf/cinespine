from typing import Callable, TypeVar

T = TypeVar('T', bound=Callable)

def tool(func: T) -> T:
    """
    Marker decorator to fulfill the requirement of @tool decorators.
    In google.adk 2.8.0, functions passed to the tools array are registered
    implicitly, so this decorator just passes through the function.
    """
    return func
