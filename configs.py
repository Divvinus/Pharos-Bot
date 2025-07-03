""" --------------------------------- Basic configuration settings -----------------------------"""
SHUFFLE_WALLETS = False                                             # True/False Shuffle the wallets
MAX_RETRY_ATTEMPTS = 3                                              # Number of retries for unsuccessful requests
RETRY_SLEEP_RANGE = (3, 9)                                          # (min, max) in seconds
SLIPPAGE = 5                                                        # Slippage

""" --------------------------------- Analytics -----------------------------"""
SIMPLIFIED_STATISTICS = False


""" --------------------------------- APi keys of captcha solvers -----------------------------"""
CAP_MONSTER_API_KEY = ""
TWO_CAPTCHA_API_KEY = ""


""" --------------------------------- Pharos Network site -----------------------------"""
REFERRAL_CODES = [                                                  # Referral codes
    "",
]
"""
- You can add unlimited number of referral codes. the bot will randomly select a code for registration
"""


""" --------------------------------- Send To Friends -----------------------------"""
MAX_SEND_PHRS = 0.01                                                 # Maximum number of tokens to send


""" --------------------------------- Zenith Finance -----------------------------"""
SLEEP_SWAP = (30, 90)                                               # (min, max) in seconds | Delay between swaps
PAIR_SWAP = {                                                       # Swap pairs
    1: ["PHRS", "USDT", 15],
    2: ["wPHRS", "PHRS", 30], 
    3: ["USDC", "USDT", 20],
    4: ["USDT", "PHRS", 20],
    5: ["wPHRS", "USDC", 10],
    6: ["PHRS", "wPHRS", 20],
    7: ["USDT", "wPHRS", 40],
    8: ["USDC", "PHRS", 50],
    9: ["wPHRS", "USDT", 20],
    10: ["PHRS", "USDC", 10],
    11: ["USDT", "USDC", 50],
    12: ["USDC", "wPHRS", 35],
    13: ["PHRS", "wPHRS", 10],
    14: ["USDC_OLD", "PHRS", 100],
    15: ["USDT_OLD", "PHRS", 100],
}
"""
Number_pair: [outgoing_token, received_token, %_of_outgoing_token]
For example: 1: ["PHRS", "USDT", 5], # Exchange PHRS → USDT, receive % of PHRS

# For empty pairs, "%_of_outgoing_token" must be 0 otherwise there will be an error.
""" 
# - List of available tokens for swap
"PHRS, wPHRS, USDC, USDT, USDC_OLD, USDT_OLD"



""" --------------------------------- Auto Route -----------------------------"""
AUTO_ROUTE_DELAY_RANGE_HOURS = (24, 30)                             # Range of waiting hours between auto route laps
AUTO_ROUTE_REPEAT = True                                            # Repeat route automatically

ROUTE_TASK = [
    'daily_check_in',
    'full_faucets',
    'send_to_friends',
    'swap_zenith'
]

"""
Basic modules for route generation:

1. 🔄 Ofchain :
   - daily_check_in
   
2. 🔐 Registration and connection:
   - full_registration
   - connect_wallet
   - connect_twitter
   - connect_discord

3. 💰 Faucets:
   - full_faucets
   - phrs_faucet
   - zenith_faucet

4. 🚀 Onchain:
   - send_to_friends
   - swap_zenith
   
5. 📊 Analytics:
    - statistics_account
    
6. 🍀 Disposable:
    - connect_twitter_zenith
    - twitter_tasks
    - mint_pharos_badge
    - mint_pharos_nft
"""


# -------------------------- Data Pharos --------------------------
TOKENS_DATA_PHAROS = {
    "PHRS": "0x0000000000000000000000000000000000000000",
    "wPHRS": "0x76aaada469d23216be5f7c596fa25f282ff9b364",
    "USDC": "0x72df0bcd7276f2dfbac900d1ce63c272c4bccced",
    "USDT": "0xD4071393f8716661958F766DF660033b3d35fD29",
    "USDC_OLD": "0xAD902CF99C2dE2f1Ba5ec4D642Fd7E49cae9EE37",
    "USDT_OLD": "0xEd59De2D7ad9C043442e381231eE3646FC3C2939"
}