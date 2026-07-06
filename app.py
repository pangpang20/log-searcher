import json
import os
import re
import logging
import zipfile
import io
import base64
import hashlib
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from flask import Flask, request, jsonify, send_from_directory, send_file
import paramiko

app = Flask(__name__, static_folder='static')

BASE_DIR = os.path.dirname(__file__)
DATA_FILE = os.path.join(BASE_DIR, 'data', 'systems.json')
KEY_FILE = os.path.join(BASE_DIR, 'data', '.secret_key')
LOG_DIR = os.path.join(BASE_DIR, 'logs')


def get_secret_key():
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, 'r') as f:
            return f.read().strip()
    key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
    with open(KEY_FILE, 'w') as f:
        f.write(key)
    return key


SECRET_KEY = get_secret_key()


def encrypt_password(password):
    if not password:
        return ''
    key_bytes = hashlib.sha256(SECRET_KEY.encode()).digest()
    password_bytes = password.encode('utf-8')
    encrypted = bytearray()
    for i, b in enumerate(password_bytes):
        encrypted.append(b ^ key_bytes[i % len(key_bytes)])
    return base64.urlsafe_b64encode(encrypted).decode()


def decrypt_password(encrypted_password):
    if not encrypted_password:
        return ''
    try:
        key_bytes = hashlib.sha256(SECRET_KEY.encode()).digest()
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_password)
        decrypted = bytearray()
        for i, b in enumerate(encrypted_bytes):
            decrypted.append(b ^ key_bytes[i % len(key_bytes)])
        return decrypted.decode('utf-8')
    except Exception:
        return encrypted_password

os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger('log_search')
logger.setLevel(logging.INFO)

file_handler = TimedRotatingFileHandler(
    os.path.join(LOG_DIR, 'app.log'),
    when='midnight',
    interval=1,
    backupCount=30,
    encoding='utf-8'
)
file_handler.suffix = '%Y-%m-%d'
file_handler.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

formatter = logging.Formatter('[%(asctime)s] %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for system in data:
                for server in system.get('servers', []):
                    if 'password' in server:
                        server['password'] = decrypt_password(server['password'])
            return data
    return []


def save_data(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    encrypted_data = []
    for system in data:
        encrypted_system = system.copy()
        encrypted_servers = []
        for server in system.get('servers', []):
            encrypted_server = server.copy()
            if 'password' in encrypted_server:
                encrypted_server['password'] = encrypt_password(encrypted_server['password'])
            encrypted_servers.append(encrypted_server)
        encrypted_system['servers'] = encrypted_servers
        encrypted_data.append(encrypted_system)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(encrypted_data, f, ensure_ascii=False, indent=2)


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/search.html')
def search():
    return send_from_directory('static', 'search.html')


@app.route('/api/systems', methods=['GET'])
def get_systems():
    data = load_data()
    logger.info(f'[查询系统列表] 结果: 共{len(data)}个系统')
    return jsonify(data)


@app.route('/api/systems', methods=['POST'])
def add_system():
    data = load_data()
    req = request.json
    name = req.get('name', '').strip()
    if not name:
        logger.warning(f'[添加系统] 失败: 系统名称为空')
        return jsonify({'error': '系统名称不能为空'}), 400
    for s in data:
        if s['name'] == name:
            logger.warning(f'[添加系统] 失败: 系统名称"{name}"已存在')
            return jsonify({'error': '系统名称已存在'}), 400
    new_system = {'name': name, 'servers': []}
    data.append(new_system)
    save_data(data)
    logger.info(f'[添加系统] 成功: 系统名称="{name}"')
    return jsonify(new_system), 201


@app.route('/api/systems/<name>', methods=['PUT'])
def update_system(name):
    data = load_data()
    req = request.json
    new_name = req.get('name', '').strip()
    if not new_name:
        logger.warning(f'[更新系统] 失败: 新系统名称为空')
        return jsonify({'error': '系统名称不能为空'}), 400
    for s in data:
        if s['name'] == new_name and s['name'] != name:
            logger.warning(f'[更新系统] 失败: 系统名称"{new_name}"已存在')
            return jsonify({'error': '系统名称已存在'}), 400
    for s in data:
        if s['name'] == name:
            s['name'] = new_name
            save_data(data)
            logger.info(f'[更新系统] 成功: "{name}" -> "{new_name}"')
            return jsonify(s)
    logger.warning(f'[更新系统] 失败: 系统"{name}"不存在')
    return jsonify({'error': '系统不存在'}), 404


@app.route('/api/systems/<name>', methods=['DELETE'])
def delete_system(name):
    data = load_data()
    system = next((s for s in data if s['name'] == name), None)
    if system:
        logger.info(f'[删除系统] 成功: 系统="{name}", 包含{len(system["servers"])}台服务器')
    else:
        logger.warning(f'[删除系统] 系统"{name}"不存在')
    data = [s for s in data if s['name'] != name]
    save_data(data)
    return jsonify({'message': '删除成功'})


@app.route('/api/systems/<name>/servers', methods=['POST'])
def add_server(name):
    data = load_data()
    req = request.json
    for s in data:
        if s['name'] == name:
            server = {
                'ip': req.get('ip', '').strip(),
                'port': int(req.get('port', 22)),
                'username': req.get('username', '').strip(),
                'password': req.get('password', ''),
                'directory': req.get('directory', '').strip(),
                'filename_pattern': req.get('filename_pattern', '').strip()
            }
            if not server['ip'] or not server['username'] or not server['directory']:
                logger.warning(f'[添加服务器] 失败: 系统="{name}", IP/用户名/目录为空')
                return jsonify({'error': 'IP、用户名和目录不能为空'}), 400
            s['servers'].append(server)
            save_data(data)
            logger.info(f'[添加服务器] 成功: 系统="{name}", 服务器={server["ip"]}:{server["port"]}, 用户={server["username"]}, 目录={server["directory"]}, 文件匹配={server["filename_pattern"] or "全部"}')
            return jsonify(server), 201
    logger.warning(f'[添加服务器] 失败: 系统"{name}"不存在')
    return jsonify({'error': '系统不存在'}), 404


@app.route('/api/systems/<name>/servers/<int:index>', methods=['PUT'])
def update_server(name, index):
    data = load_data()
    req = request.json
    for s in data:
        if s['name'] == name:
            if 0 <= index < len(s['servers']):
                server = s['servers'][index]
                old_info = f'{server["ip"]}:{server["port"]}'
                server['ip'] = req.get('ip', server['ip']).strip()
                server['port'] = int(req.get('port', server['port']))
                server['username'] = req.get('username', server['username']).strip()
                server['password'] = req.get('password', server['password'])
                server['directory'] = req.get('directory', server['directory']).strip()
                server['filename_pattern'] = req.get('filename_pattern', server.get('filename_pattern', '')).strip()
                save_data(data)
                logger.info(f'[更新服务器] 成功: 系统="{name}", 索引={index}, {old_info} -> {server["ip"]}:{server["port"]}')
                return jsonify(server)
            logger.warning(f'[更新服务器] 失败: 系统="{name}", 索引={index}无效')
            return jsonify({'error': '服务器索引无效'}), 400
    logger.warning(f'[更新服务器] 失败: 系统"{name}"不存在')
    return jsonify({'error': '系统不存在'}), 404


@app.route('/api/systems/<name>/servers/<int:index>', methods=['DELETE'])
def delete_server(name, index):
    data = load_data()
    for s in data:
        if s['name'] == name:
            if 0 <= index < len(s['servers']):
                server = s['servers'][index]
                s['servers'].pop(index)
                save_data(data)
                logger.info(f'[删除服务器] 成功: 系统="{name}", 服务器={server["ip"]}:{server["port"]}, 索引={index}')
                return jsonify({'message': '删除成功'})
            logger.warning(f'[删除服务器] 失败: 系统="{name}", 索引={index}无效')
            return jsonify({'error': '服务器索引无效'}), 400
    logger.warning(f'[删除服务器] 失败: 系统"{name}"不存在')
    return jsonify({'error': '系统不存在'}), 404


@app.route('/api/systems/<name>/servers/<int:index>/test', methods=['POST'])
def test_server(name, index):
    data = load_data()
    for s in data:
        if s['name'] == name:
            if 0 <= index < len(s['servers']):
                server = s['servers'][index]
                logger.info(f'[测试连接] 开始: 系统="{name}", 服务器={server["ip"]}:{server["port"]}, 用户={server["username"]}')
                try:
                    ssh = paramiko.SSHClient()
                    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    ssh.connect(
                        server['ip'],
                        port=server['port'],
                        username=server['username'],
                        password=server['password'],
                        timeout=30,
                        banner_timeout=30,
                        auth_timeout=30
                    )
                    ssh.close()
                    logger.info(f'[测试连接] 成功: 系统="{name}", 服务器={server["ip"]}:{server["port"]}')
                    return jsonify({'success': True, 'message': '连接成功'})
                except Exception as e:
                    logger.error(f'[测试连接] 失败: 系统="{name}", 服务器={server["ip"]}:{server["port"]}, 错误={str(e)}')
                    return jsonify({'success': False, 'message': str(e)})
            logger.warning(f'[测试连接] 失败: 系统="{name}", 索引={index}无效')
            return jsonify({'error': '服务器索引无效'}), 400
    logger.warning(f'[测试连接] 失败: 系统"{name}"不存在')
    return jsonify({'error': '系统不存在'}), 404


@app.route('/api/search', methods=['POST'])
def search_logs():
    req = request.json
    system_name = req.get('system', '')
    keyword = req.get('keyword', '').strip()
    context_lines = int(req.get('context_lines', 20))

    if not keyword:
        logger.warning(f'[搜索日志] 失败: 关键字为空')
        return jsonify({'error': '关键字不能为空'}), 400
    if len(keyword) > 200:
        logger.warning(f'[搜索日志] 失败: 关键字长度超过200')
        return jsonify({'error': '关键字长度不能超过200个字符'}), 400

    data = load_data()
    system = None
    for s in data:
        if s['name'] == system_name:
            system = s
            break

    if not system:
        logger.warning(f'[搜索日志] 失败: 系统"{system_name}"不存在')
        return jsonify({'error': '系统不存在'}), 404

    logger.info(f'[搜索日志] 开始: 系统="{system_name}", 关键字="{keyword}", 上下文行数={context_lines}, 服务器数量={len(system["servers"])}')

    results = []
    total_files = 0
    total_matches = 0
    for server in system['servers']:
        server_result = search_server_logs(server, keyword, context_lines)
        results.append(server_result)
        if not server_result['error']:
            file_count = len(server_result['files'])
            total_files += file_count
            for f in server_result['files']:
                total_matches += f['content'].count('\n') + 1

    logger.info(f'[搜索日志] 完成: 系统="{system_name}", 关键字="{keyword}", 匹配文件数={total_files}, 匹配行数={total_matches}')
    return jsonify({'results': results})


@app.route('/api/search/stream', methods=['POST'])
def search_logs_stream():
    req = request.json
    system_name = req.get('system', '')
    keyword = req.get('keyword', '').strip()
    context_lines = int(req.get('context_lines', 20))

    if not keyword:
        return jsonify({'error': '关键字不能为空'}), 400
    if len(keyword) > 200:
        return jsonify({'error': '关键字长度不能超过200个字符'}), 400

    data = load_data()
    system = None
    for s in data:
        if s['name'] == system_name:
            system = s
            break

    if not system:
        return jsonify({'error': '系统不存在'}), 404

    logger.info(f'[搜索日志-流式] 开始: 系统="{system_name}", 关键字="{keyword}", 上下文行数={context_lines}')

    def generate():
        for server in system['servers']:
            server_result = search_server_logs(server, keyword, context_lines)
            yield f"data: {json.dumps(server_result, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return app.response_class(generate(), mimetype='text/event-stream')


@app.route('/api/search/download', methods=['POST'])
def download_logs():
    req = request.json
    system_name = req.get('system', '')
    results = req.get('results', [])

    logger.info(f'[下载日志] 开始: 系统="{system_name}", 服务器数量={len(results)}')

    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for server in results:
            server_name = server['server'].replace(':', '_')
            if server['error']:
                zf.writestr(f"{server_name}/连接失败.txt", f"连接失败: {server['error']}")
                continue
            if not server['files']:
                zf.writestr(f"{server_name}/无匹配.txt", "未找到匹配的日志内容")
                continue
            for file in server['files']:
                file_name = file['path'].replace('/', '_').replace('\\', '_')
                zf.writestr(f"{server_name}/{file_name}", file['content'])

    memory_file.seek(0)
    logger.info(f'[下载日志] 完成: 系统="{system_name}"')
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'logs_{system_name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
    )


def search_server_logs(server, keyword, context_lines):
    ip = server['ip']
    port = server['port']
    username = server['username']
    password = server['password']
    directory = server['directory']
    filename_pattern = server.get('filename_pattern', '')

    result = {
        'server': f"{ip}:{port}",
        'files': [],
        'error': None
    }

    max_retries = 2
    for attempt in range(max_retries):
        try:
            logger.info(f'[搜索服务器] 开始: {ip}:{port}, 目录={directory}, 文件匹配={filename_pattern or "全部"}')
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(ip, port=port, username=username, password=password, timeout=30, banner_timeout=30, auth_timeout=30)
            transport = ssh.get_transport()
            if transport:
                transport.set_keepalive(15)

            if filename_pattern:
                patterns = [p.strip() for p in filename_pattern.split(',') if p.strip()]
                find_parts = []
                for p in patterns:
                    find_parts.append(f"-name '*{p}*'")
                find_cmd = f"find {directory} -type f \\( {' -o '.join(find_parts)} \\) 2>/dev/null"
            else:
                find_cmd = f"find {directory} -type f 2>/dev/null"

            logger.info(f'[搜索服务器] {ip}:{port} 执行命令: {find_cmd}')
            stdin, stdout, stderr = ssh.exec_command(find_cmd, timeout=60)
            file_list = stdout.read().decode('utf-8').strip().split('\n')
            file_list = [f for f in file_list if f]
            logger.info(f'[搜索服务器] {ip}:{port} 找到{len(file_list)}个文件')

            for log_file in file_list:
                safe_keyword = keyword.replace("\\", "\\\\").replace("'", "'\\''")
                grep_cmd = f"grep -F -n -i -A {context_lines} -B {context_lines} -- '{safe_keyword}' '{log_file}' 2>/dev/null"
                logger.info(f'[搜索服务器] {ip}:{port} 执行命令: {grep_cmd}')
                stdin, stdout, stderr = ssh.exec_command(grep_cmd, timeout=60)
                output = stdout.read().decode('utf-8', errors='ignore')

                if output.strip():
                    blocks = re.split(r'\n--\n', output.strip())
                    blocks.reverse()
                    reversed_output = '\n--\n'.join(blocks)
                    line_count = reversed_output.count('\n') + 1
                    logger.info(f'[搜索服务器] {ip}:{port} 文件={log_file} 匹配{line_count}行')
                    result['files'].append({
                        'path': log_file,
                        'content': reversed_output
                    })

            ssh.close()
            logger.info(f'[搜索服务器] 完成: {ip}:{port}, 匹配文件数={len(result["files"])}')
            return result
        except Exception as e:
            logger.error(f'[搜索服务器] 失败(尝试{attempt+1}/{max_retries}): {ip}:{port}, 错误={str(e)}')
            if attempt == max_retries - 1:
                result['error'] = str(e)
            try:
                ssh.close()
            except:
                pass

    return result


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)