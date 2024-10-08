from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from datetime import datetime
import re
import json
from typing import TypedDict, List, Optional
from tempfile import mkdtemp


class Song(TypedDict):
    original_artist: str
    name: str
    is_cover: bool
    position: int  # 並び替えのために一時的に使用


class Setlist(TypedDict):
    artist_name: str
    event_date: datetime
    location: str
    venue: str
    tour_name: str
    songs: List[Song]
    setlist_id: Optional[int]

class SetlistEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)
    
def handler(event, context):
    handler_type = event.get('handler_type', 'main') # defaultはmain

    print(f"ハンドラータイプ: {handler_type}")
    
    if handler_type == 'sub':
        return sub(event, context)
    else:
        return main(event, context)


def main(event=None, context=None):

    url = event.get("url") if event else None
    is_cover = event.get("iscover", False)  # デフォルトはFalse

    def get_visually_sorted_elements(url: str, is_cover: bool) -> Optional[Setlist]:
        # ヘッドレスモードの設定

        options = webdriver.ChromeOptions()
        service = webdriver.ChromeService("/opt/chromedriver")

        options.binary_location = "/opt/chrome/chrome"
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1280x1696")
        options.add_argument("--single-process")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-dev-tools")
        options.add_argument("--no-zygote")
        options.add_argument(f"--user-data-dir={mkdtemp()}")
        options.add_argument(f"--data-path={mkdtemp()}")
        options.add_argument(f"--disk-cache-dir={mkdtemp()}")
        options.add_argument("--remote-debugging-port=9222")

        driver = webdriver.Chrome(options=options, service=service)

        try:
            driver.get(url)
            # ページの読み込み完了を待つ
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "td"))
            )

            a_element = driver.find_elements(
                    By.XPATH, "//*[@id='content']/div/div[5]/p/a"
                )  # XPathでa要素を指定
            if a_element:
                a_element[0].click()

            # tdエレメントの取得とPCSL1クラスの確認
            td_elements = driver.find_elements(By.TAG_NAME, "td")
            is_pcsl1 = (
                "pcsl1" in td_elements[0].get_attribute("class")
                if td_elements
                else False
            )

            # アーティスト名の取得
            artist_name = driver.find_element(By.CSS_SELECTOR, "h4 > a").text

            # 開催日の取得と変換
            event_date_text = driver.find_element(
                By.CSS_SELECTOR, "#content > div > div.dataBlock > div.profile > p.date"
            ).text
            date_match = re.search(
                r"(\d{4})/(\d{2})/(\d{2})\s+\(.*?\)\s+(\d{2}):(\d{2})", event_date_text
            )
            if date_match:
                event_date = datetime.strptime(
                    f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}T{date_match.group(4)}:{date_match.group(5)}:00",
                    "%Y-%m-%dT%H:%M:%S",
                )
            else:
                event_date = datetime.now()  # フォールバック

            # 会場情報の取得
            try:
                venue_element = driver.find_element(
                    By.CSS_SELECTOR,
                    "#content > div > div.dataBlock > div.profile > address > a"
                )
            except:
                # aタグが見つからない場合、address要素自体のテキストを取得
                venue_element = driver.find_element(
                    By.CSS_SELECTOR,
                    "#content > div > div.dataBlock > div.profile > address"
                )
            venue = venue_element.text.replace("＠", "")

            # 都市の取得
            city_match = re.search(r"\((.*?)\)", venue)
            city = city_match.group(1) if city_match else ""

            # ツアー名の取得
            tour_name = "不明"  # デフォルト値
            selectors = ["h4.liveName2 > a", "h3.liveName > a"]
            for selector in selectors:
                try:
                    tour_name = driver.find_element(By.CSS_SELECTOR, selector).text
                    break
                except:
                    continue

            unsort_setlist_songs: List[Song] = []

            if is_pcsl1:
                for td in td_elements:
                    # getComputedStyleを使用してtop値を取得
                    top_value = driver.execute_script(
                        "return window.getComputedStyle(arguments[0]).getPropertyValue('top')",
                        td,
                    )

                    position_match = re.search(r"(\d+)px", top_value)

                    if position_match:
                        position = int(position_match.group(1))
                        a_element = td.find_element(By.CSS_SELECTOR, "div > a")
                        if a_element:
                            text_content = a_element.text
                            # カバー曲のチェック
                            cover_match = re.search(r"\[(.*?)\]", text_content)
                            if cover_match:
                                song: Song = {
                                    "original_artist": cover_match.group(1),
                                    "name": text_content.strip(),
                                    "is_cover": True,
                                    "position": position,  # top値を保存
                                }
                            else:
                                song: Song = {
                                    "original_artist": artist_name,
                                    "name": text_content.strip(),
                                    "is_cover": False,
                                    "position": position,  # top値を保存
                                }
                            unsort_setlist_songs.append(song)
            else:
                for i, td in enumerate(td_elements):
                    try:
                        a_element = td.find_element(By.CSS_SELECTOR, "div > a")
                        if a_element:
                            text_content = a_element.text
                            if text_content:
                                song: Song = {
                                    "original_artist": artist_name,
                                    "name": text_content.strip(),
                                    "is_cover": False,
                                    "position": i,  # インデックスを位置として使用
                                }
                                unsort_setlist_songs.append(song)
                    except:
                        continue

            # top値で並び替え
            sorted_songs = sorted(unsort_setlist_songs, key=lambda x: x["position"])

            # position属性を削除
            for song in sorted_songs:
                del song["position"]

            # カバー曲の除外（必要な場合）
            if is_cover:
                setlist_songs = [song for song in sorted_songs if not song["is_cover"]]
            else:
                setlist_songs = sorted_songs

            # Setlistオブジェクトの作成
            setlist: Setlist = {
                "artist_name": artist_name,
                # "event_date": event_date,
                "location": city,
                "venue": venue,
                "tour_name": tour_name,
                "songs": setlist_songs,
                "setlist_id": None,
            }

            return setlist

        except Exception as error:
            print(f"An error occurred: {error}")
            return None

        finally:
            driver.quit()

    def datetime_converter(o):
        if isinstance(o, datetime):
            return o.__str__()

    # 使用例
    setlist = get_visually_sorted_elements(url, is_cover)
    if setlist:
        # return json.dumps(setlist, default=datetime_converter, ensure_ascii=False, indent=2, cls=SetlistEncoder)
        return setlist





def sub(event=None, context=None):

    url = event.get("url") if event else None

    def extract_concert_info(driver, div_element):
        concert_name = div_element.find_element(By.CSS_SELECTOR, 'h3.artistName a').text.strip()
        date_and_venue = div_element.find_element(By.CSS_SELECTOR, 'p.date').text.strip()
        date, venue = [item.strip() for item in date_and_venue.split('\n')]
        clean_venue = venue.replace('@', '')

        # aタグのhref属性からIDを抽出
        a_element = div_element.find_element(By.CSS_SELECTOR, 'h3.artistName a')
        href = a_element.get_attribute('href')
        id_match = re.search(r'/events/(\d+)', href)
        concert_id = id_match.group(1) if id_match else None


        return {
            'concert_name': concert_name,
            'date': date,
            'venue': clean_venue,
            'concert_id': concert_id

        }


    def get_visually_sorted_elements(url: str):
        # ヘッドレスモードの設定

        options = webdriver.ChromeOptions()
        service = webdriver.ChromeService("/opt/chromedriver")

        options.binary_location = "/opt/chrome/chrome"
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1280x1696")
        options.add_argument("--single-process")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-dev-tools")
        options.add_argument("--no-zygote")
        options.add_argument(f"--user-data-dir={mkdtemp()}")
        options.add_argument(f"--data-path={mkdtemp()}")
        options.add_argument(f"--disk-cache-dir={mkdtemp()}")
        options.add_argument("--remote-debugging-port=9222")

        driver = webdriver.Chrome(options=options, service=service)

        try:
            driver.get(url)
            # 指定されたXPathのa要素を見つけてクリック
            a_element = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//a[contains(text(), 'プロフィール')]")
            )
            )
            a_element.click()

            a_element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="relLiveList"]/p/a'))
            )
            a_element.click()

            # divタグ空要素を取得
            div_elements = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, '//div[contains(@class, "whiteBack") and contains(@class, "midBox") and .//a[contains(text(), "セットリスト")]]'))
            )

            # すべてのコンサート情報を抽出
            concert_info_list = [extract_concert_info(driver, div) for div in div_elements]

            return concert_info_list

        except Exception as e:
            print(f"エラーが発生しました: {str(e)}")
            return None

        finally:
            driver.quit()


    concert_list = get_visually_sorted_elements(url)    

    if concert_list:
        return concert_list
        for concert in concert_list:
            print(json.dumps(concert, ensure_ascii=False))
    else:
        print("コンサート情報の取得に失敗しました。")
