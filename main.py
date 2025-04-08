import datetime
import hashlib
import os
import json
import asyncio
import pathlib
from quart import Quart, jsonify, request, abort, send_file
from elasticsearch import AsyncElasticsearch

app = Quart(__name__)

with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

app_port = config.get('port', 8095)
inited = config.get('inited', False)
elasticsearch = config.get('elasticsearch', {
    "host": "localhost",
    "port": 9200,
    "index": "sultansDB"
})
baseURL = config.get('baseURL', '/')

# Elasticsearch 配置
es_client = AsyncElasticsearch([f'http://{elasticsearch['host']}:{elasticsearch['port']}'])
INDEX_NAME = elasticsearch["index"]

async def init_index():
    # 删除旧索引
    if await es_client.indices.exists(index=INDEX_NAME):
        await es_client.indices.delete(index=INDEX_NAME)

    # 重新创建索引
    await es_client.indices.create(
        index=INDEX_NAME,
        body={
            'mappings': {
                'properties': {
                    'content': {'type': 'text'},
                    'file_path': {'type': 'keyword'},
                    'name': {'type': 'keyword'},
                }
            }
        }
    )

    # 重新索引文件
    await index_all_json_files('config')

async def index_all_json_files(root_dir):
    """递归索引目录下的所有 JSON 文件"""
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith('.json'):
                file_path = os.path.join(dirpath, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # 尝试获取名字
                    with open(file_path.replace('config', 'formatted'), 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                        if 'name' in json_data:
                            name = json_data['name']
                        elif 'text' in json_data:
                            name = json_data['text']
                        else:
                            name = file_path

                    # 索引文件内容
                    await es_client.index(
                        index=INDEX_NAME,
                        body={
                            'content': content,  # 索引原始 JSON 字符串
                            'file_path': file_path,
                            'name': name,
                        },
                        refresh=True  # 确保索引后立即可搜索
                    )
                    print(f"已索引: {file_path} - {name}")
                except Exception as e:
                    print(f"索引 {file_path} 时出错: {str(e)}")

if not inited:
    if not os.path.exists('config'):
        print('游戏配置数据文件夹不存在，请检查')
        exit(0)

    print('正在整理 JSON，请稍等')
    import fix_json
    
    print("重新加载所有 JSON 文件到索引")
    asyncio.get_event_loop().run_until_complete(init_index())
    print("索引完成")

    # 创建配置文件
    with open('config.json', 'w', encoding='utf-8') as f:
        config['inited'] = True
        json.dump(config, f, indent=4, ensure_ascii=False)
    

with open('key_to_name.json', 'r', encoding="utf-8") as f:
    key_to_name_table = json.load(f)

with open('char_origin_rite.json', 'r', encoding="utf-8") as f:
    char_origin_table = json.load(f)

@app.after_serving
async def cleanup():
    await es_client.close()


@app.route('/search', methods=['GET'])
async def search():
    if baseURL != '/':
        with open('template/search.html', 'r', encoding="utf-8") as f:
            content = f.read()
            content = content.replace("axios.defaults.baseURL = '/'", f"axios.defaults.baseURL = '{baseURL}'")
            return content
    else:
        return await send_file('template/search.html', mimetype='text/html')

@app.route('/search_api', methods=['GET'])
async def search_api():
    """搜索 JSON 文件内容"""
    query_text = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    size = request.args.get('size', 20, type=int)
    if not query_text:
        return jsonify({'error': 'Missing query parameter "q"'}), 400

    # 搜索文档
    result = await es_client.search(
        index=INDEX_NAME,
        body={
            'query': {
                'match': {
                    'content': query_text
                },
            },
            'highlight': {
                'fields': {
                    'content': {}
                }
            },
            'from': (page - 1) * size,
            'size': size,
        }
    )

    # 格式化结果
    formatted_results = []
    for hit in result['hits']['hits']:
        formatted_results.append({
            'file_path': hit['_source']['file_path'],
            'name': hit['_source']['name'],
            'score': hit['_score'],
            'highlights': hit.get('highlight', {}).get('content', [])
        })

    return jsonify({
        'total': result['hits']['total']['value'],
        'page': page,
        'size': size,
        'pages': (result['hits']['total']['value'] + size - 1) // size,  # 总页数
        'results': formatted_results
    })


@app.route('/', methods=['GET'])
async def get_cards():
    if baseURL != '/':
        with open('template/cards.html', 'r', encoding="utf-8") as f:
            content = f.read()
            content = content.replace("axios.defaults.baseURL = '/'", f"axios.defaults.baseURL = '{baseURL}'")
            return content
    else:
        return await send_file('template/cards.html')


@app.route('/raw/<path:file_path>')
async def serve_raw_file(file_path: str):
    """
    提供指定路径下原始文件的内容

    参数:
        file_path: 请求的文件路径，相对于配置目录

    返回:
        文件内容或404错误
    """
    # 确定基础目录（config 文件夹）
    base_dir = pathlib.Path('config')

    # 构建完整文件路径，并规范化路径以防止路径遍历攻击
    try:
        file_path = pathlib.Path(file_path)
        # 确保路径不包含 ".." 以防止目录遍历
        if '..' in file_path.parts:
            abort(403, description="访问被拒绝")

        full_path = base_dir / file_path
        abs_path = full_path.resolve()

        # 确保文件在 base_dir 目录下
        if not str(abs_path).startswith(str(base_dir.resolve())):
            abort(403, description="访问被拒绝")

        # 检查文件是否存在
        if not abs_path.exists() or not abs_path.is_file():
            abort(404, description=f"文件 '{file_path}' 不存在")

        # 返回文件内容
        return await send_file(abs_path)

    except (ValueError, OSError) as e:
        abort(500, description=f"服务器错误: {str(e)}")

# 为静态内容设置较长的缓存时间（例如1天）
STATIC_CACHE_TIMEOUT = 86400  # 24小时 = 86400秒

@app.route('/formatted/<path:file_path>')
async def serve_formatted_file(file_path: str):
    """
    提供指定路径下原始文件的内容，并添加缓存控制
    
    参数:
        file_path: 请求的文件路径，相对于配置目录
        
    返回:
        文件内容或404错误
    """
    # 确定基础目录（formatted 文件夹）
    base_dir = pathlib.Path('formatted')
    
    # 构建完整文件路径，并规范化路径以防止路径遍历攻击
    try:
        file_path = pathlib.Path(file_path)
        # 确保路径不包含 ".." 以防止目录遍历
        if '..' in file_path.parts:
            abort(403, description="访问被拒绝")
            
        full_path = base_dir / file_path
        abs_path = full_path.resolve()
        
        # 确保文件在 base_dir 目录下
        if not str(abs_path).startswith(str(base_dir.resolve())):
            abort(403, description="访问被拒绝")
            
        # 检查文件是否存在
        if not abs_path.exists() or not abs_path.is_file():
            abort(404, description=f"文件 '{file_path}' 不存在")
            
        # 获取文件最后修改时间，用于ETag和Last-Modified
        file_mtime = os.path.getmtime(abs_path)
        etag = hashlib.md5(f"{file_path}:{file_mtime}".encode()).hexdigest()
        last_modified = datetime.utcfromtimestamp(file_mtime).strftime('%a, %d %b %Y %H:%M:%S GMT')
        
        response = await send_file(abs_path)
        
        # 添加缓存控制头
        response.headers['Cache-Control'] = f'public, max-age={STATIC_CACHE_TIMEOUT}'
        response.headers['ETag'] = etag
        response.headers['Last-Modified'] = last_modified
        
        return response
        
    except (ValueError, OSError) as e:
        abort(500, description=f"服务器错误: {str(e)}")

@app.route('/config/<path:file_path>')
async def serve_config(file_path: str):
    if file_path.startswith('event'):
        if os.path.exists('formatted/' + file_path):
            with open('formatted/' + file_path, 'r', encoding='utf-8') as f2:
                json_content = f2.read()
            with open('template/event.html', 'r', encoding="utf-8") as f:
                content = f.read()
                content = content.replace('//<<<event_data>>>//', json_content)
                if baseURL != '/':
                    content = content.replace("axios.defaults.baseURL = '/'", f"axios.defaults.baseURL = '{baseURL}'")
                return content
        else:
            return await send_file(f'config/{file_path}')
    elif file_path.startswith('rite'):
        if os.path.exists('formatted/' + file_path):
            with open('formatted/' + file_path, 'r', encoding='utf-8') as f2:
                json_content = f2.read()
            with open('template/rite.html', 'r', encoding="utf-8") as f:
                content = f.read()
                content = content.replace('//<<<card_data>>>//', json_content)
                if baseURL != '/':
                    content = content.replace("axios.defaults.baseURL = '/'", f"axios.defaults.baseURL = '{baseURL}'")
                return content
        else:
            return await send_file(f'config/{file_path}')
    else:
        return await send_file(f'config/{file_path}')

@app.route('/key_name_map')
async def key_name_map():
    response = jsonify(key_to_name_table)
    
    # 生成ETag，基于内容的哈希值
    data_hash = hashlib.md5(str(key_to_name_table).encode()).hexdigest()
    
    # 添加缓存控制头
    response.headers['Cache-Control'] = f'public, max-age={STATIC_CACHE_TIMEOUT}' 
    response.headers['ETag'] = data_hash
    
    return response

@app.route('/char_origin_map')
async def char_origin_map():
    response = jsonify(char_origin_table)
    
    # 生成ETag，基于内容的哈希值
    data_hash = hashlib.md5(str(char_origin_table).encode()).hexdigest()
    
    # 添加缓存控制头
    response.headers['Cache-Control'] = f'public, max-age={STATIC_CACHE_TIMEOUT}'
    response.headers['ETag'] = data_hash

    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=config['port'])
