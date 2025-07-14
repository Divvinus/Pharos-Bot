""" --------------------------------- Basic configuration settings -----------------------------"""
SHUFFLE_WALLETS = False                                             # True/False Shuffle the wallets
MAX_RETRY_ATTEMPTS = 3                                              # Number of retries for unsuccessful requests
RETRY_SLEEP_RANGE = (3, 9)                                          # (min, max) in seconds
SLIPPAGE = 5                                                        # Slippage
SLEEP_SWAP = (30, 90)                                               # (min, max) in seconds | Delay between swaps


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


# Number_pair: [outgoing_token, received_token, %_of_outgoing_token]
# For example: 1: ["PHRS", "USDT", 5], # Exchange PHRS → USDT, receive % of PHRS
# For empty pairs, "%_of_outgoing_token" must be 0 otherwise there will be an error.
""" --------------------------------- Zenith Finance -----------------------------"""
PAIR_SWAP_ZENITH = {                                                # Swap pairs
    1: ["", "", 0],
}
# - List of available tokens for swap
"PHRS, wPHRS, USDC, USDT, USDC_OLD, USDT_OLD"


""" --------------------------------- FaroSwap -----------------------------"""
PAIR_SWAP_FAROSWAP = {                                              # Swap pairs
    1: ["", "", 0],
}

# - List of available tokens for swap
"PHRS, wPHRS_FARO, USDC, USDT, WBTC, WETH"


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
   - swap_faroswap
   
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
    "wPHRS_FARO": "0x3019B247381c850ab53Dc0EE53bCe7A07Ea9155f",
    "USDC": "0x72df0bcd7276f2dfbac900d1ce63c272c4bccced",
    "USDT": "0xD4071393f8716661958F766DF660033b3d35fD29",
    "USDC_OLD": "0xAD902CF99C2dE2f1Ba5ec4D642Fd7E49cae9EE37",
    "USDT_OLD": "0xEd59De2D7ad9C043442e381231eE3646FC3C2939",
    "WBTC": "0x8275c526d1bcec59a31d673929d3ce8d108ff5c7",
    "WETH": "0x4e28826d32f1c398ded160dc16ac6873357d048f"
}