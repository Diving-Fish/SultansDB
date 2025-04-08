from collections import defaultdict
import os
import json5  # 支持注释的 JSON 解析库
import json
import re


key_to_name_table = {}


def handle_duplicates(pairs):
    d = {}
    for k, v in pairs:
        # 替换键中的点为下划线
        k = k.replace('.', '_')
        if k in d:
            if isinstance(d[k], list):
                d[k].append(v)
            else:
                d[k] = [d[k], v]
        else:
            d[k] = v
    return d


def process_json(data):
    """
    递归处理JSON数据：
    1. 替换所有键中的点为下划线
    2. 如果数组中元素不是同一类型，则将所有元素转为字符串
    """
    if isinstance(data, dict):
        # 处理字典
        new_dict = {}
        for k, v in data.items():
            # 替换键中的点为下划线
            new_key = k.replace('.', '_')
            # 递归处理值
            new_dict[new_key] = process_json(v)
        return new_dict
    elif isinstance(data, list):
        # 处理列表
        if not data:
            return data  # 空列表不处理

        # 检查列表中元素的类型是否一致
        type_set = {type(item) for item in data}
        if len(type_set) > 1:
            # 不是同一类型，全部转为字符串
            return [str(item) for item in data]
        else:
            # 是同一类型，递归处理每个元素
            return [process_json(item) for item in data]
    else:
        # 基本类型直接返回
        return data


os.makedirs('formatted', exist_ok=True)

directory = 'config'
if os.path.exists(directory):
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.json'):
                # 获取源文件的相对路径
                rel_path = os.path.relpath(root, directory)

                # 构建目标目录路径
                target_dir = os.path.join('formatted', rel_path)

                # 确保目标目录存在
                os.makedirs(target_dir, exist_ok=True)

                # 构建源文件和目标文件的完整路径
                source_file_path = os.path.join(root, file)
                target_file_path = os.path.join(target_dir, file)

                # 读取和处理文件
                with open(source_file_path, encoding="utf-8") as f:
                    data = json5.load(f, object_pairs_hook=handle_duplicates)

                    # 进一步处理数据，替换键中的点并处理不同类型的数组
                    processed_data = process_json(data)

                    # 尝试获取 key name 映射
                    name = ''
                    if "name" in processed_data:
                        name = processed_data["name"]
                    elif "text" in processed_data:
                        name = processed_data["text"]

                    try:
                        key = int(file.replace('.json', ''))
                        if name:
                            key_to_name_table[str(key)] = name
                    except ValueError:
                        pass

                    # 写入处理后的数据到目标文件
                    with open(target_file_path, 'w', encoding="utf-8") as fw:
                        json.dump(processed_data, fw, indent=4, ensure_ascii=False)
                        print(target_file_path)

with open('formatted/cards.json', 'r', encoding="utf-8") as f:
    data = json.load(f)
    for key in data:
        key_to_name_table[key] = data[key]['name']

with open('counter_concise.json', 'r', encoding="utf-8") as f:
    data = json.load(f)
    for key in data:
        key_to_name_table[key] = data[key]
        
# 使用 str 作为默认键类型的字典
char_origin_rite = defaultdict(set)

def process_file(event_or_rite_path, event_or_rite_data):
    """处理单个文件中的人物来源信息"""
    for key in ['settlement_prior', 'settlement', 'settlement_extre']:
        if key not in event_or_rite_data:
            continue

        for result in event_or_rite_data[key]:
            # 检查结果或动作中是否有追随者相关项
            result_dict = {**result.get('action', {}), **result.get('result', {})}
            for k, v in result_dict.items():
                if '+追随者' not in k:
                    continue

                # 解析目标
                target = k[:-4]  # 去掉 '+追随者' 后缀
                reg1 = r's(\d+)'
                reg2 = r'(total|table)_(\d+)(_追随者=0)?'
                match1 = re.search(reg1, target)
                match2 = re.search(reg2, target)

                if match1:
                    target_id = match1.group(1)
                    target_char = None
                    
                    # 检查条件中是否有角色ID
                    if f's{target_id}_is' in result.get('condition', {}):
                        target_char = result['condition'][f's{target_id}_is']
                    # 检查卡槽中是否有角色ID
                    elif ('cards_slot' in event_or_rite_data and f's{target_id}' in event_or_rite_data['cards_slot'] and
                          'is' in event_or_rite_data['cards_slot'][f's{target_id}'].get('condition', {})):
                        target_char = event_or_rite_data['cards_slot'][f's{target_id}'].get('condition', {}).get('is', None)
                    
                    if target_char is not None:
                        # 确保使用字符串键
                        char_id = str(target_char)
                        char_origin_rite[char_id].add(event_or_rite_data['id'])
                        print(event_or_rite_path, "Char origin detected:", char_id, "->", event_or_rite_data['id'])
                
                elif match2:
                    # 直接从正则匹配获取人物ID
                    char_id = str(match2.group(2))  # 转换为字符串
                    char_origin_rite[char_id].add(event_or_rite_data['id'])
                    print(event_or_rite_path, "Char origin detected:", char_id, "->", event_or_rite_data['id'])


# 处理仪式文件
for root, _, files in os.walk('formatted/rite'):
    for file in files:
        if file.endswith('.json'):
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'r', encoding="utf-8") as f:
                    data = json.load(f)
                    process_file(file_path, data)
            except Exception as e:
                print(f"Error processing {file_path}: {e}")

# 处理事件文件
for root, _, files in os.walk('formatted/event'):
    for file in files:
        if file.endswith('.json'):
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'r', encoding="utf-8") as f:
                    data = json.load(f)
                    process_file(file_path, data)
            except Exception as e:
                print(f"Error processing {file_path}: {e}")


with open('char_origin_rite.json', 'w', encoding="utf-8") as f:
    json.dump({k: list(v) for k, v in char_origin_rite.items()}, f, indent=4, ensure_ascii=False)

with open('key_to_name.json', 'w', encoding="utf-8") as f:
    json.dump(key_to_name_table, f, indent=4, ensure_ascii=False)
