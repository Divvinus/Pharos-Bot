from typing import Tuple, Callable, List, Dict, Any


class ConfigValidator:
    def __init__(self):
        self.validations: Dict[str, List[Tuple[Callable, str]]] = {}
    
    def register(self, config_name: str, error_msg: str):
        """Декоратор для регистрации проверок"""
        def decorator(func: Callable[[Any, Dict], bool]):
            if config_name not in self.validations:
                self.validations[config_name] = []
            self.validations[config_name].append((func, error_msg))
            return func
        return decorator
    
    def validate(self, context: Dict[str, Any]) -> Tuple[bool, str]:
        """Выполнение всех проверок"""
        errors = []
        
        for config_name, checks in self.validations.items():
            if config_name not in context:
                errors.append(f"Config '{config_name}' not found")
                continue
            
            value = context[config_name]
            
            for check_func, error_msg in checks:
                try:
                    if not check_func(value, context):
                        errors.append(f"{config_name}: {error_msg}")
                except Exception as e:
                    errors.append(f"{config_name}: {str(e)}")
        
        if errors:
            return False, "\nConfiguration errors:\n• " + "\n• ".join(errors)
        
        return True, "All configurations are valid"