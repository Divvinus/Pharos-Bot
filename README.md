<div align="center">

```
_____  _                           ____        _   
|  __ \| |                         |  _ \      | |  
| |__) | |__   __ _ _ __ ___  ___  | |_) | ___ | |_ 
|  ___/| '_ \ / _` | '__/ _ \/ __| |  _ < / _ \| __|
| |    | | | | (_| | | | (_) \__ \ | |_) | (_) | |_ 
|_|    |_| |_|\__,_|_|  \___/|___/ |____/ \___/ \__|
                                               
```

<a href="https://t.me/divinus_xyz">
    <img src="https://img.shields.io/badge/Telegram-Channel-blue?style=for-the-badge&logo=telegram" alt="Telegram Channel">
</a>
<a href="https://t.me/divinus_py">
    <img src="https://img.shields.io/badge/Telegram-Contact-blue?style=for-the-badge&logo=telegram" alt="Telegram Contact">
</a>
<br>
<b>Multifunctional bot to automate interaction with the Pharos test network</b>
</div>

## ❤️ Donations to support the project:
  - 0x63F78ecCB360516C13Dd48CA3CA3f72eB3D4Fd3e
  - E5Nvuuixh1YXENsinSSqTCfrfNkT4tbaRbT1UbZJWyLD

## 📋 Table of Contents

- [Features](#-features)
- [Key Benefits](#-key-benefits)
- [System Requirements](#-system-requirements)
- [Installation](#️-installation)
- [Configuration Guide](#️-configuration-guide)
  - [Setup Configuration Files](#1-setup-configuration-files)
  - [Advanced Configuration](#2-advanced-configuration)
  - [Settings Configuration](#4-settings-configuration)
- [Running the Bot](#-running-the-bot)
- [Security Best Practices](#-security-best-practices)
- [Contributing](#-contributing)
- [License](#-license)
- [Disclaimer](#️-disclaimer)
- [Support](#-support)

## 🚀 Features

Pharos Bot is designed to automate various operations in the Pharos test network:

- **Pharos Network**
  - 📊 Detailed wallet statistics in testnet
  - 🤵 Registration of wallets using your referral links
  - 💬 Binding Discord and Twitter accounts
  - 👋 Daily Check-in
  - 🐦‍ Fulfillment of social tasks on Twitter
  - 🤝 Task execution "Send To Friends"
  - 🚰 Faucet $PHRS

- **Zenith Finance**
  - 🚰 Stablecoin faucet
  - 💱 Swap
  - 🛒 Provide Liquidity

- **Gotchipus**
  - 📊 Detailed statistics on the wallet in Gotchipus project
  - 🚰 Mint nft "Pharos"
  - 🧱 Creating unique Gotchipus

- **OmniHub**
  - 🛒 Buying nft

- **Auto Route**
  - 🧠 Automatic route through selected jobs with prioritization and infinite cycle with pauses within a specified time range

## 🍀 Key Benefits

- **Smart Data Management** - Automatic validation of data with invalid entries saved to separate files
- **Integrated Notifications** - Automatic statistics reporting via Telegram
- **User-Friendly Configuration** - All user data conveniently managed in a single Excel file
- **Flexible Proxy Support** - Full compatibility with HTTP, HTTPS, and SOCKS5 proxies

## 📋 System Requirements

- Python 3.11 or higher
- Windows or Linux operating system

## 🛠️ Installation

1. Clone the repository:
```bash
git clone [repository URL]
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # for Linux
.\venv\Scripts\activate   # for Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## ⚙️ Configuration Guide

### 1. Setup Configuration Files

Create the following structure in the `config/data/client/` directory:

#### accounts.xlsx
Your Excel file must contain these columns:
- `Private Key` (required) - Wallet private key for transactions
- `Proxy` (optional) - Proxy in the format described below
- `Twitter Token` (optional) - Your Twitter authentication token
- `Discord Token` (optional) - Your Discord authentication token


### 2. Advanced Configuration

For experienced users, additional configuration options are available in the `configs.py` file.

### 3. Settings Configuration

Edit the `config/settings.yaml` file with your preferred settings:

```yaml
#------------------------------------------------------------------------------
# en: Threading Configuration | ru: Конфигурация потоков
#------------------------------------------------------------------------------
# en: Controls parallel execution capacity (min: 1) | ru: Управление количеством параллельных выполнений (минимум: 1)
threads: 1

#------------------------------------------------------------------------------
# en: Timing Settings | ru: Настройки времени
#------------------------------------------------------------------------------
# en: Initial delay range before starting operations (seconds) | ru: Диапазон начальной задержки перед началом выполнения (секунды)
delay_before_start:
    min: 1
    max: 100

# en: Delay between tasks (seconds) | ru: Задержка между задачами (секунды)
delay_between_tasks:
    min: 100
    max: 300

# TELEGRAM DATA
send_stats_to_telegram: true

tg_token: ""  # https://t.me/BotFather
tg_id: ""  # https://t.me/getmyid_bot

#------------------------------------------------------------------------------
# Network Settings
#------------------------------------------------------------------------------

# Pharos RPC endpoint
pharos_rpc_endpoints: 
    - https://testnet.dplabs-internal.com
# Pharos Explorer
pharos_evm_explorer: https://testnet.pharosscan.xyz
```

## 🚀 Running the Bot

Start the bot with:
```bash
python run.py
```

## 🔒 Security Best Practices

1. **Private Key Protection**
   - Never share your private keys or mnemonic phrases
   - Store sensitive data in encrypted storage
   - Consider using environment variables for sensitive credentials

2. **Proxy Security**
   - Use reliable and secure proxy providers
   - Regularly rotate proxies to prevent IP blocking
   - Verify proxy connectivity before operations

3. **Account Security**
   - Regularly update your Discord and other platform tokens
   - Use dedicated accounts for automated operations
   - Implement proper encryption for stored credentials

4. **Rate Limiting Awareness**
   - Respect platform-specific rate limits
   - Configure appropriate delays between operations
   - Avoid patterns that might trigger security systems

## 🤝 Contributing

### How to Contribute

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/YourFeature`)
3. Commit your changes (`git commit -m 'Add YourFeature'`)
4. Push to the branch (`git push origin feature/YourFeature`)
5. Open a Pull Request

### Development Standards

- Follow PEP 8 Python style guide
- Write clear, documented code with appropriate comments
- Include type hints for better code quality
- Add unit tests for new functionality
- Update documentation to reflect changes

## 📜 License

This project is distributed under the MIT License. See `LICENSE` file for more information.

## ⚠️ Disclaimer

Use this bot at your own risk. The developers are not responsible for any consequences, such as account bans or financial losses.

## 📞 Support

For questions, issues, or support, please contact us through our Telegram channels listed at the top of this document.