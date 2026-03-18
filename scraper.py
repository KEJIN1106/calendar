import requests
from bs4 import BeautifulSoup
import json
import datetime
import os

BASE_URL = "https://nanabunnonijyuuni-mobile.com/s/n110/media/list?ima=3625&dy={}"

def fetch_events_for_month(year_month):
    url = BASE_URL.format(year_month)
    print(f"正在获取: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        events = []
        list_items = soup.find_all('li', class_='list_item')
        if not list_items:
            list_items = soup.select('.media_list li, .schedule_list li, article')
            
        for item in list_items:
            try:
                date_elem = item.find(class_=['date', 'time', 'day'])
                title_elem = item.find(class_=['title', 'name', 'txt'])
                category_elem = item.find(class_=['category', 'tag', 'label'])
                
                if not date_elem or not title_elem:
                    continue
                    
                raw_date = date_elem.text.strip()
                title = title_elem.text.strip()
                category = category_elem.text.strip() if category_elem else "Other"
                
                cat_en = "Other"
                if "TV" in category.upper() or "テレビ" in category: cat_en = "TV"
                elif "RADIO" in category.upper() or "ラジオ" in category: cat_en = "Radio"
                elif "WEB" in category.upper() or "配信" in category: cat_en = "Web"
                elif "LIVE" in category.upper() or "ライブ" in category: cat_en = "Live"
                elif "EVENT" in category.upper() or "イベント" in category: cat_en = "Event"
                
                clean_date = raw_date.replace('.', '-').replace('/', '-')
                if len(clean_date) <= 3: 
                    day = ''.join(filter(str.isdigit, raw_date)).zfill(2)
                    clean_date = f"{year_month[:4]}-{year_month[4:]}-{day}"
                
                # 提取详情链接
                link_elem = item.find('a')
                detail_url = ""
                if link_elem and link_elem.has_attr('href'):
                    detail_url = link_elem['href']
                    if detail_url.startswith('/'):
                        detail_url = "https://nanabunnonijyuuni-mobile.com" + detail_url
                
                events.append({
                    "id": f"{clean_date}-{hash(title)}",
                    "date": clean_date,
                    "title": title,
                    "category": cat_en,
                    "time": "", 
                    "url": detail_url
                })
            except Exception as e:
                print(f"解析单个项目时出错: {e}")
                
        return events
        
    except Exception as e:
        print(f"获取网页失败: {e}")
        return []

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