import sys

text=open('post_resource_article.sh','r',encoding='utf-8').read()
stack=[]
line=1
i=0
while i<len(text):
    c=text[i]
    if c=='\n':
        line+=1
    if c=='"' or c=="'":
        quote=c
        i+=1
        while i<len(text) and text[i]!=quote:
            if text[i]=='\\':
                i+=2
                continue
            i+=1
    elif c=='#':
        while i<len(text) and text[i]!='\n':
            i+=1
        continue
    elif c=='(':
        stack.append((line,i))
    elif c==')':
        if stack:
            stack.pop()
        else:
            print('unmatched ) at line',line)
    i+=1
if stack:
    print('unmatched ( starts at',stack[0])
else:
    print('all matched')
