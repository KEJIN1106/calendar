import requests
from bs4 import BeautifulSoup
import json
import datetime
import os

# 目标 URL 基础模板 (可以根据需要遍历未来几个月)
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
        
        # 注意：这里的 CSS 选择器('.media-list li', '.date' 等)
        # 是基于常见日系官网结构的猜测。
        # 实际使用时，如果抓取不到数据，请在浏览器中按 F12 检查真实网页的 HTML 结构，
        # 并在此处修改 find_all 和 select 的类名。
        
        list_items = soup.find_all('li', class_='list_item') # 假设列表项的类名
        if not list_items:
            # 尝试另一种通用选择器
            list_items = soup.select('.media_list li, .schedule_list li, article')
            
        for item in list_items:
            try:
                # 提取日期 (格式可能需要转换)
                date_elem = item.find(class_=['date', 'time', 'day'])
                title_elem = item.find(class_=['title', 'name', 'txt'])
                category_elem = item.find(class_=['category', 'tag', 'label'])
                
                if not date_elem or not title_elem:
                    continue
                    
                raw_date = date_elem.text.strip() # 例如 "2026.03.14" 
                title = title_elem.text.strip()
                category = category_elem.text.strip() if category_elem else "Other"
                
                # 简单的分类映射
                cat_en = "Other"
                if "TV" in category.upper() or "テレビ" in category: cat_en = "TV"
                elif "RADIO" in category.upper() or "ラジオ" in category: cat_en = "Radio"
                elif "WEB" in category.upper() or "配信" in category: cat_en = "Web"
                elif "LIVE" in category.upper() or "ライブ" in category: cat_en = "Live"
                elif "EVENT" in category.upper() or "イベント" in category: cat_en = "Event"
                
                # 尝试标准化日期为 YYYY-MM-DD
                # 这部分需要根据实际网页日期的格式微调
                clean_date = raw_date.replace('.', '-').replace('/', '-')
                # 如果网页只写了 "14日"，我们需要组合它
                if len(clean_date) <= 3: 
                    day = ''.join(filter(str.isdigit, raw_date)).zfill(2)
                    clean_date = f"{year_month[:4]}-{year_month[4:]}-{day}"
                
                # 提取详情链接
                link_elem = item.find('a')
                detail_url = ""
                if link_elem and link_elem.has_attr('href'):
                    detail_url = link_elem['href']
                    # 如果是相对路径，则补全为绝对路径
                    if detail_url.startswith('/'):
                        detail_url = "https://nanabunnonijyuuni-mobile.com" + detail_url
                
                events.append({
                    "id": f"{clean_date}-{hash(title)}",
                    "date": clean_date,
                    "title": title,
                    "category": cat_en,
                    "time": "", # 如果网页有提供具体时间可以提取
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
    
    # 获取从 2018 年到明年的所有数据
    now = datetime.datetime.now()
    start_year = 2018
    end_year = now.year + 1
    
    months_to_fetch = []
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            months_to_fetch.append(f"{year}{month:02d}")
            
    for ym in months_to_fetch:
        events = fetch_events_for_month(ym)
        all_events.extend(events)
        
    # 保存为 JSON 文件，供前端 HTML 读取
    with open('events.json', 'w', encoding='utf-8') as f:
        json.dump(all_events, f, ensure_ascii=False, indent=2)
    print(f"成功生成 events.json，共 {len(all_events)} 条数据")

if __name__ == "__main__":
    main()