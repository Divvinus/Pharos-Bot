""" --------------------------------- Basic configuration settings -----------------------------"""
SHUFFLE_WALLETS = False                                             # True/False Перемешивайте кошельки
MAX_RETRY_ATTEMPTS = 5                                              # Количество повторных попыток для неудачных запросов
RETRY_SLEEP_RANGE = (3, 9)                                          # (min, max) в секундах


""" --------------------------------- APi keys of captcha solvers -----------------------------"""
CAP_MONSTER_API_KEY = ""
TWO_CAPTCHA_API_KEY = ""


""" --------------------------------- Pharos Network site -----------------------------"""
REFERRAL_CODES = [                                                  # Реферальные коды
    "",
]
"""
- Вы можете добавлять неограниченное количество рефферальных кодов. бот будем рандомно выбирать код для регистрации
"""


""" --------------------------------- Send To Friends -----------------------------"""
MAX_SEND_PHRS = 0.1                                                 # Максимальное количество токенов для отправки


""" --------------------------------- Gotchipus -----------------------------"""
MAX_NFT_PHAROS = 1                                                  # Максимальное количество nft "Pharos"


""" --------------------------------- Auto Route -----------------------------"""
AUTO_ROUTE_DELAY_RANGE_HOURS = (24, 30)                             # Диапазон часов ожидания между кругами авто маршрута
AUTO_ROUTE_REPEAT = True                                            # Повторять маршрут автоматически

ROUTE_TASK = [
    '',
]

"""
Modules for route generation:
    - daily_check_in           Daily Check-in
    - twitter_tasks            Twitter tasks
    - send_to_friends          "Send To Friends" task
    - full_registration        Full registration
    - connect_wallet           Connect wallet
    - connect_twitter          Connect twitter
    - connect_discord          Connect discord
    - full_faucets             Full request tokens
    - phrs_faucet              PHRS faucet
    - zenith_faucet            Stablecoins faucet
    - statistics_account       Statistics account
    - mint_nft_pharos          Mint nft "Pharos"
"""