picks=['foo/one@@desc1@@http://a@@','bar/two@@desc2@@http://b@@']
article='#### 资源推荐\n\n'
for line in picks:
    title,desc,url,tags=line.split('@@')
    article+=f"- **资源名称：** {title}\n"
    article+=f"  - 简介： {desc}\n"
    article+=f"  - 获取： {url}\n\n"
article+="> 更多实用资源，敬请关注！\n\n---\n\nTrigger: 自动构建"
print(article)
