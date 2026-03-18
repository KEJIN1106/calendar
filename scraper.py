import requests
from bs4 import BeautifulSoup
import json
import datetime
import os

"""
This script scrapes schedule (media) entries from the official 22/7 mobile site.

The previous implementation relied on a very specific page structure built around
`<li>` elements within a `.media_list` or `.schedule_list`. However, the site
has since been redesigned: each day on the schedule is represented by a
`<div class="media_box">` containing a date header and one or more events. To
address the scraping failures reported by the user, the base URL and parsing
logic have been updated. The `ima` query parameter used previously appears
to be a session-specific identifier that is not necessary for retrieving the
monthly schedule, so it has been removed. Events are now extracted from
`.media_box` elements and mapped to English categories for the calendar.
"""

# Base URL for fetching monthly schedules. The `dy` query parameter takes a
# year/month value in YYYYMM format. Do not include an `ima` parameter here;
# it is injected by the site for internal navigation but is not required for
# retrieval.
BASE_URL = "https://nanabunnonijyuuni-mobile.com/s/n110/media/list?dy={}"

def fetch_events_for_month(year_month: str) -> list:
    """Fetch and parse schedule events for a given year/month.

    The 22/7 mobile site groups each day's entries under a `.media_box` div.
    Within that container, the date is split into separate year and month/day
    fields and each event is represented by an `<a class="media_box_list">`.

    Args:
        year_month: A string of the form "YYYYMM" representing the year and
            month to fetch.

    Returns:
        A list of event dictionaries with keys: id, date, title, category,
        time (blank), and url.
    """
    url = BASE_URL.format(year_month)
    print(f"正在获取: {url}")

    # Use a common browser user agent; some sites block generic clients.
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0 Safari/537.36'
        ),
        'Accept-Language': 'ja,en;q=0.9',
        'Referer': 'https://nanabunnonijyuuni-mobile.com/'
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as e:
        # Surface network errors to the caller and return empty list
        print(f"获取网页失败: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    events: list = []

    # Find all date containers on the page
    media_boxes = soup.find_all('div', class_='media_box')
    if not media_boxes:
        # Fallback: if we can't find the new structure, attempt the old list-based structure
        legacy_items = soup.select('.media_list li, .schedule_list li, article')
        for item in legacy_items:
            try:
                date_elem = item.find(class_=['date', 'time', 'day'])
                title_elem = item.find(class_=['title', 'name', 'txt'])
                category_elem = item.find(class_=['category', 'tag', 'label'])
                if not date_elem or not title_elem:
                    continue
                raw_date = date_elem.get_text(strip=True)
                title = title_elem.get_text(strip=True)
                category_text = category_elem.get_text(strip=True) if category_elem else ''
                clean_date = _normalize_date(raw_date, year_month)
                cat_en = _map_category(category_text)
                link_elem = item.find('a')
                detail_url = ''
                if link_elem and link_elem.has_attr('href'):
                    detail_url = link_elem['href']
                    if detail_url.startswith('/'):
                        detail_url = 'https://nanabunnonijyuuni-mobile.com' + detail_url
                events.append({
                    'id': f"{clean_date}-{hash(title + category_text)}",
                    'date': clean_date,
                    'title': title,
                    'category': cat_en,
                    'time': '',
                    'url': detail_url,
                })
            except Exception as e:
                print(f"解析旧结构时出错: {e}")
        return events

    # Parse each media box representing a single date
    for box in media_boxes:
        try:
            # Extract year and month/day
            year_div = box.find('div', class_='media_date_year')
            day_div = box.find('div', class_='media_date_day')
            if not year_div or not day_div:
                continue
            year = year_div.get_text(strip=True)
            # day_div may contain text like "03.07" followed by a day-of-week <span>
            month_day_raw = day_div.get_text(separator=' ', strip=True).split()[0]
            # month_day_raw is of the form "MM.DD"
            if '.' in month_day_raw:
                month, day = month_day_raw.split('.')
            elif '/' in month_day_raw:
                month, day = month_day_raw.split('/')
            else:
                # fallback: use substring slicing
                month = month_day_raw[:2]
                day = month_day_raw[2:]
            date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

            # Each <a class="media_box_list"> inside this box is an event
            for link in box.find_all('a', class_='media_box_list'):
                try:
                    category_elem = link.find('div', class_='media_category')
                    title_elem = link.find('div', class_='media_title')
                    category_text = ''
                    title = ''
                    if category_elem:
                        # Text may be inside a <span>
                        category_text = category_elem.get_text(strip=True)
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                    if not title:
                        continue
                    cat_en = _map_category(category_text)
                    # Construct detail URL
                    href = link.get('href', '')
                    detail_url = ''
                    if href:
                        if href.startswith('/'):
                            detail_url = 'https://nanabunnonijyuuni-mobile.com' + href
                        else:
                            detail_url = href
                    event_id = f"{date_str}-{hash(title + category_text)}"
                    events.append({
                        'id': event_id,
                        'date': date_str,
                        'title': title,
                        'category': cat_en,
                        'time': '',
                        'url': detail_url,
                    })
                except Exception as e:
                    print(f"解析单个活动时出错: {e}")
        except Exception as e:
            print(f"解析日期块时出错: {e}")

    return events


def _normalize_date(raw_date: str, year_month: str) -> str:
    """Normalize dates from legacy list structures.

    The old schedule layout uses compact date strings like "3/5" or "03.05".
    When only day and month are present, this function prepends the year from
    `year_month` to construct a full ISO date.

    Args:
        raw_date: The raw date string extracted from the page.
        year_month: The current year/month in YYYYMM format.

    Returns:
        A ISO formatted date string (YYYY-MM-DD).
    """
    # Replace separators and extract digits
    clean = raw_date.replace('.', '-').replace('/', '-').strip()
    parts = [p for p in clean.split('-') if p]
    if len(parts) == 2:
        # e.g. ['03', '07'] -> prefix year
        year = year_month[:4]
        month, day = parts
    elif len(parts) == 3:
        year, month, day = parts
    else:
        # fallback: treat raw_date as day only
        year = year_month[:4]
        month = year_month[4:]
        # keep only digits from raw_date
        day = ''.join(filter(str.isdigit, raw_date))
    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"


def _map_category(category_text: str) -> str:
    """Map Japanese or site-specific category names to English labels.

    This helper centralises category translations. If a category is unrecognised
    it defaults to "Other".

    Args:
        category_text: Raw text from the `.media_category` element.

    Returns:
        A simple English category string recognised by the calendar front-end.
    """
    if not category_text:
        return 'Other'
    text = category_text.strip().lower()
    # Japanese category names and their English counterparts
    mapping = {
        'テレビ': 'TV',
        'tv': 'TV',
        'ラジオ': 'Radio',
        'radio': 'Radio',
        'web': 'Web',
        '配信': 'Web',
        'ライブ': 'Live',
        'live': 'Live',
        'イベント': 'Event',
        'event': 'Event',
        '特典会': 'Event',
        '雑誌': 'Release',
        'cd': 'Release',
        'dvd': 'Release',
        'その他': 'Other',
        'other': 'Other',
    }
    # Attempt exact match first
    for key, value in mapping.items():
        if key.lower() == text:
            return value
    # Attempt partial matches
    for key, value in mapping.items():
        if key.lower() in text:
            return value
    return 'Other'

def main():
    all_events = []
    months_to_fetch = []
    now = datetime.datetime.now()
    
    # 读取 GitHub Actions 传进来的环境变量
    is_fetch_all = os.environ.get('FETCH_ALL') == 'true'
    
    if is_fetch_all:
        print("--- 执行全量抓取 (2018年至今) ---")
        start_year = 2018
        end_year = now.year + 1
        for year in range(start_year, end_year + 1):
            for month in range(1, 13):
                months_to_fetch.append(f"{year}{month:02d}")
    else:
        print("--- 执行日常增量抓取 (近两个月) ---")
        # 仅抓取当月和下个月
        months_to_fetch.append(now.strftime("%Y%m"))
        months_to_fetch.append((now + datetime.timedelta(days=31)).strftime("%Y%m"))

    # 去重并排序月份
    months_to_fetch = sorted(list(set(months_to_fetch)))
    
    # 尝试读取本地旧的 events.json (用于增量合并)
    existing_events = []
    if not is_fetch_all and os.path.exists('events.json'):
        try:
            with open('events.json', 'r', encoding='utf-8') as f:
                existing_events = json.load(f)
        except Exception:
            pass

    # 抓取数据
    for ym in months_to_fetch:
        events = fetch_events_for_month(ym)
        all_events.extend(events)
        
    # 合并数据
    if not is_fetch_all:
        # 使用字典按 ID 去重，新数据覆盖旧数据
        events_dict = {e['id']: e for e in existing_events}
        for e in all_events:
            events_dict[e['id']] = e
        final_events = list(events_dict.values())
    else:
        final_events = all_events
        
    # 按日期排序
    final_events.sort(key=lambda x: x['date'])
        
    # 写入 JSON
    with open('events.json', 'w', encoding='utf-8') as f:
        json.dump(final_events, f, ensure_ascii=False, indent=2)
    print(f"成功更新 events.json，当前总共 {len(final_events)} 条数据")

if __name__ == "__main__":
    main()