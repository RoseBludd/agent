from src.tools.docs_search import DocsSearchTool
t = DocsSearchTool()
print('TOOL_INIT_OK')
res = t(query='how to add text overlay', limit=3)
print('QUERY_RESULTS:', len(res))
for r in res[:3]:
    print('RESULT_CHUNK:', str(r)[:200].replace(chr(10),' | '))
