from pydantic import (
    BaseModel,
    AfterValidator,
    ConfigDict,
)
from typing import Annotated, Dict, List, Tuple, Union

from configs import PAIR_SWAP


def validate_pair_swap(value: Dict[int, Tuple[str, str, Union[int, float]]],
                         param_name: str = "PAIR_SWAP",
                         ) -> Dict[int, Tuple[str, str, Union[int, float]]]:
    has_active_pairs: bool = False

    for pair_id, swap_data in value.items():
        # Теперь swap_data - это кортеж (token_out, token_in, min_amount)
        token_out, token_in, min_amount = swap_data

        # Проверка структуры данных (кортеж из трех элементов)
        if len(swap_data) != 3:
            msg = f"{param_name}: Pair {pair_id}: Invalid format. Expected (token_out, token_in, min_amount)"
            raise TypeError(msg)

        # Пропускаем полностью пустые пары
        if token_out == "" and token_in == "" and min_amount != 0:
            msg = f"{param_name}: Pair {pair_id}: Empty pair requires min_amount = 0"
            raise ValueError(msg)

        # Помечаем что есть хотя бы одна активная пара
        has_active_pairs = True

        # Проверка частично заполненных пар
        if not token_out or not token_in:
            msg = f"{param_name}: Pair {pair_id}: Partial configuration. Out: '{token_out}', In: '{token_in}'"
            raise ValueError(msg)

        # Проверка типа токенов
        if not isinstance(token_out, str) or not isinstance(token_in, str):
            msg = f"{param_name}: Pair {pair_id}: Invalid token types. Must be strings"
            raise TypeError(msg)

        # Проверка одинаковых токенов
        if token_out.lower() == token_in.lower():
            msg = f"{param_name}: Pair {pair_id}: Same tokens ({token_out}/{token_in})"
            raise ValueError(msg)

        # Проверка минимального количества
        if not isinstance(min_amount, (int, float)) or min_amount <= 0:
            msg = f"{param_name}: Pair {pair_id}: Invalid percentage {min_amount}. Must be > 0"
            raise ValueError(msg)

    # Проверяем наличие хотя бы одной активной пары
    if not has_active_pairs:
        msg = f"{param_name}: No active swap pairs configured. Add at least one valid pair"
        raise ValueError(msg)

    return value


class ZenithSwapBaseModule(BaseModel):
    pair: Annotated[
        Dict[int, Tuple[str, str, Union[int, float]]],
        AfterValidator(validate_pair_swap)
    ] = PAIR_SWAP

    model_config = ConfigDict(
        validate_default=True,
        validate_assignment=True,
    )