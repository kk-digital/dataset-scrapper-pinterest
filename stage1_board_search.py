import os
import sqlite3
from consts import DATABASE_PATH
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from helper_functions import init_driver , create_database, page_has_loaded
import time 
import re
import socket

SCROLL_IDLE_TIME = 3
POLL_TIME = 1
SCROLL_TIMEOUT = 10
TRIGGER_STOP = 3 # If your internet connection is slow, increase this number.
RESIZE_WAIT_TIME = 10
TIMEOUT = 10



class Stage1:
    """ Stage1: getting all boards urls for a given search term"""

    def __init__(self, search_term):
        self.search_term = search_term
        self.all_data = {}
        self.driver = None
        self.db_conn = None
        

    def __start_connections(self):
        self.db_conn  = self.__initiate_db_conn() 
        self.driver = init_driver()


    def __initiate_db_conn(self):
        """ getting the connection object to the DB""" 
        if not os.path.exists(DATABASE_PATH):
            create_database()

        return sqlite3.connect(DATABASE_PATH)
        

    def __find_comma(self,str):
        """Find comma in the pins number to switch it in integer."""
        for i in range(len(str)):
            if(str[i] == ','):
                try:
                    int(str[i+1])
                    return i
                except:
                    try:
                        int(str[i+2])
                        return i+1
                    except:
                        continue
        return -1
    
    def __extract_sections(self,input_string):
        # Use a regular expression to search for the number of sections
        pattern = re.compile(r'(\d+)\ssection')
        match = pattern.search(input_string)
        return int(match.group(1).replace(',',''))
         

    def __get_sections_count(self, soup_a):
        for div in soup_a.find_all("div"):
            try:
                if div["style"] == '-webkit-line-clamp: 1;' and 'section' in div.text :
                    return self.__extract_sections(div.text)
            except Exception as e:
                pass
        return 0

    def __get_image_count(self,soup_a):
        """ getting the number of images in a certain board"""
        re = ''
        for i in soup_a.find_all("div"):
            try:
                if(i['style'] == '-webkit-line-clamp: 1;'):
                    re += i.text
            except Exception as e:
                pass
        re = re.replace('\n', '')
        if(re[self.__find_comma(re)+1:re.find("Pins")] == ''):
            return re
        return re[self.__find_comma(re)+1:re.find("Pins")]


    def __get_board_name(self,soup_a):
        for i in soup_a.find_all("div"):
            try:
                if(i['title'] != ''):
                    return i.text
            except Exception as e:
                continue

    def __get_boards(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        self.__get_sections_count(soup)
        links_list = soup.find_all("a")

        for a in links_list:
            url = a["href"]
            image_count = self.__get_image_count(a)
            board_name =  self.__get_board_name(a)
            sections_count = self.__get_sections_count(a)
            self.all_data[url] = [self.search_term, image_count, sections_count,board_name]
        
    
    def __scrape_boards_urls(self):
        # self.driver.set_window_size(1280, 720)
        tag_div = self.driver.find_element(By.XPATH , "//div[@role='list']")
        return self.__get_boards(tag_div.get_attribute('innerHTML'))


    def __get_scroll_height(self):
        return self.driver.execute_script("return document.documentElement.scrollHeight")


    def __check_existance(self, board_url):
        """checking if a board url + search term is in DB or not"""
        exist = 0
        try:
            with sqlite3.connect(DATABASE_PATH) as conn:
                cursor = conn.execute("SELECT count(*) FROM stage1 WHERE board_url=? AND search_term=?",(board_url,self.search_term)).fetchone()
                conn.commit()
                exist = cursor[0]

        except Exception as e :
            print(f"[ERROR] cannot check board existance , because of {e}")
            time.sleep(1)
            return self.__check_existance(board_url)
        return exist

    def __push_into_db(self, board_url, images_count, sections_count):
        if self.__check_existance(board_url):
            print(f"[INFO] {board_url} with {self.search_term} exists, updating it.")
            self.__update_data_in_db(board_url, images_count, sections_count)
        else:
            print(f"[INFO] inserting {board_url}.")
            self.__insert_data_into_database(board_url, images_count, sections_count)

    def __update_data_in_db(self,board_url, images_count, sections_count):
        try:
            self.db_conn.execute("UPDATE stage1 SET pin_count = ?, sections_count=? WHERE board_url = ? and search_term=?;",(images_count,sections_count,board_url,self.search_term.replace("'", "''")))
            self.db_conn.commit()        
        except Exception as e:
            print(f"[INFO] ERROR {e} in board {board_url}")
 

    def __insert_data_into_database(self, board_url, images_count, sections_count):
        try:
            self.db_conn.execute("""INSERT INTO stage1(search_term, board_url, pin_count, sections_count) VALUES (?,?,?,?)""",
                            (self.search_term.replace("'", "''"), board_url, images_count, sections_count),)
            self.db_conn.commit()
        
        except sqlite3.IntegrityError:
            print(f"[INFO] updating board : {board_url} in DB")
            self.db_conn.execute("UPDATE stage1 SET search_term = ?, pin_count = ?, sections_count=? WHERE board_url = ?;",(self.search_term.replace("'", "''"), images_count, sections_count,board_url))
            self.db_conn.commit()
        
        except Exception as e:
            print(f"[INFO] ERROR {e} in board {board_url}")
    
    def __exit_stage(self):
        self.db_conn.close()
        self.driver.quit()

    def __get_scroll_height(self):
        return self.driver.execute_script("return document.documentElement.scrollHeight")


    def __scroll_inner_height(self):
        self.driver.execute_script("window.scrollBy(0, Math.abs(window.innerHeight * 0.8));")
    
    def __is_netwrok_available(self):
        try:
            # Connect to a known website to check if there is an active network connection
            socket.create_connection(("www.pinterest.com", 80))
            return True
        except OSError:
            pass
        return False



    def __scroll_and_scrape(self):
        try:
            print(f"[INFO] STARTING SCROLLING AND SCRAPPING")
            self.driver.delete_all_cookies()
            self.driver.execute_script("document.body.style.zoom='50%'")
            self.driver.get("https://www.pinterest.com/search/boards/?q="+self.search_term.replace(" ", "%20")+"&rs=filter")

            scroll_trigger_count = 0
            pins_trigger_count = 0 
            while scroll_trigger_count <= 10 and pins_trigger_count <= TRIGGER_STOP:

                before_pins_count = len(self.all_data)
                before_scroll_height = self.__get_scroll_height()

                print(f"[INFO] SCROLLING")
                self.__scroll_inner_height()
                time.sleep(SCROLL_IDLE_TIME)
                # Scrapping the pins.
                try:
                    self.__scrape_boards_urls()
                except Exception as e:
                    print(f"[ERROR] IN GETTING URLS; {e}")
                    pins_trigger_count = 0 
                    scroll_trigger_count = 0

                    if not self.__is_netwrok_available():
                        print("[ERROR] NETWORK ERROR; PLEASE CHECK")
                        print("[INFO] RESTARTING THE SCROLL AND SCRAPPING FUNCTION")
                        self.__scroll_and_scrape()
                    
                    continue

                print(f"[INFO] NUMBER OF URLS SCRAPPED: {len(self.all_data)}")
                
                print(f"[INFO] SCROLLING")           
                self.__scroll_inner_height()
                time.sleep(SCROLL_IDLE_TIME)
                # Scrapping the pins.
                try:
                    self.__scrape_boards_urls()
                except Exception as e:
                    print(f"[ERROR] IN GETTING URLS; {e}")
                    pins_trigger_count = 0 
                    scroll_trigger_count = 0

                    if not self.__is_netwrok_available():
                        print("[ERROR] NETWORK ERROR; PLEASE CHECK")
                        print("[INFO] RESTARTING THE SCROLL AND SCRAPPING FUNCTION")
                        self.__scroll_and_scrape()     
                    continue

                print(f"[INFO] NUMBER OF URLS SCRAPPED: {len(self.all_data)}")                
                after_pins_count = len(self.all_data)
                after_scroll_height = self.__get_scroll_height()

                # Check if the scroll height is the same
                if before_scroll_height == after_scroll_height:
                    scroll_trigger_count += 1
                    print("[INFO] SCROLL STOP TRIGGER COUNT INCREASED")
                else :
                    scroll_trigger_count = 0
                    print("[INFO] SCROLL STOP TRIGGER IS ZERO NOW")

                if after_pins_count == before_pins_count:
                    pins_trigger_count += 1
                    print("[INFO] PINS COUNT STOP TRIGGER COUNT INCREASED")
                else :
                    pins_trigger_count = 0
                    print("[INFO] PINS COUNT STOP TRIGGER IS ZERO NOW")
        except Exception as e:
            print(f"[ERROR] IN SCROLL AND SCRAPE {str(e)}")
            print("[INFO] WAITING FOR 5 MINUTES")
            time.sleep(5*60)
            self.__scroll_and_scrape()


    def run(self):
        """main function of the program"""   
        self.__start_connections()     
        self.__scroll_and_scrape()
        self.driver.close()

        print(f"[INFO] NUMBER OF BOARDS SCRAPPED : {len(self.all_data)}")
        for url in self.all_data:
            print(url)
            self.__push_into_db(str(url), int(self.all_data[url][1].strip().replace(",","")),self.all_data[url][2])

        self.__exit_stage()

