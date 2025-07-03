from colorama import Fore, Style
from art import text2art

class MenuItem:
    def __init__(self, title, action=None, children=None):
        self.title = title
        self.action = action
        self.children = children or []
        self.parent = None

        for child in self.children:
            child.parent = self

class Console:
    def __init__(self):
        self.current_menu = None
        self.running = True
        self.should_exit = False
        self.selected_action = None
        
        self.main_menu = MenuItem("Main Menu", children=[     
            MenuItem("Statistics account", action="statistics_account"),
                   
            MenuItem("Registration management", children=[
                MenuItem("Full registration\n", action="full_registration"),
                
                MenuItem("Connect wallet", action="connect_wallet"),
                MenuItem("Connect twitter", action="connect_twitter"),
                MenuItem("Connect discord", action="connect_discord")
            ]),
            
            MenuItem("Pharos tasks", children=[       
                MenuItem("Daily Check-in", action="daily_check_in"),         
                MenuItem("Twitter tasks", action="twitter_tasks"),
                MenuItem('"Send To Friends" task', action="send_to_friends"),
                MenuItem('Mint Pharos Testnet Badge', action="mint_pharos_badge"),
                MenuItem('Mint Pharos Testnet Nft', action="mint_pharos_nft"),
                
            ]),
            
            MenuItem("Faucets", children=[           
                MenuItem("Full request tokens\n", action="full_faucets"),
                
                MenuItem("PHRS faucet", action="phrs_faucet"),
                MenuItem("Stablecoins faucet", action="zenith_faucet")
            ]),
            
            MenuItem("Zenith Finance", children=[           
                MenuItem("Connect twitter", action="connect_twitter_zenith"),
                MenuItem("Swap", action="swap_zenith"),
            ]),
            
            MenuItem("Auto Route", action="auto_route"),
            
        ])
        
    def show_dev_info(self):
        print("\033c", end="")
        art = text2art("Pharos  Bot", font="doom")
        print(Fore.CYAN + art)
        print(Fore.LIGHTGREEN_EX + "👉 Channel: https://t.me/divinus_xyz 💬")
        print(Fore.LIGHTGREEN_EX + "👉 GitHub: https://github.com/Divvinus 💻\n")
        print(Style.RESET_ALL)

    def display_menu(self, menu):
        print("\033c", end="")
        self.show_dev_info()

        print(Fore.YELLOW + f"\n{menu.title}")
        print(Fore.YELLOW + "-" * len(menu.title))
        
        # Только функциональные пункты меню
        for idx, item in enumerate(menu.children, 1):
            print(Fore.CYAN + f"{idx}. {item.title}")
        
        # Единый пункт возврата/выхода
        print(Fore.RED + "\n0. " + ("Back" if menu.parent else "Exit"))
        print(Style.RESET_ALL)

    def process_input(self, menu):
        try:
            choice = int(input(Fore.LIGHTBLACK_EX + "Select option: " + Style.RESET_ALL))
            
            # Главное меню: 0 = Exit
            if choice == 0:
                if menu.parent:
                    self.current_menu = menu.parent  # Back
                else:
                    self.should_exit = True
                    self.running = False
                return

            # Обработка выбранного пункта
            selected_item = menu.children[choice - 1]
            
            if selected_item.children:
                self.current_menu = selected_item
            elif selected_item.action:
                self.handle_action(selected_item.action)

        except (ValueError, IndexError):
            print(Fore.RED + "Invalid input!" + Style.RESET_ALL)

    def handle_action(self, action):
        if action == "exit":
            self.should_exit = True
            self.running = False
        elif action == "back":
            self.current_menu = self.current_menu.parent
        else:
            self.selected_action = action
            self.running = False

    def build(self):
        self.show_dev_info()
        self.current_menu = self.main_menu
        self.running = True
        self.should_exit = False
        self.selected_action = None
        
        while self.running:
            self.display_menu(self.current_menu)
            self.process_input(self.current_menu)
        
        return self.should_exit, self.selected_action