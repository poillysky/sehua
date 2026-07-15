INSERT INTO collector_settings (key, value) VALUES
  ('web_crawler_cookie', 'safe=1'),
  ('web_crawler_max_list_pages', '3'),
  ('web_crawler_max_threads_per_run', '30'),
  ('web_crawler_request_delay', '3'),
  ('web_crawl_urls', 'https://www.sehuatang.net/forum.php')
ON CONFLICT (key) DO NOTHING;
