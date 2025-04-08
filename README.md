# README

## Step 1. 运行 Elastic Search

```sh
docker run -d -p 9200:9200 -p 9300:9300 -e "xpack.security.enabled=false" -e "xpack.security.http.ssl.enabled=false" -e "xpack.security.transport.ssl.enabled=false" -e "discovery.type=single-node" elasticsearch:8.10.4
```

请注意防火墙设置或使用 elastic search 的安全选项以防滥用

## Step 2. 复制游戏文件

复制游戏目录中的 `Sultan's Game\Sultan's Game_Data\StreamingAssets\config` 到项目根目录中

## Step 3. 使用 Python（3.10+）安装依赖，修改 config.json 并运行

```sh
pip install -r requirements.txt
python main.py
```

